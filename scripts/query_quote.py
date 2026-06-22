#!/usr/bin/env python3
"""
Step 2 of the deviseur-azure workflow.

Given a chosen VM flavor + region (+ optional managed disk), output a full
quote for that region: VM compute price across price types, disk price, and
combined monthly / annual totals.

Usage:
    python3 scripts/query_quote.py --sku Standard_F4s_v2 --region francecentral \
        --disk-size 25 --disk-type premium-ssd --os linux --qty 1
    # write a Markdown file (auto-named under quotes/):
    python3 scripts/query_quote.py --sku Standard_F4s_v2 --disk-size 25 --output
    # write to a specific path:
    python3 scripts/query_quote.py --sku Standard_F4s_v2 --output /tmp/quote.md
"""

import argparse
import io
import os
import re
import sys
from contextlib import redirect_stdout
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from azure_lib import (  # noqa: E402
    normalize_sku, query_vm_prices, organize_vm_prices,
    load_disk_tiers, disk_tier_for_size, query_disk_price,
    currency_symbol, HOURS_PER_MONTH, HOURS_PER_YEAR,
)


def money(v, sym, dp=2):
    return "N/A" if v is None else f"{sym}{v:,.{dp}f}"


def render(args, sym, sku):
    """Print the full Markdown quote to stdout. Returns False if no pricing."""
    vm = organize_vm_prices(query_vm_prices(sku, args.region, args.currency))
    if vm["linux"] is None and vm["windows"] is None:
        print(f"No VM pricing found for {sku} in {args.region}. "
              f"Check the SKU name and region.")
        return False

    print(f"# Azure Quote — {sku} @ {args.region} ({args.currency})\n")
    if args.qty > 1:
        print(f"Quantity: **{args.qty} VMs**\n")

    # --- VM compute table ---
    print("## VM compute\n")
    print("| Price type | Hourly | Monthly | Annual |")
    print("|------------|--------|---------|--------|")
    rows = [
        ("Linux / Win+AHB", vm["linux"]),
        ("Windows", vm["windows"]),
        ("Spot (Linux)", vm["spot"]),
        ("1yr Reserved", vm["reserved_1yr"]),
        ("3yr Reserved", vm["reserved_3yr"]),
    ]
    for label, hourly in rows:
        if hourly is None:
            print(f"| {label} | N/A | N/A | N/A |")
            continue
        # Reserved prices from the API are already amortized to an hourly effective rate
        print(f"| {label} | {money(hourly, sym, 4)} | "
              f"{money(hourly * HOURS_PER_MONTH, sym)} | {money(hourly * HOURS_PER_YEAR, sym)} |")

    # --- Disk ---
    disk_monthly = None
    disk_info = None
    if args.disk_size:
        tiers = load_disk_tiers()
        disk_info = disk_tier_for_size(args.disk_size, args.disk_type, tiers)
        disk_monthly = query_disk_price(
            disk_info["sku_name"], disk_info["product_name"], args.region, args.currency
        )
        print(f"\n## Managed disk\n")
        print("| Requested | Billed tier | Type | Monthly |")
        print("|-----------|-------------|------|---------|")
        fit_flag = " ⤓" if disk_info.get("undersized") else ""
        print(f"| {args.disk_size:g} GiB | {disk_info['sku_name']} ({disk_info['tier_size_gib']} GiB){fit_flag} "
              f"| {disk_info['label']} | {money(disk_monthly, sym)} |")
        print("\n> Disk tier is the cheapest that fits within 80%–120% of the requested size "
              "(else the next tier above 120%).")
        if disk_info.get("undersized"):
            print(f"> ⤓ The {disk_info['tier_size_gib']:g} GiB tier sits below the requested "
                  f"{args.disk_size:g} GiB but stays within the 80% tolerance — chosen to lower cost.")

    # --- Combined total across commitment options ---
    os_hourly = vm[args.os]
    qty_label = f" × {args.qty}" if args.qty > 1 else ""
    print(f"\n## Total — {args.os.capitalize()}{qty_label} (all commitment options)\n")
    if os_hourly is None:
        print(f"No {args.os} compute price available for this SKU/region.")
        print("\n> Reserved/Spot pricing applies to Linux/base compute; "
              "rerun with `--os linux` for the full commitment comparison.")
    else:
        disk_m = disk_monthly or 0
        disk_total = disk_m * args.qty
        # (label, vm effective hourly). Reserved rates are already amortized hourly.
        if args.os == "windows":
            # Reservations discount compute only; the Windows licence is not
            # reservable. Without Azure Hybrid Benefit the licence (windows −
            # linux) stays at PAYG on top of the reserved compute; with AHB it
            # drops, leaving just the base reserved compute. Show both.
            lic = (vm["windows"] - vm["linux"]) if (vm["windows"] is not None
                                                    and vm["linux"] is not None) else 0.0

            def with_lic(hourly):
                return None if hourly is None else hourly + lic

            options = [
                ("Pay-as-you-go", os_hourly),
                ("Spot", None),  # Spot pricing is Linux-only
                ("1yr Reserved (no AHB)", with_lic(vm["reserved_1yr"])),
                ("1yr Reserved (with AHB)", vm["reserved_1yr"]),
                ("3yr Reserved (no AHB)", with_lic(vm["reserved_3yr"])),
                ("3yr Reserved (with AHB)", vm["reserved_3yr"]),
            ]
        else:
            options = [
                ("Pay-as-you-go", os_hourly),
                ("Spot", vm["spot"]),
                ("1yr Reserved", vm["reserved_1yr"]),
                ("3yr Reserved", vm["reserved_3yr"]),
            ]
        payg_month = os_hourly * HOURS_PER_MONTH * args.qty + disk_total

        print("| Commitment | VM /mo | Disk /mo | Total /mo | Total /yr | vs PAYG |")
        print("|------------|--------|----------|-----------|-----------|---------|")
        for label, hourly in options:
            if hourly is None:
                print(f"| {label} | N/A | N/A | N/A | N/A | N/A |")
                continue
            vm_total_m = hourly * HOURS_PER_MONTH * args.qty
            total_m = vm_total_m + disk_total
            if label == "Pay-as-you-go":
                vs = "—"
            else:
                pct = (payg_month - total_m) / payg_month * 100 if payg_month else 0
                vs = f"-{pct:.0f}%"
            bold = "**" if label == "Pay-as-you-go" else ""
            print(f"| {bold}{label}{bold} | {money(vm_total_m, sym)} | {money(disk_total, sym)} "
                  f"| {bold}{money(total_m, sym)}{bold} | {money(total_m * 12, sym)} | {vs} |")

        print(f"\n> Reserved = upfront/monthly commitment, amortized here to an effective rate. "
              f"Disk ({disk_info['sku_name'] if disk_info else 'n/a'}) has no reservation discount "
              f"and is the same in every row.")
        if args.os == "windows":
            print("> **Windows licence:** PAYG/reserved (no AHB) include the Windows Server "
                  "licence. With **Azure Hybrid Benefit** you reuse an owned licence, so only "
                  "the reserved compute is billed — quote both so the customer sees the AHB upside.")

    print(f"\n*Generated {date.today().isoformat()} from Azure Retail Prices API. "
          f"Prices are indicative and subject to change.*")
    return True


