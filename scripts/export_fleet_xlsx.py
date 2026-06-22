#!/usr/bin/env python3
"""
Export a multi-VM (fleet) Azure quote to a multi-sheet Excel workbook.

Builds, from live Azure Retail Prices, an .xlsx with:
  * Selection   — the per-group source spec → Azure SKU mapping
  * Per-Group   — monthly cost per group across every commitment option
  * Fleet Total — the whole-fleet monthly + annual rollup
  * TCO         — cumulative cost over 1 / 2 / 3 year ownership horizons

Windows groups carry two reserved figures: **no AHB** (the Windows Server
licence stays at PAYG on top of the reserved compute) and **with AHB** (Azure
Hybrid Benefit — only the reserved compute is billed). Azure VM reservations
exist only in 1yr and 3yr terms; the 2-year TCO column is a *time horizon*
(a 1yr reservation renewed), not a 2-year reservation product.

Usage:
    python3 scripts/export_fleet_xlsx.py            # writes under quotes/
    python3 scripts/export_fleet_xlsx.py --output /tmp/quote.xlsx
"""

import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from azure_lib import (  # noqa: E402
    query_vm_prices, organize_vm_prices, currency_symbol, HOURS_PER_MONTH,
)

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# ── Fleet definition (this quote) ───────────────────────────────────────────
REGION = "francecentral"
CURRENCY = "EUR"
GROUPS = [
    {"label": "A", "src": "4U8G",  "os": "windows", "qty": 10,
     "sku": "Standard_D4as_v5", "vcpu": 4, "ram": 16},
    {"label": "B", "src": "3U6G",  "os": "linux",   "qty": 10,
     "sku": "Standard_D2as_v5", "vcpu": 2, "ram": 8},
    {"label": "C", "src": "5U11G", "os": "linux",   "qty": 10,
     "sku": "Standard_D4as_v5", "vcpu": 4, "ram": 16},
]

# Commitment keys carried through every table (None = not available).
COMMITMENTS = [
    "payg", "spot", "ri1y_noahb", "ri1y_ahb", "ri3y_noahb", "ri3y_ahb",
]
COMMIT_LABEL = {
    "payg": "PAYG (on-demand)",
    "spot": "Spot",
    "ri1y_noahb": "1yr Reserved (Win no AHB)",
    "ri1y_ahb": "1yr Reserved (Win AHB)",
    "ri3y_noahb": "3yr Reserved (Win no AHB)",
    "ri3y_ahb": "3yr Reserved (Win AHB)",
}


def group_monthly(g):
    """Return {commitment: monthly_total_for_group} (None where unavailable)."""
    pr = organize_vm_prices(query_vm_prices(g["sku"], REGION, CURRENCY))
    qty, mo = g["qty"], HOURS_PER_MONTH

    def m(hourly):
        return None if hourly is None else hourly * mo * qty

    if g["os"] == "windows":
        lic = ((pr["windows"] - pr["linux"])
               if pr["windows"] is not None and pr["linux"] is not None else 0.0)

        def wl(hourly):  # reserved compute + licence at PAYG (no AHB)
            return None if hourly is None else hourly + lic

        return {
            "payg": m(pr["windows"]),
            "spot": None,  # Spot is Linux-only
            "ri1y_noahb": m(wl(pr["reserved_1yr"])),
            "ri1y_ahb": m(pr["reserved_1yr"]),
            "ri3y_noahb": m(wl(pr["reserved_3yr"])),
            "ri3y_ahb": m(pr["reserved_3yr"]),
        }
    # Linux: AHB columns mirror the base reserved rate (no licence involved).
    return {
        "payg": m(pr["linux"]),
        "spot": m(pr["spot"]),
        "ri1y_noahb": m(pr["reserved_1yr"]),
        "ri1y_ahb": m(pr["reserved_1yr"]),
        "ri3y_noahb": m(pr["reserved_3yr"]),
        "ri3y_ahb": m(pr["reserved_3yr"]),
    }


def add(a, b):
    """Sum two optional numbers; None only if BOTH are None."""
    if a is None and b is None:
        return None
    return (a or 0) + (b or 0)


# ── Styling helpers ─────────────────────────────────────────────────────────
HDR_FILL = PatternFill("solid", fgColor="1F4E78")
HDR_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=13, color="1F4E78")
BOLD = Font(bold=True)
THIN = Side(style="thin", color="D9D9D9")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
MONEY_FMT = '#,##0.00 "€"'


