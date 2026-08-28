# 赛道二方向 1A 提交材料草案（P1-P20）

> 版本：2026-08-29。本文依据《赛道二-方向1A-科学数据查找解析与整合-提交要求及模板》整理。
> “本项目”指乳腺癌精准治疗科研数据智能体；“对照组”指本项目在相同公开任务上重跑的基线；“外部方法”指尚未在相同条件重跑的其他项目或模型。

## P1 项目名称与场景

乳腺癌精准治疗科研数据智能整合系统。面向“研究问题到可分析数据”的场景：研究者输入自然语言问题，系统查找真实公开数据，解析表格和接口结果，统一字段，保留原始值与来源，并输出可复核的数据包。

## P2 科研痛点

乳腺癌临床、组学、治疗响应和证据数据分散在不同数据库；同一概念的字段名、检测维度和结局定义并不一致。直接拼接会造成患者错配、HER2 语义混淆和响应域混淆，因此系统把模型规划、数据获取和安全发布分开。

## P3 输入与输出

输入：自然语言科研问题、可选数据库和字段约束。输出：`research_spec`、候选来源、标准化科研数据集、字段字典、`source_manifest`、Evidence、质量门、修复日志和 CSV/Parquet/Excel 导出。

## P4 总体架构

```mermaid
flowchart LR
  Q[科研问题] --> P[Qwen 结构化规划]
  P --> B[来源路由与受控 Adapter]
  B --> N[Canonical Schema / raw 值保留]
  N --> S[医学规则与 Quality Gate]
  S --> O[数据集 + Evidence + 报告]
  O --> F[缺口诊断]
  F --> B
```

千问是比赛主链的基座模型，生产 Agent 与两轮闭环均固定使用千问。DeepSeek 只在独立消融中替换中间规划/工具选择智能体，绝不进入生产会话。

## P5 模型与职责边界

Qwen-plus 负责研究问题结构化、函数调用工具选择和数据层总结；GDC、GEO、cBioPortal、ClinicalTrials.gov/AACT、CIViC Adapter 负责真实数据；Schema、医学规则、来源审计和发布门控由程序执行。模型不能写入未经来源验证的患者事实。

## P6 数据来源

支持的主要官方来源包括 GDC/TCGA-BRCA、NCBI GEO、cBioPortal、ClinicalTrials.gov/AACT 和 CIViC。来源记录包含 `source_id`、官方 URL、accession、状态、checksum（可用时）和原始字段。不同研究入口默认保持独立，不因相同字符串患者编号自动合并。

## P7 解析与整合

当前真实链路已验证接口 JSON、GEO Series Matrix、cBioPortal 临床/突变/CNA 表。系统将患者/样本、治疗响应、药物实验、临床试验和知识证据分成不同逻辑表，并通过 `response_domain` 区分患者临床、细胞系、临床试验和知识证据。

当前未完成的解析能力：通用用户上传 CSV/Excel/PDF 的完整生产链、PDF 表格/图像 OCR、图表数字化。提交材料中不把这些能力写成已完成。

## P8 标准 Schema 与医学安全

冻结 `configs/canonical_schema.yaml`，标准化后保留 `raw_field` 和 `raw_value`。执行以下硬规则：HER2 IHC 2+ 不自动判阳性；ERBB2 CNA amplification 不等同 HER2 IHC positive；低置信度患者/样本关联进入 `review/unresolved`；高权威冲突不自动选边；AUC/IC50 与临床 response 不跨域解释。

## P9 典型任务

示例问题：“HER2 阳性乳腺癌中 PIK3CA 突变与新辅助治疗响应的关系”。系统可从 GSE76360 解析基线样本和响应注释，并从 cBioPortal 等来源取得临床/分子候选。每个字段都能回到来源项和原始值；跨研究患者级拼接不会被自动执行。

## P10 两轮闭环

第一轮保存完整输入、工具调用、数据概要、缺失字段和 Evidence 缺口。第二轮只根据第一轮诊断生成补充检索，固定最多两轮（兼容接口可关闭）；若没有可验证改进或触发安全门，保留 `REVIEW` 并停止。闭环进度分只用于任务内反馈，不冒充 SDTI。

## P11 质量反馈与修正

低风险药物/基因别名、大小写和精确重复可自动修复；患者身份、医学语义、关键来源冲突和缺失证据进入审核。修复前后值、规则命中、Evidence 和再次验证结果写入 repair log。

## P12 评价指标

正式 Retrieval Precision/Recall/F1、Faithfulness、Traceability、Error F1、Repair Accuracy 和 SDTI 公式以冻结文档为准。正式乳腺癌 Gold Set 尚未冻结，因此这些正式指标目前统一标记为 `NOT_EVALUATED`，不使用内部诊断分填充。

## P13 本项目已完成的公开对照

以下是本项目在相同公开任务上重跑的“对照组/实验组”，不是外部模型排名：

