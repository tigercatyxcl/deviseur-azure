---
name: deviseur-azure
description: Azure pre-sales quoting from a hardware spec. Use when a user describes a VM by specs (e.g. "4U8G, 25G SSD", "4 vCPU 8GB", "8 cores 64GB memory") and wants Azure pricing or a quote. Two-step flow - first PROPOSE several matching Azure flavors (SKUs) across families with live prices in a region, let the user pick one, then output a full region QUOTE including managed disk and monthly/annual totals. Defaults to francecentral region and EUR currency.
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
