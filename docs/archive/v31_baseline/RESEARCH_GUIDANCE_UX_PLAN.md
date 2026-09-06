# V3.1 Research Guidance UX 计划

- 日期：2026-09-05
- 性质：前端引导体验设计，不是代码，不是授权改后端
- 基线：`FRONTEND_UX_PHASE_REPORT.md`
- 范围：只改 `frontend/v31/`
- 禁止：新增 API、改 `backend/app/v30/`、改旧 `frontend/`

本文回答：如何把 Copilot 从「等待用户回答问题」收成「帮助用户形成科研问题」。

---

## 0. 现状与目标

上一轮已经做到：

- 先欢迎，再 `sendTurn`
- 中列是理解总结 → 当前任务 → 下一步问题
- 方案按钮只在 `ready_for_planner===true` 出现
- 开发状态默认折叠

还没做到的是**成题**：

| 用户此刻 | 现在系统做什么 | 用户感受 |
|---|---|---|
| 有对象、有待澄清问题 | 甩出「机制探索 / 疗效预测」 | 像考试，不知道为什么要选 |
| 有对象、没有 target、也没有 question | 「继续补充约束或修正目标」+ 空输入框 | 不知道写什么 |
| 「什么是HER2」 | 说明概念，停住 | 知道这不是研究，但不会自己改写成研究问题 |
| 「我还没想好研究方向」 | 可能进 CHAT，或卡在空输入 | 系统在等我先会提问 |
| 已 ready | 「生成研究方案」 | 这一步是清楚的，应保留 |

结论：第一层还在问「请回答」，没有解释「差哪一块、选了会改变什么、不知道时怎么往前走」。

### 目标

用户始终能回答四句：

1. 系统已经听懂了哪一部分？
2. 为什么现在还不能规划？
3. 如果我不确定，系统建议我先按哪条走？
4. 我现在该点哪一个下一步？

### 非目标

- 不改 Router / Copilot / Planner 语义
- 不新增 `/api/v30` 字段（没有 `rationale`、`recommended_option`、`unsure`）
- 不把 Copilot 做成多页问卷、量表、角色选择
- 不做聊天窗、打字机、机器人形象
- 不假装新模型推理；推荐必须能追溯到已有回包字段
- 不在本阶段做 Preview / Dataset / Execute
- 主按钮仍不叫「发送并开始研究」
- CONCEPT_QA 仍不得写入研究目标

---

## 1. 设计原则：成题，不是问卷

科研过程不是把用户填满一张表。后端本来就只允许**一次一个** `clarifying_questions[0]`。前端必须守住这条，并把「问」改成「帮用户作一个研究判断」。

| 要做 | 不要做 |
|---|---|
| 解释这一问会改变后面看什么证据 | 连续抛出对象 / 人群 / 终点 / 数据源四问 |
| 用已听懂的对象，建议一条可提交的选项 | 让用户从空白输入框发明研究方向 |
| 「不确定」展开同一问的对比，再确认建议 | 「不确定」再开一轮新问卷 |
| Next Action Card 永远只有一个主行动 | 一屏两个墨底主按钮抢注意力 |
| 方向辅助先在本地选好一句「我想研究…」再 `sendTurn` | 把「我不知道」原文丢给 CHAT 然后停住 |

诚实口径：页面上的「AI 建议」是**前端投影**，来自 `understood_goal` / `memory.goal` / `clarifying_questions[0].options` / `suggested_data_needs` / `route.route`。不是新接口，也不是诊疗建议。

医学边界不变：HER2 IHC 2+ 不自动 Positive；ERBB2 CNA ≠ IHC；AUC/IC50 ≠ pCR；禁止跨研究 Join。推荐文案不得写成诊断或疗效承诺。

---

## 2. 页面结构

Copilot 中列第一层固定为四块，顺序不变。第二层、第三层沿用上一轮。

```text
第一层（默认看见）
  1. 理解总结          已经听懂的对象 / 目标；或「这不是研究对象」
  2. 为什么要确认      仅目标未齐时出现；一句话，不露 error code
  3. 澄清决策          仅有 clarifying_questions[0] 时出现
       背景解释
       选项（可带「建议」标记）
       不确定入口（同卡展开，不是新页）
  4. Next Action Card  永远在；告诉用户现在点哪里

第二层（需要时）
  补充限制或修正
  建议关注的数据类型（折叠）

第三层（展开才见）
  技术细节 / retrieval_status / route
  研究上下文明细
```

