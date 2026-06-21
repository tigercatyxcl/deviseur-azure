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
families, exact-spec match first), then ask the user to pick a flavor.

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
| `--output` / `-o` | none | Write quote to Markdown. Bare flag → `quotes/quote-<sku>-<region>-<date>.md`; or pass a PATH. Still echoes to screen. |

## Pricing notes (do not "fix" these — they are correct)

- **Spot** is returned by the API as `type=Consumption` with "Spot" in the
  meter name (NOT `type=Spot`). The scripts already handle this.
- **Reservation** `retailPrice` is the TOTAL for the whole term; the scripts
  convert it to an effective hourly/monthly rate.
- **Linux and Windows+AHB** share the same compute price.
- **Disk** is billed at the next tier up (25 GiB → P4 = 32 GiB) and has no
  reservation discount.
- Monthly = hourly × 730; annual = hourly × 8760.

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
