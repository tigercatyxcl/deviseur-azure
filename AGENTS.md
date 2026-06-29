# AGENTS.md — Deviseur Azure

Project instructions for coding agents (OpenAI Codex, and any tool that reads
`AGENTS.md`). This repo turns a plain hardware spec into an Azure price quote.

> Claude Code users: the same workflow lives in `SKILL.md`.
> GitHub Copilot users: see `.github/copilot-instructions.md`.
> Hermes Agent users: this repo IS a Hermes skill (`SKILL.md` frontmatter is
> Hermes-compatible). Register it without copying the code by adding the repo
> path to `skills.external_dirs` in your Hermes `config.yaml` (per active
> profile under `~/.hermes/profiles/<name>/config.yaml`, or the default
> `~/.hermes/config.yaml`):
>
> ```yaml
> skills:
>   external_dirs:
>     - /path/to/deviseur-azure
> ```
>
> Hermes discovers `SKILL.md`, injects the absolute `[Skill directory: …]`, and
> the agent runs the same `scripts/` via its shell. Requires `requests` in the
> Python env Hermes shells into.
> All of these share the same `scripts/` and `references/` — do not fork the logic.

## What this does

Live prices come from the Azure Retail Prices API
(`https://prices.azure.com/api/retail/prices`). The spec→flavor mapping uses the
local catalog in `references/vm-catalog.json` (the pricing API has no
vCPU/RAM metadata, so the catalog supplies it).

**Defaults:** region `francecentral`, currency `EUR`. Override with
`--region` / `--currency`.

## Requirements

- Python 3.9+
- `pip install requests`
- Network access to `prices.azure.com` (no auth/API key needed)

## Sizing rule (specs that don't match an Azure standard size)

Azure vCPUs come in a fixed grid (1, 2, 4, 8, 16, 32 …). When a spec falls
between sizes:

- **RAM must meet-or-exceed** the customer's RAM — never under-provision memory.
- **vCPU may sit just below** the customer's vCPU — floor the core count to the
  nearest Azure size instead of rounding up (3 vCPU → 2).
- **Prefer the D family** ("Standard" general-purpose) when it satisfies the RAM
  floor; fall back to E (memory) only when D can't meet the RAM at that core
  count, then F/B.

Example: `3U4G` → recommend `D2s_v5`-style sizing (2 vCPU, RAM ≥ 4 GiB, D-series).
Implemented in `pick_flavor` / `target_vcpu` (`scripts/azure_lib.py`); drives
both the interactive proposal and the RVTools batch mapping.

## Disk-sizing rule (no exact tier match)

Disk tiers are discrete (4, 8, 16, 32, 64, 128 … GiB). Minimize cost within
tolerance: pick the **smallest tier within 80%–120%** of the request (may sit
just below it, e.g. 80 GiB → 64 GiB); if none falls in that band, step up to the
**smallest tier above 120%** (100 GiB → 128 GiB). Implemented in
`select_disk_tier` / `disk_tier_for_size`; a sub-request tier is flagged
`undersized`.

## Workflow — TWO steps, always interactive

When the user describes a VM by specs (e.g. "4U8G, 25G SSD", "4 vCPU 8GB",
"8 cores 64GB") and wants Azure pricing, run this two-step flow. Do NOT skip
straight to the quote — the user picks a flavor first.

### Step 1 — Propose flavors
Parse the spec into vCPU and RAM (GiB). Shorthands: `4U8G`/`4C8G`/`4 vCPU 8GB`
→ `--vcpu 4 --ram 8`.

```bash
python3 scripts/propose_flavors.py --vcpu 4 --ram 8 --region francecentral
```

Show the full proposal table (candidates across Burstable/General/Memory/Compute
families, recommended D-series first per the sizing rule above; each row lists
the Linux monthly price across all four commitment options — PAYG / Spot / 1yr /
3yr Reserved), then ask the user to pick a flavor.

### Step 2 — Quote the chosen flavor
Capture the disk requirement from the spec ("25G SSD" → `--disk-size 25
--disk-type premium-ssd`) and run:

```bash
python3 scripts/query_quote.py --sku Standard_D4as_v5 --region francecentral \
    --disk-size 25 --disk-type premium-ssd --os linux --qty 1
```

Show the full output: VM compute table, managed disk, and the combined total
across all commitment options (PAYG / Spot / 1yr / 3yr Reserved).

To save/export/deliver the quote as a Markdown file, add `--output` (bare flag
auto-names it under `quotes/`, or pass a PATH).

## Batch mode — RVTools import