左轨、右轨不改产品语义：左轨仍是研究进程，右轨仍是研究上下文摘要。

### 各状态中列草图

**目标模糊（有对象、无问题、未 ready）**

```text
理解总结：你想研究 乳腺癌，分析目标还没成形。
为什么要确认：还缺「想回答什么」。没有目标就不能规划，也不会去找数据。
（无澄清卡）
Next Action：先选定一个可研究的问题
  [ 从常见方向里选 ]     ← 主行动，打开方向辅助
  或自己写一句「我想研究…」
```

**有澄清问题**

```text
理解总结：你想研究 HER2阳性乳腺癌，当前目标偏向 耐药机制分析。
为什么要确认：机制探索和疗效预测后面看的证据不一样。现在选，是为了形成研究问题，不是取数。
澄清：
  背景：……
  [ 机制探索 ]  建议
  [ 疗效预测 ]
  还不确定 → 展开对比，主行动变成「先按建议走」
Next Action：确认研究重点（或「采用建议：机制探索」）
```

**不知道研究方向（本地辅助，尚未 sendTurn）**

```text
理解总结：还没有形成研究对象。
为什么要确认：先有一句能规划的研究问题，系统才听得懂。
方向辅助（本地，不是问卷）：
  我想研究HER2阳性乳腺癌耐药机制
  我想研究Ia型超新星光变曲线与红移的关系
  先弄清一个概念（不会写入研究目标）
Next Action：用选中的那一句开始
```

**概念问答**

```text
理解总结：这不是研究对象，不会写入研究目标。
为什么要确认：概念说明不能生成方案。若要做研究，需要改写成「我想研究…」。
Next Action：把这个概念变成研究问题
  [ 我想研究 HER2 相关问题 ]
```

**已可规划**

```text
理解总结：对象 + 目标已齐。
（无「为什么要确认」）
Next Action：生成研究方案（不发现来源，不执行）
```

主按钮规则仍是每屏最多一个墨底：方向辅助确认 **或** 采用建议 **或** 生成研究方案 **或** 开始研究。选项卡是决策，不是第二颗主按钮。

---

## 3. 交互流程

全程仍只调用已有接口：`POST /api/v30/copilot/turn`、`GET .../memory`、`POST /api/v30/plan`。用户点选项时，提交的仍是选项原文或一句完整研究陈述。

```text
Home
  ├─ 有明确想法 / 案例     → pending → Onboarding → 开始研究 → turn
  └─ 「还没想好研究方向」  → Copilot 本地方向辅助（先不 turn）
                              └─ 选出一句「我想研究…」或「什么是…」再 turn

turn 之后
  CONCEPT_QA / CHAT
      → 解释不是研究目标
      → Next Action：改写成研究问题（本地拼「我想研究…」再 turn）
      → 不写 goal，无方案按钮

  CLARIFY 且有 questions[0]
      → 解释为什么要确认
      → 大卡片；可标建议
      → 不确定：同卡对比 → 确认建议选项（turn 提交选项原文）
      → 未确认前无方案按钮

  CLARIFY 但无 question、无 target
      → 解释缺分析目标
      → Next Action 打开方向辅助，选项必须能被现有抽取听懂
      → 不新造后端问题

  ready_for_planner===true
      → Next Action = 生成研究方案
      → 成功跳 Timeline，不取数
```

### 3.1 为什么需要澄清

前端用已有字段投影一句人话，**禁止**把 `awaiting_clarification` / `research_goal_not_ready` / `not_a_research_request` 写到第一层。

| 条件 | 用户看到的「为什么」 |
|---|---|
| `clarifying_questions[0]` 存在 | 这一问会决定后面看机制证据还是结局/响应证据。现在选是为了形成研究问题，不是取数。 |
| 有 `object`、无 `target`、无 question | 已经有对象，但还没有「想回答什么」。没有分析目标就不能规划。 |
| 无 `object` 且不是 CONCEPT_QA | 还没有研究对象。先说出对象，或从常见方向里选一句。 |
| `route===CONCEPT_QA` 或 `CHAT` | 这是说明或闲聊，不会写入研究目标，因此不能生成方案。 |
| `ready_for_planner===true` | 不显示「为什么要确认」。 |

