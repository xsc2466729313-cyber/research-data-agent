# Research Workspace UX 计划

- 日期：2026-09-05
- 性质：前端工作空间设计，不是代码，不是授权改后端
- 基线：`RESEARCH_INTENT_UX_FIX_REPORT.md`
- 范围：只改 `frontend/v31/`
- 禁止：新增 API、改 `backend/app/v30/`、改旧 `frontend/`、用 localStorage 存科研内容

本文回答：如何把当前「单次 Copilot 屏幕」收成可切换、可回看、互不污染的科研工作空间。

---

## 0. 现状与要解决的问题

当前已经能：听懂「我想研究…」、分清闲聊/概念/科研、一次选一个方向。  
仍然是**一屏一次研究**：

| 问题 | 现在为什么会这样 |
|---|---|
| 没有连续过程记录 | Store 只留 `lastTurn` / `lastUserMessage`。上一次想法、方向卡、确认都被下一轮盖掉 |
| 无法回看研究过程 | Timeline 页是 API 事件卡；左轨是八步门。都不是「我说过什么、系统听成了什么」 |
| 不能并行管理多个问题 | Home 每次 `createSession()` 后 `reset()`，单例 `session-store` 只活一份。HER2 与超新星不能同时挂着 |
| Memory 和工程状态过多 | 右轨研究上下文 + 诚实边界 + 医学限制；左轨八门。第一层像调试台 |

后端其实已经按 `session_id` 隔离 Memory（`POST /api/v30/sessions`、`GET .../memory`）。  
缺的是前端工作空间：列表、切换、每项研究自己的过程记录和摘要。

### 目标

用户能同时放两扇窗：

- HER2 耐药研究
- Ia 超新星光变研究

各自独立 `session_id`、独立 Memory、独立过程时间线。切换时互不污染。  
中列回看的是研究过程，不是聊天气泡。右轨是研究摘要，不是裸 Memory。

### 非目标

- 不新增「列出全部 session」API
- 不把 Copilot 做成聊天窗 / 打字机 / 机器人
- 不把左轨八步做成假进度条
- 不把科研内容写入 localStorage
- 不改 Router / Copilot / Planner 语义
- 本阶段仍不做 Preview / Dataset / Execute

---

## 1. Research Workspace

工作空间是壳，不是新后端资源。  
一条「研究」= 一个已有 `session_id`。

```text
┌ 研究列表 ──────────┐  ┌ 当前研究 ─────────────────────┐  ┌ 研究摘要 ──┐
│ HER2阳性乳腺癌…    │  │ Conversation Timeline           │  │ 对象        │
│ Ia型超新星光变…    │  │ Next Action / 方向 / 澄清       │  │ 目标        │
│ + 新建研究         │  │                                 │  │ 阶段        │
└────────────────────┘  │                                 │  │ 已确认      │
                        │                                 │  │ 下一步      │
                        └─────────────────────────────────┘  │ 技术细节 ▸ │
                                                              └────────────┘
```

### 1.1 研究列表

左轨从「八步门墙」改成**研究列表**（门状态收到摘要「当前阶段」里）。

每项一行：

- 标题：`goal.object` 或 `topicFromRaw(raw_text)` 或「未命名研究」
- 一句阶段：澄清中 / 可规划 / 已有方案 / 概念说明 / 闲聊
- 当前项加字重或细竖线

操作：

| 动作 | 前端怎么做 | 后端 |
|---|---|---|
| 新建研究 | `POST /api/v30/sessions`，登记到工作空间索引，进入该 session 的 Copilot（可先 Onboarding） | 已有 |
| 切换研究 | 先把当前 Store 快照进该 session 槽，再 `go(#/r/{id}/copilot)`，灌回目标槽；`GET .../memory` 刷新 Memory | 已有 |
| 打开未知 hash | `GET memory` 成功则加入列表 | 已有 |
| 回首页 | 不销毁列表；Home 只负责「再开一项」 |

Home 不再是唯一入口。列表里的「新建研究」等于现在的 Home 开会话，但**禁止 `reset()` 掉其它研究的快照**。

### 1.2 每项研究的隔离边界

