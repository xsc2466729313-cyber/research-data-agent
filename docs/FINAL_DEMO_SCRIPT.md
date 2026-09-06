# 最终比赛演示脚本

- 时长：5–8 分钟
- 入口：`http://127.0.0.1:8000/v31/`（必须用 uvicorn 托管的 FastAPI，不要用 Docker Nginx `:8888`）
- 备援：`http://127.0.0.1:8000/docs`（Swagger，只在需要证明 Preview / Execute 后端时打开）
- 禁止：把旧页「发送并开始研究」讲成 V3.1 Copilot

一句话开场（15 秒）：

> 这不是聊天机器人，也不是已经自动整出主表的医学黑盒。它是一条可审计的研究链：问题被理解、来源被假设、字段被对齐、证据可追问；只有医学插件就绪时，才把请求交给旧执行内核。

---

## 0. 演示纪律（先对评委说 20 秒）

左轨八步：

科研问题 → AI理解 → 研究规划 → 数据发现 → 字段映射 → 证据解释 → 执行 → 科研数据资产

**前六步有页面。后两步后端 API 已通，v31 前端尚未开放。**  
所以案例 1 主戏走 `/v31/` 到 Graph；若还有 60 秒，再用 Swagger 点 Preview，口头说明 Execute 不在新 UI 里自动跑。

诚实三句，全程可指右轨：

- 发现不是覆盖
- 预览不是执行
- 图理解不入库

不要说：已找到数据、已覆盖、已整合、智能整合完成。

---

## 案例 1：HER2 阳性乳腺癌耐药（约 4 分钟）

目标：证明医学主链能从一句话走到「为什么这样选、为什么 REVIEW」，并且执行被单独门控。

### 1. 科研问题 · Home

- **页面：** `/v31/#/home`
- **操作：** 点案例「HER2阳性乳腺癌耐药」，或输入「我想研究HER2阳性乳腺癌耐药机制」
- **接口：** `POST /api/v30/route` → `POST /api/v30/sessions`
- **讲：** 回车只创建会话，不取数。左轨「科研问题」变 ready。

### 2. AI理解 · Copilot

- **页面：** `/v31/#/r/{session}/copilot`
- **接口：** `POST /api/v30/copilot/turn`，随后可 `GET /api/v30/sessions/{id}/memory`
- **展示：**
  - 对象 `HER2阳性乳腺癌`，目标仍偏机制
  - 数据需求表全部 `not_retrieved`
  - 一张澄清卡：机制探索 / 疗效预测
- **操作：** 点「疗效预测」；可选再输入「排除 METABRIC」并点继续澄清
- **讲：** CONCEPT_QA「什么是HER2」不会写研究目标。这里是研究秘书，不是诊断引擎。IHC 2+ 不会在这一步被判成 Positive。

注意：若 ready 后系统仍弹出「本阶段尚未挂载 Planner」，那是 Copilot 旧文案，**不要跟着念**。直接指按钮「生成研究方案」。

### 3. 研究规划 · Timeline

- **操作：** 点「生成研究方案」
- **接口：** `POST /api/v30/plan` `{ session_id }`
- **页面跳到：** `/timeline`
- **讲：** 方案来自现有 RequirementAgent / PlanningV2。notice 写明不取数、不冻结合同、不写 CanonicalRecord。未澄清会 422 `research_goal_not_ready`。来源门此时仍 idle。

### 4. 数据发现 · Sources

- **操作：** 「进入数据发现」→「发现候选」→「应用选择」
- **接口：**
  - `GET /api/v30/registry/sources?domain=oncology`
  - `POST /api/v30/discover`
  - `POST /api/v30/source-selection`
- **讲：**
  - Registry 是能力目录：`official_api` + `active`，不是已经下载的库
  - 每张卡必须看见 `unverified`、`fetched=false`、`integrated=false`
  - 选择表里是 API 的 `reason_code`，不是前端写死 METABRIC
  - 若有约束，排除行应出现 `user_constraint`
  - Join 风险：禁止跨研究患者合并

### 5. 字段映射 · Mapping

- **操作：** 「进入字段映射」→「生成或绑定 Schema Pack」→「预览映射」
- **接口：**
  - `POST /api/v30/schema-packs/generate`
  - `GET /api/v30/schema-packs/{id}`
  - `POST /api/v30/schema-packs/match`
- **讲：**
  - 医学 pack 绑定冻结 `oncology_canonical_v0.1`，`entity_type=patient`
  - 看见 `source_id` / `raw_field` / `raw_value` / `response_domain`
  - `row_count=0`，文案「未生成数据行」
  - AUTO 是墨色对齐，不是绿勾完成；REVIEW 是风险，不是失败
  - 细胞系 AUC/IC50 不能当患者 pCR——指右轨医学限制

### 6. 证据解释 · Graph

- **操作：** 「进入证据解释」→「生成解释图」→点「未选择 …」或 REVIEW / QualityFinding
- **接口：**
  - `POST /api/v30/graphs/project`
  - `GET /api/v30/graphs/{graph_id}`
  - `GET /api/v30/graphs/{graph_id}/why/{finding_id}`