背景解释挂在**当前这一问**上，不展开成知识课。焦点问（`question_id===research_focus` 或问题文本含「机制探索 / 疗效预测」）用固定短文案：

- 机制探索：更靠近通路、耐药、分子改变；后面的数据需求仍只是建议，尚未检索。
- 疗效预测：更靠近治疗响应、结局；细胞系敏感性不能当成患者疗效。

其他未知 `question_id`：只用 `user_visible_reply` 压成一句，不编造学科讲义。

### 3.2 推荐选项与 AI 建议

后端选项只有 `clarifying_questions[0].options`（当前焦点问是「机制探索」「疗效预测」）。前端不得增删选项，只能**标记其中一个为建议**。

建议规则（只读已有字段，按序命中第一条）：

1. `goal.target` 含「耐药 / 机制」且不含「疗效 / 预测」→ 建议「机制探索」
2. `goal.target` 或 `goal.raw_text` 含「疗效 / 预测 / pCR / response」→ 建议「疗效预测」
3. `suggested_data_needs` 同时偏 `drug_response` 与机制类，且 target 已是耐药机制分析 → 仍建议「机制探索」
4. 否则不标建议，只保留选项，避免假装很懂

建议标记写「建议」，旁注最多一句：「因为已经听到你在谈{target}。」  
不要写「AI 已决定」「最优」「准确率」。

点建议项与点普通项相同：立刻 `sendTurn(option)`。不要先弹确认再二次提交。

### 3.3 「不确定」入口

「还不确定」不是新问题，也不是新 API。

1. 点击后在同一张澄清卡内展开对比：每个选项一行「选它意味着什么」。
2. Next Action 主按钮改成「先按建议走：{option}」。
3. 点主按钮或点选项，都提交**后端已有的 option 原文**。
4. 用户仍可用底部输入框自己改写；能被后端识别的只有现有答案词（「疗效预测」「机制探索」）。输入框提示保持「排除 METABRIC」这类限制，不诱导再填一张表。
5. 若当前没有可计算的建议，不确定展开后主行动改成「先看两个方向的差别」，不替用户自动提交。

禁止：把不确定变成「你是学生还是老师 / 有没有队列 / 想发什么杂志」。

### 3.4 用户不知道研究方向

分两层，都先本地成句，再 `sendTurn`。

**A. Home / Onboarding**

增加一条弱入口：「还没想好研究方向」。  
不创建新会话语义，不改 Home 主按钮文案。

进入 Copilot 后若 pending 为空或用户点了该入口：显示方向辅助，**先不调用 turn**。

方向辅助只给 2–3 个现成研究句 + 1 个概念句（沿用 Home 已有案例，不新造领域）：

- `我想研究HER2阳性乳腺癌耐药机制`
- `我想研究Ia型超新星光变曲线与红移的关系`
- `什么是HER2`（明确：说明概念，不写入研究目标）

用户点中一句 → 写入 pending 或直接 `sendTurn` 该句。这样 Router 仍走现有 `research_tokens` / `concept_prefixes`，不会把「我不知道」送进 CHAT 后停死。

**B. 已有对象、没有目标**

方向辅助改为「把对象补成问题」，本地拼句后再 turn。拼句必须能被现有 `_extract_goal` / `_apply_focus_answer` 听懂，例如：

- `我想研究{object}的耐药机制`
- `我想研究{object}的疗效预测`

不要提供「随便研究一下{object}」这种后端抽不出 target 的空句。

**C. CONCEPT_QA 之后**

Next Action 提供一条改写，例如对象来自回复里的概念名：

- `我想研究HER2阳性乳腺癌耐药机制`

用户点了才 turn。未点之前 Memory 必须仍是「还没有形成研究对象」。

---

## 4. 组件设计

只在现有 Copilot 页内增减呈现，不新开路由。

