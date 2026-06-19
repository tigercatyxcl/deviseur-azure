# Deviseur Azure

把一句话的硬件规格（如 `4U8G、25G SSD`）变成一份 Azure 报价。实时价格来自
[Azure Retail Prices API](https://prices.azure.com/api/retail/prices)（无需密钥），
规格→机型（flavor）映射使用本地目录 `references/vm-catalog.json`。

同一套 `scripts/` + `references/` 可被三种 AI 编码工具复用：

| 工具 | 入口文件 |
|------|---------|
| Claude Code | `SKILL.md` |
| OpenAI Codex | `AGENTS.md` |
| GitHub Copilot | `.github/copilot-instructions.md` |

---

## 1. 环境要求

- **Python 3.9+**
- 依赖：`requests`
- 能访问 `prices.azure.com`（无需 Azure 账号 / API key）

```bash
pip install -r requirements.txt
# 或： pip install requests
```

验证：
```bash
python3 scripts/propose_flavors.py --vcpu 2 --ram 8
```
能打印出一张机型候选表即说明环境就绪。

---

## 2. 安装

### 2.1 作为 Claude Code skill（自动触发 + `/deviseur-azure`）

把整个 skill 目录复制到全局 skills 目录：

```bash
mkdir -p ~/.claude/skills/deviseur-azure
cp -R SKILL.md scripts references ~/.claude/skills/deviseur-azure/
```

重开一个 Claude Code 会话后，直接说「帮我报一个 4U8G、25G SSD 的 Azure 价」即可自动触发，
也可手动 `/deviseur-azure`。

> 注意：全局安装的副本与本仓库是两份拷贝。改了脚本要么重新 `cp`，要么直接在仓库里跑脚本。

### 2.2 作为 Codex 项目（`AGENTS.md`）

无需额外安装：Codex（CLI 或云端 agent）会自动读取仓库根目录的 `AGENTS.md`。
在该仓库里向 Codex 描述规格报价需求即可，它会运行 `scripts/` 下的脚本。

### 2.3 作为 GitHub Copilot 项目（`.github/copilot-instructions.md`）

无需额外安装：在 VS Code 用 **Copilot Chat 的 agent mode**（能执行终端命令）打开本仓库，
`.github/copilot-instructions.md` 会自动注入。普通行内补全只会参考说明、不会自动跑脚本。

---

## 3. 使用：两步工作流

报价始终是两步、交互式的——先选机型，再出报价。

### 第 1 步：提议机型（propose）

把规格拆成 vCPU 与内存（GiB）：`4U8G` → `--vcpu 4 --ram 8`。

```bash
python3 scripts/propose_flavors.py --vcpu 4 --ram 8 --region francecentral
```

输出一张跨家族（Burstable / General / Memory / Compute）的候选表，精确匹配项排在最前，
含 Linux €/小时、€/月、1 年预留 €/月。**从中选一个机型。**

### 第 2 步：整机报价（quote）

带上磁盘需求（`25G SSD` → `--disk-size 25 --disk-type premium-ssd`）：

```bash
python3 scripts/query_quote.py --sku Standard_D4as_v5 --region francecentral \
    --disk-size 25 --disk-type premium-ssd --os linux --qty 1
```

输出：VM 计算价表 + 托管磁盘 + 四种付费方式合计（按需 / Spot / 1 年预留 / 3 年预留）。

### 导出为 Markdown 文件

```bash
# 自动命名到 quotes/quote-<sku>-<region>-<date>.md
python3 scripts/query_quote.py --sku D4as_v5 --disk-size 25 --output

# 指定路径
python3 scripts/query_quote.py --sku D4as_v5 --disk-size 25 --output /tmp/quote.md
```

---

## 4. 参数速查

### propose_flavors.py
| 参数 | 默认 | 说明 |
|------|------|------|
| `--vcpu` / `-v` | 必填 | vCPU 数量 |
| `--ram` / `-m` | 必填 | 内存（GiB） |
| `--region` / `-r` | francecentral | Azure 区域 |
| `--currency` / `-c` | EUR | 货币代码 |
| `--max` | 6 | 最多候选数 |

### query_quote.py
| 参数 | 默认 | 说明 |
|------|------|------|
| `--sku` / `-s` | 必填 | 选定机型（自动补 `Standard_` 前缀） |
| `--region` / `-r` | francecentral | Azure 区域 |
| `--currency` / `-c` | EUR | 货币代码 |
| `--os` | linux | `linux` 或 `windows`（合计行用哪种 OS） |
| `--qty` / `-q` | 1 | 相同 VM 台数 |
| `--disk-size` | 无 | 磁盘大小 GiB（向上取整到档位） |
| `--disk-type` | premium-ssd | `premium-ssd` / `standard-ssd` / `standard-hdd` |
| `--output` / `-o` | 无 | 导出 Markdown；裸标志自动命名，或传 PATH。仍会回显屏幕 |

---

## 5. 定价口径（理解报价的关键）

- **Spot**：API 里被标成 `type=Consumption` 且 meter 名含 "Spot"（不是 `type=Spot`），脚本已正确处理。
- **预留（Reservation）**：`retailPrice` 是**整个周期的总价**，脚本已折算成有效时价/月价。
- **Linux 与 Windows+AHB**：计算价相同。
- **磁盘**：按**向上一档**计费（25 GiB → P4 = 32 GiB），无预留折扣。
- 月 = 时价 × 730；年 = 时价 × 8760。

---

## 6. 扩展

- 加机型（GPU N 系列、约束核机型等）：编辑 `references/vm-catalog.json`，补一行 `sku/family/vcpu/ram_gib`。
- 加磁盘档位：编辑 `references/disk-tiers.json`。
- 非 VM/磁盘的服务名映射：见 `references/service-mapping.md`。

> 改动行为时，请同步更新 `SKILL.md`、`AGENTS.md`、`.github/copilot-instructions.md` 三份说明。

---

## 7. 常见问题

| 现象 | 排查 |
|------|------|
| `ModuleNotFoundError: requests` | `pip install -r requirements.txt` |
| 价格全是 N/A | 该 SKU 在此 region 不可用；换 region，或确认 SKU 名拼写 |
| 连接超时 | 检查网络是否能访问 `prices.azure.com`（公司代理/防火墙） |
| Copilot 不自动跑脚本 | 需用 agent mode；普通补全不执行命令 |
| Claude Code 没触发 skill | 确认已复制到 `~/.claude/skills/deviseur-azure/` 并重开会话 |
