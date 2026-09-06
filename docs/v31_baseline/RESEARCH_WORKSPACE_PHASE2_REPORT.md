# Research Workspace UX Phase 2 报告

- 完成日期：2026-09-05
- 依据：`docs/v31_baseline/RESEARCH_WORKSPACE_UX_PLAN.md`
- 基线：`docs/v31_baseline/RESEARCH_WORKSPACE_PHASE1_REPORT.md`
- 范围：只改 `frontend/v31/`
- 未做：Preview / Dataset / Execute、list API、localStorage 持久化

Phase 1 只有摘要和过程带。本阶段补上多研究窗口：列表、分槽、切换、独立上下文。

---

## 1. 本阶段实现

1. **研究列表**  
   左轨从八门改成「我的研究」。顶部「+ 新建研究」。每项：标题、阶段、更新时间（刚刚 / n分钟前）。当前项细竖线加字重。八门不再当主导航。

2. **workspace-store**  
   内存槽：`sessionId / title / stage / snapshot / conversationLog`。科研内容不写 localStorage。

3. **新建研究**  
   「+ 新建研究」调用已有 `POST /api/v30/sessions`，再进入该 session 的 Copilot。不 `reset()` 已有研究。

4. **切换**  
   先保存当前槽，再走 `#/r/{session_id}/copilot`，恢复 memory、摘要、过程带。

5. **阶段文案**  
   选方向时为「方向选择」；可生成方案后为「研究规划」。

---

## 2. 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/v31/app/workspace-store.js` | 多 session 槽、快照、切换 |
| `frontend/v31/app/components/research-list.js` | 列表：标题 / 阶段 / 更新时间 / + 新建研究 |
| `frontend/v31/app/session-store.js` | `hydrate` / `snapshotOf` |
| `frontend/v31/app/pages/home.js` | `createStudy`，去掉工作空间级 `reset()` |
| `frontend/v31/app/pages/copilot.js` | `adoptSession` |
| `frontend/v31/app/main.js` | 左轨列表；+ 新建研究直接建 session |
| `frontend/v31/app/timeline-store.js` | 事件按 session 分桶 |
| `frontend/v31/index.html` | 左轨「我的研究」 |
| `frontend/v31/copy/honesty.zh.js` | 方向选择 / 研究规划 |
| `frontend/v31/styles/shell.css` | 列表样式 |
| `backend/tests/v31_frontend/test_research_workspace_phase2.py` | 新建 |

未修改：`frontend/v31/app/api/v30.js`、`backend/app/v30/`、旧 frontend。

---

## 3. 手验隔离

1. 打开 HER2：列表「HER2阳性乳腺癌 · 阶段：方向选择 · 刚刚」；中列机制探索 / 疗效预测。  
2. 「+ 新建研究」再建 Ia 超新星：HER2 仍在列表。  
3. 超新星窗：光变曲线建模 / 距离测量 / 爆炸机制分析，**没有**机制探索。  
4. 切回 HER2：URL 回到 HER2 session；过程带与摘要仍是 HER2；**没有**超新星方向。  
5. 再切回超新星：**没有** HER2 确认。

---

## 4. 测试

| 集合 | 结果 |
|---|---|
| `backend/tests/v31_frontend` | passed |
| `backend/tests/v30` | passed |
| Phase 0 固定回归 234 | **234 passed / 0 failed** |

旧 `/` 仍是「发送并开始研究」。无新 API，无科研 localStorage。

---

## 5. 明确不做

- 不向后端要 session 目录或 turn 历史  
- 刷新后不承诺还挂着未打开过的其它项  
- 不把过程带做成聊天窗  
- 不删除工程 Timeline 页  