| 能力 | 对照组（本项目基线） | 实验组（本项目方案） | 结果 |
|---|---|---|---:|
| 科学检索 | 调参 BM25 | **BGE-small-en-v1.5** | **nDCG@10 0.3966 vs 0.3376，+17.5%** |
| 字段对齐 | Token Jaccard | **值分布画像 V2** | **F1 0.8451 vs 0.6882，+22.8%** |
| 实体关联 | 标题 Jaccard | **学习规则 V2** | **F1 0.7408 vs 0.5577，+32.8%** |

这些指标分别来自 BEIR、Valentine 和 DeepMatcher，证明的是模块通用能力，不是乳腺癌临床效果。

## P14 消融实验

消融只改变一个本项目模块：规则查询改写 + RRF 相对原始查询 + BM25 的 nDCG@10 变化为 `-0.000014`，且延迟增加 61.49 ms；字段对齐 V3 F1 `0.7994` 低于 V2 `0.8451`；实体关联 V3 F1 `0.5579` 低于 V2 `0.7408`。因此当前默认保留 BM25 回退、V2 字段对齐和 V2 实体关联。公开消融不等同正式医学 Gold Set 消融。

## P15 模型对比：当前真实状态

此前没有完成“将中间智能体从 Qwen 替换为 DeepSeek”的同条件消融。历史 `comparison.json` 是旧的 DeepSeek Judge 小样本审阅，不是中间智能体替换实验；Qwen 探测只证明连接、鉴权、函数调用和结构化输出可用。

现已新增 `scripts/run_planner_replacement_ablation.py`：生产路径固定 Qwen；独立消融路径只替换中间规划/工具选择智能体为 DeepSeek。两种输出使用相同题集、预算和轮数，并统一由 Qwen 评审。

运行前必须由用户轮换已暴露的 DeepSeek Key，并将新密钥放入本地忽略文件：

```powershell
python scripts/run_planner_replacement_ablation.py --repeats 3 --data-mode live --allow-provisional
```

在真实凭据和冻结题集运行前，替换中间智能体后的指标变化仍是 `NOT_EVALUATED`。运行器只写入不含密钥的消融结果；Qwen 评审分只作辅助诊断，不替代人工 Gold Set。

## P16 对照组、实验组、外部方法的区分

- 对照组：本项目重跑的 BM25、Jaccard、无结构化规划等基线。
- 实验组：本项目 BGE、字段对齐 V2、实体关联 V2 和完整 Agent。
- 外部模型消融：DeepSeek 只替换中间规划/工具选择智能体；必须在同题集、同预算、同脚本、至少三次重复后报告相对变化。本轮没有可比结果，不填宣传数字。

## P17 当前缺点与风险

1. 正式乳腺癌 Gold Set、Error Gold Set 尚未冻结，无法给出正式 SDTI。
2. DeepSeek 替换中间智能体的同条件重复消融尚待新凭据和冻结题集完成。
3. 研究相关性和分析充分性受关键结局、分子变量覆盖限制；质量门可能保持 `REVIEW`。
4. PDF 表格/图像 OCR、用户上传文件的完整生产链尚未达到可宣称状态。
5. 公开 benchmark 与乳腺癌患者身份、临床疗效并不等价；V2Plus 仍是候选安全层，尚未在独立乳腺癌 validation 集切换默认。

## P18 复现与 API

- 后端：`http://127.0.0.1:8000`；Swagger：`/docs`；健康检查：`GET /health`。
- 创建生产临时会话：`POST /api/agent/qwen-sessions`，使用 Qwen 的 `api_key`、`base_url`、`model`；返回 `session_id`，密钥只在进程内存保存。DeepSeek 不允许用于生产会话。
- 执行任务：`POST /api/agent/tasks`，提交 `question`、`qwen_session_id`、`data_mode`、`max_sources`、`max_records` 等。
- 两轮闭环：`POST /api/v2/agent/closed-loop`；查询：`GET /api/v2/agent/closed-loop/{loop_id}`。

本机可在 `.env` 中配置 Qwen，在 `evaluation/deepseek.local.env` 中配置仅供独立消融的 DeepSeek；这些文件已加入 `.gitignore`，不提交 GitHub。

## P19 GitHub 可恢复内容

GitHub 保留代码、配置模板、官方来源 URL、脚本、测试、无密钥汇总和复现命令。`.env`、API Key、凭据 CSV、患者级导出、缓存、BEIR 原始语料、逐运行目录和日志不提交。部署者按报告命令重新配置本地 env 并运行 Adapter/评测脚本即可恢复。

## P20 结论与证据边界

项目已经形成“科研问题 → 多源查找 → 解析整合 → 来源审计 → 医学安全 → 两轮闭环 → 可下载输出”的可运行链路。**本项目在公开检索、字段对齐和实体关联任务上有可复现实测结果**；Qwen 已完成真实接入探测。**正式乳腺癌质量指标和 DeepSeek 中间智能体替换消融尚未完成**，这是当前最重要的补测项。提交时应把已完成能力、对照关系和未完成边界同时展示，避免把模块分数写成临床结论。
