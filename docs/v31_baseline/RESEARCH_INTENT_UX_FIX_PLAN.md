# Research Intent UX 修复计划

- 日期：2026-09-05
- 性质：前端意图投影与引导修复计划，不是代码，不是授权改后端
- 基线：`docs/v31_baseline/RESEARCH_GUIDANCE_PHASE1_REPORT.md`
- 范围：只改 `frontend/v31/`
- 禁止：新增 API、改 `backend/app/v30/`、改旧 `frontend/`、把科研做成表单

本文回答：为什么「我想研究Ia型超新星光变曲线」会被做成概念说明 / 补充信息，以及如何在不改 Router 契约的前提下，把它送回科研助手。

---

## 0. 问题诊断（基于当前代码，不是猜测）

用户输入：

> 我想研究Ia型超新星光变曲线

### 后端实际怎么分

`RouterAgent` 含「研究 / 想研究」即 `_is_research`。  
「什么是…」只有在**没有**科研词时才进 `CONCEPT_QA`。

因此这句的后端路由是：

| 层 | 结果 |
|---|---|
| `POST /api/v30/route` | `CLARIFY`，`domain=astronomy`（命中「超新星」），`reason=research_intent_needs_clarification` |
| `POST /api/v30/copilot/turn` | 仍走科研草稿：`write_goal=true`，`ready_for_planner=false` |
| `understood_goal.object` | **空**（抽取只认 HER2 / 乳腺癌 / 红移） |
| `understood_goal.target` | **空**（抽取只认 耐药 / 机制 / 关联） |
| `understood_goal.domain` | `astronomy` |
| `understood_goal.raw_text` | 用户原句 |
| `clarifying_questions` | **空**（焦点问只在已有 target 或「耐药/机制」时出现） |
| `suggested_data_needs` | 一条 `domain_evidence`（非 oncology） |

后端**没有**把它判成 `CONCEPT_QA`。  
「你好」才是 `CHAT`；「什么是红移」才是 `CONCEPT_QA`。

### 前端为什么看起来像概念说明

Phase 1 用「有没有 `questions[0]` / 有没有 `object`」投影下一步：

| 组件 | 对这句实际输出 | 用户读到的意思 |
|---|---|---|
| UnderstandingBar | `你想研究 尚未明确的对象，当前目标偏向 尚未明确的分析目标` | 系统没听懂 |
| WhyClarify | 无 object →「还没有研究对象…补充一句我想研究」 | 像没进入研究 |
| NextActionCard | 无 question、未 ready → **「补充信息」** | 像填表 |
| `GUIDE.whyConcept` / `emptyGoal` | 「这是说明或闲聊，因此不能生成方案」「概念问答与闲聊不会写入研究目标」 | 只要 route 被当成 CHAT/CONCEPT_QA，或空 goal 文案泄漏，科研句就被污名为闲聊 |

根因不是「Router 把我想研究判成概念」，而是：

1. **前端没有 RESEARCH_INTENT 层**。把 `CHAT` 与 `CONCEPT_QA` 绑在同一套「不是研究」文案上；把「CLARIFY 但目标不完整」降成「补充信息」。
2. **理解总结依赖 `object/target` 字段**。字段空就写成「尚未明确」，丢掉 `raw_text` 里已经有的对象。
3. **没有方向辅助**。后端此时不给 `clarifying_questions`，前端就只剩输入框。

结论：这是科研意图、目标不完整。应进入科研助手帮用户成题，而不是停成闲聊或问卷。

---

## 1. 目标与非目标

### 目标

前端必须先投影三种**意图**（不是新 API enum）：

| 意图 | 含义 | 例子 |
|---|---|---|
| `CHAT` | 真正闲聊，停止科研流程 | 你好、嗨、天气、谢谢 |
| `CONCEPT_QA` | 只要解释概念，不写研究目标 | 什么是HER2、什么是红移 |
| `RESEARCH_INTENT` | 科研意图；目标可以不完整 | 我想研究Ia型超新星光变曲线、我想研究HER2阳性乳腺癌耐药机制 |

用户始终看到：

