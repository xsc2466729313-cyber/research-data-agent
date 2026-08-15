# AACT / ClinicalTrials.gov Adapter（阶段 04）

## 边界

输入：

```text
SearchPlan（必须包含 AACT/ClinicalTrials.gov task）
+ AACTAdapterOptions
```

输出：

```text
AACTUnifiedTrial[]
+ AACTRawTable[]
+ SourceItem[]
+ search_request / pagination / cache_hit
```

Adapter 使用 ClinicalTrials.gov v2 官方 API 获取最新公开记录，并按 AACT 的多关系表语义拆分。它不执行跨试验患者合并，不将试验结果解释为患者级临床疗效，也不进行疗效结论推断。

## 数据来源与表结构

官方来源：

- ClinicalTrials.gov v2 API：`GET https://clinicaltrials.gov/api/v2/studies`
- 单试验 API：`https://clinicaltrials.gov/api/v2/studies/{nct_id}`
- AACT schema：以 `nct_id` 连接 studies、conditions、interventions、outcomes 等复数关系表

参考：

- https://clinicaltrials.gov/data-api/api
- https://clinicaltrials.gov/data-api/about-api/study-data-structure
- https://clinicaltrials.gov/data-api/about-api/search-areas
- https://aact.ctti-clinicaltrials.org/schema

本阶段生成六张表：

```text
studies
conditions
interventions
eligibilities
outcomes
outcome_measurements
```

每一行都包含：

- `nct_id`
- `trial_id`（与 `nct_id` 相同的统一主键别名）
- `source_id = clinicaltrials:{nct_id}`

上游对象和字段保留原始 camelCase，例如 `protocolSection`、`eligibilityCriteria`、`measure`、`groupId`、`lowerLimit`。层级化 outcome measurement 通过明确的 measure/class/category/measurement 索引拆成可追溯行，并保留各层原始对象。

## API 请求示例

```json
{
  "search_plan": {
    "task_id": "task_aact_001",
    "plans": [
      {
        "source": "AACT/ClinicalTrials.gov",
        "goal": "获取乳腺癌临床试验多关系原始表",
        "priority": 1,
        "mode": "live"
      }
    ]
  },
  "options": {
    "condition": "Breast Cancer",
    "query_terms": null,
    "max_trials": 5,
    "max_rows_per_table": 10000,
    "page_token": null,
    "refresh_cache": false
  }
}
```

端点：`POST /api/adapters/aact`

`query_terms` 直接对应官方 `query.term`，`condition` 对应 `query.cond`。响应保留 `total_count` 和 `next_page_token`，可用 `page_token` 获取后续页。单次最多请求 25 个完整试验记录；每张关系表另有显式响应行数上限和 `truncated/upstream_row_count`。

## 缺失结果的安全语义

每个统一 trial 使用以下状态之一：

- `available`：`hasResults=true` 且存在 `resultsSection`
- `not_reported`：`hasResults=false` 且不存在 `resultsSection`
- `inconsistent`：标志与实际结果区不一致或无法确认

`not_reported` 只表示当前公开记录没有结果区。它不表示阴性结果、治疗无效、零响应或失败试验。没有结果区时，`outcome_measurements` 不生成任何虚构行。

Protocol 中预设的 primary/secondary/other outcomes 仍进入 `outcomes` 表；只有公开 Results Section 中实际存在的 measurement 才进入 `outcome_measurements`。

## 缓存与来源登记

- 搜索请求由官方 URL 和完整 query parameters 生成确定性缓存键。
- 搜索响应默认缓存 24 小时，并使用 SHA-256 校验。
- 每个 trial 的原始 JSON 单独写入 `trials/{nct_id}/`，文件名包含内容摘要。
- 每个 NCT 生成独立 `SourceItem`，记录真实 NCT ID、官方单试验 API URL、本地原始 JSON、SHA-256 和 `retrieved/cached` 状态。
- `refresh_cache=true` 强制重新访问官方 API。
- Docker 命名卷 `aact_cache` 挂载至 `/workspace/data/cache/aact`。

## 错误分类

```text
invalid_plan
invalid_query
no_studies
network_error
timeout
rate_limited
remote_error
invalid_response
cache_error
```

无结果检索、网络失败、超时、限流、上游错误和缓存损坏分别返回不同错误码。

## 测试

普通测试不访问外网：

```powershell
python -m pytest backend/tests/test_aact_adapter.py backend/tests/test_aact_api.py
```

真实乳腺癌试验集成测试：

```powershell
$env:RUN_AACT_INTEGRATION='1'
python -m pytest backend/tests/test_aact_integration.py
```

真实测试包含：

- `NCT01104584`：验证公开 outcome measurements
- `NCT03751449`：验证缺失结果只标记 `not_reported`
