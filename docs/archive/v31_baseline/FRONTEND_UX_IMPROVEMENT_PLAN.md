# V3.1 Research Copilot UX 改进计划

- 日期：2026-09-05
- 性质：前端交互与信息架构计划，不是代码，不是授权改后端
- 范围：只改 `frontend/v31/`
- 禁止：新增 API、改 `backend/app/v30/`、改旧 `frontend/app.js`

本文回答：如何把当前 Copilot 从「状态展示 / 调试面板」收成「AI 科研助手引导页」。

---

## 0. 现状诊断（基于当前代码）

当前页面：`frontend/v31/app/pages/copilot.js`

默认一屏同时出现：

| 区块 | 现在长什么样 | 问题 |
|---|---|---|
| Route pills | `CHAT / CONCEPT_QA / CLARIFY / PLAN` | 内部路由，用户不需要 |
| Understanding Bar | `对象 / 目标 / 领域` 三列 | 像字段表，不像理解总结 |
| `blocked_reason` | 原样横幅 | 经常是代码味文案 |
| `user_visible_reply` | 灰字长段 | 与理解条、澄清卡重复 |
| 数据需求表 | 类别 / 说明 / `retrieval_status` | 调试表；「未检索」被当成失败 |
| 澄清卡 | 细线选项 | 不像下一步决策 |
| `ready_for_planner=true` | 明文 | 开发状态 |
| 生成研究方案 | **未 ready 也显示**，旁注「后端会返回 research_goal_not_ready」 | 教用户去撞 422 |
| `#shell-error` | 失败时写错误码 | 调试台 |
| 右轨 Memory | `goal / clarifications / constraints` 全开 | 术语外露 |
| 左轨 | 八门 + `idle/ready/blocked` | 后台流程图 |

首次进入：Home 写入 `pending-intent` 后，Copilot **自动** `sendTurn`，没有欢迎、没有能力说明、没有「开始研究」。

结论：信息架构按 API 字段铺开，而不是按「我理解了什么 → 你现在要做什么 → 下一步点哪里」。

---

## 1. 目标与非目标

### 目标

用户 8 秒内能回答三句：

1. 系统听懂了我要研究什么？
2. 我现在该选什么 / 补充什么？
3. 什么时候可以生成方案？

### 非目标

- 不做聊天窗、不做打字机、不做机器人形象
- 不新增 `/api/v30` 字段
- 不把 Timeline 做成假进度百分比
- 不在 Copilot 展示来源、映射、图、预览、数据集
- 不改 Router / Copilot / Planner 后端语义
- 不默认展示「已检索 / 已覆盖 / 已完成」

仍遵守：主按钮不叫「发送并开始研究」；CONCEPT_QA 不把概念问答写成研究目标。

---

## 2. 信息架构（只读已有回包）

数据仍只来自现有字段，只改呈现优先级。

```text
第一层（默认看见）
  AI 理解总结     ← understood_goal 或 memory.goal + user_visible_reply 压缩
  当前任务        ← 一句话：澄清中 / 可以规划 / 这是概念问答
  下一步          ← clarifying_questions[0] 或「生成研究方案」

第二层（需要时）
  补充说明输入框
  数据需求建议    ← category + description，不露 retrieval_status

第三层（展开才见）
  路由 CHAT/CONCEPT_QA/CLARIFY/PLAN
  retrieval_status
  blocked_reason / lastError.error
  ready_for_planner 字面量
  Memory 明细
```

字段映射（不改 API）：

| 用户看到的 | 后端字段 | 默认 |
|---|---|---|
| 理解总结 | `understood_goal.object/target/domain` + 短回复 | 显示 |
| 当前任务 | 由 `route.route` + `ready_for_planner` + 是否有 question **投影成中文** | 显示 |
| 下一步问题 | `clarifying_questions[0].question` + `options[]` | 显示 |
| 开始研究 | 现有 `pending-intent` + `copilot/turn` | 仅首次 |
| 生成研究方案 | `POST /plan`，仅 `ready_for_planner===true` | 条件显示 |
| 研究上下文 | `memory.goal` 一行 | 折叠 |
| 调试详情 | `route` `blocked_reason` `retrieval_status` `lastError` | 折叠 |

「当前任务」投影规则（前端文案，不新增状态机）：

