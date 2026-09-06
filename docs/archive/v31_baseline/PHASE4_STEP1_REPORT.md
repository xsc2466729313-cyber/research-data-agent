# V3.1 Phase 4-A 报告

- 完成日期：2026-09-05
- 分支：`feat/v31-phase1-copilot`
- 基线 HEAD：`8e023e1ee2b37abf0f9b114ddf53661444d97f7c`
- 范围：Evidence Graph 最小投影层
- 未做：Integrate、Adapter 执行、CSV 生成、图数据库、Figure Understanding、前端溯源接线

这是科研证据关系图，不是知识图谱，不是患者关系图，也不替代 EvidenceBuilder。只记录：为什么选择这个来源、为什么字段这样映射、为什么质量状态是 REVIEW。

---

## 1. 修改文件列表

- `backend/app/v30/api.py`：挂载图投影与查询
- `backend/app/v30/models.py`：增加图节点 / 边 / 投影请求 / why 响应

未修改：

- `configs/canonical_schema.yaml`
- `configs/medical_rules.yaml`
- `backend/app/evidence/evidence_builder.py`
- Quality Gate / Quality V2
- Adapter / SchemaMatcher 核心算法
- `ResearchAgentService`

---

## 2. 新增文件列表

```text
backend/app/v30/graph/__init__.py
backend/app/v30/graph/store.py
backend/app/v30/graph/service.py
backend/tests/v30/test_graph_constraints.py
PHASE4_STEP1_REPORT.md
```

存储是进程内字典，没有图数据库。

---

## 3. 节点与边

节点：

- `UserGoal`
- `ResearchContract`
- `SourceCandidate`
- `SelectedSource`
- `SchemaPack`
- `FieldMapping`
- `QualityFinding`

边：

- `FORMULATES`
- `DISCOVERED`
- `SELECTED`
- `MAPPED_TO`
- `FLAGGED_BY`

禁止：

- `SAME_PATIENT`
- `JOINED_ACROSS_STUDY`
- 复制患者数据
- 复制事实值（`canonical_value` / `raw_value` / EvidenceCell）

写入非法边会抛 `ForbiddenGraphEdgeError`。患者跨研究 Join 只作为 `QualityFinding` 记录，不会变成图边。

---

## 4. API 说明

查询接口：

- `GET /api/v30/graphs/{graph_id}`
- `GET /api/v30/graphs/{graph_id}/why/{finding_id}`

投影写入（本刀最小入口，供 GET 有图可查；不是 Integrate）：

- `POST /api/v30/graphs/project`

输入是已有 v30 产物的 ID/原因投影：goal、contract、candidates、selection、schema_pack、mappings。节点只保存引用与理由，不保存患者行或标准值。

`why/{finding_id}` 沿入边回溯，解释 REVIEW 或用户约束排除，例如 METABRIC 是约束，不是数据缺失证明。

未增加 `GET /api/v30/graphs/{graph_id}/facts/{evidence_id}`。事实权威仍是 EvidenceBuilder。

---

## 5. 测试结果

`backend/tests/v30`：**52 passed / 0 failed**

`test_graph_constraints.py`：

1. 可查询字段来源链：`her2 → her2_status` 可回溯到 UserGoal / Contract / Candidate / SelectedSource / SchemaPack
2. 可解释来源选择原因：GEO 选中理由、METABRIC 的 `user_constraint`
3. 可解释 REVIEW 原因：confidence / risk_level / Matcher REVIEW
4. 禁止患者跨研究关系：图中无 `SAME_PATIENT` / `JOINED_ACROSS_STUDY`，写入会被拒绝
5. 不复制患者数据或事实值；不导入 EvidenceBuilder / Quality / Adapter

Phase 0 固定回归：**234 passed / 0 failed**。

---

## 6. git diff 检查

| 路径 | 本刀 diff |
|---|---|
| `configs/canonical_schema.yaml` | 无 |
| `configs/medical_rules.yaml` | 无 |
| EvidenceBuilder | 无 |
| SchemaMatcher 核心文件 | 无 |
| Quality / Adapter | 无 |

---

## 7. 医学链路影响

**未影响。** 图层不生成 EvidenceCell，不改 Quality Gate，不取数，不写 CanonicalRecord。旧导出与评测仍读原 Evidence / Quality 路径。

---

## 8. 下一步

Integrate / Adapter 执行属于后续阶段。本任务到此停止。
