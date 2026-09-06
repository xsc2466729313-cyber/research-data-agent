# Frontend Phase 1 报告

- 完成日期：2026-09-05
- 依据：`FRONTEND_IMPLEMENTATION_PLAN.md`
- 范围：Home + Research Copilot
- 未做：Timeline、Sources、Mapping、Graph、Preview、Dataset、`/plan`、`/discover`、`/integration/*`、`/api/agent/tasks`

用户现在可以从首页输入问题、创建 session、进入 Copilot，看到理解目标、数据需求、澄清问题与 Memory。

---

## 1. 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/v31/app/main.js` | 挂载 Home / Copilot，未实现页仍显示「本阶段尚未开放」 |
| `frontend/v31/app/router.js` | 增加 `go()` |
| `frontend/v31/app/api/v30.js` | 接线 sessions / route / turn / memory；`planSession` 仍抛错 |
| `frontend/v31/index.html` | 增加页面样式与 Memory 右轨槽位 |
| `frontend/v31/styles/shell.css` | 错误条样式 |
| `backend/tests/v31_frontend/test_phase0_shell.py` | 允许 Phase 1 的 `/api/v30` 四条，仍禁止 plan / discover / integration / agent |

未修改：

- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- 任何后端业务模块

---

## 2. 新增文件

```text
frontend/v31/app/dom.js
frontend/v31/app/pending-intent.js
frontend/v31/app/pages/home.js
frontend/v31/app/pages/copilot.js
frontend/v31/app/components/understanding-bar.js
frontend/v31/app/components/data-need-table.js
frontend/v31/app/components/clarify-card.js
frontend/v31/app/components/memory-rail.js
frontend/v31/styles/pages/home.css
frontend/v31/styles/pages/copilot.css
frontend/v31/styles/components/cards.css
frontend/v31/styles/components/tables.css
backend/tests/v31_frontend/test_phase1_copilot.py
FRONTEND_PHASE1_REPORT.md
```

---

## 3. 页面效果说明

**首页 `/v31/#/home`**

- 大输入「告诉我你想研究什么」
- 主按钮「开始澄清研究目标」（没有「发送并开始研究」）
- 两个案例磁贴：HER2阳性乳腺癌耐药、Ia型超新星光变曲线
- 案例只预填并创建**新** session，不取数、不执行
- 诚实句：发现不是覆盖；预览不是执行

**Copilot `/v31/#/r/{session}/copilot`**

- Route Pill：CHAT / CONCEPT_QA / CLARIFY / PLAN
- Understanding Bar：对象 / 目标 / 领域；概念问答不写研究目标
- Data Need Table：类别、说明、`retrieval_status`；`not_retrieved` 显示为未检索，不显示完成
- Clarifying Card：一次一个问题 + 选项按钮
- 短回复，无聊天气泡、无机器人头像、无打字机
- Memory 右轨：goal / clarifications / constraints
- 「生成研究方案」可见但禁用，旁注下一阶段才调用 `/plan`

浏览器已走通：点 HER2 案例 → 创建 session → CLARIFY → 点「疗效预测」→ Memory 写入澄清，方案按钮仍禁用。

---

## 4. API 调用说明

| 时机 | API | 写入 Store |
|---|---|---|
| 首页提交 / 点案例 | `POST /api/v30/route` | 只写 `lastRoute`，不写 goal |
| 同上 | `POST /api/v30/sessions` | `sessionId` `memory` |
| 进入 Copilot 后首轮与后续澄清 | `POST /api/v30/copilot/turn` | `lastTurn` `lastRoute` `memory` |
| 每轮之后刷新右轨 | `GET /api/v30/sessions/{id}/memory` | `memory` |

未调用：`/api/v30/plan`、`/discover`、`/integration/*`、`/api/agent/tasks`。  
不用 `localStorage` 保存科研数据。首句通过内存 `pending-intent` 交给 Copilot，刷新后不会重放。

---

## 5. 测试结果

| 套件 | 结果 |
|---|---|
| `backend/tests/v31_frontend` | **13 passed**（Phase 0 + Phase 1） |
| `backend/tests/v30` | **75 passed** |
| Phase 0 固定回归 234 | **234 passed** |

Phase 1 覆盖：首页创建 session、Copilot 仅四条 API、无 plan/discover/execute、CONCEPT_QA 不写研究目标、`not_retrieved` 不标完成、旧前端无 `/api/v30`。

---

## 6. 是否进入 Frontend Phase 2

**可以进入 Phase 2（Timeline + `/plan`）。**

本阶段到此停止，未开发 Timeline。
