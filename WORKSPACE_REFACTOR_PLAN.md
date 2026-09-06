# Research Workspace 前端产品形态重构计划

- 日期：2026-09-05
- 状态：待架构确认，暂不实施
- 范围：`frontend/v31/` 产品壳、路由、状态组织与视觉层
- 明确不做：本轮不写业务代码，不修改后端 session 契约，不增加页面数量

## 1. 结论先行

当前系统已经有“多研究”的第一轮实现，但还不是以研究为中心的 Workspace：

1. `workspace-store`、`session-store`、`timeline-store`、`pending-intent` 分散持有状态；研究隔离依赖多个模块共同遵守约定。
2. 左侧虽然已经是“我的研究”，但中间仍以 Copilot / Timeline / Sources / Mapping / Graph 的工程页面为主，用户仍容易把它理解为流程控制台。
3. `conversationLog` 与前端 Timeline 是当前浏览器进程内的投影，不是后端历史；刷新后只有当前 URL 对应的 `MemorySnapshot` 可重新读取。
4. 后端 v30 的研究 session 与 Qwen 临时凭据 session 是两种不同对象，前端不能把它们混为一个“工作区 session”。

本次重构的核心不是再做一层流程 UI，而是建立一个稳定的“研究槽”模型：

> 一个研究 = 一个 `session_id` + 一个前端 Research Slot；所有 Memory、过程记录、工程产物、摘要和异步请求都必须归属于该 Slot。

最终产品形态：

```text
Research Workspace
├── 左：Research List              研究窗口切换
├── 中：Research Conversation       用户想法 → AI理解 → 方向建议 → 用户确认 → 研究进展
└── 右：Research Summary            对象 / 目标 / 阶段 / 已确认 / 下一步
    └── Technical Details Drawer    route / retrieval_status / constraints / evidence
```

Copilot、Timeline、Sources、Mapping、Graph 不删除，但降级为当前研究内部的工作面；它们不再承担产品主导航。

## 2. 已核对的后端事实与边界

### 2.1 研究 session

后端 v30 已提供并测试以下语义：

- `POST /api/v30/sessions` 创建新的 `session_id` 和空 `MemorySnapshot`。
- `GET /api/v30/sessions/{session_id}/memory` 读取该 session 的 `goal`、`clarifications`、`constraints`。
- `POST /api/v30/copilot/turn` 严格按请求中的 `session_id` 读写 Memory，并返回 `route`、`understood_goal`、数据需求建议、澄清问题和最新 memory。
- `POST /api/v30/plan` 只使用指定 `session_id` 的 Memory；未准备好时返回 `research_goal_not_ready`。
- `MemoryService` 进程内按 session 存储，测试已验证两个 session 的 goal 与 constraints 不互相继承。

### 2.2 后端没有提供的能力

当前没有研究目录、turn history、前端 conversation history、前端 timeline、summary 的后端 API。因此本次前端方案遵守以下现实边界：

- 同一浏览器标签页内的多个研究，可通过前端 Slot 完整隔离和切换。
- 刷新后，只能通过 URL 中的 `session_id` 重新读取当前研究的 Memory；之前未保存在后端的过程 log 和前端事件不能伪造恢复。
- 如果未来要求跨刷新、跨设备保留完整对话历史，必须另行设计后端持久化契约；不在本次前端重构中偷偷使用 `localStorage` 或把科研内容写入 Qwen session。

### 2.3 不得混用的 session

`backend/app/agent/session_registry.py` 中的 Qwen session 只负责临时 API 凭据、模型连接和 TTL；它不是研究窗口，不承载研究 Memory、conversation 或 timeline。前端现有 v31 主链只继续使用 v30 research session。

### 2.4 不变的冻结边界

