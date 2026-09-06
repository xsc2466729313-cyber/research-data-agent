# Research Workspace UX Phase 1 报告

- 完成日期：2026-09-05
- 依据：`docs/v31_baseline/RESEARCH_WORKSPACE_UX_PLAN.md`
- 范围：只改 `frontend/v31/`
- 未做：研究列表、多 session 切换、`workspace-store`、改 Home `reset()`、Preview / Dataset / Execute

本阶段先解决两件事：右轨不再像调试面板；用户能回看「刚才发生了什么」。

---

## 1. 本阶段实现

1. **Research Summary**  
   右轨默认改为五块：研究对象 / 研究目标 / 当前阶段 / 已确认内容 / 下一步。只读现有 `memory`、`goal`、`clarifications`、`projectGates`、NextAction。CONCEPT_QA / CHAT 不写入研究对象。第一层不再展示 `route`、`retrieval_status`、`constraints`。

2. **Conversation Timeline**  
   中列过程带，不是聊天气泡。类型：用户想法 / AI理解 / 方向建议 / 用户确认。数据写在当前 session 内存 `conversationLog`。刷新且 log 空时，只用 Memory 最少回放（`raw_text` → 想法；已答 clarifications → 确认），不编造方向卡。无头像、无打字机。

3. **Context Drawer**  
   `<details>` 默认关闭。展开才见技术细节、route、`retrieval_status`、constraints、Evidence、诚实边界、医学限制。`#shell-error` 仍不展示 `research_goal_not_ready`。

4. **单 session 保持不变**  
   Home 仍 `createSession()` 后 `reset()`。没有研究列表，没有多窗切换。

---

## 2. 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/v31/app/components/research-summary.js` | 新建。摘要五块 |
| `frontend/v31/app/components/conversation-timeline.js` | 新建。过程带 |
| `frontend/v31/app/components/context-drawer.js` | 新建。技术细节抽屉 |
| `frontend/v31/app/components/research-rail.js` | 新建。摘要 + 抽屉灌入右轨 |
| `frontend/v31/app/conversation-log.js` | 新建。内存追加 / 去重 / Memory 回放 |
| `frontend/v31/app/session-store.js` | 增加 `conversationLog` |
| `frontend/v31/app/pages/copilot.js` | 写 log、装过程带、右轨改摘要 |
| `frontend/v31/app/main.js` | Timeline / Sources / Mapping / Graph 共用摘要右轨 |
| `frontend/v31/index.html` | 右轨标题改为「研究摘要」；保留「研究上下文」 |
| `frontend/v31/copy/honesty.zh.js` | 阶段中文、过程类型标签 |
| `frontend/v31/styles/pages/copilot.css` | 过程带与摘要样式 |
| `backend/tests/v31_frontend/test_research_workspace_phase1.py` | 新建。呈现与单 session 契约 |

未修改：`frontend/v31/app/api/v30.js`、`backend/app/v30/`、旧 frontend、冻结配置。

---

## 3. 手验

**我想研究HER2阳性乳腺癌耐药机制**

- 过程带：用户想法 → AI理解 → 方向建议
- 点「机制探索」后追加用户确认
- 右轨：HER2阳性乳腺癌 / 耐药机制分析 / 澄清中→可规划 / 已确认「机制探索」 / 下一步「生成研究方案」
- 「技术细节」默认关闭；第一层无 route、无 `retrieval_status`、无医学限制常驻

**什么是HER2**

- 过程带：用户想法 + 「这不是研究对象，不会写入研究目标。」
- 摘要：还没有形成研究对象；阶段「概念说明」；下一步改写成「我想研究...」
- 无方向卡，不写 goal

---

## 4. 测试

| 集合 | 结果 |
|---|---|
| `backend/tests/v31_frontend` | passed |
| `backend/tests/v30` | passed |
| Phase 0 固定回归 234 | **234 passed / 0 failed** |

旧 `/` 仍是「发送并开始研究」。`/v31/` 仍是科研数据工作台。

---

## 5. 明确不做（留给后续 Phase）

- 左轨改成研究列表
- 多 session 快照与切换
- 新建研究时保留其它槽
- 把工程 Timeline 页从第一层拿掉
