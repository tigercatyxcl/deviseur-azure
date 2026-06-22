# Deviseur Azure

**English** | [中文](README.zh-CN.md)

Turn a one-line hardware spec (e.g. `4U8G, 25G SSD`) into an Azure price quote.
Live prices come from the
[Azure Retail Prices API](https://prices.azure.com/api/retail/prices) (no key
required); the spec→flavor mapping uses the local catalog in
`references/vm-catalog.json`.

One set of `scripts/` + `references/` is reusable by four AI coding tools:

| Tool | Entry file |
|------|-----------|
| Claude Code | `SKILL.md` |
| Hermes Agent | `SKILL.md` (same file — Hermes reads the Claude skill format) |
| OpenAI Codex | `AGENTS.md` |
| GitHub Copilot | `.github/copilot-instructions.md` |

---

## 1. Requirements

- **Python 3.9+**
- Dependency: `requests`
- Network access to `prices.azure.com` (no Azure account / API key needed)

```bash
pip install -r requirements.txt
# or: pip install requests
```

Verify:
```bash
python3 scripts/propose_flavors.py --vcpu 2 --ram 8
```
If it prints a candidate-flavor table, your environment is ready.

---

## 2. Installation

### 2.1 As a Claude Code skill (auto-trigger + `/deviseur-azure`)

Copy the whole skill into your global skills directory:

```bash
mkdir -p ~/.claude/skills/deviseur-azure
cp -R SKILL.md scripts references ~/.claude/skills/deviseur-azure/
```

Open a new Claude Code session and just say "quote a 4U8G, 25G SSD Azure VM" —
it triggers automatically. You can also invoke `/deviseur-azure`.

> Note: the global copy is separate from this repo. After changing scripts,
> re-copy them, or run the scripts directly from the repo.

### 2.2 As a Hermes Agent skill (no copy needed)

