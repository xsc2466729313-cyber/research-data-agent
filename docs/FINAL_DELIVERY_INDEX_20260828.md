# 最终交付索引（2026-08-28）

## 结论与边界

本仓库交付的是可在本地运行的乳腺癌科研数据智能体，不是临床决策系统。模型只负责研究问题结构化、检索计划和工具选择；患者事实、标准化、医学安全、来源追溯和发布门控均由程序执行并接受测试。公开检索评测、闭环运行诊断和冻结 Gold Set 的正式指标是不同层次的证据，不能加总为 SDTI。

## 交付物

| 文件 | 内容 | 证据状态 |
| --- | --- | --- |
| `docs/FINAL_SYSTEM_ARCHITECTURE.md` | 模块边界、数据流、医学安全与部署接口 | 已实现 |
| `docs/FINAL_DESIGN_REPORT_20260828.md` | 模型整合策略、职责分离和技术取舍 | 已实现 / 有运行证据 |
| `docs/FINAL_FUNCTION_REPORT_20260828.md` | 前端主路径、端点、最小请求和本地绑定 | 已实现 |
| `docs/FINAL_INTEGRATED_REPORT_20260829.md` | 分层整合的设计、功能、公开评测、闭环、模型和对比说明 | 真实产物汇总，明确证据边界 |
| `evaluation/FINAL_EVALUATION_REPORT_20260828.md` | 检索横向对比、查询理解消融、闭环和模型状态 | 真实产物，分层说明 |
| `evaluation/PUBLIC_BENCHMARK_STRATIFIED_REPORT_20260828.md` | BEIR 逐数据集指标 | 真实重跑；FiQA 未纳入本轮宏平均 |
| `evaluation/planner_replacement_ablation_20260829/planner_replacement_ablation.md` | Qwen 对照组与 DeepSeek 中间智能体替换实验组 | 3 条 provisional 题目 × 每组 3 次；非正式排名 |

## 当前可据实陈述的结果

- **Qwen-plus 在本机完成连接、鉴权和结构化 Agent 探测**，产物为 `evaluation/model_integration_probe_20260828.json`；产物不含 API Key。
- 五个 BEIR 任务的历史完整检索运行中，**BGE-small-en-v1.5 的 nDCG@10 宏平均为 `0.3880`**，高于 tuned BM25 的 `0.3147`；仅代表检索层。
- 本轮重新运行 SciFact、NFCorpus、SciDocs、ArguAna，共 **3,029 个测试查询**。**BGE nDCG@10 宏平均 `0.3966`**，tuned BM25 为 `0.3376`。FiQA 因资源窗口未完成，没有纳入该平均。
- 五数据集查询理解 A/B 消融中，规则+RRF 未提高宏 nDCG@10 且增加延迟，因此生产默认保持 `compat`。Qwen C/D/E 缺少全量有效计划缓存，保持 `NOT_EVALUATED`。
- 两轮闭环具有输入/输出哈希和诊断审计。计划模式无真实数据时正确输出 **REVIEW 与零覆盖**，不会伪装成改进。
- 中间智能体替换消融完成 18/18 次 Agent 运行：**Qwen 对照组 Recall@3 `0.6667`、Analysis Ready `66.67%`**；DeepSeek 实验组 Recall@3 `1.0000`、Analysis Ready `55.56%`。两组均为 9/9 `REVIEW`，只作为小样本诊断。

## 多模型对比状态

`/api/agent/qwen-sessions` 和 `/api/agent/api-check` 只接受 Qwen。DeepSeek 仅由 `scripts/run_planner_replacement_ablation.py` 在独立进程中替换中间规划/工具选择智能体；数据总结和两组辅助评审仍统一使用 Qwen。当前已完成同题集、同预算、同规则、每题三次重复的小样本实验；由于题集未冻结、Qwen 辅助评审不完整且缺少人工乳腺癌 Gold Set，正式模型排名和 SDTI 必须写 `NOT_EVALUATED`。

## GitHub 不包含的数据与恢复

| Git 忽略内容 | 原因 | 恢复方式 |
| --- | --- | --- |
| `.env`、API Key、凭据 CSV | 密钥不能进入版本库 | `Copy-Item .env.example .env` 后填写本机变量，或使用临时会话端点 |
| `data/benchmarks/` | BEIR 原始语料较大 | 对公开评测脚本添加 `--download` |
| `evaluation/public_benchmarks/runs/` | 可重复生成的逐运行产物 | 运行脚本；报告保留来源 URL、SHA-256 和汇总指标 |
| 患者级导出、缓存、日志 | 受访问条件、体积和隐私限制 | 通过 API 重新请求公开源；本地输出保存在 `data/output/` |

## 最小本地绑定

```powershell
Copy-Item .env.example .env
# 填写 DASHSCOPE_API_KEY；可保留默认 QWEN_BASE_URL 与 QWEN_MODEL
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

原生启动后打开 `http://127.0.0.1:8000/`，接口文档为 `http://127.0.0.1:8000/docs`。Docker 启动时前端默认是 `http://127.0.0.1:8888`，后端仍为 `http://127.0.0.1:8000`。配置写入 `.env` 后，同一台本机上的后续调用无需重复输入 Key；浏览器临时连接只在服务内存保存 `session_id`，最长两小时。