1. 系统听懂了哪一句研究对象（即使用户没写完分析目标）
2. 现在是在**形成研究问题**，不是补表
3. 可以点 2–3 个方向卡往前走

### 非目标

- 不新增 `/api/v30` 字段，不新增 `RouteKind.RESEARCH_INTENT`
- 不改 `backend/app/v30/router` / Copilot 抽取词表
- 不把「我想研究xxx」做成多页问卷（人群、杂志、数据源偏好）
- 不把 CONCEPT_QA 写成研究目标（「什么是HER2」仍不写 goal）
- 不做聊天窗、打字机
- 主按钮仍不叫「发送并开始研究」

---

## 2. Router 前端适配（不改后端路由）

后端继续返回 `CHAT | CONCEPT_QA | CLARIFY | PLAN`。  
前端增加 `intentOf(...)`，只用于呈现与下一步，**不改网络请求**。

### 2.1 判定顺序（从严到宽）

只读：本轮用户句（pending / `goal.raw_text` / 刚提交的 `message`）、`route.route`、`understood_goal` / `memory.goal`、`suggested_data_needs`。

```text
1. 空句                     → 仍按现有 Onboarding，不进闲聊停机
2. 真正闲聊
     整句规范化后等于「你好/您好/嗨/在吗/hello/hi/hey/thanks/谢谢」
     或明显天气/寒暄（前端小词表，例如 天气、今天天气）
     且句中没有「研究/想研究/打算研究/耐药/机制/疗效/关联/队列」
     → CHAT
3. 概念解释
     以「什么是/什么叫/何为/what is/解释一下」开头
     且没有「想研究/打算研究」
     → CONCEPT_QA
4. 其余
     含科研词，或 route 为 CLARIFY/PLAN，
     或 goal 已有 object/target/domain/raw_text，
     或 suggested_data_needs 非空
     → RESEARCH_INTENT
```

硬规则：

- **「我想研究xxx」永远是 RESEARCH_INTENT**，即使 `object/target` 为空，即使后端暂时抽不出对象。
- **禁止**因 `object` 为空，把 CLARIFY 投影成 CONCEPT_QA 或 CHAT。
- **禁止**对 RESEARCH_INTENT 使用「说明或闲聊」「不能生成方案」类文案。
- 后端 `route.route` 仍可写在「技术细节」里；第一层只说人话意图。

### 2.2 与后端 route 的对照（实施时对照，不改契约）

| 用户句 | 后端 route（现状） | 前端 intent | 第一层 |
|---|---|---|---|
| 你好 | CHAT | CHAT | 闲聊；停止科研 |
| 今天天气怎么样 | 可能 CHAT / fallback | CHAT | 闲聊；停止科研 |
| 什么是HER2 | CONCEPT_QA | CONCEPT_QA | 概念解释；不写 goal |
| 我想研究Ia型超新星光变曲线 | CLARIFY | **RESEARCH_INTENT** | 听懂对象 + 方向卡 |
| 我想研究HER2阳性乳腺癌耐药机制 | CLARIFY | RESEARCH_INTENT | 听懂对象 + 焦点问或方向 |
| 疗效预测（澄清答案） | CLARIFY | RESEARCH_INTENT | 已有问题则确认；ready 则方案 |

若实施时实测某句「我想研究…」后端不是 CLARIFY：前端仍按科研词判 RESEARCH_INTENT，照样进助手。不把后端 fallback 文案直接铺到中列。

---

## 3. 未明确目标时：AI 辅助形成研究问题

删除第一层「补充信息」。  
RESEARCH_INTENT 且未 ready、且没有 `clarifying_questions[0]` 时，改为方向辅助。

### 3.1 超新星光变曲线（验收句）

```text
理解
  你希望研究 Ia型超新星光变曲线。
  分析目标还没选定。这一步不找数据。

为什么现在选方向
  选择方向会影响后续数据来源和字段。现在选是为了形成研究问题，不是取数。

这个方向通常包含
  [ 光变曲线建模 ]     建议
  [ 距离测量 ]
  [ 爆炸机制分析 ]

下一步
  选定一个研究问题
```

