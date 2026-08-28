# 乳腺癌候选 Gold Set 构建方案

> 状态：开发/验证候选任务包，不是冻结 Gold Set，不产生正式 SDTI 成绩。
> 版本：2026-08-29

## 1. 目标与边界

该方案解决正式 Gold Set 为空的问题：先以真实官方来源构造可审核的候选任务，再进行独立复核和冻结。它不把任何单一模型、脚本输出或公开 benchmark 标签直接当作乳腺癌真值。

候选条目进入正式评测前必须保留：`source_id`、官方 accession/URL、`raw_field`、`raw_value`、标注依据、审核人、审核状态和 checksum。字段规范、医学规则和 SDTI 公式均不在本方案中改动。

## 2. 来源项目池

| 来源 | 官方入口 | 候选用途 | 不可跨越的边界 |
|---|---|---|---|
| TCGA-BRCA / GDC | https://portal.gdc.cancer.gov/projects/TCGA-BRCA | 临床、突变、表达、拷贝数的来源与字段候选 | 不以 ERBB2 CNA 替代 HER2 IHC；不与其他研究患者编号拼接 |
| GSE76360 / GEO | https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE76360 | HER2 靶向治疗响应、ER/PR 与配对时间点候选 | 公开矩阵无 PIK3CA 时不得补造或跨库贴值 |
| GSE25066 / GEO | https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE25066 | 新辅助化疗响应的独立验证候选 | 仅按真实样本注释判断 response domain |
| METABRIC / cBioPortal | https://www.cbioportal.org/study/summary?id=brca_metabric | 独立临床与分子字段、字段映射候选 | 主要结局不是治疗响应时不得作为响应任务正例 |
| ClinicalTrials.gov / AACT | https://clinicaltrials.gov/data-api/api | 临床试验关系、试验结局与干预候选 | 每个入集试验必须有真实 NCT 编号及官方验证 |
| CIViC | https://civicdb.org/ | 变异-药物-疾病知识证据候选 | 仅接收已验证的具体 EID/官方记录；知识证据不等同患者疗效 |

## 3. 三个分层集合

| 集合 | 允许用途 | 建议规模 | 冻结规则 |
|---|---|---:|---|
| development | 调整提示词、适配器和 V2Plus 安全策略 | 30-50 个研究问题、约 300 对问题-数据集 | 可多次查看，不报告正式成绩 |
| validation | 选择阈值、决定是否启用融合候选 | 与 development 来源或问题独立 | 只用于选择，不能与冻结集混用 |
| frozen_test | 计算 Retrieval F1、Faithfulness、Traceability、Error F1、Repair Accuracy 与 SDTI | 与前两者独立 | 人工复核后生成 checksum；最终报告只运行一次 |

每一层都覆盖 HER2 阳性、HR 阳性/HER2 阴性、TNBC、混合/未知四种亚型；同时覆盖 clinical、preclinical_cell_line、clinical_trial、knowledge_evidence 四类 `response_domain`。

## 4. 必须纳入的负例与高风险例

- `HER2 IHC 2+`：只能保留 IHC 和原始值，自动路径不得判为 HER2 Positive。
- `ERBB2 CNA amplification`：与 HER2 IHC 分开记录，不能作为同义字段自动合并。
- 跨研究相同患者编号：应为 `REJECT` 或 `unresolved`，不得因编号相同合并。
- 同研究但样本编号冲突：不得自动链接。
- 细胞系 AUC/IC50 与患者 pCR/response：必须标明不同 `response_domain`，不能互作正例。
- METABRIC 分子信息但缺同域治疗响应：是“来源真实但任务不相关”的检索负例。

## 5. 审核流程

```text
官方来源验证
  -> 初标模型生成 provisional 候选
  -> 独立模型或人工第二审核
  -> 确定性 Schema/医学规则验证
  -> 分歧、高风险和低置信度进入 review queue
  -> 人工确认后写入对应 CSV
  -> 生成 checksum 并冻结
```

当前 DeepSeek 可以作为初标模型，但在用户完成密钥轮换并仅在本地忽略的环境变量中配置后才可调用。没有独立第二模型或人工审核时，其输出只能是 `provisional`，不能转入 `frozen_test`。

## 6. 与 V2Plus 融合的验证关系

V2Plus 不是把 V2/V3 在公开测试集上事后挑出“最好字段”重新拼分数。字段对齐保留 V2 的候选和评分；V3 只提供审计特征并阻断 ERBB2 CNA、HER2 IHC 2+ 与 response-domain 风险。实体关联保留 V2 候选；V3 特征、`PatientSampleLinker` 与显式患者/样本冲突决定是否降级或阻断。

是否把 V2Plus 设为默认，必须在 validation 集比较其安全阻断、人工复核负担及任务相关指标；frozen_test 仅用于最终一次结论。当前状态为 `CANDIDATE_NOT_DEFAULT`，不新增任何性能数字。

## 7. 可执行下一步

1. 从 GDC、GEO、cBioPortal、ClinicalTrials.gov 和 CIViC 为每类任务登记具体来源记录。
2. 先填充 development 模板，使用 `/api/goldset/sources/verify` 验证官方来源。
3. 初标和独立复核后运行 `/api/goldset/validate`；所有高风险字段保持人工审核。
4. 人工确认 validation 后，才判断 V2Plus 是否替代当前 V2 默认。
5. 最后冻结 CSV、清单和 checksum，运行正式 SDTI。
