---
name: deviseur-azure
description: Azure pre-sales quoting from a hardware spec. Use when a user describes a VM by specs (e.g. "4U8G, 25G SSD", "4 vCPU 8GB", "8 cores 64GB memory") and wants Azure pricing or a quote. Two-step flow - first PROPOSE several matching Azure flavors (SKUs) across families with live prices in a region, let the user pick one, then output a full region QUOTE including managed disk and monthly/annual totals. Also supports BATCH sizing from a VMware RVTools .xlsx export (vInfo sheet) - lift-and-shift map every VM to the cheapest meet-or-exceed Azure flavor with rollup totals. Defaults to francecentral region and EUR currency.
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
Compute), the exact-spec match first, with Linux €/hr, €/month, and 1yr
reserved €/month.

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
reads the `vInfo` sheet and, per VM, maps the allocated vCPU/RAM/disk to the
cheapest Azure flavor that **meets-or-exceeds** it (lift-and-shift), then prints
per-VM mapping plus rollup totals (PAYG + 1yr Reserved) for a target region.

```bash
python3 scripts/analyze_rvtools.py inventory.xlsx --region francecentral
# include powered-off VMs / write a Markdown report:
python3 scripts/analyze_rvtools.py inventory.xlsx --include-poweredoff --output
```

Tell the user up front: RVTools has **no Azure region** (region is a target you
pick, default `francecentral`) and is a point-in-time *allocation* snapshot, not
performance data — for true right-sizing use Azure Migrate. Powered-off VMs and
templates are excluded by default. Requires `openpyxl` (`pip install openpyxl`).

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

### analyze_rvtools.py
| Option | Default | Notes |
|--------|---------|-------|
| `file` | required | Path to the RVTools `.xlsx` export |
| `--region` / `-r` | francecentral | Target Azure region |
| `--currency` / `-c` | EUR | Currency code |
| `--os` | linux | `linux` or `windows` (headline totals) |
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
- **Disk** is billed at the next tier up (25 GiB → P4 = 32 GiB). Disks have no
  reservation discount.
- Monthly = hourly × 730; annual = hourly × 8760.

## Reference data

- `references/vm-catalog.json` — SKU → family / vCPU / RAM. Extend this to add
  flavors (e.g. GPU N-series, constrained-core sizes).
- `references/disk-tiers.json` — managed-disk size tiers and API sku names.
- `references/service-mapping.md` — user term → Azure `serviceName` and region
  aliases, for ad-hoc queries beyond VMs/disks.
