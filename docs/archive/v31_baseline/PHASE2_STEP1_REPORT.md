# V3.1 Phase 2-A 报告

- 完成日期：2026-09-05
- 分支：`feat/v31-phase1-copilot`
- 基线 HEAD：`8e023e1ee2b37abf0f9b114ddf53661444d97f7c`
- 范围：Universal Source Registry
- 未做：Discovery 完整流程、Schema Generator、Evidence Graph、Figure Understanding、新 Adapter、自动取数

Registry 是来源能力目录，不是数据源本身。本刀只让系统按领域查询“有哪些来源、能不能进入 integrate”，不发现数据集，不取数。

---

## 1. 修改文件列表

- `backend/app/v30/api.py`：增加 `GET /api/v30/registry/sources`
- `backend/app/v30/models.py`：增加 `RegistrySource` / `RegistrySourceList`

`backend/app/main.py` 本刀未改。`mount_v30_routes` 已在 Phase 1 挂载。

未修改：

- `configs/canonical_schema.yaml`
- `configs/medical_rules.yaml`
- `backend/app/sources/**`
- SchemaMatcher / Quality Gate / Quality V2
- `backend/app/agent/service.py`
- 任何旧测试文件

---

## 2. 新增文件列表

```text
configs/v30/source_registry/oncology.yaml
configs/v30/source_registry/astronomy.yaml
configs/v30/source_registry/materials.yaml
backend/app/v30/registry/__init__.py
backend/app/v30/registry/service.py
backend/tests/v30/test_registry.py
PHASE2_STEP1_REPORT.md
```

未创建：`discovery/`、`schema_generator/`、`graph/`、`figures/`。未挂 `POST /api/v30/discover`。

---

## 3. API 说明

`GET /api/v30/registry/sources`

可选查询：

- `domain`：`oncology` / `astronomy` / `materials`
- `status`：`active` / `catalog_only` / `planned`
- `integrate_eligible`：`true` 只返回已绑定旧工具、允许后续 integrate 的条目

每条来源只描述能力：

| 字段 | 含义 |
|---|---|
| `source_key` | 稳定键 |
| `display_name` | 展示名 |
| `domain` | 领域 |
| `resource_kind` | official_api / repository / catalog / literature |
| `modalities` | 数据模态 |
| `fetch_binding` | 已有工具名或空 |
| `discovery_binding` | 已有目录工具名或空 |
| `status` | active / catalog_only / planned |
| `integrate_eligible` | 派生：仅 `active` 且 `fetch_binding` 为已知旧工具时为 true |

医学绑定：

| source_key | fetch_binding |
|---|---|
| gdc | `search_gdc` |
| geo | `search_geo`（`discovery_binding=search_geo_catalog`） |
| cbioportal | `search_cbioportal` |
| aact | `search_trials` |
| civic | `search_civic` |
| europe_pmc | `search_europe_pmc` |

天文 / 材料：只有 `catalog_only` 或 `planned`，`fetch_binding` 为空，`integrate_eligible=false`。加载时若给这些领域写 `active` 或假 Adapter 名，注册表会拒绝。

---

## 4. 测试结果

解释器：仓库 `.venv`（Python 3.11.3，pytest 8.3.5）。`PYTHONPATH=.`。

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/v30 -q
```

**28 passed / 0 failed**

`test_registry.py` 4 项：

1. 医学来源可查询，且绑定上述 6 个已有工具
2. `planned` / `catalog_only` 不能进入 integrate
3. Registry API 可按领域与 integrate 资格过滤；OpenAPI 无 `/api/v30/discover`
4. Registry 源码不导入 Adapter / `ResearchAgentService`

Phase 0 固定回归：**234 passed / 0 failed**。未改旧测试期望。

---

## 5. git diff 检查

相对 HEAD `8e023e1ee2b37abf0f9b114ddf53661444d97f7c`：

| 路径 | 本刀 diff |
|---|---|
| `backend/app/sources/**` | 无 |
| `backend/app/agent/service.py` | 无 |
| 旧 Adapter 测试 | 无 |
| `configs/canonical_schema.yaml` | 无 |
| `configs/medical_rules.yaml` | 无 |

本刀变更在 `backend/app/v30/`、`backend/tests/v30/`、`configs/v30/source_registry/`。

---

## 6. 医学链路影响

**未影响。** Registry 只读配置、只查询能力，不调用 Adapter，不生成 CanonicalRecord，不进入 integrate。旧医学取数路径不变。

---

## 7. 下一步

Phase 2-B 才是 Discovery Agent。本任务到此停止，没有实现 Discovery。
