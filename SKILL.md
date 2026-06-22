---
name: deviseur-azure
description: Azure pre-sales quoting from a hardware spec. Use when a user describes a VM by specs (e.g. "4U8G, 25G SSD", "4 vCPU 8GB", "8 cores 64GB memory") and wants Azure pricing or a quote. Two-step flow - first PROPOSE several matching Azure flavors (SKUs) across families with live prices in a region, let the user pick one, then output a full region QUOTE including managed disk and monthly/annual totals. Also supports BATCH sizing from a VMware RVTools .xlsx export (vInfo sheet) - map every VM to a D-preferred Azure flavor (RAM meets-or-exceeds source, vCPU floors to nearest size just below) with rollup totals. Defaults to francecentral region and EUR currency.
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [azure, pricing, quoting, pre-sales, vm, cloud, devops]
    related_skills: []
---

# Deviseur Azure

Turn a plain hardware spec into an Azure quote. Live prices come from the
Azure Retail Prices API (https://prices.azure.com/api/retail/prices); the
spec→flavor mapping uses the local catalog in `references/vm-catalog.json`.

**Defaults:** region `francecentral`, currency `EUR`. Override with `--region` / `--currency`.

Scripts are under `scripts/`. Reference data is under `references/`.

## Sizing rule (when the spec doesn't match an Azure standard size)

Customer specs often don't line up with Azure's fixed vCPU grid (1, 2, 4, 8,
16, 32 …). When the spec falls between sizes, apply this rule:

- **RAM must meet-or-exceed** the customer's RAM — never give them less memory.
- **vCPU may sit just below** the customer's vCPU — round the core count *down*
  to the nearest Azure size rather than up.
- **Prefer the D family** (general-purpose — Azure's "Standard" tier) when a
  D-series flavor satisfies the RAM floor; fall back to E (memory) when only E
  can meet the RAM at that core count, then F/B.

Example: a `3U4G` request (3 vCPU, 4 GiB) → recommend **`D2s_v5`** style sizing
(2 vCPU, RAM ≥ 4 GiB, D-series). The 3rd core is dropped (no 3-vCPU Azure size);
RAM is honored; D-series wins because it's the Standard general-purpose family.

This rule is implemented in `pick_flavor` / `target_vcpu` (`scripts/azure_lib.py`)
and drives both the interactive proposal and the RVTools batch mapping.

## Disk-sizing rule (when no tier matches exactly)

Azure managed-disk tiers are discrete (4, 8, 16, 32, 64, 128, 256 … GiB). When a
requested size has no exact tier, **minimize cost by minimizing the disk size
within technical tolerance**:

- Consider tiers within **80%–120%** of the requested size and pick the
  **smallest** one (cheapest — this may sit *just below* the request, e.g. an
  80 GiB request → a 64 GiB tier, since 64 = 80% of 80).
- If **no tier falls in 80%–120%**, step up to the **smallest tier above 120%**.

Examples: `80 GiB → 64 GiB tier` (in-band, cost down); `100 GiB → 128 GiB`
(64 is below 80%, 128 is the smallest above 120%); `300 GiB → 256 GiB` (in-band).

Implemented in `select_disk_tier` / `disk_tier_for_size` (`scripts/azure_lib.py`);
a tier below the request is flagged `undersized`. Drives every disk price across
the quote, RVTools, and fleet-export paths.

## Workflow (TWO steps — always interactive)

### Step 1 — Propose flavors
Parse the spec into **vCPU** and **RAM (GiB)**. Common shorthands:
- `4U8G` / `4C8G` / `4 vCPU 8GB` → `--vcpu 4 --ram 8`
- `8U64G` → `--vcpu 8 --ram 64`

Run:
```bash
python3 scripts/propose_flavors.py --vcpu 4 --ram 8 --region francecentral
```
Display the full proposal table, then **ask the user to pick a flavor (#)**.
Do NOT skip ahead to the quote — the user chooses first.

The table shows candidates across families (Burstable / General / Memory /
Compute), the recommended D-series first (per the **Sizing rule** above — RAM
meets-or-exceeds, vCPU floored to the nearest size just below). Every row lists
the Linux monthly price across **all four commitment options — PAYG, Spot, 1yr
Reserved, 3yr Reserved** (N/A where a family has no such rate).

### Step 2 — Quote the chosen flavor
Once the user picks a flavor, capture the disk requirement from the original
spec (e.g. "25G SSD" → `--disk-size 25 --disk-type premium-ssd`) and run:
```bash
python3 scripts/query_quote.py --sku Standard_F4s_v2 --region francecentral \
    --disk-size 25 --disk-type premium-ssd --os linux --qty 1
```
Display the full output: VM compute table, managed disk, and combined total
(with the 1yr-reserved saving note).

## Batch mode — RVTools import

When the user provides a VMware **RVTools** export (`.xlsx`) and wants the whole
estate sized, skip the interactive flavor pick and run the batch analyzer. It
reads the `vInfo` sheet and, per VM, maps the allocated vCPU/RAM/disk to a
D-preferred Azure flavor following the **Sizing rule** above (RAM meets-or-
exceeds; vCPU floors to the nearest size just below), then prints per-VM mapping
plus rollup totals (PAYG + 1yr Reserved) for a target region.

```bash
python3 scripts/analyze_rvtools.py inventory.xlsx --region francecentral
# include powered-off VMs / write a Markdown report:
python3 scripts/analyze_rvtools.py inventory.xlsx --include-poweredoff --output
# try it with the bundled sample:
python3 scripts/analyze_rvtools.py examples/rvtools-sample.xlsx
```

**OS is auto-detected per VM** from the sheet's OS column (Windows rows are
priced with the Windows rate; `--os` is only the fallback when the column is
absent). Tell the user up front: RVTools has **no Azure region** (region is a
target you pick, default `francecentral`) and is a point-in-time *allocation*
snapshot, not performance data — for true right-sizing use Azure Migrate.
Powered-off VMs and templates are excluded by default. Requires `openpyxl`
(`pip install openpyxl`). A sample export lives at `examples/rvtools-sample.xlsx`.

## Scripts

### propose_flavors.py
| Option | Default | Notes |
|--------|---------|-------|
| `--vcpu` / `-v` | required | vCPU count |
| `--ram` / `-m` | required | RAM in GiB |
| `--region` / `-r` | francecentral | Azure region |
| `--currency` / `-c` | EUR | Currency code |
| `--max` | 6 | Max candidates |

### query_quote.py
| Option | Default | Notes |
|--------|---------|-------|
| `--sku` / `-s` | required | Chosen flavor (Standard_ prefix auto-added) |
| `--region` / `-r` | francecentral | Azure region |
| `--currency` / `-c` | EUR | Currency code |
| `--os` | linux | `linux` or `windows` (headline total) |
| `--qty` / `-q` | 1 | Number of identical VMs |
| `--disk-size` | none | Disk size in GiB (rounded up to next tier) |
| `--disk-type` | premium-ssd | `premium-ssd`, `standard-ssd`, `standard-hdd` |
| `--output` / `-o` | none | Write the quote to a Markdown file. Bare flag auto-names it `quotes/quote-<sku>-<region>-<date>.md`; pass a PATH to choose the location. Output is still echoed to the screen. |

When the user asks to save/export/deliver the quote as a file, add `--output`
(bare for an auto-named file under `quotes/`, or with a PATH).

For a **Windows** headline (`--os windows`), the total table splits each
reserved term into **no AHB** (Windows Server licence stays at PAYG on top of
the reserved compute) and **with AHB** (Azure Hybrid Benefit — only the reserved
compute is billed). Always quote both so the customer sees the licence upside.

### export_fleet_xlsx.py
Export a **multi-group fleet quote to a multi-sheet Excel workbook** (Selection,
Per-Group, Group Detail, Fleet Total, TCO — where Group Detail breaks each group
into VM + disk for PAYG / 1yr / 3yr). Use when the user wants several different specs /
OSes / quantities priced together, or asks for **Excel/`.xlsx` output**. Pulls
live prices, carries the Windows AHB / no-AHB split, and builds a 1/2/3-year TCO.
Define the fleet with one repeatable `--group "SPEC,OS,QTY[,SKU]"` per distinct
group; the SKU is auto-picked from the sizing rule unless pinned as a 4th field.
```bash
python3 scripts/export_fleet_xlsx.py \
    --group 4U8G,windows,10 --group 3U6G,linux,10 --group 5U11G,linux,10
# pin a SKU, set region / output path:
python3 scripts/export_fleet_xlsx.py --group 8U64G,linux,5,E8s_v5 \
    --region westeurope --output /tmp/quote.xlsx
```

| Option | Default | Notes |
|--------|---------|-------|
| `--group` / `-g` | required | `SPEC,OS,QTY[,SKU]`; repeat per group. SKU optional (auto-picked) |
| `--region` / `-r` | francecentral | Azure region |
| `--currency` / `-c` | EUR | Currency code |
| `--output` / `-o` | auto | `.xlsx` path; default auto-named under `quotes/` |

The 2-year TCO column is a **time horizon** (a 1yr reservation renewed) — Azure
VM reservations exist only in 1yr and 3yr terms.

### analyze_rvtools.py
| Option | Default | Notes |
|--------|---------|-------|
| `file` | required | Path to the RVTools `.xlsx` export |
| `--region` / `-r` | francecentral | Target Azure region |
| `--currency` / `-c` | EUR | Currency code |
| `--os` | linux | Fallback OS when the sheet has no OS column (OS is auto-detected per VM otherwise) |
| `--disk-type` | premium-ssd | Disk type applied to every VM |
| `--sheet` | auto | Worksheet name (auto-detects `vInfo`) |
| `--include-poweredoff` | off | Include powered-off VMs |
| `--include-templates` | off | Include VM templates |
| `--output` / `-o` | none | Write Markdown report; bare flag auto-names under `quotes/`, or pass a PATH |

## Pricing notes (important for correct quotes)

- **Spot** is returned by the API as `type=Consumption` with "Spot" in the
  meter name (not `type=Spot`). The scripts handle this.
- **Reservation** `retailPrice` is the TOTAL for the whole term; the scripts
  convert it to an effective hourly/monthly rate.
- **Linux and Windows+AHB** share the same compute price.
- **Windows licence** = Windows PAYG − Linux PAYG. Reservations discount compute
  only, so a reserved Windows VM is *reserved compute + licence at PAYG* without
  AHB, or just *reserved compute* with Azure Hybrid Benefit. Quote both.
- **Reservations** come only in **1yr and 3yr** terms — there is no 2-year RI. A
  "2-year" figure is a time horizon (1yr reservation renewed), not a product.
- **Disk** is mapped to a tier by the **disk-sizing rule** below (not always a
  round-up). Disks have no reservation discount.
- Monthly = hourly × 730; annual = hourly × 8760.

## Reference data

- `references/vm-catalog.json` — SKU → family / vCPU / RAM. Extend this to add
  flavors (e.g. GPU N-series, constrained-core sizes).
- `references/disk-tiers.json` — managed-disk size tiers and API sku names.
- `references/service-mapping.md` — user term → Azure `serviceName` and region
  aliases, for ad-hoc queries beyond VMs/disks.
