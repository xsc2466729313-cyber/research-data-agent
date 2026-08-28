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

## 不重复输入本地凭据

服务读取项目根目录、被 Git 忽略的 `.env`。复制 `.env.example` 后填入 `DASHSCOPE_API_KEY`、`QWEN_BASE_URL` 和 `QWEN_MODEL`，再以 `python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000` 启动；同一台本机的前端和 API 请求会复用服务配置，不需逐任务提交 Key。

不希望写入 `.env` 时，先调用 `POST /api/agent/qwen-sessions`。该端点在内存创建会话并返回 `session_id`；后续 `/api/agent/tasks` 或闭环请求只传该 ID。会话最长保留两小时，重启后失效，Key 不进入任务结果、日志或 GitHub。

```json
{
  "question": "整理乳腺癌患者的 ERBB2 相关临床特征、突变信息和样本级证据",
  "use_qwen": true,
  "allow_deterministic_fallback": true,
  "data_mode": "live",
  "max_sources": 3,
  "max_records": 500
}
```

生产部署请经 HTTPS 反向代理暴露服务；默认仅绑定本机 `127.0.0.1`。完整端口、Docker 前端地址、GitHub 缺失数据恢复与安全边界见 `docs/FINAL_DELIVERY_INDEX_20260828.md`。

## 不会随 GitHub 一起提交的内容

- API Key、业务空间凭据和 `.env`；
- `data/benchmarks/` 中的 BEIR 原始语料及下载压缩包；
- `evaluation/public_benchmarks/runs/` 的重复逐查询运行目录；
- 患者级导出文件、运行日志和本地缓存；
- 未完成的 Qwen/DeepSeek/GLM 结果不会生成占位分数。

这些内容都可以由脚本、来源 URL、SHA-256 清单和 API 参数重新生成。提交到仓库的是代码、测试、配置模板、报告和汇总指标。
