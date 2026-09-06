# Frontend Phase 3 报告

- 完成日期：2026-09-05
- 依据：`FRONTEND_IMPLEMENTATION_PLAN.md`
- 范围：Sources + Schema Mapping
- 未做：Evidence Graph、Preview、Dataset、Execute

来源发现与字段对齐两个工作面已落地。这不是搜索结果页，也不是数据表。状态只写入 SessionStore 的 API 回包。

---

## 1. 修改文件列表

| 文件 | 改动 |
|---|---|
| `frontend/v31/app/api/v30.js` | `getRegistrySources` / `discoverSources` / `selectSources` / `generateSchemaPack` / `getSchemaPack` / `matchSchema` |
| `frontend/v31/app/main.js` | 挂载 Sources、Mapping；Graph 等仍显示「本阶段尚未开放」 |
| `frontend/v31/app/timeline-store.js` | 来源门：`discovery` 或 `selection`；字段门：仅 `mappings` |
| `frontend/v31/app/pages/timeline.js` | plan ready 可进 Sources；来源 ready 可进 Mapping |
| `frontend/v31/index.html` | 引入 `sources.css`、`mapping.css` |
| `frontend/v31/styles/components/tables.css` | Selection 表样式 |
| `frontend/v31/styles/components/badges.css` | `badge-auto` 墨色，不是绿完成 |
| `backend/tests/v31_frontend/test_phase0_shell.py` | 仍禁止 graphs / integration / agent |
| `backend/tests/v31_frontend/test_phase1_copilot.py` | Copilot 自身不调用 discover |
| `backend/tests/v31_frontend/test_phase2_timeline.py` | 字段门只认 `mappings` |

未修改：`frontend/index.html`、`frontend/app.js`、`frontend/styles.css`、后端业务模块、冻结配置。

---

## 2. 新增文件列表

```text
frontend/v31/app/pages/sources.js
frontend/v31/app/pages/mapping.js
frontend/v31/app/components/source-card.js
frontend/v31/app/components/selection-board.js
frontend/v31/app/components/mapping-table.js
frontend/v31/styles/pages/sources.css
frontend/v31/styles/pages/mapping.css
backend/tests/v31_frontend/test_phase3_sources_mapping.py
FRONTEND_PHASE3_REPORT.md
```

---

## 3. Sources 页面效果

打开只读 Registry，不自动 Discover。核心文案：发现不是覆盖；候选不是已验证。

**Registry Strip**

- 字段：`display_name`、`domain`、`resource_kind`、`status`、`fetch_binding`、`integrate_eligible`
- `active`：原样显示
- `catalog_only`：目录来源
- `planned`：计划支持
- 无下载按钮，无「已覆盖」

**Source Card**

- `source_id` / `source_key` / `resource_kind` / `locator` / `field_hypotheses` / `verification_status` / `next_action`
- 必须可见 `unverified`
- 必须可见 `fetched=false` · `integrated=false`
- 无覆盖率进度条，无「已找到数据」

**Selection Board**

- 两组：`selected_candidates` / `rejected_candidates`
- 每条显示 API 的 `reason_code` 与 `reason`
- 前端不写死 METABRIC

浏览器 HER2：Registry 显示 `official_api` + `active`；发现六张 unverified 卡；应用选择后出现两组 reason_code 表。来源门在 discovery 进入 Store 后 ready，不按 domain 判断。

---

## 4. Mapping 页面效果

打开不自动 Match。这是 Schema Pack + 字段对齐，不是数据表。

**Schema Pack**

- `schema_pack_id` / `domain` / `entity_type` / `binding` / `status`
- 医学：`frozen_canonical`（`oncology_canonical_v0.1`，`entity_type=patient`）
- 天文：回包 `status=DRAFT`
- 生成后立刻 `GET /schema-packs/{id}` 回看

**Mapping**

- 视觉：`source_field` ↓ `target_field`
- `confidence` / `status` / `risk_level` 来自 API
- `AUTO` 墨色，不是绿色完成
- `REVIEW` 琥珀，不是失败
- 不可编辑字段

**Honest Display**

- 固定 `row_count`、`generates_data`
- `row_count=0` 显示「未生成数据行。」
- 不画空数据表假装有行

浏览器：生成 pack 后字段门仍 idle；预览映射后字段门才 ready。Graph 未实现。

---

## 5. API 调用说明

| 时机 | 封装 | API |
|---|---|---|
| 打开 Sources 且有 `plan.domain` | `getRegistrySources()` | `GET /api/v30/registry/sources?domain=` |
| 点「发现候选」 | `discoverSources()` | `POST /api/v30/discover` |
| 点「应用选择」 | `selectSources()` | `POST /api/v30/source-selection` |
| 点「生成或绑定 Schema Pack」 | `generateSchemaPack()` 后 `getSchemaPack()` | `POST /api/v30/schema-packs/generate` + `GET /api/v30/schema-packs/{id}` |
| 点「预览映射」 | `matchSchema()` | `POST /api/v30/schema-packs/match` |

写入 SessionStore：`registry`、`discovery`、`selection`、`schemaPack`、`mappings`。

未调用：`/api/v30/graphs/*`、`/api/v30/integration/*`、`/api/agent/tasks`、`/api/adapters/*`。

---

## 6. 测试结果

| 套件 | 结果 |
|---|---|
| `backend/tests/v31_frontend` | **25 passed** |
| `test_phase3_sources_mapping.py` | Registry 状态文案；catalog_only 无下载；Discovery unverified；Selection 分组 + API `reason_code`；Mapping AUTO/REVIEW；`row_count` 来自 API；不调用 integration/adapters/graphs；旧前端不变 |
| `backend/tests/v30` | **75 passed** |
| Phase 0 234 回归 | **234 passed** |

旧 `frontend/app.js` 仍无 `/api/v30`。`GET /` 仍是「发送并开始研究」。

---

## 7. 是否进入 Frontend Phase 4

**可以进入 Frontend Phase 4（Evidence Graph）。**

本阶段到此停止。未开发 Evidence Graph，未调用 `/api/v30/graphs/*`。