[Hermes Agent](https://github.com/tigercatyxcl) reads the same Claude `SKILL.md`
format, so this repo is already a Hermes skill. Register it **without copying the
code** by adding the repo path to `skills.external_dirs` in your Hermes
`config.yaml`. Hermes uses one config per active profile, so edit the profile(s)
you run — `~/.hermes/profiles/<name>/config.yaml` — and/or the default
`~/.hermes/config.yaml`:

```yaml
skills:
  external_dirs:
    - /path/to/deviseur-azure
```

Hermes then discovers `SKILL.md`, injects the absolute `[Skill directory: …]`,
and runs the same `scripts/` via its shell — so edits to the repo take effect
immediately, no re-copy. Make sure `requests` is installed in the Python env
Hermes shells into.

### 2.3 As a Codex project (`AGENTS.md`)

No extra install: Codex (CLI or cloud agent) reads `AGENTS.md` at the repo root.
Describe a spec quote in this repo and it runs the scripts under `scripts/`.

### 2.4 As a GitHub Copilot project (`.github/copilot-instructions.md`)

No extra install: open this repo in VS Code with **Copilot Chat agent mode**
(which can run terminal commands) and `.github/copilot-instructions.md` is
injected automatically. Plain inline completion only reads the guidance; it does
not run scripts.

---

## 3. Usage — two-step workflow

Quoting is always two interactive steps: pick a flavor first, then quote.

### Step 1 — Propose flavors

Split the spec into vCPU and RAM (GiB): `4U8G` → `--vcpu 4 --ram 8`.

```bash
python3 scripts/propose_flavors.py --vcpu 4 --ram 8 --region francecentral
```

Outputs candidates across families (Burstable / General / Memory / Compute),
the recommended D-series (RAM meets-or-exceeds, vCPU floored to the nearest size
just below) first, each with the Linux monthly price across all four commitment
options — **PAYG, Spot, 1yr Reserved, 3yr Reserved**. **Pick one flavor.**

### Step 2 — Full quote

Add the disk requirement (`25G SSD` → `--disk-size 25 --disk-type premium-ssd`):

```bash
python3 scripts/query_quote.py --sku Standard_D4as_v5 --region francecentral \
    --disk-size 25 --disk-type premium-ssd --os linux --qty 1
```

Outputs: VM compute table + managed disk + total across all commitment options
(PAYG / Spot / 1yr Reserved / 3yr Reserved).

### Export to a Markdown file

```bash
# auto-named under quotes/quote-<sku>-<region>-<date>.md
python3 scripts/query_quote.py --sku D4as_v5 --disk-size 25 --output

# specific path
python3 scripts/query_quote.py --sku D4as_v5 --disk-size 25 --output /tmp/quote.md
```

### Batch mode — size a whole estate from RVTools

Already have a VMware [RVTools](https://www.robware.net/rvtools/) export? Skip the
interactive flow and size every VM at once. The analyzer reads the `vInfo` sheet
and maps each VM's allocated vCPU/RAM/disk to a D-preferred Azure flavor under
the sizing rule — **RAM meets-or-exceeds** the source while **vCPU floors** to
the nearest Azure size just below it — then prints a per-VM mapping plus
rollup totals (PAYG + 1yr Reserved). Needs `openpyxl` (already in
`requirements.txt`).

```bash
python3 scripts/analyze_rvtools.py inventory.xlsx --region francecentral

# include powered-off VMs and write a Markdown report under quotes/
python3 scripts/analyze_rvtools.py inventory.xlsx --include-poweredoff --output

# try it now with the bundled sample export
python3 scripts/analyze_rvtools.py examples/rvtools-sample.xlsx
```

**OS is auto-detected per VM** from the sheet's OS column — Windows VMs are
priced with the Windows rate (licence included; the reserved column keeps the
licence at PAYG, i.e. assume Azure Hybrid Benefit to drop it), Linux with the
base rate. `--os` is only the fallback when the sheet has no OS column.

> **Heads-up:** RVTools contains **no Azure region** — region is a target you
> choose (default `francecentral`). It's also a point-in-time *allocation*
> snapshot, not performance data, so this is an allocation-based estimate; for
> performance-based right-sizing use Azure Migrate. Powered-off VMs and templates
> are excluded by default; one `--disk-type` applies to all VMs. A sample export
> ships at [`examples/rvtools-sample.xlsx`](examples/rvtools-sample.xlsx).

---

## 4. Options reference

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
| `--sku` / `-s` | required | Chosen flavor (`Standard_` prefix auto-added) |
| `--region` / `-r` | francecentral | Azure region |
| `--currency` / `-c` | EUR | Currency code |
| `--os` | linux | `linux` or `windows` (which OS the total row uses) |
| `--qty` / `-q` | 1 | Number of identical VMs |
| `--disk-size` | none | Disk size in GiB (rounded up to next tier) |
| `--disk-type` | premium-ssd | `premium-ssd` / `standard-ssd` / `standard-hdd` |
| `--output` / `-o` | none | Export Markdown; bare flag auto-names, or pass a PATH. Still echoes to screen |

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
| `--output` / `-o` | none | Export Markdown report; bare flag auto-names under `quotes/`, or pass a PATH |

---

## 5. Pricing model (key to reading a quote)

- **Spot** is returned by the API as `type=Consumption` with "Spot" in the meter
  name (not `type=Spot`); the scripts handle this.
- **Reservation** `retailPrice` is the TOTAL for the whole term; the scripts
  amortize it to an effective hourly/monthly rate.
- **Linux and Windows+AHB** share the same compute price.
- **Disk** is mapped to the cheapest tier within 80%–120% of the request (else
  the next tier above 120% — e.g. 80 GiB → 64 GiB, 100 GiB → 128 GiB), with no
  reservation discount.
- Monthly = hourly × 730; annual = hourly × 8760.

---

## 6. Extending

- Add flavors (GPU N-series, constrained-core sizes, etc.): edit
  `references/vm-catalog.json` with a `sku/family/vcpu/ram_gib` row.
- Add disk tiers: edit `references/disk-tiers.json`.
- Non-VM/disk service-name mapping: see `references/service-mapping.md`.

> When you change behavior, keep `SKILL.md` (shared by Claude Code and Hermes),
> `AGENTS.md`, and `.github/copilot-instructions.md` in sync.

---

## 7. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError: requests` | `pip install -r requirements.txt` |
| `ModuleNotFoundError: openpyxl` (RVTools mode) | `pip install openpyxl` (or `-r requirements.txt`) |
| RVTools: "Could not find CPU/Memory columns" | Point `--sheet vInfo`, or confirm the export has `CPUs` + `Memory` columns |
| All prices show N/A | SKU not available in that region; change region or check the SKU name |
| Connection timeout | Check access to `prices.azure.com` (corporate proxy/firewall) |
| Copilot doesn't run scripts | Use agent mode; inline completion does not execute commands |
| Claude Code doesn't trigger the skill | Ensure it's copied to `~/.claude/skills/deviseur-azure/` and start a new session |

---

## License

[MIT](LICENSE)