- **讲：**
  - 这是科研证据地图，不是患者关系图
  - 打开页不会自动投影；证据门此时才可能 ready
  - Why 回答：为什么选、为什么映射、为什么 REVIEW、为什么排除
  - 图上没有 `SAME_PATIENT` / `JOINED_ACROSS_STUDY`
  - `replaces_evidence_builder=false`，不复制事实值

附图按钮可点一次，但不要展开成数字化故事：`POST /api/v30/figures/understand`，`enters_primary_table=false`。

### 7. 执行 · 后端有、新 UI 无（45 秒，可砍）

**不要假装 v31 有 Preview 页。** 左轨「执行」仍是 idle。

两条合法演示：

**A. 推荐（稳）：** 打开 `/docs`，找到

- `POST /api/v30/integration/preview`
- `POST /api/v30/integration/prepare`

指字段：`execution_allowed=false`、`would_invoke=false`、`join_policy=forbid_cross_entity`。

**讲：** 预览不是执行。系统先告诉你将调用谁，默认立场是还不能跑。

**B. 只有网络与时间都够，才口头提：**

- `POST /api/v30/integration/execute` 仅 oncology
- runner 是旧 `ResearchAgentService`，`use_qwen=false`
- 成功后才有 `task_id` / `quality_status` / 可导出格式
- **现场不要承诺一定出满表。** live Adapter 可能慢或空。

### 8. 科研数据资产

**v31 Dataset 页不存在。**

若必须展示表：打开顶栏「内核实验室」`/`，说明这是**另一套旧协议**（`/api/agent/tasks`），与刚才 `/v31/` 会话**不自动共享**。  
更好的说法：

> 资产在旧执行成功后才存在。新工作台目前停在证据解释，避免把规划页装成已经出库。

---

## 案例 2：Ia 型超新星光变曲线（约 2 分 30 秒）

目标：证明系统**不是**医学工具套皮。

### 用户输入

Home 点「Ia型超新星光变曲线」，或输入「我想研究Ia型超新星光变曲线与红移的关系」。

### 哪些步骤走通

| 步 | 走得通吗 | 评委应看到 |
|---|---|---|
| 科研问题 | 是 | 新 session，与 HER2 隔离 |
| AI理解 | 是 | domain 倾向 astronomy；不要把 HER2 字段读进这条会话 |
| 研究规划 | 部分 | Planner **不**伪造冻结合同；notice 说非肿瘤不是医学合同 |
| 数据发现 | 是，但是目录 | Registry：`catalog_only` / `planned`，无下载按钮 |
| 字段映射 | 是，但是 DRAFT | pack `status=DRAFT`，字段像 `sn_id` / `band` / `flux`，不是 `her2_status` |
| 证据解释 | 是 | 仍可投影「为什么选 / 为什么排除」 |
| 图理解 | 是（浅） | caption 含光变 → `figure_type=light_curve`，仍不入库 |
| 执行 | **停** | 后端 422 `only_oncology_integrate_supported` |
| 科研数据资产 | **停** | 无主表，也不允许编一行测光点 |

### 停在哪里，为什么

停在 **Integrate 门**，不是停在「系统不懂天文」。

代码事实：`OncologyIntegrator` 对 astronomy / materials 直接拒绝。Registry 禁止这些域挂 `active + fetch`。

**必须说的一句：**

> 通用入口可以规划到字段和证据；没有插件就不假装取数。这比乱套 HER2 字段更接近科研工具。

不要在超新星案例点旧页「发送并开始研究」——旧内核会按肿瘤任务跑。

---

## 时间盒

| 时间 | 内容 | 可砍 |
|---|---|---|
| 0:00–0:40 | 定位 + 八步脊骨 | 不砍 |
| 0:40–4:20 | HER2 到 Graph + Why | 可砍附图 |
| 4:20–6:50 | 超新星：目录、DRAFT、拒绝执行 | 可砍 Matcher 细节 |
| 6:50–8:00 | 边界：前端未做 Preview；医学执行是插件 | 超时就只留一句话总结 |

超时优先级：保住 Graph Why 和超新星 422，砍 Swagger Preview。

---

## 演示失败预案

| 现象 | 怎么说 | 不要做什么 |
|---|---|---|
| 方案 422 | 指出 `research_goal_not_ready`，回去点疗效预测 | 不要改口说系统坏了 |
| Discover 只有 unverified | 这是设计 | 不要手写「已覆盖」 |
| Mapping 全是 REJECT | 说明 Matcher 低置信，图上仍可解释 | 不要改数字 |
| Graph 节点很多 | 这是 API 投影，不是力导向表演 | 不要拖节点 |
| Execute 超时 | 承认 live 依赖外部 API | 不要用假 CSV |
| 误开 `/` | 立刻说这是内核实验室，不是 V3.1 | 不要点「发送并开始研究」 |

---

## 最终答辩一句话

> 我们做的是可拒绝的科研数据智能体：先理解、再规划、再解释；医学插件才能执行，天文必须停在规划层——因为没有证据，就不生成数据。