| 组件 | 文件 | 职责 |
|---|---|---|
| WhyClarify | 新建 `components/why-clarify.js` | 一句话解释为什么还不能规划 |
| ClarifyCard | 改 `components/clarify-card.js` | 背景 + 选项 + 建议标记 + 不确定展开 |
| NextActionCard | 新建 `components/next-action-card.js` | 永远告诉用户下一步；容纳方案按钮 / 采用建议 / 打开方向辅助 |
| DirectionAssist | 新建 `components/direction-assist.js` | 本地选研究句；选中前不 turn |
| UnderstandingBar | 基本不动 | 继续只负责「听懂了什么」 |
| Copilot page | 改 `pages/copilot.js` | 组装四块第一层；方案按钮移入 Next Action |
| Copy | 改 `copy/honesty.zh.js` | 为什么、建议、不确定、方向辅助、Next Action 文案 |

### 4.1 WhyClarify

```text
props ← { routeName, goal, questions, ready, blockedReason }
render → "" | <p class="why-line">...</p>
```

无 ready、且（有 question 或缺 object/target 或 CONCEPT_QA/CHAT）时才渲染。  
`blockedReason` 只作内部投影键，不输出原文。

### 4.2 ClarifyCard

```text
props ← { question, recommendation, whyLines[] }
state  ← unsureOpen: boolean   // 模块内存，不写 localStorage

默认：
  背景 1–2 句
  选项大卡片；recommendation.option 上标「建议」
  文本按钮「还不确定」

unsureOpen：
  每个 option 下多一行差别说明
  不新增 input、不新增问题
```

无 `questions[0]` 时仍返回空，把主位让给 Next Action。

### 4.3 NextActionCard

页面上的「当前任务」与「生成研究方案」合并到这里，避免任务条和主按钮各说各话。

```text
title     现在做什么
why       可与 WhyClarify 共用短句，或更短
primary   { label, kind }
secondary 可选弱操作（还不确定已在澄清卡时，这里不再重复）
```

`kind` 只描述前端动作：

| kind | 动作 |
|---|---|
| `start` | 已有，Onboarding「开始研究」 |
| `send_option` | `sendTurn(option)` |
| `open_assist` | 展开 DirectionAssist，不 turn |
| `send_text` | `sendTurn("我想研究…")` |
| `plan` | 仅 `ready_for_planner===true` 时 `POST /plan` |
| `compose` | 聚焦底部输入，不自动提交 |

未 ready 时 `kind=plan` 不得出现。

### 4.4 DirectionAssist

本地组件。选项是完整句子，不是标签云。

选中态：一句高亮 + Next Action「用这句开始」。  
点主按钮才 `sendTurn`。  
概念句必须在卡片上标明「不会写入研究目标」。

### 4.5 视觉

- 继续阅读宽，不要卡片墙
- 建议标记用字重或细边，不用绿灯表示「正确」
- 「不确定」用文本按钮，不要做成第三选项冒充后端 option
- 动效不超过现有 180–200ms
- `prefers-reduced-motion` 瞬时

---

## 5. 数据字段映射

不新增字段。用户看见的全部由现有回包投影。

| 用户看见 | 来源字段 | 前端怎么用 | 默认 |
|---|---|---|---|
| 理解总结 | `understood_goal` / `memory.goal` + 短 `user_visible_reply` | 沿用现组件 | 显示 |
| 为什么要确认 | `route.route` + goal 是否缺 object/target + 是否有 `questions[0]` + `blocked_reason`（仅作键） | 中文一句 | 条件显示 |
| 问题标题 | `clarifying_questions[0].question` | 原样 | 条件显示 |
| 背景解释 | `question_id` / 问题文本 + `user_visible_reply` 首句 | 文案表，不新接口 | 条件显示 |
| 选项 | `clarifying_questions[0].options` | 大卡片；不增删 | 条件显示 |
| AI 建议 | `goal.target` / `goal.raw_text` / needs.category | 标记其中一个 option | 能判断才标 |
| 不确定 | 无字段 | 本地展开 + 提交已有 option | 有选项才出现 |
| Next Action 主按钮 | `ready_for_planner` / 是否有 question / 是否缺 target / route | 见 §4.3 | **始终有** |
| 方向辅助句子 | Home 已有案例 + `goal.object` 拼句 | 本地；选中后当 `message` | 条件显示 |
| 研究上下文 | `memory.goal` / clarifications / constraints | 沿用折叠摘要 | 显示 |
| 数据需求 | `suggested_data_needs.category/description` | 仍折叠；`retrieval_status` 不进第一层 | 第二层 |
| 生成方案 | `POST /api/v30/plan` | 仅 ready | 条件显示 |

提交给后端的 `message` 只允许三类，避免问卷化：