| 条件 | 当前任务 | 下一步 |
|---|---|---|
| 无 `lastTurn` | 还没开始这次研究 | 点「开始研究」或写下想法 |
| `route===CONCEPT_QA` 或 `CHAT` | 这是说明，不是一次取数 | 若要做研究，请说出「我想研究…」 |
| 有 `clarifying_questions[0]` | 需要你确认一个问题 | 点大卡片选项 |
| `ready_for_planner===true` | 目标已经够清楚 | 生成研究方案（仍不取数） |
| 其他 | 继续补充约束或修正目标 | 底部输入框 |

禁止把 `awaiting_clarification`、`not_a_research_request`、`research_goal_not_ready` 写在第一层。

---

## 3. 首次进入 Onboarding

### 何时出现

同时满足：

- 当前 hash 是 `#/r/{session}/copilot`
- `lastTurn` 为空
- 尚未点过本页「开始研究」

Home 案例点击后：**停止自动 `sendTurn(pending)`**。  
pending 仍由 Home 写入，但改由 Onboarding 的「开始研究」消费。

刷新且 Memory 已有 goal、但 `lastTurn` 空：跳过欢迎长文，直接进入主区域（用 Memory 画理解总结），避免每次刷新都迎新。

### 默认内容（只前端文案）

**欢迎语**

> 我是科研数据助手。先听懂你的研究想法，再决定要不要规划。这一步不找数据、不生成数据表。

**系统能力（三条，不要做成功能墙）**

- 听懂研究对象、目标和限制
- 一次只问一个关键问题
- 澄清之后才生成研究方案；发现和执行在后面

**主按钮**

- 有 pending：「开始研究」→ `takePendingIntent()` + `POST /api/v30/copilot/turn`
- 无 pending：主按钮禁用或改为「请先写下想法」，输入框在卡片内

不要出现：Route pills、数据需求表、`retrieval_status`、方案按钮。

### 视觉

中列一张安静卡片：标题 + 三行能力 + 一个主按钮。  
不要插画、不要轮播、不要「跳过」进调试全景。

---

## 4. Copilot 主区域（进入研究后）

中列只保留三块主视觉，顺序固定：

### 4.1 AI 理解总结

替换现在的三列表 + 大段 `reply-block` 并排。

默认展示一段话，例如：

> 你想研究 **HER2阳性乳腺癌**，当前目标偏向 **疗效预测**。  
> 建议的数据方向还只是清单，没有检索任何公开数据集。

来源：优先 `user_visible_reply` 压成 2–3 句；若过长，只用 `object / target` 拼一句，原文放进「详情」。  
CONCEPT_QA：明确写「这不是研究对象，不会写入研究目标。」

不要默认展示 `domain=oncology` 作为徽章墙。领域可放在折叠的研究上下文里。

### 4.2 当前任务

一行，不用表。

例：

- 「请确认研究重点」
- 「可以生成研究方案了（不会取数）」
- 「这是概念说明，不是一次数据任务」

### 4.3 下一步问题

有澄清：只渲染 **一个** 问题 + 大卡片选项（见第 6 节）。  
无澄清且 ready：主按钮就是「生成研究方案」。  
无澄清且未 ready：只留补充输入，不放方案按钮。

数据需求从主视觉撤下：改为「建议关注的数据类型」折叠列表，只显示 `category` 与 `description`。表头禁止出现 `retrieval_status`。折叠标题可用已有诚实句「数据需求建议尚未检索」。

---

## 5. 隐藏开发状态

默认删除或移入 `<details>`「技术细节」：

| 现在 | 处理后 |
|---|---|
| Route pills | 折叠；文案改「内部路由」，仍不要当导航 |
| `ready_for_planner=true` | 删除明文；只用它控制方案按钮 |
| `blocked_reason` 横幅 | 折叠；第一层改写为「当前任务」中文 |
| `research_goal_not_ready` / `#shell-error` | Copilot **不展示** 该错误码（见第 7 节） |
| 数据需求第三列 | 默认不渲染 |
| 旁注「将调用 /plan」「后端会返回 422」 | 删除 |
| Memory 英文字段名 | 改中文并折叠 |

展开后仍必须诚实：可以看到 `not_retrieved`，但不能把它画成红错。

`#shell-error`：Copilot 调用 `onError` 时，对 `research_goal_not_ready` **不要写入可见错误条**。其他真正的网络失败可以留在右轨，但不要用英文 error key 当主文案。

---

## 6. 澄清问题：大卡片按钮

文件：`frontend/v31/app/components/clarify-card.js` + `styles/pages/copilot.css`

规则：

