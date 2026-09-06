# Frontend Phase 2 报告

- 完成日期：2026-09-05
- 依据：`FRONTEND_IMPLEMENTATION_PLAN.md`
- 范围：Timeline + `POST /api/v30/plan`
- 未做：Sources、Mapping、Graph、Preview、Dataset、discover / source-selection / schema-packs / integration

科研流程脊骨已落地。门状态只由 SessionStore 字段投影，不按 `domain` 猜测。

---

## 1. 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/v31/app/api/v30.js` | 实现 `planSession()` → `POST /api/v30/plan` |
| `frontend/v31/app/pages/copilot.js` | 「生成研究方案」调用 `/plan`；422 显示诚实文案 |
| `frontend/v31/app/main.js` | 左轨改用投影门；挂载 Timeline 页 |
| `frontend/v31/app/session-store.js` | 增加 `subscribe`，供左轨刷新 |
| `frontend/v31/app/router.js` | 无逻辑变更需求（已支持 `#/r/{id}/timeline`） |
| `frontend/v31/index.html` | 引入 `timeline.css`；左轨说明改为非进度条 |
| `frontend/v31/copy/honesty.zh.js` | `GATE_MESSAGES.research_goal_not_ready` |
| `frontend/v31/styles/components/gates.css` | ready / blocked / executed 点样式 |
| `backend/tests/v31_frontend/test_phase0_shell.py` | 允许 `/plan` |
| `backend/tests/v31_frontend/test_phase1_copilot.py` | 允许 `/plan` |

未修改：`frontend/index.html`、`frontend/app.js`、`frontend/styles.css`、后端业务模块。

---

## 2. 新增文件

```text
frontend/v31/app/timeline-store.js
frontend/v31/app/timeline-fixtures.json
frontend/v31/app/pages/timeline.js
frontend/v31/app/components/gate-node.js
frontend/v31/app/components/event-card.js
frontend/v31/styles/pages/timeline.css
backend/tests/v31_frontend/test_phase2_timeline.py
FRONTEND_PHASE2_REPORT.md
```

---

## 3. Timeline 效果

八个门：会话 → 澄清 → 方案 → 来源 → 字段 → 证据 → 预览 → 数据。

状态只有 `idle / blocked / ready / executed`，没有百分比。

投影规则（字段存在性）：

| 门 | ready | blocked |
|---|---|---|
| 会话 | 有 `sessionId` | `session not found` |
| 澄清 | `memory.goal.object/target` 或 `ready_for_planner` | `blocked_reason`（CHAT/CONCEPT_QA 保持 idle） |
| 方案 | 有 `plan` | `lastError.error==research_goal_not_ready` 且尚未 ready |
| 来源及之后 | 仅当对应 Store 对象存在 | 本阶段均为 idle |
| 数据 | 永不因 `domain=oncology` 点亮 | 仅 `executionResult.executed===true` 才是 executed |

全页 `#/r/{session}/timeline` 展示门列表与事件卡：API 名、对象 ID、状态、诚实提示。  
用户约束事件标明「用户约束，不是数据缺失」。

浏览器已核对：未澄清点「生成研究方案」→ 方案门 `blocked`，文案「研究目标尚未澄清，不能生成方案」；来源/数据门保持 idle。

---

## 4. API 调用

| 时机 | API |
|---|---|
| Copilot 点「生成研究方案」 | `POST /api/v30/plan` `{ session_id }`，不传猜测目标 |
| 422 | 写入 `lastError.error=research_goal_not_ready` |
| 200 | 写入 `plan`，跳转 Timeline，**不**调用 discover |

未调用：`/discover`、`/source-selection`、`/schema-packs`、`/integration/*`、`/api/agent/tasks`。

---

## 5. 测试结果

| 套件 | 结果 |
|---|---|
| `backend/tests/v31_frontend` | **18 passed** |
| `test_phase2_timeline.py` | 无 plan → idle；422 → blocked；成功 plan → ready；oncology 不点亮数据门；CONCEPT_QA 后续 idle |
| `backend/tests/v30` | **75 passed** |
| Phase 0 234 回归 | **234 passed** |

旧 `frontend/app.js` 仍无 `/api/v30`。

---

## 6. 是否进入 Phase 3

**可以进入 Phase 3（Sources + Mapping）。**

本阶段到此停止，未开发 Sources。