- 不修改 `configs/canonical_schema.yaml`、`configs/medical_rules.yaml`、`configs/quality_rules.yaml`。
- 不修改 v30 的路径、请求字段和响应语义。
- 不把 `HER2 IHC 2+`、`ERBB2 CNA amplification` 或细胞系 `AUC/IC50` 在 UI 投影成患者临床结论。
- 不把 `source_id`、`raw_field`、`raw_value`、Evidence 的缺失隐藏成“已完成”。

## 3. 目标信息架构

### 3.1 全局 Workspace 壳

全局只负责“我正在看哪个研究”，不负责展示八步工程流程：

- 顶栏：产品名、当前研究标题、次级的“内核实验室”入口、连接状态。
- 左侧：研究列表、当前项、新建研究。
- 中间：当前研究的默认 Conversation 工作面。
- 右侧：当前研究的 Summary；Technical Details 默认收起。

左侧不再出现 `科研问题 / AI理解 / 研究规划 / 数据发现 / 字段映射 / 证据解释 / 执行 / 科研数据资产` 作为主导航节点。八步状态只在研究内部的次级研究进展面或详情中出现。

### 3.2 当前研究的默认工作面

进入 `#/r/{session_id}` 或 `#/r/{session_id}/conversation` 时，用户看到的是 Research Conversation：

1. 用户想法：保留用户提交的研究原句。
2. AI 理解：展示对象、目标、领域的自然语言理解。
3. 方向建议：展示当时给出的研究方向或澄清问题。
4. 用户确认：展示用户选择的原始选项或补充约束。
5. 研究进展：展示“已形成目标”“已生成方案”“已发现候选来源”等人话进展。
6. 当前决策区：只保留当前真正需要用户处理的一个问题或一个主操作。
7. 底部输入：用于补充限制或修正目标，不做无限聊天流。

这是一条有语义的研究过程带，不是 `user / assistant` 气泡，也不展示打字机效果。API 名、内部 route、`ready_for_planner`、`fetched=false` 等工程字段不进入主叙事。

### 3.3 研究内部工作面

以下能力继续保留，但改为当前研究的二级工作面：

| 工作面 | 入口定位 | 主叙事要求 |
|---|---|---|
| Conversation | 默认面 | 研究过程与下一步决策 |
| Research Progress | 次级面 | 需要审计时查看工程事件和阶段状态 |
| Sources | 次级面 | 查看候选来源、选择理由与覆盖假设 |
| Mapping | 次级面 | 查看字段对齐、AUTO / REVIEW、医学约束 |
| Graph | 次级面 | 查看证据解释路径与 Why Drawer |
| Preview / Dataset | 已有能力对应时再进入 | 仍受执行安全门控制 |

页面数量不增加；变化是入口层级和默认呈现顺序。

## 4. 统一状态架构

### 4.1 单一事实源

实施时将 `workspace-store` 提升为前端唯一的研究状态协调器。`session-store` 不再与它平行拥有一份研究事实；如果为了最小迁移保留，应只作为“当前 Slot 的读写适配层”。

每个 Research Slot 概念上包含：

| 分区 | 内容 | 归属 |
|---|---|---|
| Identity | `sessionId`、标题来源、创建/更新时间 | 研究槽 |
| Backend Memory | `memory`、最近 `route`、最近 `lastTurn` | 研究槽 |
| Conversation | 过程条目：idea / understand / suggest / confirm / progress | 研究槽 |
| Research Artifacts | `plan`、`registry`、`discovery`、`selection`、`schemaPack`、`mappings`、`graph`、`lastWhy`、错误 | 研究槽 |
| Research Timeline | 由该槽的回包投影出的工程事件 | 研究槽 |
| Pending Input | 新建后尚未提交的首句研究想法 | 研究槽 |
| Derived View Model | 标题、阶段、摘要、下一步、可进入的工作面 | 从以上数据派生，不单独写入 |

全局只保留不属于某个研究的 UI 状态，例如当前 Drawer 类型、窗口尺寸和连接状态。任何 goal、constraint、conversation、timeline、graph、plan 都不能放在全局 singleton 中。

