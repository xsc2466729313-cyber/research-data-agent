# 框架说明报告（2026-08-30）

## 1. 框架定位

本系统是面向乳腺癌精准治疗科研的数据整合 Agent。输入是自然语言科研问题，输出是可分析、可追溯、带质量状态的数据包；系统不提供临床诊疗建议，也不允许模型直接生成患者事实。

一句话框架：**模型负责理解、规划和反思；公开数据源提供事实；确定性程序负责解析、标准化、关联和安全守门；Evidence 与 Gold Set 负责证明和评测。**

## 2. 五层框架

| 层级 | 核心职责 | 主要产物 |
|---|---|---|
| 交互与接入层 | 研究者输入、规划工作台、REST API、临时模型会话 | 科研问题、任务状态、导出请求 |
| 智能体编排层 | ResearchSpec、Research Contract、工具选择、Goal Loop | 结构化需求、工具调用、补搜计划 |
| 真实数据源层 | GDC、GEO、cBioPortal、AACT、CIViC、DepMap、Europe PMC | 带真实 accession/URL 的原始记录 |
| 处理与治理层 | 解析、Canonical Schema、医学归一化、实体关联、Evidence、质量门 | 标准记录、关联决策、冲突与 Gap |
| 科研输出层 | 分析矩阵、数据字典、来源清单、质量报告与评测 | CSV/Excel/Parquet/JSON/HTML |

![系统技术架构](images/system-architecture-v3.png)

## 3. 核心工作链

```text
科研问题
-> ResearchSpec / Research Contract
-> 数据源发现与字段覆盖规划
-> Adapter 真实取数
-> 原始记录解析并保留 source_id/raw_field/raw_value
-> Canonical Schema 与医学标准化
-> 患者/样本安全关联
-> Evidence、冲突与四层质量门
-> Gap Diagnosis
-> 第二轮补搜或停止
-> 数据包、质量报告与审计记录
```

闭环的目标不是“多跑一轮”，而是依据缺口换方法。需要患者 pCR 时，不允许用 OS/DFS 或细胞系 AUC/IC50 代替；找不到同队列 PIK3CA 与 response 的可靠 crosswalk 时，保持独立队列和 REVIEW。

## 4. 模型与程序边界

| 组件 | 可以做 | 不可以做 |
|---|---|---|
| Qwen | 解析科研问题、生成 ResearchSpec、选择已注册工具、总结缺口 | 修改冻结 Schema/医学规则、写入患者事实、绕过质量门 |
| 数据 Adapter | 调用公开接口、校验 accession、解析结构化响应 | 猜测来源、伪造缺失患者或字段 |
| Normalizer/Matcher | 字段映射、别名归一、同研究内实体关联 | 低置信度跨研究自动合并 |
| Safety/Quality | HER2、response domain、Evidence 和发布门控 | 为提高得分放宽红线 |
| Evaluation | 对冻结/审核样本计算指标并保存证据 | 用 development 或模型自评分冒充正式成绩 |

## 5. 数据治理原则

- 外部数据必须记录 `source_id` 和真实来源。
- 标准化结果必须保留 `raw_field` 与 `raw_value`。
- `study_id` 是患者/样本关联的命名空间，跨 study 无可靠 crosswalk 不自动 Join。
- HER2 IHC 2+ 保持 Equivocal/Review；ERBB2 CNA amplification 不等价于 HER2 IHC Positive。
- `clinical`、`clinical_trial`、`knowledge_evidence`、`preclinical_cell_line` 用 `response_domain` 分层。
- 高权威来源不可解释冲突保留双方 Evidence，进入人工复核。

## 6. 生产主链与扩展能力

当前生产主链采用 Qwen 规划、真实 Adapter、Schema/Entity V2、安全层、Quality V2、Critic/goal_loop 与两轮 closed-loop。V3 Matcher、公开 BEIR/Valentine/DeepMatcher、查询理解消融和模型替换实验用于能力诊断，不自动替换生产默认。

该框架的优势是端到端可追溯和医学边界明确；主要不足是正式 Retrieval、Faithfulness、Repair 尚未达到目标，跨队列患者级关联仍受公开数据覆盖限制。