When the user supplies a VMware **RVTools** export (`.xlsx`) instead of a single
spec, run the batch analyzer rather than the two-step flow. It reads the
`vInfo` sheet and, per VM, maps allocated vCPU/RAM/disk to a D-preferred Azure
flavor under the sizing rule (RAM meets-or-exceeds source; vCPU floors to the
nearest size just below), then prints per-VM mapping plus rollup totals (PAYG +
1yr Reserved) for a target region.

```bash
python3 scripts/analyze_rvtools.py inventory.xlsx --region francecentral
python3 scripts/analyze_rvtools.py inventory.xlsx --include-poweredoff --output
python3 scripts/analyze_rvtools.py examples/rvtools-sample.xlsx   # bundled sample
```

OS is auto-detected per VM from the sheet (Windows priced with the Windows rate;
`--os` is the fallback when there is no OS column). State the caveats: RVTools
has **no Azure region** (region is a target choice, default `francecentral`) and
is a point-in-time *allocation* snapshot, not performance data — for right-sizing
use Azure Migrate. Powered-off VMs and templates are excluded by default. Needs
`openpyxl`. Sample export: `examples/rvtools-sample.xlsx`.

## Scripts

### propose_flavors.py
| Option | Default | Notes |
|--------|---------|-------|
| `--vcpu` / `-v` | required | vCPU count |
| `--ram` / `-m` | required | RAM in GiB |
| `--region` / `-r` | francecentral | Azure region |
| `--currency` / `-c` | EUR | Currency code |
| `--max` | 6 | Max candidates |

### analyze_rvtools.py
| Option | Default | Notes |
|--------|---------|-------|
| `file` | required | Path to the RVTools `.xlsx` export |
| `--region` / `-r` | francecentral | Target Azure region |
| `--currency` / `-c` | EUR | Currency code |
| `--os` | linux | Fallback OS when the sheet has no OS column (auto-detected per VM otherwise) |
| `--disk-type` | premium-ssd | Disk type applied to every VM |
| `--sheet` | auto | Worksheet name (auto-detects `vInfo`) |
| `--include-poweredoff` | off | Include powered-off VMs |
| `--include-templates` | off | Include VM templates |
| `--output` / `-o` | none | Write Markdown report; bare flag auto-names under `quotes/`, or a PATH |

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
| `--output` / `-o` | none | Write quote to Markdown. Bare flag → `quotes/quote-<sku>-<region>-<date>.md`; or pass a PATH. Still echoes to screen. |

## Pricing notes (do not "fix" these — they are correct)

- **Spot** is returned by the API as `type=Consumption` with "Spot" in the
  meter name (NOT `type=Spot`). The scripts already handle this.
- **Reservation** `retailPrice` is the TOTAL for the whole term; the scripts
  convert it to an effective hourly/monthly rate.
- **Linux and Windows+AHB** share the same compute price.
- **Windows reserved** = reserved compute + Windows licence at PAYG (no AHB), or
  just reserved compute (with Azure Hybrid Benefit). `query_quote.py --os
  windows` prints both rows; always present both.
- **Reservations** come only in **1yr and 3yr** terms — there is no 2-year RI.
- **Disk** is mapped by the disk-sizing rule above (smallest tier in 80%–120%,
  else next above 120% — not always a round-up) and has no reservation discount.
- Monthly = hourly × 730; annual = hourly × 8760.

## Multi-group fleets & Excel export

For several specs/OSes/quantities priced together, or when the user asks for
**Excel/`.xlsx`**, use `scripts/export_fleet_xlsx.py`. Define the fleet with one
repeatable `--group "SPEC,OS,QTY[,SKU]"` per distinct group (SKU auto-picked from
the sizing rule unless pinned):
```bash
python3 scripts/export_fleet_xlsx.py \
    --group 4U8G,windows,10 --group 3U6G,linux,10 --group 5U11G,linux,10
```
It writes a multi-sheet workbook — Selection, Per-Group, Group Detail (each
group's VM + disk for PAYG / 1yr / 3yr), Fleet Total, and a 1/2/3-year TCO —
with the Windows AHB / no-AHB split carried through. `.xlsx` outputs land under
`quotes/` (git-ignored).

## Reference data

- `references/vm-catalog.json` — SKU → family / vCPU / RAM. Extend to add
  flavors (GPU N-series, constrained-core sizes, etc.).
- `references/disk-tiers.json` — managed-disk size tiers and API sku names.
- `references/service-mapping.md` — user term → Azure `serviceName` and region
  aliases, for ad-hoc queries beyond VMs/disks.

## Conventions

- Keep `scripts/` and `references/` as the single source of truth; if you change
  behavior, update `SKILL.md`, `AGENTS.md`, and `.github/copilot-instructions.md`
  together.
- Quote prices are indicative; always note the generation date in deliverables
  (the script footer does this automatically).