- 仍只取 `questions[0]`（后端已是最多一个）
- 问题作大标题，不用 `stage-kicker「澄清问题」` 当主视觉
- 每个 `options[]` 做成整行大按钮：更高点击区（建议最小高度 52px）、短说明可复用选项原文
- 一次只能点一个；点完立刻 `copilot/turn`，与现在相同
- 「当前没有待澄清问题」在 ready 时不要占一整块——直接让位给方案按钮
- 自由输入保留在卡片下方，标题改为「补充限制或修正」，placeholder 仍可用「排除 METABRIC」

不要做成单选 radio 群再二次确认。一步即提交。

---

## 7. 生成研究方案

| `ready_for_planner` | UI |
|---|---|
| `true` | 显示主按钮「生成研究方案」；短提示只用用户语言：「生成方案，不发现来源，不执行。」 |
| `false` / 空 | **隐藏按钮**（推荐）或 `disabled` 且无 422 旁注 |

禁止：

- 未 ready 仍可点、等后端 422
- 展示 `research_goal_not_ready`
- 展示 `honestyFor("research_goal_not_ready")` 红条作为主反馈
- 旁注「未澄清时仍可请求」

成功：`POST /api/v30/plan` 后仍跳 `#/r/{session}/timeline`。  
失败且非 422：右轨一句「暂时无法生成方案」，不把 `error` 字面量铺在中列。

CONCEPT_QA / CHAT：即使误点，按钮也应隐藏（`ready_for_planner` 为假时自然隐藏）。

---

## 8. Memory → 研究上下文（折叠）

文件：`frontend/v31/app/components/memory-rail.js`、`frontend/v31/index.html` 右轨 `#memory-block`

默认：

```text
研究上下文
HER2阳性乳腺癌 · 疗效预测
已记录 1 条确认 · 无额外限制
```

点击「查看详情」展开：

- 研究对象 / 分析目标 / 领域
- 已确认的问题与回答
- 用户限制（如排除 METABRIC）

默认不显示英文 `goal` `clarifications` `constraints`。  
无 goal：一行「还没有形成研究对象」。

Timeline / Sources / Mapping / Graph 若继续打开 `#memory-block`，必须同样走折叠摘要，禁止再露出空的「Memory」调试盒。本计划优先改 Copilot；其他页只要求不回退成全开字段表。

---

## 9. 左侧 Timeline 弱化

文件：`frontend/v31/app/pages/timeline.js` 的 `railMarkup`、`gate-node.js`、`styles/components/gates.css`、`index.html` 左轨文案

从「后台流程图」改为「研究进程」：

1. 左轨标题由「流程」改为「研究进程」。
2. 说明由门/回包术语改为：「只标记已经发生的步骤，不是完成度。」
3. **不要默认显示** 英文 `idle / ready / blocked / executed`。改映射：
   - `idle` → 不写状态，或写「未到」
   - `ready` → 「已记录」
   - `blocked` → 「需确认」（琥珀点保留）
   - `executed` → 「已执行」（本阶段不会在 Copilot 出现）
4. Copilot 期间只强调前三步：科研问题、AI理解、研究规划。后五步仍列出但降对比（更灰、更小），避免像监控台。
5. 当前步用一条细竖线或字重表示，不要进度条、不要百分比、不要绿勾墙。
6. Timeline 全页可以保留事件列表，但事件卡默认显示人话（「已创建会话」），API 路径放到第二行小字或展开。

跳转逻辑不变：未解锁仍回 Timeline，不新造门状态算法。仍只认 SessionStore 字段存在性。

---

## 10. 建议改动文件（实施时才动）

只列计划，本文件不改这些文件。

| 文件 | 计划中的职责 |
|---|---|
| `frontend/v31/app/pages/copilot.js` | Onboarding 门；取消自动 turn；方案按钮条件渲染；不把 422 推到中列 |
| `frontend/v31/app/components/understanding-bar.js` | 改成理解总结，而不是三列表 |
| `frontend/v31/app/components/clarify-card.js` | 大卡片选项；无问题时不占主位 |
| `frontend/v31/app/components/data-need-table.js` | 降为折叠；去掉默认 `retrieval_status` 列 |
| `frontend/v31/app/components/memory-rail.js` | 研究上下文摘要 + 详情 |
| `frontend/v31/app/components/gate-node.js` | 状态中文；弱化后步 |
| `frontend/v31/app/pages/timeline.js` | 左轨标题与当前步强调 |
| `frontend/v31/copy/honesty.zh.js` | 欢迎语、能力三条、当前任务文案（集中，页面不手写「已覆盖」） |
| `frontend/v31/styles/pages/copilot.css` | 大卡片、onboarding、主区留白 |
| `frontend/v31/styles/components/gates.css` | 研究进程弱化 |
| `frontend/v31/index.html` | 左轨「研究进程」；右轨「研究上下文」 |

