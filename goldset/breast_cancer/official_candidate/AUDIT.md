# 正式考卷候选：审核清单

**状态：xsc 于 2026-08-29 审核通过并写入 `goldset/templates/`。`copied_to_templates=true`，`frozen=false`，不是 `frozen_test`。已对本卷跑正式评测 `official-candidate-20260829T132222Z`，SDTI = 63.36，`publish_allowed=false`。**

审核授权原句：「审核通过，写入正式入口 署名xsc」。题面与金标准行来自本 held-out 候选卷，没有把 `development/` 拷进 templates。

---

## 这份卷在哪

| 文件 | 行数 | 考什么 |
|---|---:|---|
| `goldset/breast_cancer/official_candidate/retrieval_gold.csv` | 50 | 这句话该不该检索到某数据集（找得准 / 找得全） |
| `goldset/breast_cancer/official_candidate/field_gold.csv` | 26 | 原始字段/值应标准化成什么（整得真） |
| `goldset/breast_cancer/official_candidate/error_gold.csv` | 18 | 哪些错必须检出、能不能自动修（改得对） |
| `MANIFEST.json` | — | 分册元数据；`copied_to_templates=true`，`frozen=false`，审核人 xsc |

列格式与 `goldset/templates/`、加载器 `GoldSetCsvLoader` 完全一致。`review_status` 已全部为 `approved`。Excel 若再改，请另存为 **UTF-8（带 BOM 亦可）**。

看板正式格读的是 `goldset/templates/`。正式卷已写入，并已对本卷跑 `gold_set` 评测（SDTI 63.36，安全门 FAIL）。development 分册上的千问 LIVE 观察（含 66.94）**禁止**填进正式栏。

---

## 为什么不能把 development 直接「考进去」

`goldset/breast_cancer/development/`（`breast-cancer-development-20260829`）已经用来：

- 跑千问 LIVE Agent，得到非正式 SDTI 观察；
- 据此改检索种子、DepMap 工具、任务内闭环补搜。

同一套题再当正式 Gold Set = **用练习册当期末考**。系统已经见过题面和金标准，成绩不可信。

正式考卷必须是 **held-out**：

- 题面（`research_question`）不得整句复制 development；
- 金标准行（`question_id` / `case_id` 与对应 gold 行）不得整份复制；
- 可以用同一批公开真实队列（GSE76360、METABRIC、TCGA-BRCA 等），但必须换提问角度或换题；
- 本卷另外用了 development 金标准里没当正例写进去的公开编号：`GSE50948`、`NCT01104584`。

本目录是 **official_candidate**，已写入看板正式入口 `goldset/templates/`，仍不是 sealed `frozen_test`。

---

## 你怎么审（总规则）

打开三个 CSV（Excel 可直接打开）：

- 同意：该行 `review_status` 改为 `approved`
- 不同意：改为 `rejected`，并在 `notes` 写原因
- 不确定：保持 `pending`

**请不要**整表一键全改成 `approved`。至少逐条勾选下面清单。高风险行（IHC 2+、CNA、身份合并、细胞系当 pCR）不得把 `allowed_auto_transform` / `auto_repair_allowed` 改成可自动。

初标署名是 `official-candidate-draft-builder`，不能和独立审核人同名。

---

## 检索题逐题勾选

每题核：正例 accession 是否真实、负例是否合理、题面是否与 development 整句重复。

| 勾选 | 题号 | 题意（摘要） | 建议正例 | 建议负例 | 你要核的点 |
|---|---|---|---|---|---|
| ☑ | oc01 | 只要化疗队列的患者级 pCR 注释 | GSE25066 | GSE76360、METABRIC、DepMap、CIViC | 不要因为「也有 pCR」就把 HER2 靶向系列当成本题正例 |
| ☑ | oc02 | HER2 术前靶向：基线注释 + 术后响应 | GSE50948、GSE76360 | GSE25066、DepMap、METABRIC | GSE50948 是否同意作为 held-out 正例；时间点不得拆成两名患者 |
| ☑ | oc03 | 同患者同时有 PIK3CA 与 PI3K 抑制剂响应 | breast_alpelisib_2020、brca_mskcc_2019 | GSE76360、METABRIC、CIViC | 禁止跨库贴突变 |
| ☑ | oc04 | ESR1/ER + 体细胞突变共存表，不要疗效 | METABRIC、TCGA-BRCA | GSE76360、DepMap、CIViC | 与 development「只问 PIK3CA」不是同一题 |
| ☑ | oc05 | 哪些队列能对照 IHC 与 ERBB2 CNA | TCGA-BRCA、METABRIC | GSE76360、CIViC、DepMap | 正例是「对照」，不是「合并成一个状态」 |
| ☑ | oc06 | ERBB2 文献级预测性证据 | CIViC | METABRIC、GSE76360、DepMap | 知识证据 ≠ 患者疗效 |
| ☑ | oc07 | 带公开结局测量的登记试验，落到 NCT | NCT01104584、AACT | GSE76360、GSE25066、DepMap | 打开 ClinicalTrials.gov 核对 NCT01104584 |
| ☑ | oc08 | 细胞系 IC50/AUC，分域 | DepMap | GSE76360、GSE25066、CIViC | 不得与患者 pCR 混为正例 |
| ☑ | oc09 | 受体字段筛患者 TNBC | TCGA-BRCA、METABRIC | GSE76360、DepMap | 细胞系不是患者 TNBC |
| ☑ | oc10 | SCAN-B 表达 + 临床特征 | GSE96058 | GSE25066、NCT01104584、CIViC | 不是新辅助 pCR 专用试验 |
| ☑ | oc11 | HR+/HER2- 临床分层 | METABRIC、TCGA-BRCA | GSE76360、DepMap | HER2 靶向 GEO 不得当主队列 |