| 必须按 session 分开 | 现在为什么会串 |
|---|---|
| `session_id` / `memory` | 单例 Store |
| `lastTurn` / `lastRoute` / `lastUserMessage` | 单例 |
| 过程记录（见 §2） | 不存在 |
| Timeline 事件、`plan` / `discovery` / `selection` / `mappings` / `graph` | 单例 + `timeline-store` 模块级 `events` |
| pending-intent | 全局一份，切换前必须清空或跟 session 走 |

`pending-intent` 只属于「刚新建、尚未第一轮 turn」的那一项。切换走时带走或丢弃，不得写进另一项。

### 1.3 索引存什么（内存，不落盘）

工作空间索引只存指针和展示用短标题，不另造科研库：

```text
{ sessionId, title, stage, domain?, updatedAt }
```

标题、阶段从该槽的 Memory / lastTurn **派生**，不手写第二份 goal。  
刷新标签页后：列表可能空，但 hash 里的 `session_id` 仍能 `GET memory` 恢复**这一项**。不承诺刷新后还挂着未打开过的其它项——没有 list API，也不用 localStorage 偷存。

两枚浏览器标签分别打开 `#/r/{her2}/copilot` 与 `#/r/{sn}/copilot`，后端 Memory 已隔离；前端各有一份 Store，互不污染。同标签内并行靠列表 + 快照。

---

## 2. Conversation Timeline

中列增加**过程带**，在理解总结 / 方向卡 / Next Action **之上或左侧窄列**，不要做成聊天气泡。

### 2.1 记录什么

按发生顺序，一条一事：

| 类型 | 用户看见 | 数据从哪来 |
|---|---|---|
| 用户想法 | 原句「我想研究…」 | `lastUserMessage` / 本轮提交；入槽日志 |
| AI理解 | 「你希望研究 {topic}」 | `understood_goal` / `raw_text` / `intentOf` |
| 方向建议 | 当时给出的方向标签 | DirectionAssist / `clarifying_questions` |
| 用户确认 | 点过的方向或 option | 提交的完整科研句或 option 原文 |
| 研究进展 | 已可规划 / 已生成方案 / 已发现来源… | `ready_for_planner`、`plan`、后续 Store 字段存在性 |

不是：

- `user` / `assistant` 气泡
- 打字机
- 把 `blocked_reason`、`route` 当正文

### 2.2 如何在没有新 API 的情况下累积

后端不返回历史 turn 列表。过程带是**前端按 session 追加的日志**：

1. 每次 `sendTurn` / 点方向卡 / 点澄清 / `planSession` 成功，往**当前 session 的 log** 推一条。
2. 切换研究时 log 跟快照走。
3. 仅有 `GET memory`、没有 log 时（刷新后只开这一项）：用 Memory **投影最少几条**——有 `raw_text` → 一条用户想法；有 goal → 一条理解；有已答 clarifications → 若干确认。不编造没发生过的方向卡。

诚实：刷新后过程带可能短于本页停留期间。摘要仍以 Memory 为准。

### 2.3 和现有 Timeline 页的关系

| | Conversation Timeline | `#/r/{id}/timeline` |
|---|---|---|
| 给谁看 | 研究者回看「想了什么、选了什么」 | 回看 API 门是否发生 |
| 默认 | Copilot 工作空间第一层 | 生成方案后的工程页 |
| 仍保留 | 是 | 是，不删 |

左轨八门不再默认铺开。工程 Timeline 页可继续用门 + 事件卡（人话标题，API 作小字）。

---

## 3. Research Summary

右轨「研究上下文 / 裸 Memory 字段」改成**研究摘要**。仍只读现有 Memory + Store，不新字段。

默认五块，顺序固定：

| 块 | 来源 | 空时 |
|---|---|---|
| 研究对象 | `goal.object` 或 `topicFromRaw(raw_text)` | 「还没有形成研究对象」（概念/闲聊） |
| 研究目标 | `goal.target` | 「尚未选定」——科研意图未齐时允许，不当闲聊 |
| 当前阶段 | `projectGates` 投成中文：澄清中 / 可规划 / 已有方案 / 已发现来源… | 「刚创建」 |
| 已确认内容 | `clarifications` 中已有 `answer` 的问答；方向卡确认句 | 「尚无确认」 |
| 下一步 | 与 NextActionCard 同一套投影 | 选择方向 / 生成方案 / 说出想法 |

