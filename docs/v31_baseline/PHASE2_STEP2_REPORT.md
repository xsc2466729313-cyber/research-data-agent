# V3.1 Phase 2-B1 报告

- 完成日期：2026-09-05
- 分支：`feat/v31-phase1-copilot`
- 基线 HEAD：`8e023e1ee2b37abf0f9b114ddf53661444d97f7c`
- 范围：Discovery Candidate Generator
- 未做：SourceBroker 改造、Integrate、自动取数、新 Adapter、Schema Generator、Evidence Graph、Figure Understanding

Discovery 只根据 Registry 与合同输入产生候选。它不是取数器，也不证明字段已经存在。

---

## 1. 修改文件列表

- `backend/app/v30/api.py`：增加 `POST /api/v30/discover`
- `backend/app/v30/models.py`：增加 Discover 请求/候选模型
- `backend/tests/v30/test_registry.py`：OpenAPI 现包含 `/api/v30/discover`，仍不包含 select

未修改：

- `backend/app/sources/**`
- `backend/app/source_broker/**`
- `backend/app/agent/service.py`
- Adapter / Quality / SchemaMatcher
- 任何旧测试文件
- `configs/canonical_schema.yaml`、`configs/medical_rules.yaml`

---

## 2. 新增文件列表

```text
backend/app/v30/discovery/__init__.py
backend/app/v30/discovery/service.py
backend/tests/v30/test_discovery_honesty.py
docs/v31_baseline/PHASE2_STEP2_REPORT.md
```

未创建 select/integrate 路由，未改 SourceBroker。

---

## 3. API 说明

`POST /api/v30/discover`

输入：

```json
{
  "domain": "oncology",
  "topic": "HER2阳性乳腺癌耐药机制",
  "contract_id": null,
  "required_modalities": ["expression"],
  "field_gaps": ["gene_expression"]
}
```

输出：`DiscoveryCandidate` 列表。每条包含：

| 字段 | 本刀取值 |
|---|---|
| `candidate_id` | `disc-{domain}-{source_key}` |
| `source_key` | 来自 Registry |
| `resource_kind` | 来自 Registry |
| `locator` | 方案级定位（如 GSE 模式），不是已找到的具体 accession |
| `source_id` | `registry:{source_key}` |
| `discovered_from` | `registry` |
| `field_hypotheses` | 假说；`coverage_claimed=false` |
| `verification_status` | `unverified` / `catalog_only` / `verified`（本刀不发出 `verified`） |
| `next_action` | 医学建议 `fetch_via_adapter`；目录 `request_upload`；planned `reject` |

响应另有 `fetched=false`、`integrated=false`。

医学：从 Registry 读取 GEO / GDC / cBioPortal / Europe PMC 等，只生成候选，不调用 Adapter。  
天文 / 材料：`verification_status=catalog_only`，`registry_status` 只能是 `catalog_only` 或 `planned`，不会变成 `active`。

未挂 `POST /api/v30/discover/{set_id}/select`。

---

## 4. 测试结果

解释器：仓库 `.venv`。`PYTHONPATH=.`。

`backend/tests/v30`：**33 passed / 0 failed**

`test_discovery_honesty.py` 5 项：

1. GEO 候选可生成，但未取数、未声称已找到 GSE
2. planned 来源不能变成 active / verified
3. catalog_only 不能声称字段覆盖
4. Discovery 不导入 Adapter / SourceBroker / `ResearchAgentService`
5. `/api/v30/discover` 只返回候选；select 不存在

Phase 0 固定回归：**234 passed / 0 failed**。

---

## 5. git diff 检查

| 路径 | 本刀 diff |
|---|---|
| `backend/app/sources/**` | 无 |
| `backend/app/source_broker/**` | 无 |
| `backend/app/agent/service.py` | 无 |
| 旧测试 | 无 |
| 冻结 configs | 无 |

---

## 6. 医学链路影响

**未影响。** 不下载数据，不写 CanonicalRecord，不生成 CSV，不调用 Adapter，不进入 integrate。旧 234 回归保持。

---

## 7. 下一步

SourceBroker 组合与 Integrate 属于后续刀。本任务到此停止。
