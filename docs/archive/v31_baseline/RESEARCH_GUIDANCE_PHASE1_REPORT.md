# Research Guidance UX Phase 1 报告

- 完成日期：2026-09-05
- 依据：`RESEARCH_GUIDANCE_UX_PLAN.md`
- 范围：只改 `frontend/v31/`
- 未做：DirectionAssist、「不确定」入口、Home「还没想好研究方向」、Preview / Dataset / Execute

本阶段把 Copilot 从「当前任务 + 裸选项」收成：解释为什么要确认 → 带背景与建议的澄清 → 永远可见的下一步。

---

## 1. 本阶段实现

1. **WhyClarify**  
   目标未齐时用一句话解释为什么还不能规划。`ready_for_planner===true` 时不出现。第一层不展示 `awaiting_clarification`、`research_goal_not_ready` 或其它 error code。

2. **NextActionCard**  
   替代「当前任务」和独立方案按钮。永远告诉用户下一步：  
   - ready：生成研究方案  
   - 有澄清问题：确认研究方向  
   - 其余：补充信息

3. **ClarifyCard 增强**  
   增加焦点问背景解释，并按 `goal.target` 给已有 option 标「建议」。选项仍只来自 `clarifying_questions[0].options`，不新增选项，也没有「不确定」。

4. **开发状态默认隐藏**  
   route、`retrieval_status`、`ready_for_planner` 明文、`blocked_reason` 不进第一层。技术细节与隐藏表仍可展开核对。

---

## 2. 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/v31/app/components/why-clarify.js` | 新建。按 route / goal / questions / ready 投影「为什么要确认」 |
| `frontend/v31/app/components/next-action-card.js` | 新建。ready 才渲染方案按钮 |
| `frontend/v31/app/components/clarify-card.js` | 背景、建议标记、大卡片；`recommendOption()` 不增删 options |
| `frontend/v31/app/pages/copilot.js` | 组装 Why / Clarify / Next Action；去掉 task-block |
| `frontend/v31/copy/honesty.zh.js` | 为什么、背景、建议、下一步文案 |
| `frontend/v31/styles/pages/copilot.css` | Why / Next Action / 建议卡片 |
| `backend/tests/v31_frontend/test_phase1_copilot.py` | 增补引导页断言，不改 API 契约 |

未修改：`frontend/v31/app/api/v30.js`、`backend/app/v30/`、旧 frontend、冻结配置。

---

## 3. 页面效果

**HER2 澄清中**

- 理解总结：HER2阳性乳腺癌 / 耐药机制分析
- 为什么要确认：机制与疗效看的证据不同；现在选是为了形成研究问题，不是取数
- 大卡片：机制探索（建议）/ 疗效预测
- 下一步：确认研究方向
- 无方案按钮，无 `research_goal_not_ready`

**确认疗效预测后**

- 不再显示「为什么要确认」
- 下一步：可以生成研究方案了 + 「生成研究方案」
- 仍不取数

**什么是HER2**

- 不是研究对象，不写 goal
- 为什么要确认：说明或闲聊不能生成方案
- 下一步：补充信息
- 无方案按钮

---

## 4. 测试

| 集合 | 结果 |
|---|---|
| `backend/tests/v31_frontend` | passed |
| `backend/tests/v30` | passed |
| Phase 0 固定回归 234 | **234 passed / 0 failed** |

仍保持：只调 `copilotTurn` / `getMemory` / `planSession`；CONCEPT_QA 不写 goal；展开可读 `not_retrieved`；无聊天窗、无打字机、无「发送并开始研究」；无 integration；无科研 `localStorage`；旧 `/` 不变。

---

## 5. 明确未做

- 「还不确定」同卡展开
- DirectionAssist / Home「还没想好研究方向」
- CONCEPT_QA 一键改写成「我想研究…」
- Preview / Dataset / Execute
- 任何后端字段或新 API