def auto_filename(args, sku):
    """quotes/quote-<sku>-<region>-<date>.md"""
    safe_sku = re.sub(r"[^A-Za-z0-9_]", "", sku.replace("Standard_", ""))
    name = f"quote-{safe_sku}-{args.region}-{date.today().isoformat()}.md"
    return os.path.join("quotes", name)


def main():
    p = argparse.ArgumentParser(description="Quote a chosen Azure VM flavor in a region")
    p.add_argument("--sku", "-s", required=True, help="VM SKU (e.g. Standard_F4s_v2)")
    p.add_argument("--region", "-r", default="francecentral", help="Azure region (default: francecentral)")
    p.add_argument("--currency", "-c", default="EUR", help="Currency code (default: EUR)")
    p.add_argument("--os", default="linux", choices=["linux", "windows"], help="OS for the headline total (default: linux)")
    p.add_argument("--qty", "-q", type=int, default=1, help="Number of identical VMs (default: 1)")
    p.add_argument("--disk-size", type=float, default=None, help="OS/data disk size in GiB (optional)")
    p.add_argument("--disk-type", default="premium-ssd",
                   choices=["premium-ssd", "standard-ssd", "standard-hdd"],
                   help="Managed disk type (default: premium-ssd)")
    p.add_argument("--output", "-o", nargs="?", const="auto", default=None,
                   metavar="PATH",
                   help="Write the quote to a Markdown file. Bare flag auto-names "
                        "it under quotes/; pass a PATH to choose the location.")
    args = p.parse_args()

    sym = currency_symbol(args.currency)
    sku = normalize_sku(args.sku)

    buf = io.StringIO()
    with redirect_stdout(buf):
        ok = render(args, sym, sku)
    text = buf.getvalue()

    # Always echo to the screen
    print(text, end="" if text.endswith("\n") else "\n")

    if args.output and ok:
        path = auto_filename(args, sku) if args.output == "auto" else args.output
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"\n✅ Written to {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