### 4.2 关键不变量

1. `activeResearchId` 必须与 URL 中的 `session_id` 一致；不以页面渲染时残留的全局 `sessionId` 为准。
2. 所有 API 请求在发起时捕获目标 `session_id`，响应只能提交回同一个 Slot。
3. 切换研究前先保存当前 Slot；切换后再 hydrate 目标 Slot，并以目标 `session_id` 刷新 Memory。
4. 新建研究只创建新 Slot，不得调用工作空间级 `reset()` 清空旧研究。
5. 方向卡、澄清选项、composer 提交必须从当前 Slot 取 `session_id`；禁止使用闭包中已经过期的研究 ID。
6. 异步响应返回时，如果 Slot 已不是 active 或请求序号已过期，只允许丢弃 UI 提交，不得覆盖当前研究。
7. 切换后右侧 Summary、过程带、工程 Timeline、Sources/Mapping/Graph 全部来自目标 Slot。
8. `pendingIntent` 与研究槽绑定；它不能以单独模块级变量存在。
9. 研究槽之间不共享可变数组或对象引用；快照和恢复必须深拷贝可变内容。

### 4.3 切换流程

```text
点击研究 B
  → 保存当前研究 A 的 Slot
  → 设置 activeResearchId = B
  → URL 导航到 #/r/B/conversation
  → 恢复 B 的前端快照
  → GET /api/v30/sessions/B/memory
  → 只合并 B 的 Memory
  → 重算 B 的 Summary / Conversation / 可用工作面
```

如果 A 的请求晚于 B 返回，必须通过 Slot ID + 请求序号校验后丢弃，不能把 A 的结果写入 B 的中间区域。

## 5. 路由方案

### 5.1 产品路由

| 路由 | 作用 | 默认可见性 |
|---|---|---|
| `#/home` | 无研究时的入口；也可创建新研究 | 可见 |
| `#/r/{session_id}` | 当前研究默认入口 | 可见 |
| `#/r/{session_id}/conversation` | 研究过程工作面 | 可见 |
| `#/r/{session_id}/progress` | 工程进展与门状态 | 次级 |
| `#/r/{session_id}/sources` | 来源工作面 | 次级 |
| `#/r/{session_id}/mapping` | 字段映射工作面 | 次级 |
| `#/r/{session_id}/graph` | 证据解释工作面 | 次级 |
| `#/r/{session_id}/preview` | 执行前预览 | 按后端能力开放 |
| `#/r/{session_id}/dataset` | 结果/导出 | 按执行结果开放 |

现有 `copilot` 与 `timeline` 可在迁移期保留兼容别名，但产品默认不再把 `copilot` 当成流程节点，也不从左侧展示八步列表。兼容路由最终统一重定向到对应的新语义路由。

### 5.2 技术细节 Drawer

右侧默认显示自然语言 Summary。Technical Details 使用折叠 Drawer，展开后才显示：

- `route` / `RouteKind`；
- 数据需求及 `retrieval_status`；
- `constraints`；
- `ready_for_planner`、`blocked_reason`；
- evidence / graph / figure understanding 的回包摘要；
- `fetched`、`integrated`、`execution_allowed` 等诚实状态。

Drawer 是解释和审计入口，不是工程状态主导航。错误仍保留后端原始语义，不为了“好看”改写成已完成。

## 6. 视觉与交互原则

### 左侧 Research List

- 研究标题优先，阶段只作为弱辅助文本。
- 当前项用细边线、背景或字重表达，不用流程点。
- 新建研究是明确操作；新建后自动进入新 Slot。
- 空态只说明“还没有研究”，不列八步能力清单。

### 中间 Research Conversation

