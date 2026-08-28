# RAG 查询理解与消融实验

## 范围

本模块落实 `2026-08-28-rag-query-understanding-ablation-design.md`：查询理解只改变检索前的查询构造，不改变语料、tokenizer、BM25/HybridRetriever、相关性标签、切分、冻结 SDTI 公式或医学安全规则。原始 query 始终保留，生成计划只接受 query 文本，不读取文档、排名或 qrels。

共享实现位于 `backend/app/retrieval/query_understanding.py`，公开 BEIR 适配位于 `backend/app/evaluation/public_retrieval.py`。规则模式会归一化文本、展开已有静态别名并提取数字、标识符、全大写缩写和引号短语作为保护词。计划校验失败时丢弃无效子查询；全部失败、超时或漂移时回退原始 query，并记录 `fallback_count`。

## 固定实验矩阵

| 组别 | 查询输入 | 融合 |
| --- | --- | --- |
| A `raw` | 原始 query | tuned BM25 单查询 |
| B `rules` | 原始 query + 确定性规则 query | 同一 BM25，各 top-100 后 RRF |
| C `qwen_single` | Qwen `keyword_query`，失败回退原始 query | tuned BM25 单查询 |
| D `qwen_multi_validated` | 原始 query + Qwen keyword/paraphrase/evidence | 各 top-100 后 RRF |
| E `rules_qwen` | 原始 + 规则 + 通过保护词/漂移校验的 Qwen query | 各 top-100 后 RRF |

RRF 使用冻结常数 `k=60`，候选深度固定为 `top-100`，各查询等权，分数相同按文档 ID 升序。BM25 参数一次用 train/dev 选择后由 A-E 共同复用；test qrels 只在最终指标计算时读取。Qwen 计划缓存键包含 dataset、query、model、prompt 和 schema 版本，C/D/E 共用同一缓存。

## 运行与状态

```powershell
python scripts/run_query_understanding_ablation.py `
  --dataset beir_scifact --dataset beir_nfcorpus --dataset beir_scidocs `
  --dataset beir_arguana --dataset beir_fiqa `
  --output evaluation/query_understanding/ablation_20260828.json
```

没有外部结构化 Qwen 计划缓存时，脚本只计算 A/B，C/D/E 明确写为 `NOT_EVALUATED`，不会把规则或原始回退结果伪装成 Qwen 成绩。2026-08-28 五任务运行产物为 `evaluation/query_understanding/ablation_20260828.json`，等权宏平均如下：A raw 的 nDCG@10 `0.314678`、Recall@100 `0.555205`、MRR@10 `0.362859`；B rules 的 nDCG@10 `0.314664`（相对 A `-0.000014`）、Recall@100 `0.553234`（`-0.001971`）、MRR@10 `0.361934`（`-0.000925`），平均检索延迟 `54.30ms -> 115.79ms`。因此当前规则组未通过部署门槛，生产默认保持 `compat`。SciFact 单数据集 smoke 仍保存在 `evaluation/query_understanding/ablation_smoke.json`：A nDCG@10 `0.604449`、B `0.606652`；这只是检索层诊断，不是临床效果或 SDTI。

正式部署门槛仍按附件规格执行：五数据集宏平均 nDCG@10 高于 `0.3147`、单数据集相对 A 降幅不超过 `0.02`、Qwen/校验回退率不超过 `1%`，并且来源哈希、无泄漏审计和回归测试完整。未满足全部条件时生产默认仍为 `compat`；安装 Qwen 凭据不会静默切换路径。

## 生产接入

`backend/app/retrieval/service.py` 提供显式模式：`compat`、`raw`、`rules`、`qwen_single`、`qwen_multi_validated`。Planning RAG 与 HybridRetrieverV2 在正式门槛通过、计划缓存/API 可复现并完成 Gold/回归评测前继续使用兼容默认。查询理解层不改变证据来源、章节、四项检索子分数或患者级医学事实。
