# Frontend UX Phase 报告

- 完成日期：2026-09-05
- 依据：`FRONTEND_UX_IMPROVEMENT_PLAN.md`
- 范围：只改 `frontend/v31/`，把 Copilot 从状态展示页收成 AI 科研助手引导页
- 未做：Preview、Dataset、Execute；不新增 API；不改 `backend/app/v30/`；不改旧 `frontend/`

---

## 1. 本阶段改了什么

按计划顺序实施，没有加新能力，只改呈现与点击时机。

1. **停止 Home 自动 `sendTurn(pending)`**  
   Home 仍写入 `pending-intent` 并跳 Copilot。首次进入若没有 `lastTurn`、Memory 也还没有 goal，先显示欢迎卡。点「开始研究」才 `takePendingIntent()` + `POST /api/v30/copilot/turn`。刷新且 Memory 已有 goal 时跳过欢迎，用 Memory 画理解总结。

2. **默认隐藏开发状态**  
   Route pills、`ready_for_planner` 明文、`blocked_reason`、`retrieval_status` 表头、`research_goal_not_ready` 都不再出现在第一层。路由与 `not_retrieved` 仍可在「技术细节 / 数据需求」折叠里读到，满足诚实与旧测试。

3. **主区域改为引导结构**  
   理解总结 → 当前任务 → 下一步问题。字段三列表和长段 `reply` 并排已去掉。

4. **澄清大卡片**  
   仍只渲染 `questions[0]`。选项是整行大按钮（最小高度 52px），点一下即提交。无问题时整块不占位。

5. **Memory 改为研究上下文**  
   默认一行摘要（对象 · 目标 + 确认条数）。展开「查看详情」才见对象 / 目标 / 领域 / 确认 / 限制。Timeline / Sources / Mapping / Graph 共用同一摘要，不再露出空的 Memory 调试盒。

6. **左轨弱化成研究进程**  
   标题与说明改为「研究进程 / 只标记已经发生的步骤，不是完成度。」默认不写英文 `idle/ready/blocked`。`idle` 不写状态字；`ready` → 已记录；`blocked` → 需确认。Copilot 期间后五步降对比。

---

## 2. 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/v31/app/pages/copilot.js` | Onboarding；取消自动 turn；主区三块；方案按钮仅 `ready_for_planner===true`；422 不进中列/`#shell-error` |
| `frontend/v31/app/pending-intent.js` | 增加 `peekPendingIntent()`，开始研究前不消费 pending |
| `frontend/v31/app/components/understanding-bar.js` | 理解总结段落；CONCEPT_QA/CHAT 明确不是研究对象 |
| `frontend/v31/app/components/clarify-card.js` | 大卡片选项；无问题返回空 |
| `frontend/v31/app/components/data-need-table.js` | 折叠列表；隐藏表保留 `retrieval_status` / `not_retrieved` |
| `frontend/v31/app/components/memory-rail.js` | 研究上下文摘要 + 详情 |
| `frontend/v31/app/components/gate-node.js` | 中文状态；`data-status` 仍保留英文；支持 `later` |
| `frontend/v31/app/components/event-card.js` | 人话标题；API 路径作小字；不把 idle 当主文案 |
| `frontend/v31/app/pages/timeline.js` | 左轨当前步；Copilot 后五步 `later` |
| `frontend/v31/app/main.js` | 422 不写错误条；其他页填同一研究上下文 |
| `frontend/v31/copy/honesty.zh.js` | 欢迎语、能力三条、当前任务、进程文案 |
| `frontend/v31/index.html` | 左轨「研究进程」；右轨「研究上下文」 |
| `frontend/v31/styles/pages/copilot.css` | Onboarding、理解总结、大卡片、折叠细节 |
| `frontend/v31/styles/components/gates.css` | 当前步细线；后步降对比 |
| `frontend/v31/styles/pages/timeline.css` | 事件卡 API 小字 |
| `frontend/v31/styles/shell.css` | 研究上下文摘要 |
| `backend/tests/v31_frontend/test_phase1_copilot.py` | 增补引导页静态断言，不改 API 契约 |

未修改：

- `frontend/v31/app/api/v30.js`
- `backend/app/v30/`
- 旧 `frontend/index.html` / `app.js` / `styles.css`
- 冻结配置与评测公式

---

## 3. 引导效果（手验）

环境：`http://127.0.0.1:8000/v31/`（不要用 Docker Nginx `:8888`，镜像没有 v31）。

### HER2 研究路径

1. Home 点「HER2阳性乳腺癌耐药」→ 进入 Copilot，**先看到欢迎语、三条能力、「开始研究」**，不自动铺调试字段。
2. 点「开始研究」后中列是：  
   理解总结（HER2阳性乳腺癌 / 耐药机制分析）→ 当前任务「请确认研究重点」→ 一个问题 + 「机制探索 / 疗效预测」大卡片。  
   此时没有「生成研究方案」，也没有 `research_goal_not_ready`。
3. 点「疗效预测」后当前任务变为「可以生成研究方案了（不会取数）」，方案按钮出现。研究上下文默认：`HER2阳性乳腺癌 · 耐药机制分析` / `已记录 1 条确认`。
4. 点「生成研究方案」仍跳 Timeline，事件是「已创建会话 / 已更新理解 / 已生成研究方案」，不取数。

### 「什么是HER2」路径

1. Home 输入「什么是HER2」→ 同样先 onboarding。
2. 开始后：理解总结写「这不是研究对象，不会写入研究目标。」当前任务是「这是说明，不是一次取数」。无方案按钮。研究上下文仍是「还没有形成研究对象」。

### 左轨

- 标题「研究进程」，说明不是完成度。
- 可见状态只有中文「已记录」等；idle 步骤不写英文。
- 证据门在 Graph 回包前保持未到。

---

## 4. 测了什么

| 集合 | 结果 |
|---|---|
| `backend/tests/v31_frontend` | passed |
| `backend/tests/v30` | passed |
| Phase 0 固定回归 234 | **234 passed / 0 failed** |

解释器：仓库 `.venv`，工作目录仓库根，`$env:PYTHONPATH="."`。

仍保持：

- Copilot 只调 `copilotTurn` / `getMemory` / `planSession`
- CONCEPT_QA 不写 goal
- 展开数据需求仍能读到 `not_retrieved`
- 无 `chat-bubble`、无打字机、无「发送并开始研究」
- 无 `/api/v30/integration`、无 `localStorage` 科研数据
- 旧 `/` 仍是内核实验室，「发送并开始研究」仍在

---

## 5. 明确未做

- Preview / Dataset / Execute 页面仍显示「本阶段尚未开放」
- 不改 Copilot 后端回复语义（理解总结里的目标字段仍以后端 `understood_goal` 为准）
- 不把左轨八步删掉，只减弱后五步
- 不把 Onboarding 做成强制问卷
- 不新增 `/api/v30` 字段
