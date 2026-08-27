# Planning RAG / Scientific KG（总方案 Phase 3）

## 本阶段结果

本阶段落实总方案“Codex 第二轮执行目标”，把 Phase 2 Literature Layer 取得的论文证据变成可检索、可回链和可评测的 Planning RAG：

```text
ResearchTopic
→ LiteratureProvider / PaperRecord
→ 论文结构化切片
→ 混合检索（语义 + 词法 + 章节优先级 + 图谱关联）
→ 可点击 Evidence
→ FieldRequirement
→ Scientific Knowledge Graph
```

该层只管理“应该找什么、为什么要这个字段”，不将论文内容写入患者表，不从论文语句推断患者身份，也不改变冻结 Schema、医学规则或 SDTI 公式。

## 论文结构化切片

`PaperChunker` 按科研证据价值排序，而不是把全文当作无结构文本：

1. Methods
2. Data Availability
3. Supplementary
4. Table
5. Cohort / Population / Variables / Outcome / Statistical Analysis
6. Results
7. Abstract
8. Title

每个 chunk 保留 `paper_id`、`source_id`、真实 `source_url`、`raw_field`、`raw_value` 和字符位置。缺失的论文章节不会被补写。

Europe PMC Provider 对有开放全文标记的 PMC 记录限量读取 `fullTextXML`，提取 Methods、Data Availability、Supplementary、Cohort、Outcome、Statistical Analysis、Results 和 Limitations。全文请求单独记录时间、状态、URL、结果数和错误类型；失败时回退到 title/abstract，不伪造全文内容。

## 可替换 RAG 后端

默认路径为可离线回归的 `memory-cosine + hashing-lexical-v1`，不会隐式下载模型。生产路径可选：

```powershell
python -m pip install -r backend/requirements.txt
python -m pip install -r backend/requirements-rag.txt

$env:RAG_VECTOR_BACKEND = "chroma"
$env:RAG_EMBEDDING_BACKEND = "bge"
$env:RAG_CHROMA_PATH = "data/cache/planning_rag"
$env:RAG_BGE_MODEL = "BAAI/bge-small-zh-v1.5"
```

Docker 构建时可设置 `INSTALL_RAG_EXTRAS=1`。如 ChromaDB 或 BGE 不可用，系统返回明确 warning 并回退到离线后端；不会把 hashing 说成 BGE。

## 混合检索与字段 Evidence

混合分数是可审计的固定组合：

```text
0.55 × semantic
+ 0.30 × lexical
+ 0.10 × section priority
+ 0.05 × field graph relation
```

返回值分别暴露四个子分数、命中理由、论文来源、章节和证据原文。`field_id` 会通过 `Paper -[DEFINES]→ Variable` 关系给相关论文加图谱分，但不会越过 Evidence 门控自动补齐字段。

## Scientific KG MVP

当前图谱节点：

- `ResearchTopic`
- `Paper`
- `Dataset`
- `ResearchQuestion`
- `PaperChunk`
- `ResearchContract`
- `Variable`

当前关系：`HAS_EVIDENCE_CANDIDATE`、`USES_DATASET`、`FORMULATES`、`SUPPORTS`、`EXTRACTED_FROM`、`SELECTED_AS`、`REQUIRES_*` 和 `DEFINES`。NetworkX 可用时作为图后端，否则使用内置邻接表；两者输出同一 API Schema。

## API

### 建立或重建索引

```http
POST /api/research/topics/{topic_id}/rag-index
Content-Type: application/json

{
  "contract_id": "optional-contract-id"
}
```

### 查询论文 Evidence

```http
POST /api/research/topics/{topic_id}/evidence-query
Content-Type: application/json

{
  "query": "为什么把 pCR 作为主要结局？",
  "field_id": "pcr",
  "top_k": 5,
  "sections": ["methods", "table", "outcome_definition"]
}
```

### 读取图谱

```http
GET /api/research/topics/{topic_id}/knowledge-graph
```

### 运行冻结 Gold Set 评测

```http
POST /api/research/topics/{topic_id}/rag-evaluate
Content-Type: application/json

{
  "gold_set_id": "planning-rag-gold",
  "gold_set_version": "1.0.0",
  "gold_set_frozen": true,
  "top_k": 5,
  "cases": [
    {
      "case_id": "pcr-001",
      "query": "为什么把 pCR 作为主要结局？",
      "field_id": "pcr",
      "expected_source_ids": ["europepmc:..."],
      "expected_sections": ["methods", "outcome_definition"]
    }
  ]
}
```

评测返回 `Recall@K`、`MRR`、`NDCG@K` 和 `Evidence Hit Rate`。未冻结 Gold Set 会被 422 拒绝。这些数值只对当次请求中的真实标注集有效，不替代冻结 SDTI，也不是临床有效性成绩。

## 已知边界

- Topic、Contract 和索引管理器仍为进程内状态；只有选用 ChromaDB 时向量数据可持久化。
- 当前是 Planning RAG，尚未建立针对数据字典、清洗日志和 Transformation 的 Evidence RAG。
- Europe PMC 全文解析仅针对可访问的 PMC XML，付费或不可用全文不会被绕过。
- Scientific KG 是科研证据关系图，不是患者 Entity Resolution 图。

## 验证

```powershell
python -m pytest backend/tests/test_research_planning.py backend/tests/test_planning_rag.py
python -m pytest
```

业务测试覆盖章节优先级、原值/来源保留、字段图谱加分、数据集节点、全文获取追踪、四项 RAG 指标、未冻结 Gold Set 拒绝和端到端 API 链路。