理解句从 `goal.raw_text` 去「我想研究/打算研究」前缀得到；不要写「尚未明确的对象」。  
`domain=astronomy` 只用于选方向表，不做成徽章墙。

### 3.2 方向卡怎么提交（仍走现有 turn）

选项**展示名**可以是短标签。  
点击后 `sendTurn` 必须是一句完整科研陈述，让现有抽取有机会补 `target`，例如：

| 卡片 | 提交的 message（前端拼，不新接口） |
|---|---|
| 光变曲线建模 | `我想研究Ia型超新星光变曲线建模` |
| 距离测量 | `我想研究Ia型超新星光变曲线与距离测量的关系` |
| 爆炸机制分析 | `我想研究Ia型超新星爆炸机制` |

「关系 / 机制」是为了迁就**现有** `_extract_goal`，不是让用户填表。  
用户也可以不点卡，自己在底部写限制（「排除 METABRIC」那类），但不能把底部升级成必填问卷。

有后端 `clarifying_questions[0]` 时：仍用后端 options，不另起一套方向卡。

### 3.3 不是问卷

- 一次只给 2–3 个方向
- 不收集身份、经验、期刊、是否有数据
- 不要求先填 object / target / domain 三列表
- 点一下即提交，无二次确认页

---

## 4. AI 推荐方向（无新 API）

推荐是前端投影，文案写「建议」，不写「模型已决定」。

只读：

- `understood_goal.object / target / domain / raw_text`
- `route.domain`（goal.domain 为空时）
- `suggested_data_needs[].category`

### 4.1 方向表（前端常量表，按 domain + 原文关键词）

**astronomy**（原文含 光变 / 超新星 / supernova 时优先用验收三卡）：

1. 光变曲线建模
2. 距离测量
3. 爆炸机制分析

建议标记：原文含「光变」→ 光变曲线建模；含「距离 / 红移」→ 距离测量；含「爆炸 / 机制」→ 爆炸机制分析。默认建议第一项。

**oncology**（无后端焦点问时才用；有 `research_focus` 则只用后端 options）：

1. 机制探索
2. 疗效预测

建议规则沿用 Phase 1：`target` 含耐药/机制且不含疗效 → 机制探索。

**其它 / unknown**：

1. 机制分析
2. 关联分析

`suggested_data_needs` 仅作旁证（例如已有 `domain_evidence` 说明已在科研草稿里），**不**用来画「已检索」。

不得新增第四、第五个方向凑问卷。

---

## 5. 三种意图的第一层结构

```text
理解总结
为什么 / 闲聊说明          ← CHAT 与 CONCEPT_QA 用各自文案；RESEARCH 未齐时用「为什么选方向」
澄清卡 或 方向卡           ← 二者只出其一
Next Action                ← 永远有；禁止「补充信息」
```

| intent | 理解总结 | Why | 决策 | Next Action |
|---|---|---|---|---|
| CHAT | 这是闲聊，还没有科研问题 | 不出现「说明或闲聊因此不能生成方案」；改「可以说你想研究什么」 | 无方向卡 | 说出研究想法（弱提示，无方案按钮） |
| CONCEPT_QA | 这不是研究对象，不会写入研究目标 | 这是概念解释，不是一次取数 | 无方向卡 | 若要做研究，改写成「我想研究…」 |
| RESEARCH 有后端问题 | 你希望研究 {object 或 raw} | 选方向会影响后续来源和字段 | 后端 options | 确认研究方向 |
| RESEARCH 无问题未 ready | 你希望研究 {raw 抽出的对象} | 同上 | **前端方向卡** | 选定一个研究问题 |
| RESEARCH ready | 对象 + 目标 | 不显示 Why | 无 | 生成研究方案 |

### 必须删除的误导句（第一层）

- 「这是说明或闲聊，不会写入研究目标，因此不能生成方案」
- 「概念问答与闲聊不会写入研究目标」（夹在科研句的空 goal 上）
- 「补充信息」作为 RESEARCH 的下一步标题
- 「还没有研究对象。先说出对象，或补充一句我想研究…」（当用户已经说了「我想研究Ia型超新星光变曲线」）

CONCEPT_QA 仍可说「这不是研究对象」；**不要**再绑「闲聊」「因此不能生成方案」。

