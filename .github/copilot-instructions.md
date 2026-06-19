# GitHub Copilot instructions — Deviseur Azure

This repo turns a plain hardware spec into an Azure price quote. The logic lives
in `scripts/` (Python) and `references/` (JSON/Markdown data). Use Copilot Chat
**agent mode** (which can run terminal commands) to drive the workflow.

> The same workflow is defined for Claude Code in `SKILL.md` and for Codex in
> `AGENTS.md`. All three share the same `scripts/` and `references/` — never
> duplicate or fork the pricing logic.

## When to use this

When the user describes a VM by specs (e.g. "4U8G, 25G SSD", "4 vCPU 8GB",
"8 cores 64GB memory") and wants Azure pricing or a quote, run the two-step
workflow below. Requires Python 3.9+, `pip install requests`, and network
access to `prices.azure.com` (no API key needed).

**Defaults:** region `francecentral`, currency `EUR` (override with
`--region` / `--currency`).

## Workflow — TWO steps, interactive

Do NOT skip ahead to the quote; the user picks a flavor first.

### Step 1 — Propose flavors
Parse the spec into vCPU and RAM (GiB): `4U8G` → `--vcpu 4 --ram 8`.

```bash
python3 scripts/propose_flavors.py --vcpu 4 --ram 8 --region francecentral
```

Show the full proposal table, then ask the user to pick a flavor.

### Step 2 — Quote the chosen flavor
Capture disk from the spec ("25G SSD" → `--disk-size 25 --disk-type premium-ssd`):

```bash
python3 scripts/query_quote.py --sku Standard_D4as_v5 --region francecentral \
    --disk-size 25 --disk-type premium-ssd --os linux --qty 1
```

Show the full output (VM compute, disk, and the PAYG/Spot/1yr/3yr commitment
table). To export the quote as a Markdown file, add `--output` (bare flag →
`quotes/quote-<sku>-<region>-<date>.md`, or pass a PATH).

## Script options (quick reference)

- `propose_flavors.py`: `--vcpu` (req), `--ram` (req), `--region`, `--currency`, `--max`
- `query_quote.py`: `--sku` (req), `--region`, `--currency`, `--os {linux,windows}`,
  `--qty`, `--disk-size`, `--disk-type {premium-ssd,standard-ssd,standard-hdd}`,
  `--output [PATH]`

## Pricing notes (these are correct — do not "fix" them)

- **Spot** comes back as `type=Consumption` with "Spot" in the meter name
  (not `type=Spot`); the scripts handle it.
- **Reservation** `retailPrice` is the TOTAL for the whole term; the scripts
  amortize it to an effective hourly/monthly rate.
- **Linux and Windows+AHB** share the same compute price.
- **Disk** bills at the next tier up (25 GiB → P4 = 32 GiB), no reservation discount.
- Monthly = hourly × 730; annual = hourly × 8760.

## Editing guidance

- `references/vm-catalog.json` is the spec→flavor source (SKU → family/vCPU/RAM);
  extend it to add flavors.
- Keep `SKILL.md`, `AGENTS.md`, and this file in sync when behavior changes.