def style_header(ws, row, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER


def autofit(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w


def write_row(ws, row, values, money_cols=(), bold=False):
    for i, v in enumerate(values, 1):
        cell = ws.cell(row=row, column=i, value=v)
        cell.border = BORDER
        if bold:
            cell.font = BOLD
        if i in money_cols and isinstance(v, (int, float)):
            cell.number_format = MONEY_FMT
            cell.alignment = Alignment(horizontal="right")


def build(path):
    sym = currency_symbol(CURRENCY)
    for g in GROUPS:
        g["monthly"] = group_monthly(g)

    # Fleet monthly per commitment
    fleet = {k: None for k in COMMITMENTS}
    for k in COMMITMENTS:
        for g in GROUPS:
            fleet[k] = add(fleet[k], g["monthly"][k])

    wb = openpyxl.Workbook()

    # ---- Sheet 1: Selection ----
    ws = wb.active
    ws.title = "Selection"
    ws["A1"] = f"Azure Quote — {len(GROUPS)} groups / {sum(g['qty'] for g in GROUPS)} VMs @ {REGION} ({CURRENCY})"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = (f"Generated {date.today().isoformat()} · live Azure Retail Prices · "
                f"sizing rule: RAM meets-or-exceeds, vCPU floors to nearest size, D-family preferred")
    ws["A2"].font = Font(italic=True, color="808080")
    hdr = ["Group", "Source spec", "OS", "Qty", "Azure SKU", "vCPU", "RAM (GiB)"]
    ws.append([])
    ws.append(hdr)
    style_header(ws, ws.max_row, len(hdr))
    for g in GROUPS:
        write_row(ws, ws.max_row + 1,
                  [g["label"], g["src"], g["os"].capitalize(), g["qty"],
                   g["sku"], g["vcpu"], g["ram"]])
    autofit(ws, [8, 14, 10, 6, 20, 7, 11])

    # ---- Sheet 2: Per-Group monthly ----
    ws = wb.create_sheet("Per-Group")
    ws["A1"] = "Monthly cost per group — all commitment options (€/month)"
    ws["A1"].font = TITLE_FONT
    hdr = ["Group", "OS", "Qty", "SKU"] + [COMMIT_LABEL[k] for k in COMMITMENTS]
    ws.append([])
    ws.append(hdr)
    style_header(ws, ws.max_row, len(hdr))
    money_cols = tuple(range(5, 5 + len(COMMITMENTS)))
    for g in GROUPS:
        row = [g["label"], g["os"].capitalize(), g["qty"], g["sku"]]
        row += [g["monthly"][k] for k in COMMITMENTS]
        write_row(ws, ws.max_row + 1, row, money_cols=money_cols)
    # fleet subtotal
    total_row = ["TOTAL", "", sum(g["qty"] for g in GROUPS), ""] + [fleet[k] for k in COMMITMENTS]
    write_row(ws, ws.max_row + 1, total_row, money_cols=money_cols, bold=True)
    autofit(ws, [8, 10, 6, 20] + [24] * len(COMMITMENTS))

    # ---- Sheet 3: Fleet Total (monthly + annual) ----
    ws = wb.create_sheet("Fleet Total")
    ws["A1"] = f"Whole-fleet rollup — {sum(g['qty'] for g in GROUPS)} VMs (€)"
    ws["A1"].font = TITLE_FONT
    hdr = ["Commitment", "Total / month", "Total / year", "vs PAYG"]
    ws.append([])
    ws.append(hdr)
    style_header(ws, ws.max_row, len(hdr))
    payg_y = (fleet["payg"] or 0) * 12
    for k in COMMITMENTS:
        mo = fleet[k]
        if mo is None:
            write_row(ws, ws.max_row + 1, [COMMIT_LABEL[k], "N/A", "N/A", "N/A"])
            continue
        yr = mo * 12
        vs = "—" if k == "payg" else f"-{(payg_y - yr) / payg_y * 100:.0f}%"
        write_row(ws, ws.max_row + 1, [COMMIT_LABEL[k], mo, yr, vs],
                  money_cols=(2, 3), bold=(k == "payg"))
    ws.append([])
    note = ws.cell(row=ws.max_row + 1, column=1,
                   value="Spot shown for Linux groups only (B+C); Windows has no Spot rate. "
                         "Windows reserved given both with/without Azure Hybrid Benefit.")
    note.font = Font(italic=True, color="808080")
    autofit(ws, [30, 16, 16, 10])

    # ---- Sheet 4: TCO over 1/2/3 year horizons ----
    ws = wb.create_sheet("TCO")
    ws["A1"] = "Total Cost of Ownership — cumulative spend by horizon (€)"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = ("Azure VM reservations exist only in 1yr & 3yr terms. The 2-year column is a "
                "time horizon (1yr reservation renewed), not a 2-year reservation product. "
                "A 3yr reservation requires a full 3-year commitment.")
    ws["A2"].font = Font(italic=True, color="808080")
    hdr = ["Strategy", "€/month", "1-year TCO", "2-year TCO", "3-year TCO"]
    ws.append([])
    ws.append(hdr)
    style_header(ws, ws.max_row, len(hdr))
    for k in COMMITMENTS:
        if k == "spot":
            continue  # spot is interruptible, not a TCO commitment baseline
        mo = fleet[k]
        if mo is None:
            continue
        write_row(ws, ws.max_row + 1,
                  [COMMIT_LABEL[k], mo, mo * 12, mo * 24, mo * 36],
                  money_cols=(2, 3, 4, 5), bold=(k == "payg"))
    autofit(ws, [30, 14, 16, 16, 16])

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    wb.save(path)
    return fleet


def main():
    p = argparse.ArgumentParser(description="Export a fleet Azure quote to Excel")
    default = os.path.join("quotes", f"azure-fleet-quote-{REGION}-{date.today().isoformat()}.xlsx")
    p.add_argument("--output", "-o", default=default, help=f"Output .xlsx path (default: {default})")
    args = p.parse_args()
    fleet = build(args.output)
    print(f"✅ Wrote {args.output}")
    print("Fleet monthly totals:")
    for k in COMMITMENTS:
        v = fleet[k]
        print(f"  {COMMIT_LABEL[k]:32s} {'N/A' if v is None else f'€{v:,.2f}'}")


if __name__ == "__main__":
    main()
