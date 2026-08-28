# 最终设计报告（2026-08-28）

## 结论先行

当前系统已经形成“问题理解 → 真实数据获取 → 标准化与患者/样本关联 → 医学安全门控 → 两轮闭环 → 可追溯导出”的可运行链路。Qwen-plus 是默认规划模型；会话接口支持 Qwen、DeepSeek 和 OpenAI-compatible provider。Qwen-plus 已在本机完成真实连接、鉴权和结构化 Agent 探测，见 `evaluation/model_integration_probe_20260828.json`。未配置的 provider 不产生分数。

公开 BEIR 的 BGE-small-en-v1.5 检索结果优于 tuned BM25；查询理解规则组在五任务宏平均没有提升。因此生产默认保留兼容路径，不能把局部 SciFact 改善解释为完整临床科研能力。

## 设计依据

1. 冻结接口和医学边界来自 `configs/canonical_schema.yaml`、`configs/medical_rules.yaml`、`configs/quality_rules.yaml`。
2. 查询理解消融遵循 `docs/QUERY_UNDERSTANDING_ABLATION.md`：A-E 共用语料、BM25 参数、top-100 和 test 计算方式；Qwen 缓存缺失时 C/D/E 为 `NOT_EVALUATED`。
3. 闭环遵循 `docs/CLOSED_LOOP_ITERATION.md`：默认两轮，第二轮问题包含第一轮指标、诊断和策略摘要，并保留输入/输出哈希及工具调用审计。
4. 正式 SDTI 仍受 `docs/06_评测指标与SDTI.md` 和人工 Gold Set 约束，本文不修改其公式。

## 模型整合方案

| 模型/接口 | 当前角色 | 证据状态 |
| --- | --- | --- |
| Qwen-plus | 默认中文科研问题理解、工具规划和摘要 | 已接入本地 FastAPI 与前端临时会话 |
| Qwen-max / Qwen-turbo | 可选同供应商对照 | 连接后才产生真实观测 |
| DeepSeek Chat / Reasoner | 可选兼容模型或独立评委 | 已有 provider/session 适配；本机本轮未配置独立 Key，因此未参与排名 |
| GLM 等 OpenAI-compatible 模型 | 外部评测或自定义端点 | 通过 `openai_compatible` provider 接入；未连接不计分 |
| BGE-small-en-v1.5 | 检索模型对照 | 五个 BEIR 任务已有真实检索层结果 |

模型只输出结构化 proposal；数据事实、患者关联、医学规则和发布判定由程序层完成。

## 本地 API 绑定

```powershell
Copy-Item .env.example .env
# 在 .env 中填入 DASHSCOPE_API_KEY、QWEN_BASE_URL、QWEN_MODEL
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

主要端点见 `docs/FINAL_FUNCTION_REPORT_20260828.md`。使用 `.env` 后，同一台本地服务的前端任务不需要反复输入凭据；临时会话方式适用于不希望写入环境文件的场景。

最终交付、证据边界和 GitHub 数据恢复方式见 `docs/FINAL_DELIVERY_INDEX_20260828.md`。
