# cBioPortal Adapter（阶段 03）

## 边界

输入：

```text
SearchPlan（必须包含 cBioPortal task）
+ CBioPortalAdapterOptions
```

输出：

```text
CBioPortalStudyRecord（含原始 study metadata）
+ CBioPortalSelection
+ CBioPortalRawTable[]
+ SourceItem[]
+ cache_hit
```

Adapter 负责从 cBioPortal 官方公开 API 读取研究元数据和原始表格切片，并登记可追溯来源。它不负责标准化、患者合并或医学解释。

## 官方端点

- Study：`GET /api/studies/{studyId}`
- Molecular profiles：`GET /api/studies/{studyId}/molecular-profiles`
- Sample lists：`GET /api/studies/{studyId}/sample-lists`
- Gene lookup：`POST /api/genes/fetch`
- Clinical data：`GET /api/studies/{studyId}/clinical-data`
- Mutations：`POST /api/molecular-profiles/{profileId}/mutations/fetch`
- Discrete CNA：`POST /api/molecular-profiles/{profileId}/discrete-copy-number/fetch`

官方资料：

- https://docs.cbioportal.org/web-api-and-clients/
- https://www.cbioportal.org/api/swagger-ui/index.html
- https://github.com/cBioPortal/datahub

首个固定测试研究为 `brca_metabric`。Adapter 不硬编码 METABRIC 的 profile 或样本列表答案，而是读取官方 metadata 后按数据类型和 sample-list category 动态选择；用户也可显式指定并接受合法性检查。

## API 请求示例

```json
{
  "search_plan": {
    "task_id": "task_cbioportal_001",
    "plans": [
      {
        "source": "cBioPortal",
        "goal": "获取 METABRIC 临床、突变和拷贝数原始表",
        "priority": 1,
        "mode": "live"
      }
    ]
  },
  "options": {
    "study_id": "brca_metabric",
    "tables": [
      "clinical_sample",
      "clinical_patient",
      "mutations",
      "discrete_cna"
    ],
    "gene_symbols": ["ERBB2", "PIK3CA", "TP53"],
    "max_records_per_table": 100,
    "cna_event_type": "ALL",
    "sample_list_id": null,
    "mutation_profile_id": null,
    "cna_profile_id": null,
    "refresh_cache": false
  }
}
```

端点：`POST /api/adapters/cbioportal`

## 原始字段与截断语义

返回表包括：

- `molecular_profiles`
- `sample_lists`
- `genes`
- `clinical_sample`
- `clinical_patient`
- `mutations`
- `discrete_cna`

`rows` 保持 cBioPortal JSON 的原始字段和值，包括 `studyId`、`patientId`、`sampleId`、`clinicalAttributeId`、`proteinChange`、`alteration` 及嵌套 `gene`。`raw_fields` 只是原始顶层字段名索引，不改写行数据。

Clinical 和 mutation 端点使用官方分页参数；当一页达到 `max_records_per_table` 时，`truncated=true`，且因上游未返回总数，`upstream_row_count=null`。Discrete CNA 端点不提供分页参数，因此完整响应写入可校验缓存，再限量放入 API 响应；此时 `upstream_row_count` 是完整响应行数。

## 医学安全边界

离散 CNA 的 `alteration` 保持 cBioPortal 原值，绝不在本阶段转换成 `her2_status`。尤其是 ERBB2 amplification 不等价于 HER2 IHC positive；临床 `HER2_STATUS` 与 ERBB2 CNA 必须留待后续标准化阶段按不同 assay/语义维度处理。

## 缓存与 SourceItem

- 每次官方请求以 method、URL、query parameters 和 JSON body 生成确定性缓存键。
- 原始 JSON payload 与缓存 manifest 分开保存。
- payload 写入时计算 SHA-256；缓存复用前重新计算并比对。
- 每个 study/table 都有独立 `SourceItem`，记录真实 study ID、官方 API URL、本地原始 JSON、校验值和 `retrieved/cached` 状态。
- 默认缓存 24 小时；`refresh_cache=true` 强制刷新。
- Docker 命名卷 `cbioportal_cache` 挂载至 `/workspace/data/cache/cbioportal`。

POST 请求的完整 query/body 记录在对应 `CBioPortalRawTable.request` 中，确保仅有 URL 时仍可重放同一数据切片。

## 错误分类

```text
invalid_plan
invalid_study_id
invalid_selection
study_not_found
profile_not_found
sample_list_not_found
gene_not_found
network_error
timeout
auth_required
rate_limited
remote_error
invalid_response
cache_error
```

不存在、网络失败、超时和上游限流分别返回不同错误码；错误体还包含 `retryable`、上游 HTTP 状态和非敏感详情。

## 测试

普通测试不访问外网：

```powershell
python -m pytest backend/tests/test_cbioportal_adapter.py backend/tests/test_cbioportal_api.py
```

真实 METABRIC 集成测试：

```powershell
$env:RUN_CBIOPORTAL_INTEGRATION='1'
python -m pytest backend/tests/test_cbioportal_integration.py
```