CONCEPT_QA：对象空、阶段写「概念说明」，下一步写改写成「我想研究…」。  
CHAT：摘要标明闲聊，不写入研究对象。

不再默认展示英文 `goal` / `clarifications` / `constraints` 字段名。  
`domain=oncology|astronomy` 不做成徽章墙；需要时放进 Context Drawer。

---

## 4. Context Drawer

把工程态从第一层拿走。右轨底部或摘要下一条「技术细节」，默认收起。

展开才见：

| 内容 | 来源 | 注意 |
|---|---|---|
| 内部路由 | `route.route` CHAT/CONCEPT_QA/CLARIFY/PLAN | 不是导航 |
| `retrieval_status` | 数据需求隐藏表 | 不画成红错 |
| Evidence / 图理解 | 仅当该 session 已有 graph / figure 回包 | 「图理解不入库」 |
| 用户限制 constraints | `memory.constraints` | 从摘要详情挪到这里 |
| `ready_for_planner` 字面量、`blocked_reason` | 可放最底 | 第一层禁止 |

诚实边界、医学限制：从常驻右轨改为 Drawer 内一节，或顶栏「说明」一次打开。第一层不再三块说明书压住摘要。

`#shell-error` 仍不展示 `research_goal_not_ready`。

---

## 5. 多研究隔离（验收场景）

### 5.1 同标签：HER2 窗 + 超新星窗

1. 新建「我想研究HER2阳性乳腺癌耐药机制」→ 列表项 A，session `s1`。
2. 再新建「我想研究Ia型超新星光变曲线」→ 列表项 B，session `s2`。**A 的 Memory / 过程 log / lastTurn 仍在。**
3. 在 B 选「光变曲线建模」后切回 A：仍是 HER2 理解 + 机制/疗效（或已确认），**没有**超新星方向卡，没有超新星 `raw_text`。
4. 再切回 B：仍是超新星对象与方向，**没有** HER2 疗效确认。

`GET /api/v30/sessions/{id}/memory` 以当前 id 为准。禁止把 A 的 turn 发到 B 的 session。

### 5.2 两标签

标签 1：`#/r/{s1}/copilot`  
标签 2：`#/r/{s2}/copilot`  

后端会话本就隔离。前端不要用共享 localStorage 同步，以免串题。

### 5.3 禁止

- 新建研究时 `reset()` 掉整个工作空间
- 方向卡 message 写错 session
- 用 HER2 关键词点亮超新星的医学门（门投影仍只认**当前槽** Store 字段）
- 把两个 goal 拼进同一份 Memory

---

## 6. 页面结构与交互

### 6.1 信息架构

```text
第一层
  研究列表（左）
  过程带 + 当前决策（中：理解 / Why / 方向或澄清 / Next Action）
  研究摘要（右）

第二层
  补充限制输入（Copilot 底部，仍弱）
  数据需求折叠

第三层（Drawer）
  route / retrieval_status / constraints / evidence
  诚实边界 / 医学限制
```

### 6.2 交互流程

```text
Home 或「新建研究」
  → POST /sessions → 索引 + 快照槽
  → Onboarding / 开始研究 → turn 写入该槽 log
  → 过程带追加：用户想法 → AI理解 → 方向建议

选方向 / 澄清
  → sendTurn(本 session)
  → log：用户确认
  → 摘要更新对象/目标/已确认/下一步

生成方案
  → POST /plan（本 session）
  → log：研究进展
  → 可进入该 session 的工程 Timeline

切换研究
  → 快照当前槽 → 换 hash → 灌回目标槽 → GET memory
  → 中列过程带与摘要换成目标研究
```

闲聊、概念仍可发生在某个 session 里，但列表标题不要写成研究对象；摘要保持「不是研究目标」。

### 6.3 视觉

