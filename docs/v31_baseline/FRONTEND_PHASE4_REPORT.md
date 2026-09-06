# Frontend Phase 4 报告

- 完成日期：2026-09-05
- 依据：`docs/v31_baseline/FRONTEND_IMPLEMENTATION_PLAN.md`
- 范围：Evidence Graph（只读解释页）
- 未做：Preview、Dataset、Execute

本阶段只回答四个问题：为什么选择这个来源、为什么这样映射、为什么是 REVIEW、为什么排除。图是投影，不是事实库。

---

## 1. 修改文件列表


| 文件                                                          | 改动                                                                                                |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| `frontend/v31/app/api/v30.js`                               | `projectGraph` / `getGraph` / `getGraphWhy` / `understandFigure`                                  |
| `frontend/v31/app/main.js`                                  | 挂载 Graph；Preview / Dataset 仍显示「本阶段尚未开放」                                                           |
| `frontend/v31/app/timeline-store.js`                        | 证据门：`store.graph` 存在且 `contains_patient_edges!==true` 才 ready；事件记录 `POST /api/v30/graphs/project` |
| `frontend/v31/app/pages/timeline.js`                        | 字段 ready 可进 Graph；左轨 `graph` 可点                                                                   |
| `frontend/v31/app/pages/mapping.js`                         | mappings 存在时 CTA「进入证据解释」                                                                          |
| `frontend/v31/index.html`                                   | 引入 `graph.css`、`drawers.css`                                                                      |
| `frontend/v31/copy/honesty.zh.js`                           | `GATE_MESSAGES.contains_patient_edges`                                                            |
| `backend/tests/v31_frontend/test_phase0_shell.py`           | 允许 graphs，仍禁 integration / agent                                                                  |
| `backend/tests/v31_frontend/test_phase1_copilot.py`         | Copilot 自身不含 graphs                                                                               |
| `backend/tests/v31_frontend/test_phase2_timeline.py`        | 允许 joined 含 graphs，仍禁 integration                                                                 |
| `backend/tests/v31_frontend/test_phase3_sources_mapping.py` | Sources / Mapping 页自身不调 graphs                                                                    |


未修改：`frontend/index.html`、`frontend/app.js`、`frontend/styles.css`、后端业务模块、冻结配置。

---



## 2. 新增文件列表

```text
frontend/v31/app/pages/graph.js
frontend/v31/app/components/graph-canvas.js
frontend/v31/app/components/why-drawer.js
frontend/v31/styles/pages/graph.css
frontend/v31/styles/components/drawers.css
backend/tests/v31_frontend/test_phase4_graph.py
docs/v31_baseline/FRONTEND_PHASE4_REPORT.md
```

---



## 3. Graph 效果

进入 `#/r/{session}/graph` **不会**自动投影。证据门在打开页面时仍为 idle，只在 `store.graph` 写入后 ready。

**Graph Canvas**

- 按 API `node_type` 分列：UserGoal、ResearchContract、SourceCandidate、SelectedSource、SchemaPack、FieldMapping、QualityFinding、FigureUnderstanding
- 节点只显示 `node_type` + `label`，可点，不可拖、不可改
- 边只画 API 回包中的允许边：FORMULATES / DISCOVERED / SELECTED / MAPPED_TO / FLAGGED_BY（以及后端可能给出的 EXTRACTED_FROM）
- 过滤 `SAME_PATIENT` / `JOINED_ACROSS_STUDY`，不绘制
- `contains_patient_edges===true`：整页错误「图包含禁止的患者关系边，不能展示。」，不画网
- 无力导向、无图谱库；SVG 直线 + 绝对定位
- 宽屏中列约 960px，右侧 Why Drawer；四周留白

**Graph Notice**

- 回包 `notice`
- 三否定原样展示：`replaces_evidence_builder` / `contains_patient_edges` / `copies_fact_values`

浏览器 HER2：进入页时空态 +「进入本页不会自动投影」；点「生成解释图」后出现 UserGoal、契约、GEO/GDC 等候选、选中源、排除 finding、Schema Pack、字段映射。证据门变为 ready。图上无患者—患者边。

---



## 4. Why 解释效果

点击节点：

- QualityFinding，或节点 `refs.finding_id`，或出边 `FLAGGED_BY` 指向的 finding → `GET /api/v30/graphs/{graph_id}/why/{finding_id}`
- 写入 `store.lastWhy`，打开右侧抽屉
- 抽屉展示 API 字段：`statement` / `why[]` / `path[]` / `edges[]`
- `forbidden_edges_present===true`：抽屉错误态，不展示禁边
- 关闭抽屉（按钮或 Escape）保留 `lastWhy`，不改 `graph`

浏览器：

- 点「未选择 geo」：调用 `.../why/finding-rejected-disc-oncology-geo`；why 含 `reason_code=not_in_cover`；path 为 UserGoal → ResearchContract → SourceCandidate geo → QualityFinding
- 点「禁止患者跨研究 Join」：why 写明不创建 SAME_PATIENT / JOINED_ACROSS_STUDY
- 点 FieldMapping（本趟 match 为 REJECT，无 REVIEW finding）：用节点自带 `reasons` 说明 `status` / `confidence`，不编造映射值

REVIEW 映射在后端会另建 `finding-review-{source}-{target}`。点 HER2 映射节点时，画布会沿 `FLAGGED_BY` 找到该 finding 再调 why。本趟 HER2 发现字段未直接打出 `her2→her2_status`，所以用排除 finding 与 join-risk 验收 Why 合同。

---



## 5. API 调用说明


| 时机                                         | 封装                              | API                                                               |
| ------------------------------------------ | ------------------------------- | ----------------------------------------------------------------- |
| 点「生成解释图」                                   | `projectGraph()` 后 `getGraph()` | `POST /api/v30/graphs/project` + `GET /api/v30/graphs/{graph_id}` |
| 点击 QualityFinding / 带 finding 的节点          | `getGraphWhy()`                 | `GET /api/v30/graphs/{graph_id}/why/{finding_id}`                 |
| 点「理解附图（不入库）」且 Store 已有 `source_id` 与 graph | `understandFigure()`            | `POST /api/v30/figures/understand`                                |


Project 入参只拼 SessionStore 已有对象：`goal` `contract` `candidates` `selection` `schema_pack` `mappings` `constraints`。不传患者行，不传数值事实。`contract` 为 SelectionContract 形状，不是 FrozenResearchContract。

写入 SessionStore：`graph`、`lastWhy`。

前端不修改边，不生成节点，不合并 `patient_id`。

未调用：`/api/v30/integration/*`、`/api/agent/tasks`、`/api/adapters/*`。

---



## 6. 测试结果


| 套件                           | 结果                                                                                                                                        |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/tests/v31_frontend` | **31 passed**                                                                                                                             |
| `test_phase4_graph.py`       | Graph 可展示 API 节点；Why 调 `.../why/{finding_id}`；`contains_patient_edges=true` 错误态不画网；前端无 `addEdge` / 不创建 SAME_PATIENT；不调用 integration；旧前端不变 |
| `backend/tests/v30`          | **75 passed**                                                                                                                             |
| Phase 0 234 回归               | **234 passed**                                                                                                                            |


旧 `frontend/app.js` 仍无 `/api/v30`。`GET /` 仍是「发送并开始研究」。

---



## 7. 是否进入 Frontend Phase 5

**可以进入 Frontend Phase 5（Integration Preview + Dataset）。本阶段到此停止。未开发 Preview，未调用** `/api/v30/integration/`***。**