CHAT 只说「这是闲聊」；不要说用户在做概念问答。

---

## 6. 字段映射

不新增后端字段。

| 用户看见 | 来源 | 用法 |
|---|---|---|
| 意图 | 用户句 + `route.route` + goal + needs | `intentOf`，只前端 |
| 「你希望研究 X」 | `goal.raw_text` 去前缀；否则 `goal.object` | RESEARCH 理解总结 |
| 领域选方向表 | `goal.domain` 或 `route.domain` | 不展示 domain=astronomy 徽章 |
| 后端澄清 | `clarifying_questions[0]` | 优先于前端方向卡 |
| 前端方向 | domain + raw_text 关键词 + needs 仅作科研旁证 | 展示 2–3 卡 |
| 建议标记 | raw_text / target 规则 | 只标已有卡片之一 |
| 提交句 | 卡片 → 拼好的「我想研究…」或后端 option 原文 | `POST /api/v30/copilot/turn` |
| 方案按钮 | 仅 `ready_for_planner===true` | 不变 |
| 闲聊停机 | 真 CHAT | 无方向卡、无方案按钮 |

前端可在 SessionStore 记 `lastUserMessage`（内存，不 localStorage），以便 raw_text 尚未回来时也能写「你希望研究…」。不存科研表、不新增 API。

---

## 7. 组件与实施建议

本文件阶段不写代码。实施时建议只动这些文件：

| 文件 | 职责 |
|---|---|
| `frontend/v31/app/intent.js`（新建） | `intentOf`、闲聊/概念/科研词、从 raw_text 抽展示对象 |
| `frontend/v31/app/components/direction-assist.js`（新建） | RESEARCH 未齐且无后端问题时的 2–3 方向卡 |
| `frontend/v31/app/components/understanding-bar.js` | RESEARCH 用 raw_text；禁止把科研句写成闲聊 |
| `frontend/v31/app/components/why-clarify.js` | 按 intent 分支；删除 whyConcept 误导句 |
| `frontend/v31/app/components/next-action-card.js` | 删除「补充信息」；RESEARCH 未齐 →「选定一个研究问题」 |
| `frontend/v31/app/pages/copilot.js` | 用 intent 组装；方向卡点击 `sendTurn(拼句)` |
| `frontend/v31/copy/honesty.zh.js` | 拆开闲聊 / 概念 / 科研未齐三套文案 |
| `frontend/v31/styles/pages/copilot.css` | 方向卡沿用大卡片 |

不改：`app/api/v30.js`、后端、旧 frontend。

### 建议顺序

1. `intentOf` + 删掉误导文案（CHAT / CONCEPT / RESEARCH 分家）
2. UnderstandingBar：RESEARCH 显示「你希望研究 {raw}」
3. NextAction：RESEARCH 未齐改为「选定一个研究问题」，去掉「补充信息」
4. DirectionAssist：astronomy 验收三卡 + oncology 回退
5. 手验三句：超新星光变、什么是HER2、你好
6. 补静态断言，跑 `v31_frontend` + `v30` + 234

---

## 8. 验收

1. 「我想研究Ia型超新星光变曲线」→ 科研助手。理解句含光变曲线。下一步是三个方向卡，不是「补充信息」，不是「说明或闲聊」。
2. 点「光变曲线建模」只 `sendTurn` 一句「我想研究…」，不出现表单。
3. 文案出现「选择方向会影响后续数据来源和字段」。
4. 「什么是HER2」仍不写 goal，无方案按钮；文案是概念解释，不叫闲聊。
5. 「你好」停止科研：无方向卡、无方案按钮。
6. HER2 耐药路径仍先欢迎再澄清，后端焦点问优先于前端方向卡。
7. 网络面板 API 集合不变。

---

## 9. 明确不做

- 不改 Router YAML / Copilot `_extract_goal` 词表（本计划用前端投影兜住「超新星光变曲线」）
- 不把 RESEARCH_INTENT 写进后端枚举
- 不恢复「补充信息」当科研主行动
- 不把天气闲聊做成研究方向
- 本文件发布后先评审，再单独开实施