- 不是卡片墙、不是多聊天列
- 过程带：时间向下，类型用短标签，不要头像
- 研究列表宽度接近现在左轨
- 主按钮每屏仍最多一个（新建 / 开始研究 / 生成方案）
- 方向卡仍是决策，不是第二颗墨底按钮

---

## 7. 字段映射（不新增 API）

| 用户看见 | 已有来源 |
|---|---|
| 研究身份 | `session_id` |
| 列表标题 | `memory.goal` / `raw_text` / `topicFromRaw` |
| 列表阶段 | 当前槽 `projectGates` + `ready_for_planner` + intent |
| 过程：用户想法 | 该槽 log ← `sendTurn` 的 message |
| 过程：AI理解 | `understood_goal` / 理解条同一套投影 |
| 过程：方向建议 | 当时渲染的 DirectionAssist / `clarifying_questions` |
| 过程：用户确认 | option 原文或拼好的「我想研究…」 |
| 过程：进展 | `plan` / `discovery` / … 字段是否存在 |
| 摘要五块 | Memory + Next Action 投影 + gates |
| Drawer | `route`、needs.`retrieval_status`、`constraints`、graph/figure 回包 |

网络请求仍只是现有 `/api/v30/sessions`、`/route`、`/copilot/turn`、`/memory`、`/plan` 及后续发现/映射/图。不增 list、不增 history。

---

## 8. 建议改动文件（实施时才动）

| 文件 | 职责 |
|---|---|
| `frontend/v31/app/workspace-store.js`（新建） | 研究索引 + 每 session 快照 + log；禁止串槽 |
| `frontend/v31/app/session-store.js` | 变成「当前槽」视图，或由 workspace 灌入 |
| `frontend/v31/app/pages/home.js` | 新建研究不 `reset()` 整个工作空间 |
| `frontend/v31/app/pages/copilot.js` | 写 log；装过程带 |
| `frontend/v31/app/pages/timeline.js` | 事件按 session 分槽 |
| `frontend/v31/app/timeline-store.js` | `events` 按 `sessionId` 分桶 |
| `frontend/v31/app/components/research-list.js`（新建） | 列表 / 新建 / 切换 |
| `frontend/v31/app/components/conversation-timeline.js`（新建） | 过程带，非气泡 |
| `frontend/v31/app/components/research-summary.js`（新建） | 替代 memory-rail 第一层 |
| `frontend/v31/app/components/context-drawer.js`（新建或扩 why-drawer） | 技术细节 |
| `frontend/v31/index.html` | 左轨改为研究列表；右轨改为摘要 |
| `frontend/v31/copy/honesty.zh.js` | 阶段中文、过程类型标签 |
| `backend/tests/v31_frontend/test_research_workspace_ux.py`（实施时） | 隔离与无 localStorage |

不改：`app/api/v30.js`、后端、旧 frontend。

### 建议实施顺序

1. workspace-store：快照 / 切换 / 新建不摧毁其它槽  
2. 研究列表替换左轨八门  
3. Research Summary 替换右轨 Memory  
4. Conversation Timeline（先 log，再 Memory 回放）  
5. Context Drawer，收起诚实/医学/route  
6. 手验 HER2 + 超新星同页切换  
7. `v31_frontend` + `v30` + 234  

---

## 9. 验收

1. 可新建两项研究并在列表间切换，hash 与 `session_id` 一致。  
2. HER2 窗的确认不会出现在超新星窗；超新星方向卡不会出现在 HER2 窗。  
3. Copilot 能回看：用户想法 → AI理解 → 方向建议 → 用户确认，无聊天气泡。  
4. 右轨先看到对象 / 目标 / 阶段 / 已确认 / 下一步，而不是英文 Memory。  
5. route、`retrieval_status`、constraints 默认在 Drawer 里。  
6. 无新 API；无科研 localStorage。  
7. 「什么是HER2」仍不写研究目标；「你好」仍是闲聊。

---

## 10. 明确不做

- 不向后端要 session 目录或 turn 历史  
- 不用 localStorage / IndexedDB 持久化 goal、log、字段  
- 不把过程带做成聊天产品  
- 不删除工程 Timeline 页，只把它降为第二层  
- 本文件先评审，再单独开实施