官方入口（抽查即可，不要改编号）：

- GSE25066 / GSE76360 / GSE50948 / GSE96058 → `https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=...`
- METABRIC → `https://www.cbioportal.org/study/summary?id=brca_metabric`
- alpelisib 2020 / MSK 2019 → cBioPortal `study/summary?id=`
- TCGA-BRCA → `https://portal.gdc.cancer.gov/projects/TCGA-BRCA`
- NCT01104584 → `https://clinicaltrials.gov/study/NCT01104584`
- CIViC → `https://civicdb.org/`
- DepMap → `https://depmap.org/portal/`
- AACT → `https://aact.ctti-clinicaltrials.org/`

---

## 字段题：高风险必须看

其余行是别名、大小写、source_id、对照映射，可较快扫过；下面几条必须逐条。

| 勾选 | case_id | 标准答案要点 |
|---|---|---|
| ☑ | oc_f04 / oc_f05 / oc_f06 | `HER2 IHC score=2+` → `her2_status=Equivocal`，assay=IHC，保留 raw `2+`；`allowed_auto_transform=false`（status） |
| ☑ | oc_f10 / oc_f11 | `ERBB2_CNA=Amp` → gene=ERBB2，**不得**写成 her2_status=Positive |
| ☑ | oc_f18 / oc_f19 | DepMap `IC50` → `response_domain=preclinical_cell_line`，`response=IC50`，不得写成 pCR |
| ☑ | oc_f21 / oc_f22 | 身份字段示例 ID，禁止跨库自动对齐 |
| ☑ | oc_f01–oc_f03 | IHC 3+ 可以 Positive，但必须留 assay 与 raw |
| ☑ | oc_f16 / oc_f17 | 患者 pCR 的 domain 必须是 `clinical` |
| ☑ | oc_f20 / oc_f26 | 真实 `geo:GSE96058` / `nct:NCT01104584` |

`raw_field` / `raw_value` 必须保留；不要改成只有 canonical。字段映射用例里的患者/样本号（如 PT001）是**规则示例**，不是声称该队列里真有这个编号。

---

## 错误/修复题：医学红线必须看

| 勾选 | case_id | 必须成立 |
|---|---|---|
| ☑ | oc_e01 | IHC 2+ 写成 Positive → 必须检出；`auto_repair_allowed=false` |
| ☑ | oc_e02 | ERBB2 CNA 写成 IHC 阳性 → 必须检出；不可自动修 |
| ☑ | oc_e03 | 细胞系 IC50 当成患者 pCR → 必须检出 |
| ☑ | oc_e04 | `match_score=0.35` 自动合并 → unresolved |
| ☑ | oc_e05 / oc_e10 | 跨研究同号、无 crosswalk 的患者 Join → 禁止 |
| ☑ | oc_e09 / oc_e16 | 缺 source 或缺 raw_value → 不可发布 |
| ☑ | oc_e11 / oc_e12 / oc_e17 | 对照题：正确映射不应报错（用于 Error Precision） |
| ☑ | oc_e06 / oc_e07 / oc_e08 | 低风险别名/去重才允许自动修 |

---

## 审核结论（2026-08-29）

- 审核人：**xsc**
- 授权：「审核通过，写入正式入口」
- 已写入 `goldset/templates/`（retrieval 50 / field 26 / error 18）
- `gold_set_id`：`breast-cancer-official-candidate-20260829`
- `independent_reviewer` / `human_reviewer`：xsc
- **不是** `frozen_test`；`frozen=false`（来源复验、规则复验、checksum 冻结仍未做）
- 已对本卷采集系统观察并评分：`POST /api/evaluation/official-run` / `collect_official_sdti.py` → **SDTI 63.36**，`publish_allowed=false`
- development 千问 LIVE 观察（含 66.94）不得进正式栏

---

## 为什么仍不是 sealed 终考

- 正式入口 `goldset/templates/` 已有 held-out 行，并已对本卷跑出 SDTI 63.36。
- 评测使用 `allow_reviewed_unfrozen=True`，因为来源复验、规则复验与 `frozen=true` 仍未做；这不是 sealed `frozen_test`。
- 安全门 FAIL（Faithfulness < 90%；5 个高风险问题未解决）。数字见 `docs/DATA_REPORT_20260829.md`。