- 以研究过程条目为主，不采用聊天气泡、头像、打字机。
- 每屏最多一个主操作：开始研究、选择方向或生成方案。
- “方向建议”和“用户确认”必须可区分，且只能写入当前 Slot。
- 进展条目由真实 API 回包或明确的本地过程事件产生，不手动标记完成。

### 右侧 Research Summary

固定展示五块：

1. 研究对象；
2. 研究目标；
3. 当前阶段；
4. 已确认内容；
5. 下一步。

概念问答和闲聊必须保持诚实空态：不写入研究对象，不点亮规划后的能力，不将解释文本伪装成研究目标。

## 7. 文件级改造边界

### 需要重构的前端职责

| 文件/区域 | 目标职责 |
|---|---|
| `app/workspace-store.js` | 唯一 Slot 注册、active 切换、快照、请求提交保护 |
| `app/session-store.js` | 降为当前 Slot 适配层，或在迁移完成后移除重复写入 |
| `app/timeline-store.js` | 事件成为 Slot 内数据；禁止模块级跨研究事件池 |
| `app/pending-intent.js` | 合并进 Slot；不保留全局 pending 变量 |
| `app/router.js` | 增加默认研究路由和兼容重定向，路由不持有业务状态 |
| `app/main.js` | 只负责壳、active research、全局 UI 和工作面分发 |
| `app/pages/copilot.js` | 迁移为 Conversation 工作面，保留现有 v30 调用语义 |
| `app/pages/timeline.js` | 降为 Progress 次级面；不再作为左侧主导航 |
| `app/components/conversation-timeline.js` | 成为过程叙事组件，条目带来源和研究槽边界 |
| `app/components/research-summary.js` | 只读派生 Summary，不直接展示裸 Memory |
| `app/components/context-drawer.js` | 集中承载 route、retrieval、constraints、evidence |
| `app/components/research-list.js` | 只负责研究列表和切换，不渲染门状态 |
| `index.html` / `styles/` | 固化三栏 Workspace 壳和次级工作面样式 |

### 明确不改

- `app/api/v30.js` 的现有 v30 API 包装器语义；如需新增接口必须另行评审，不作为本计划前提。
- `backend/app/v30/` 和 Qwen session registry。
- 旧 `frontend/` 根页面及其兼容入口。
- 冻结 schema、医学规则、质量规则和评测公式。

## 8. 实施顺序

### Phase 0：架构契约冻结

- 将 Slot 字段、归属边界、异步提交规则写成前端内部契约。
- 明确 `session-store` 是适配层，不再产生第二份事实。
- 确认新旧路由兼容策略。

### Phase 1：统一 Slot 状态与切换安全

- 合并 `workspace-store`、`session-store`、`timeline-store`、`pending-intent` 的研究归属。
- 先完成 A/B 两个 session 的创建、切换、恢复和过期响应丢弃。
- 不改变中间页面视觉，先保证状态正确。

### Phase 2：Workspace 壳与主路由

- 将默认研究入口切到 Conversation。
- 左侧固定为 Research List。
- 将旧页面入口降为当前研究的次级工作面。
- 清理主界面中八步流程的导航语义，但保留需要审计的 Progress 面。

### Phase 3：Research Conversation

- 固化五类过程条目和时间顺序。
- 将方向建议、用户确认、研究进展与当前决策区分开。
- 保持现有 `CLARIFY`、`PLAN`、`CHAT`、`CONCEPT_QA` 后端语义不变。

### Phase 4：Summary 与 Technical Drawer

- 右侧只显示对象、目标、阶段、确认、下一步。
- route、retrieval_status、constraints、evidence 默认收起。
- 医学安全边界继续可查，但不压住研究摘要。

### Phase 5：全链路工作面接入

- Sources / Mapping / Graph 使用当前 Slot 的 artifacts。
- 重新运行某一工作面时生成新本地版本或替换当前结果，必须在 Progress 中留下事实依据；不得污染其它研究。
- Preview / Dataset 保持现有执行门和跨域限制，不扩展为本次 UI 重构的隐含需求。

