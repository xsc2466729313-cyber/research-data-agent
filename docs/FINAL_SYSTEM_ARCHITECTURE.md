# 乳腺癌科研数据智能体：系统架构图

## 总体架构

```mermaid
flowchart LR
  U[研究者
  宽泛方向或科研问题] --> UI[本地 Web 工作台
  规划页 / 数据页 / 评测页]
  UI --> API[FastAPI
  127.0.0.1:8000]
  API --> PLAN[研究问题理解
  PICO/PECO + Research Contract]
  PLAN --> LIT[文献与 RAG
  Europe PMC / BEIR 查询理解]
  PLAN --> BROKER[Source Broker
  数据源候选 / 字段覆盖 / JoinPolicy]
  API --> LOOP[两轮闭环控制器
  诊断 -> 补充检索 -> 指标对比]
  LOOP --> AGENT[研究数据 Agent
  Qwen / 兼容模型 + Function Calling]
  AGENT --> ADAPTERS[GDC | GEO | cBioPortal
  ClinicalTrials.gov | CIViC]
  ADAPTERS --> NORM[Canonical Schema
  raw_field/raw_value/source_id]
  NORM --> LINK[患者-样本关联
  低置信度 unresolved/review]
  LINK --> SAFE[独立安全层与质量门
  医学规则 / 冲突 / 证据 / 发布判定]
  SAFE --> OUT[患者/样本级数据集
  字典 / Evidence / CSV-Parquet-Excel]
  API --> EVAL[统一评测
  BEIR / BGE / 消融 / 模型对比]
  EVAL --> REPORT[指标摘要与最终报告
  不把检索层指标冒充 SDTI]
```

## 责任边界

| 层 | 主要职责 | 不允许做的事 |
| --- | --- | --- |
| 模型层 | 理解问题、生成结构化计划、选择工具 | 直接写入患者事实或绕过安全层 |
| 数据适配层 | 从官方公开接口取得数据并登记来源 | 用猜测补齐不存在的记录 |
| 标准化/关联层 | 字段映射、原始值保留、患者/样本匹配 | 低置信度自动合并 |
| 安全与质量层 | HER2、response_domain、证据和发布门控 | 用模型自评替代 Gold Set |
| 评测层 | 在固定数据和脚本上计算指标 | 读取 test qrels 调参或伪造成绩 |

## 本地绑定与数据持久化

- 前端：`http://127.0.0.1:8000/`；Swagger：`http://127.0.0.1:8000/docs`；健康检查：`GET /health`。
- 模型凭据优先放在本机 `.env`（该文件已被 Git 忽略），或通过 `POST /api/agent/qwen-sessions` 建立最长 2 小时的内存会话。浏览器后续只携带 `session_id`，不重复输入 API Key。
- 公开评测语料放在被忽略的 `data/benchmarks/`；运行目录放在被忽略的 `evaluation/public_benchmarks/runs/`。仓库只提交脚本、数据哈希、汇总 Markdown/JSON 和小型 smoke 产物。
- API Key、CSV 凭据、患者级下载文件、缓存和服务器日志不进入 GitHub。重新部署后通过 `.env.example`、脚本参数和 API 文档恢复连接。
