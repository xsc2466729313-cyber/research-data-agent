# V3.1 Phase 0 输出契约

- 盘点日期：2026-09-05
- 用途：后续旁路模块不得减少或改写这些输出约束
- 依据：`configs/canonical_schema.yaml`、`backend/app/models.py`、`EvidenceBuilder`、`QualityGateBuilder`、`AgentDatasetExportService`

后续 v30 可以**新增**图快照或 Copilot 回复，但不能**替换**本契约中的主表、追溯字段、质量门和导出入口。

## 1. 主表来源

主科研数据集只能来自现有执行引擎可解析的真实来源结果，不能由模型直接生成患者/样本行。

当前可建成主表或 companion 表的路径：

- NCBI GEO Series Matrix（`search_geo` / `GEOAdapter`）
- cBioPortal 临床 + 分子透视（`search_cbioportal` / `CBioPortalAdapter`）
- DepMap 细胞系表（仅 `response_domain=preclinical_cell_line`，不得当患者主表）

GDC、AACT、CIViC、Europe PMC、BioSample 提供来源/关系/证据，不自动变成跨库患者主表。

不同研究的队列只能作为独立表或 companion 表。禁止凭同名 `patient_id` 跨 GDC / GEO / cBioPortal 合并。

## 2. source_id

- CanonicalRecord 与 SourceItem 必须带非空 `source_id`。
- 外部数据必须能回到真实入口（官方 URL、accession、项目/研究编号）。
- 无 `source_id` 的记录不得作为可发布事实。
- 关键字段缺少来源时，规则侧阻断发布（`MISSING_EVIDENCE` / provenance 检查）。

## 3. raw_field 与 raw_value

冻结 Canonical Schema 要求标准化后仍保留：

- `raw_field`：原始列名或原始特征名
- `raw_value`：原始值

`CanonicalRecord` 将二者标为必填。后续对齐只允许增加映射，不允许丢掉原始字段。

HER2 IHC 2+ 的原始值不得被自动写成 `her2_status=Positive`。该约束同时写在模型校验与 `medical_rules.yaml`。

## 4. Evidence

`EvidenceCell` 至少包含：

- `evidence_id`
- `field`
- `canonical_value`
- `raw_field` / `raw_value`
- `source_id`
- `confidence`
- `status`（如 verified / review / unverified）

Evidence 由 `EvidenceBuilder` 从已映射记录生成。新 Agent 可以引用 `evidence_id`，不得另造一套无 raw 的“证明”。

前端 Evidence Drawer 与 `/api/v3/evidence/field/{record_id}/{field}` 只展示或回查上述追溯，不改写主表。

## 5. Quality 状态

并存两套相关枚举，后续不得混用或删减：

| 层 | 取值 | 位置 |
|---|---|---|
| SafetyGate | `PASS` / `REVIEW` / `FAIL` | `backend/app/models.py` |
| QualityAgent | `READY` / `REVIEW` / `FAIL` | `backend/app/agent/quality_agent.py` |
| QualityGate 四层总评 | `PASS` / `REVIEW` / `REJECT` | `QualityGateBuilder` |
| 单层 decision | `PASS` / `REVIEW` / `REJECT` | `QualityGateLayer` |

四层质量门：

1. 来源可信
2. 字段质量
3. 实体/身份
4. 科研适用性

`publish_allowed` 仅在总评为 `PASS` 且主表行数大于 0 时可为真。模型自评不能把它改成真。

Gold Set 观察成绩即使很高，只要考卷未 sealed 或任务为 REVIEW，仍须保持 `publish_allowed=false` 的诚实口径。这是评测纪律，不是输出格式。

## 6. PASS / REVIEW / FAIL

对外产品语言应对齐：

- **PASS / READY**：来源、字段、身份和适用性均达到门内阈值，且允许发布检查通过。
- **REVIEW**：可返回数据包，但必须人工或继续补搜；不得宣传为正式发表结论。
- **FAIL / REJECT**：阻断发布。缺 Evidence、非法冻结字段值、高风险医学语义等可走此路。

细胞系 AUC/IC50 不得解释为患者 pCR。跨域 response 必须保留 `response_domain`。

## 7. CSV / Excel / Parquet 输出

导出入口：`GET /api/agent/tasks/{task_id}/export/{file_format}`

`AgentExportFormat` 当前取值：

- `csv`
- `parquet`
- `xlsx`
- `json`
- `metadata`
- `quality_report`

Excel（xlsx）当前 sheet 至少包括：

- 科研数据集（主表）
- 独立来源 companion 表（按 study_key）
- 字段字典
- 可科研性报告
- 数据来源
- 研究设计
- 队列构建
- 搜集智能体
- 比赛报告

后续新增 sheet（例如证据图快照）可以追加，不得删除或改名导致旧对照脚本找不到“数据来源 / 可科研性报告 / 科研数据集”。

CSV / Parquet 输出主表行；metadata 与 quality_report 输出任务级说明，不替代来源审计字段。

## 8. 后续对照检查表

每个 Phase 结束后至少确认：

1. 主表行仍能指出 Adapter / DatasetBuilder 来源
2. 抽检字段仍有 `source_id` + `raw_field` + `raw_value`
3. companion 表仍独立，不出现跨研究患者拼接
4. 质量门枚举仍是上表集合
5. 旧导出路径仍可用，旧 sheet 仍在
6. 评测仍读 `goldset/templates/`，公式文档无 diff
