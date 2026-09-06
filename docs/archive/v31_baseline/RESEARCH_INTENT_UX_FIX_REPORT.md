# Research Intent UX Fix 报告

- 完成日期：2026-09-05
- 依据：`RESEARCH_INTENT_UX_FIX_PLAN.md`
- 范围：只改 `frontend/v31/`
- 未做：改后端 Router / Copilot 抽取、新增 API、DirectionAssist 以外的问卷

「我想研究Ia型超新星光变曲线」不再被第一层做成概念说明或「补充信息」。前端用 `intentOf` 把它投影为 `RESEARCH_INTENT`，并给出方向卡。

---

## 1. 本阶段实现

1. **`intent.js`**  
   `CHAT` / `CONCEPT_QA` / `RESEARCH_INTENT`。含「我想研究 / 打算研究 / 研究」优先科研。不改后端 `route`。

2. **UnderstandingBar**  
   科研意图展示「你希望研究」+ `raw_text` 去掉前缀。不再写「尚未明确的对象」。

3. **NextActionCard**  
   删除「补充信息」。未 ready 的科研意图：「选择一个研究方向」。闲聊：「说出研究想法」。概念：「如果想研究，请改写成“我想研究...”。」

4. **DirectionAssist**  
   仅 `RESEARCH_INTENT` 且没有后端 `clarifying_questions`。超新星三卡；医学两卡。点击 `sendTurn` 完整「我想研究…」句，不提交「不确定 / 帮我选择」。

5. **文案**  
   第一层删除「说明或闲聊，因此不能生成方案」。CHAT 与 CONCEPT_QA 分开。

---

## 2. 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/v31/app/intent.js` | 新建 `intentOf` / `topicFromRaw` |
| `frontend/v31/app/components/direction-assist.js` | 新建方向卡 |
| `frontend/v31/app/components/understanding-bar.js` | 按 intent 展示 |
| `frontend/v31/app/components/next-action-card.js` | 去掉补充信息 |
| `frontend/v31/app/components/why-clarify.js` | 按 intent 解释 |
| `frontend/v31/app/pages/copilot.js` | 组装 intent + 方向卡点击 |
| `frontend/v31/app/session-store.js` | 内存 `lastUserMessage` |
| `frontend/v31/copy/honesty.zh.js` | 闲聊 / 概念 / 选方向文案 |
| `frontend/v31/styles/pages/copilot.css` | 研究对象标题 |
| `backend/tests/v31_frontend/test_research_intent_ux.py` | 新建 |
| `backend/tests/v31_frontend/test_phase1_copilot.py` | 「补充信息」改为「选择一个研究方向」 |

未修改：`app/api/v30.js`、`backend/app/v30/`、旧 frontend。

---

## 3. 手验

**我想研究Ia型超新星光变曲线**

- 你希望研究：Ia型超新星光变曲线
- 三张卡：光变曲线建模（建议）、距离测量、爆炸机制分析
- 下一步：选择一个研究方向
- 无「补充信息」，无「说明或闲聊」，无方案按钮
- 点「光变曲线建模」会 `POST /api/v30/copilot/turn`

**什么是HER2**

- CONCEPT_QA，不写 goal
- 「这不是研究对象」；下一步改写成「我想研究...」
- 无方向卡

**你好**

- 闲聊；下一步「说出研究想法」
- 无方向卡、无方案按钮

---

## 4. 测试

| 集合 | 结果 |
|---|---|
| `backend/tests/v31_frontend` | passed |
| `backend/tests/v30` | passed |
| Phase 0 固定回归 234 | **234 passed / 0 failed** |

`test_research_intent_ux.py` 覆盖：超新星 → RESEARCH_INTENT；什么是HER2 不写 goal；你好 → CHAT；方向卡走 `copilotTurn`；API 集合不变。

---

## 5. 明确未做

- 不改后端对象抽取（超新星仍可能没有 `object` 字段）
- 不把 RESEARCH_INTENT 写入后端枚举
- 不做问卷或 Preview / Dataset