### Phase 6：验证与交付

- 先跑现有 v31 前端、v30 memory isolation 测试。
- 增加状态隔离、异步竞态、路由恢复和主导航文案的回归测试。
- 手验 HER2 + Ia 型超新星 + 概念问答 + 闲聊四条路径。

## 9. 验收标准

### 研究隔离

1. 新建 HER2 研究 A 和 Ia 型超新星研究 B，二者拥有不同 `session_id`。
2. A 的 goal、clarifications、constraints、conversation、timeline、plan、graph 不出现在 B。
3. 从 B 切回 A，右侧 Summary、中间过程带和下一步恢复为 A；反向切换同理。
4. 在 B 选方向后切回 A，A 不出现 B 的方向建议。
5. A 的迟到 API 回包不会覆盖 B 的中间区域。

### 产品形态

1. 左侧主导航只表达 Research List，不表达八步流程。
2. 默认中间工作面明确叫 Research Conversation / 研究过程，不是聊天气泡流。
3. 中间能按顺序看见：用户想法、AI理解、方向建议、用户确认、研究进展。
4. 右侧默认显示五块 Research Summary，不显示裸 Memory 字段表。
5. `route`、`retrieval_status`、`constraints`、`evidence` 默认在折叠 Drawer。
6. Sources / Mapping / Graph 仍可访问，但不抢占 Workspace 主导航。

### 医学与诚实性

1. 「什么是 HER2」不写研究目标，也不点亮后续研究门。
2. 「你好」仍保持 CHAT，不生成研究目标。
3. HER2 IHC 2+ 不被 UI 自动显示为 HER2 Positive。
4. 细胞系 `AUC/IC50` 与患者 `pCR/response` 保持 `response_domain` 分离。
5. `unverified`、`not_retrieved`、`fetched=false`、`integrated=false` 不被视觉包装为已完成。

### 持久性边界

1. 不使用 `localStorage` / `IndexedDB` 持久化科研内容。
2. 刷新当前 URL 时，能重新读取当前 session 的 Memory；对于后端未保存的过程历史，显示诚实的有限恢复状态。
3. 不承诺没有后端目录/历史 API 时的跨设备研究列表和完整历史。

## 10. 风险与需要确认的架构决策

| 风险/决策 | 本计划默认选择 | 影响 |
|---|---|---|
| 是否需要刷新后完整恢复 conversation/timeline | 暂不需要；先做同标签页隔离 | 若需要，必须另开后端持久化设计 |
| 是否增加 session list/history API | 不增加 | 研究列表只在当前前端运行时存在 |
| 是否把 `timeline` 删除 | 不删除，降为 Progress 次级面 | 保留审计能力，降低主流程工程感 |
| 是否把 Sources/Mapping/Graph 合并为一页 | 不合并 | 保持已有后端能力和回归边界，只改变入口层级 |
| 是否使用 Qwen session 作为 workspace session | 禁止 | 避免凭据生命周期与研究生命周期耦合 |
| 是否允许后端返回未授权的患者事实 | 不改变现有边界 | 前端只展示已有契约，不能自行补事实 |

## 11. 本轮确认点

请先确认以下架构方向，再进入实施：

1. 采用“一个后端 research `session_id` = 一个前端 Research Slot”的一对一模型。
2. 以统一 Workspace Store 作为唯一研究状态事实源，消除多个模块级状态池的并列写入。
3. 以 Research Conversation 作为默认主工作面；Copilot / Progress / Sources / Mapping / Graph 作为研究内部次级工作面。
4. 右侧默认只显示 Research Summary，工程字段统一进入折叠 Technical Details Drawer。
5. 本轮不加后端 list/history API，不使用 localStorage；完整跨刷新历史作为后续独立架构议题。

确认后再开始 Phase 1；在确认前不修改 `frontend/v31` 业务代码。