不改：`frontend/v31/app/api/v30.js`、后端、旧 frontend。

可选极小 Store：本页模块级 `onboardingSeen`（内存即可）。**不要**用 localStorage 存科研内容；若只存「已看过欢迎」，也必须不写 goal/字段。更稳：用 `lastTurn` 是否存在判断，零新键。

---

## 11. 页面状态草图

### Onboarding

```text
左：研究进程（前三步轻亮）
中：
  欢迎语
  · 听懂想法
  · 一次一问
  · 先方案后发现
  [ 开始研究 ]
右：研究上下文（还没有研究对象）
```

### 澄清中

```text
中：
  理解总结（2 句）
  当前任务：请确认研究重点
  你的研究重点是机制探索还是疗效预测？
    [ 机制探索 ]     ← 大卡片
    [ 疗效预测 ]
  补充限制或修正
右：研究上下文 ▸
```

### 可规划

```text
中：
  理解总结
  当前任务：可以生成研究方案了
  [ 生成研究方案 ]
  补充限制或修正
右：研究上下文 ▸ HER2阳性乳腺癌 · 疗效预测
```

### 概念问答

```text
中：
  理解总结：这是说明，未写入研究目标
  当前任务：若要做研究，请用「我想研究…」
  （无方案按钮）
```

---

## 12. 视觉约束

- 中列仍是阅读宽，不要卡片墙
- 主按钮每屏最多一个：开始研究 **或** 生成研究方案 **或** 无
- 大卡片选项是决策，不是主按钮；墨底只给当前真正的前进一步
- 动效不超过现有 180–200ms；`prefers-reduced-motion` 瞬时
- AUTO/READY 不用绿表示完成
- 留白优先：理解总结与下一步之间至少一组 `space-3`

---

## 13. 测试与回归（实施阶段才跑）

现有 `backend/tests/v31_frontend/test_phase1_copilot.py` 会受文案影响，实施时只改断言呈现，不改 API 契约：

必须保持：

- 仍调用 `copilotTurn` / `getMemory` / `planSession`
- CONCEPT_QA 不写 goal
- 数据需求若展开仍能读到 `not_retrieved`（可在详情里）
- 无 `chat-bubble`、无打字机、无「发送并开始研究」
- 无 `/api/v30/integration`、无 `localStorage` 科研数据
- 旧 `/` 不变

建议新增（实施时）：

- 无 `lastTurn` 时源码/结构含欢迎语与「开始研究」
- `ready_for_planner` 为假时页面不含「生成研究方案」或按钮 disabled
- 默认 DOM/源码主路径不含 `retrieval_status` 表头、不含 `ready_for_planner=true`、不含 Route pills
- 左轨不含默认英文 `idle` 作为用户主文案（实现可用 data 属性保留状态）

实施后仍跑：`v31_frontend` + `v30` + 234。本计划阶段不跑、不改测试。

---

## 14. 验收标准

1. 从 Home 点 HER2，先看到欢迎与「开始研究」，不自动铺调试字段。
2. 开始后中列先是理解、当前任务、一个问题；选项是大卡片。
3. 未确认前看不见「生成研究方案」，也看不到 422 / `research_goal_not_ready`。
4. 确认疗效预测后，方案按钮出现；点下后仍进 Timeline，且不取数。
5. Memory 默认一行上下文；展开才见明细。
6. 左轨读起来像研究进程，不像后台流程图。
7. 「什么是HER2」仍不写入研究对象。
8. 后端零改动，网络面板里 API 集合与现在相同。

---

## 15. 明确不做

- 不改 Copilot 后端回复（包括「尚未挂载 Planner」那句——若出现，前端第一层应改写/截断，不新增 API 去修）
- 不在本计划实现 Preview / Dataset
- 不把 Onboarding 做成强制问卷
- 不把左轨八步删掉，只减弱
- 本文件发布后先评审，再单独开实施任务

---

## 16. 实施顺序建议

1. 停掉 Copilot 自动 `sendTurn(pending)`，加上 Onboarding  
2. 藏 Route / ready 明文 / 422 / retrieval 列  
3. 理解总结 + 当前任务 + 大卡片澄清  
4. 方案按钮条件显示  
5. 研究上下文折叠  
6. 左轨弱化  

一次只交一屏。做完用 HER2 与「什么是HER2」两条路径手验，再改 Phase 1 测试断言。