1. 选项原文：`机制探索` / `疗效预测`
2. 完整研究句：`我想研究…`（含对象或目标词，现有抽取能听懂）
3. 限制句：`排除 METABRIC`

不要提交：`不确定`、`帮我选`、`我不知道`——后端当前不会把它们写成澄清答案，只会空转。

---

## 6. 实施建议

一次只交一屏。仍禁止改后端、旧前端、新增 API。

### 建议顺序

1. **Next Action Card**  
   把「当前任务」和方案按钮收进去。用户永远看得到下一步。CONCEPT_QA 的「请用我想研究…」从灰字升级为可点行动（点了才 turn）。

2. **WhyClarify**  
   有澄清或目标不齐时，先解释为什么。第一层继续禁止 error code。

3. **澄清卡增强**  
   背景 + 建议标记。建议规则写进纯函数，单测只测投影，不测后端。

4. **不确定**  
   同卡展开对比；主行动改为提交建议选项。不新增问题。

5. **DirectionAssist**  
   Home/Onboarding 弱入口 + 缺 target 时的成句辅助。选中前不 turn。

6. **文案收入 `honesty.zh.js`**  
   页面不手写「已覆盖 / 已检索 / 最优」。

### 建议改动文件

| 文件 | 计划中的职责 |
|---|---|
| `frontend/v31/app/pages/copilot.js` | 组装 Why / Clarify / Next Action / Assist；方案按钮搬家 |
| `frontend/v31/app/pages/home.js` | 可选：一条「还没想好研究方向」，不改主 CTA |
| `frontend/v31/app/components/why-clarify.js` | 新建 |
| `frontend/v31/app/components/next-action-card.js` | 新建 |
| `frontend/v31/app/components/direction-assist.js` | 新建 |
| `frontend/v31/app/components/clarify-card.js` | 背景、建议、不确定 |
| `frontend/v31/copy/honesty.zh.js` | 成题文案 |
| `frontend/v31/styles/pages/copilot.css` | Next Action、建议标记、不确定展开 |
| `backend/tests/v31_frontend/test_phase1_copilot.py` | 只改呈现断言 |

不改：`frontend/v31/app/api/v30.js`、`backend/app/v30/`、旧 frontend。

状态只放模块内存（`unsureOpen`、`assistOpen`）。**不要**用 localStorage 存科研内容。

### 测试与回归

现有 Phase 1 断言继续有效：

- 仍调用 `copilotTurn` / `getMemory` / `planSession`
- CONCEPT_QA 不写 goal
- 展开仍能读到 `not_retrieved`
- 无 `chat-bubble`、无打字机、无「发送并开始研究」
- 无 `/api/v30/integration`、无科研 `localStorage`

建议新增（实施时）：

- 有 `questions[0]` 时源码/结构含「为什么」类文案，不含 `awaiting_clarification`
- 建议标记不新增 option，只包装已有 `options[]`
- 「不确定」不作为 `sendTurn` 的 message
- 方向辅助在选中前不出现自动 turn
- `ready_for_planner` 为假时 Next Action 不含「生成研究方案」
- 未 ready 主路径仍无 `ready_for_planner=true` 明文

实施后跑：`v31_frontend` + `v30` + 234。本文件阶段不跑、不改测试。

### 验收

1. HER2 路径：欢迎 → 开始研究 → 先看到「为什么要确认」和带建议的大卡片，不是裸问题。
2. 点「还不确定」不出现新问题；可以一键采用建议，提交的仍是「机制探索」或「疗效预测」。
3. 「什么是HER2」仍不写 goal；Next Action 能把概念改写成「我想研究…」再 turn。
4. 「还没想好」先看到方向辅助，不先打出 CHAT 空转。
5. 未澄清看不见方案按钮，也看不见 422。
6. 整页仍然一次只推进一个判断，不像问卷。
7. 后端零改动，网络面板 API 集合与现在相同。

---

## 7. 明确不做

- 不增加 Copilot 后端问题（人群、终点、杂志、数据源偏好）
- 不把建议伪装成新模型接口或新字段
- 不把「不确定」提交给 `/copilot/turn`
- 不在 Home 做强制问卷或跳过欢迎
- 不恢复 Route pills / ready 明文 / 进度百分比
- 本文件发布后先评审，再单独开实施任务
