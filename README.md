# Deviseur Azure

**English** | [中文](README.zh-CN.md)

Turn a one-line hardware spec (e.g. `4U8G, 25G SSD`) into an Azure price quote.
Live prices come from the
[Azure Retail Prices API](https://prices.azure.com/api/retail/prices) (no key
required); the spec→flavor mapping uses the local catalog in
`references/vm-catalog.json`.

One set of `scripts/` + `references/` is reusable by three AI coding tools:

| Tool | Entry file |
|------|-----------|
| Claude Code | `SKILL.md` |
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

### 2.2 As a Codex project (`AGENTS.md`)

No extra install: Codex (CLI or cloud agent) reads `AGENTS.md` at the repo root.
Describe a spec quote in this repo and it runs the scripts under `scripts/`.

### 2.3 As a GitHub Copilot project (`.github/copilot-instructions.md`)

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
exact-spec match first, with Linux €/hr, €/month, and 1yr reserved €/month.
**Pick one flavor.**

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

---

## 5. Pricing model (key to reading a quote)

- **Spot** is returned by the API as `type=Consumption` with "Spot" in the meter
  name (not `type=Spot`); the scripts handle this.
- **Reservation** `retailPrice` is the TOTAL for the whole term; the scripts
  amortize it to an effective hourly/monthly rate.
- **Linux and Windows+AHB** share the same compute price.
- **Disk** bills at the next tier up (25 GiB → P4 = 32 GiB), with no reservation
  discount.
- Monthly = hourly × 730; annual = hourly × 8760.

---

## 6. Extending

- Add flavors (GPU N-series, constrained-core sizes, etc.): edit
  `references/vm-catalog.json` with a `sku/family/vcpu/ram_gib` row.
- Add disk tiers: edit `references/disk-tiers.json`.
- Non-VM/disk service-name mapping: see `references/service-mapping.md`.

> When you change behavior, keep `SKILL.md`, `AGENTS.md`, and
> `.github/copilot-instructions.md` in sync.

---

## 7. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError: requests` | `pip install -r requirements.txt` |
| All prices show N/A | SKU not available in that region; change region or check the SKU name |
| Connection timeout | Check access to `prices.azure.com` (corporate proxy/firewall) |
| Copilot doesn't run scripts | Use agent mode; inline completion does not execute commands |
| Claude Code doesn't trigger the skill | Ensure it's copied to `~/.claude/skills/deviseur-azure/` and start a new session |

---

## License

[MIT](LICENSE)
