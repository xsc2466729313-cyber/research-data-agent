# Gold Set 草案审核说明

**当前状态（2026-08-29）：** 独立审核人 `xsc` 已把三表标为 `approved`，development 分册已冻结，见 `FROZEN.md` 与 `MANIFEST.json`。`goldset/templates/` 现为 held-out 正式考卷（不是本目录的拷贝）。正式实测 SDTI 63.36；本分册千问 LIVE 66.94 不得进正式栏。下面是当时的审核步骤，保留备查。

## 先分清三样东西

| 它叫什么 | 文件在哪 | 干什么 | 答辩怎么说 |
|---|---|---|---|
| **医学/质量规则** | `configs/medical_rules.yaml` 等 | 系统运行时的**守门**：2+ 不能自动变阳性、不能跨库拼患者 | 「Agent 怎么干活的约束」 |
| **Gold Set（这三张表）** | 本目录三个 CSV | 评测用的**标准答案/考题**：给定问题该找谁、原始值该标成什么、哪种错必须抓到 | 「阅卷答案，用来算找得准、整得真、改得对」 |
| **SDTI** | 公式在 `docs/06` | 用 Gold Set 对系统输出打的**综合分** | 「考完才有分；没冻结答案就不能报 SDTI」 |

所以：你觉得「全是规则」，是因为考题必须覆盖那些安全边界。**规则是法律，Gold Set 是考卷。** 法律写在 yaml 里，系统一直在用；考卷是用来检查系统有没有真的守法、有没有找对 GEO/cBio 队列。没有考卷，只能说「我们写了规则」，不能说「规则生效且可复现地得分」。

三张表各自考什么：

1. `retrieval_gold.csv`：这句话该不该检索到 GSE76360 / METABRIC……（找得准、找得全）
2. `field_gold.csv`：原始 `her2_ihc=2+` 标准答案是 Equivocal，不是 Positive（整得真）
3. `error_gold.csv`：如果系统把 2+ 写成 Positive，必须报错且不能自动修（改得对）

`e12` 那种「正确映射不应报错」是对照题，避免系统乱报警。

## 为什么先是乳腺癌，别的病怎么办

赛题和仓库定位就是**乳腺癌精准治疗科研数据**，总览写明第一版不追求全医学领域。不是系统只能处理乳腺癌，而是：

- **主链可复用**：需求合同、检索、解析、字段对齐、身份关联、质量门、闭环，换癌种不用重做 Agent。
- **领域包要换**：字段表、医学规则、Gold Set 考题要按病种重做（肺癌会有 EGFR/PD-L1，不会有 HER2 IHC 2+ 这套考题）。
- **已经在测的「其他东西」**：BEIR / Valentine / DeepMatcher / 清洗基准是通用数据能力，不是乳腺癌临床结论。

对外建议一句：领域落地在乳腺癌；方法是通用科研数据 Agent；其他癌种是换领域包和金标准，不是现在没做完的同一张 SDTI 考卷。

状态：development 分册已由 `xsc` 审核并冻结 checksum。这仍不是 `frozen_test`，也不是看板正式入口。正式入口已是 `templates/` 上的 official_candidate，正式 SDTI 63.36。development 上已有千问 LIVE 观察（`development-xsc-qwen-live-20260829`，见 `FROZEN.md`），不得填进看板正式栏。

初标来源：官方 accession 与项目文档中已写明的队列能力（GEO / GDC / cBioPortal / CIViC / ClinicalTrials.gov）。**不是**把网上别人的 benchmark 分数抄进来。

## 你在看板里看到的两个徽章是什么

- **Gold Set 正式栏**：看板读 `goldset/templates/` 上对本卷的观察分（当前 63.36）。development 已实测出分（见 `FROZEN.md` 的 66.94），也不得填进看板正式 SDTI。
- **Rule / Qwen / Full Agent 矩阵未填分**：那是五套系统对照，不是这一次 development 单次观察。现在填任何数字都是造假，所以保持空。

## 你只需要做什么

打开下面三个 CSV（Excel 可直接打开，保存时用 UTF-8）：

| 文件 | 行数含义 | 你怎么审 |
|---|---|---|
| `retrieval_gold.csv` | 某科研问题该不该检索到某数据集 | `label` 是否同意；不同意就改 `relevant`/`not_relevant`，或整行 `review_status=rejected` |
| `field_gold.csv` | 原始字段/值应标准化成什么 | 核对 `canonical_field/value`；`allowed_auto_transform=false` 的（尤其 IHC 2+、CNA）不要改成可自动 |
| `error_gold.csv` | 哪些错必须检出、能不能自动修 | 高风险必须 `auto_repair_allowed=false` |

每行当时从 `pending` 改起。当前已全部 `approved` 并冻结，不要再跑 `build_draft.py`。

- 同意：改成 `approved`
- 不同意：改成 `rejected`，并在 `notes` 写原因
- 不确定：保持 `pending`

**请不要**把整张表一次性全改成 `approved` 而不看高风险行。至少逐条看：

1. `f04` / `e01`：HER2 IHC 2+ 不得变成 Positive  
2. `f12` / `e02`：ERBB2 CNA ≠ HER2 IHC 阳性  
3. `e03` / `e16`：跨研究同号不得合并  
4. `e04`：细胞系 AUC 不得写成患者 pCR  

## 审完之后告诉我

1. 三个文件已保存  
2. 你的审核署名（将作为 `independent_reviewer`；初标署名为本草案生成器，不能和你同名）  
3. 是否还有要改的行  

然后我才会：核验官方链接、写冻结 manifest、跑 SDTI。在那之前看板仍应显示未冻结。

## 不要把本目录拷进 `goldset/templates/`

`templates/` 只允许 held-out `official_candidate`。本 development 草案不得再写入正式入口。
