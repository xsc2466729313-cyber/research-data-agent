# 系统设计报告（2026-08-30）

## 1. 设计目标

系统把“科研问题”变成“可复用科研数据包”，设计目标包括：真实来源、字段级审计、安全关联、医学语义隔离、质量闭环和可复现评测。设计上把概率模型与确定性治理分开，避免模型输出直接成为事实或发布判定。

## 2. 总体架构

![系统技术架构](images/system-architecture-v3.png)

系统由 FastAPI 统一提供 API 与静态前端。后端按领域拆为研究规划、来源发现、数据 Adapter、解析、标准化、融合、Evidence、质量、修复、评测和导出模块。前端提供规划五阶段、数据表、Evidence Drawer、质量看板、闭环审计和导出入口。

## 3. 关键模块设计

| 模块 | 设计职责 | 输入 | 输出 |
|---|---|---|---|
| Requirement/Research Planning | 从自然语言形成 PICO/PECO 与冻结研究契约 | 科研方向或问题 | ResearchSpec、Research Contract |
| Source Broker | 依据字段覆盖、权威性、粒度和 JoinPolicy 组合来源 | Research Contract、能力目录 | Source Plan、候选来源、Gap |
| Adapters/Parsers | 调用真实公开接口并解析 JSON/表格/Series Matrix | accession、URL、查询参数 | RawSourceRecord、来源审计 |
| Normalization | 对齐冻结 Canonical Schema，保留原始字段和值 | 原始记录 | CanonicalRecord、映射证据 |
| Integration | 在同研究命名空间关联患者/样本，检测冲突 | CanonicalRecord | MergedRecord、LinkDecision |
| Evidence/Governance | 字段级来源、冲突、置信度和审计 | 标准记录、来源信息 | EvidenceCell、Provenance |
| Quality/Repair | 四层质量门、确定性修复、人工审核队列 | 数据集、契约、Evidence | PASS/REVIEW/FAIL、Repair Log |
| Goal Loop | 根据字段、结局域、来源和身份缺口换方法 | 第一轮结果与 Gap | 补搜请求、第二轮结果、停止原因 |
| Evaluation | Gold Set 与公开基准统一计算 | 预测、真值、运行元数据 | metrics.json、报告、图表 |

## 4. 端到端状态流

![端到端流程与质量闭环](images/system-workflow-v3.png)

1. 用户输入研究方向，系统生成候选问题和研究契约。
2. Source Broker 形成来源组合，Adapter 只执行已注册工具。
3. 解析层保留原始记录和来源，标准化层生成统一字段。
4. 实体层在 `study_id` 命名空间内建立患者/样本关系。
5. Evidence 和质量门检查身份、结局域、分子覆盖与来源完整性。
6. 不满足时，Gap Diagnosis 决定补响应队列、分子队列、临床表或文献证据。
7. 有合法未尝试策略则进入第二轮；否则输出当前最佳数据包与 REVIEW/GAP。

## 5. 四层质量门

| Gate | 检查内容 | 失败处理 |
|---|---|---|
| G1 身份与主表 | patient/sample 能否可靠定位 | 低置信度进入 unresolved，不自动合并 |
| G2 结局域匹配 | 问题结局与数据结局是否同域 | 禁止用生存或细胞系药敏替代患者响应 |
| G3 分子覆盖 | 目标变量是否在同队列或有可靠 crosswalk | 独立队列保留，不伪造患者级 Join |
| G4 证据与安全 | 来源、原始值、冲突、医学规则是否完备 | REVIEW/FAIL，阻止自动发布 |

## 6. API 与会话安全

- 本地入口：`http://127.0.0.1:8000/`；Swagger：`/docs`；健康检查：`/health`。
- API Key 只放本机 `.env` 或最长 2 小时的内存会话，不写入前端、报告或 Git。
- 浏览器后续只携带 `session_id`，服务端不把 Key 回传。
- 生产部署应使用 HTTPS、反向代理、访问控制和共享状态存储；当前 SQLite/内存会话适合单实例演示。

## 7. 冻结接口与变更纪律

`configs/canonical_schema.yaml`、`configs/medical_rules.yaml` 与 `docs/06_评测指标与SDTI.md` 是发布边界。任何变更必须先提交 `CHANGE_REQUEST.md`，说明理由、影响、迁移与测试；本次整理未修改这些冻结内容。

## 8. 复现设计

仓库保存脚本、配置、Gold Set manifest/checksum、评测 JSON 和图表。大体量公开基准语料、缓存、运行日志与密钥由 `.gitignore` 排除。README 给出本地启动、Docker、测试和公开基准复现入口，确保克隆后可按同一口径运行。
