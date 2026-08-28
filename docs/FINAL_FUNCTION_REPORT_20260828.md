# 最终功能报告（2026-08-28）

## 评委主路径

1. 打开 `http://127.0.0.1:8000/`，输入研究方向。
2. 系统先生成文献依据、候选问题、研究方案和数据源计划。
3. 点击生成数据集后，默认进行两轮研究：第一轮形成数据和缺口，第二轮基于反馈补充检索并比较指标。
4. 结果页首屏展示状态、矩阵规模、质量门、证据和闭环改进；技术日志、候选登记和原始字段审计放在可展开区域。

## API 输入与输出

| 方法 | 路径 | 输入重点 | 输出重点 |
| --- | --- | --- | --- |
| GET | `/health` | 无 | 服务状态和版本 |
| POST | `/api/agent/qwen-sessions` | `provider`、`api_key`、`base_url`、`model`、可选 `workspace_id` | 内存 `session_id` 和过期时间 |
| DELETE | `/api/agent/qwen-sessions/{session_id}` | 路径参数 | 删除会话 |
| POST | `/api/agent/tasks` | `question`、`data_mode`、`use_qwen`、`qwen_session_id`、来源/记录上限 | 单轮 `AgentTaskResult` |
| POST | `/api/v2/agent/closed-loop` | `initial_request`、`max_iterations`、`require_two_rounds=true` | 两轮结果、诊断、指标和审计 |
| GET | `/api/v2/agent/closed-loop/{loop_id}` | 路径参数 | 已保存闭环结果 |
| POST | `/api/v2/retrieval/search` | query、documents、显式查询理解模式 | 检索排名、RRF、延迟和审计遥测 |
| POST | `/api/v2/research/plan` | topic 或研究问题 | PICO/PECO、Evidence Pack、变量和 Source Plan |
| POST | `/api/v2/governance/decide` | proposal、证据和医学语义 | `AUTO` / `REVIEW` / `REJECT` |
| POST | `/api/evaluation/model-tests/generate` | 问题数量、模型目标、`run_mode` | 统一模型测试计划 |
| POST | `/api/evaluation/model-tests/run` | `report_id`、各目标 `session_ids` | 真实结构化输出指标 |

## 不会随 GitHub 一起提交的内容

- API Key、业务空间凭据和 `.env`；
- `data/benchmarks/` 中的 BEIR 原始语料及下载压缩包；
- `evaluation/public_benchmarks/runs/` 的重复逐查询运行目录；
- 患者级导出文件、运行日志和本地缓存；
- 未完成的 Qwen/DeepSeek/GLM 结果不会生成占位分数。

这些内容都可以由脚本、来源 URL、SHA-256 清单和 API 参数重新生成。提交到仓库的是代码、测试、配置模板、报告和汇总指标。
