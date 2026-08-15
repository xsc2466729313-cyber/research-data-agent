# CIViC Adapter（阶段 05）

## 边界

输入：

```text
SearchPlan（必须包含 CIViC task）
+ CIViCAdapterOptions
```

输出：

```text
CIViCEvidenceRecord[]
+ CIViCRawTable[]
+ SourceItem[]
+ search_request / pagination / cache_hit
```

Adapter 只接入 CIViC 状态为 `ACCEPTED` 的公开知识证据，输出域固定为 `knowledge_evidence`。它不执行患者或样本匹配，不把知识库陈述直接解释为个体治疗建议，也不把复杂分子谱中的成员变异拆成彼此独立的疗效结论。

## 官方数据源

- CIViC V2 GraphQL：`POST https://civicdb.org/api/graphql`
- GraphiQL：`https://civicdb.org/api/graphiql`
- V2 schema 文档：`https://griffithlab.github.io/civic-v2/`
- Evidence 数据模型：`https://docs.civicdb.org/en/latest/model/evidence.html`

CIViC V1 REST API 已停用。匿名公开读取可用，但官方默认匿名限流为长期平均每秒 3 次；因此单页最多 25 条、默认 5 条，并使用 24 小时本地缓存。可选 `CIVIC_API_KEY` 只通过 `Authorization: Bearer` 请求头传递，不写入查询追踪、缓存或 API 响应。

## 查询与原始表

默认查询 `Breast Cancer`，并把 `status: ACCEPTED` 固定在 GraphQL 查询中。可选上游过滤器：

- `molecular_profile_name`
- `therapy_name`
- `evidence_type`
- `evidence_level`
- `after_cursor`

本阶段生成八张原始关系表：

```text
evidence_items
molecular_profiles
diseases
genes
variants
therapies
sources
evidence_relations
```

每一行都包含 `raw_field` 和 `raw_value`。CIViC 原始 `id`、EID、分子谱 ID、Variant ID、Gene/Feature ID、Therapy ID、Disease ID、Source ID、PubMed/ASCO/ASH citation ID 和原始 publication 字段均被保留。

`evidence_relations` 每个 EID 只生成一行，并以数组保存同一分子谱中的 gene、variant 和 therapy 成员：

```text
evidence_id
civic_disease_id
civic_molecular_profile_id
civic_gene_ids / gene_symbols
civic_variant_ids / variant_names
civic_therapy_ids / therapy_names
civic_source_id / publication_id
relation_scope = molecular_profile_context
raw_field / raw_value
```

这种结构不会对多变异、多药组合做笛卡尔展开，因此不会制造“单个成员变异独立对应单药疗效”的错误语义。

部分当前 CIViC 记录在请求 `variantHgvs` 时会触发 GraphQL 非空约束错误。本 Adapter 不请求该字段，而是保留 `molecularProfile.variants[]` 的完整原始对象；没有明确 HGVS 时不会猜测或补造。

## API 请求示例

```json
{
  "search_plan": {
    "task_id": "task_civic_001",
    "plans": [
      {
        "source": "CIViC",
        "goal": "获取乳腺癌变异、药物和出版物证据关系",
        "priority": 1,
        "mode": "live"
      }
    ]
  },
  "options": {
    "disease_name": "Breast Cancer",
    "molecular_profile_name": null,
    "therapy_name": null,
    "evidence_type": null,
    "evidence_level": null,
    "max_evidence_items": 5,
    "max_rows_per_table": 10000,
    "after_cursor": null,
    "refresh_cache": false
  }
}
```

端点：`POST /api/adapters/civic`

响应中的 `total_count` 是当前上游过滤条件下的总数；存在后续页时，`next_cursor` 可传给下一次请求的 `after_cursor`。

## 缓存与来源登记

- GraphQL URL、完整 query 和 variables 共同生成确定性缓存键。
- GraphQL 响应默认缓存 24 小时，并通过 manifest 中的 SHA-256 校验。
- 每个 EID 的原始 JSON 独立写入 `evidence/EID{id}/`，文件名包含内容摘要。
- 每个 EID 生成独立 `SourceItem`，格式为 `source_id = civic:EID{id}`，记录真实 CIViC 页面、本地原始 JSON、SHA-256 和 `retrieved/cached` 状态。
- `refresh_cache=true` 强制重新访问官方 API。
- Docker 命名卷 `civic_cache` 挂载到 `/workspace/data/cache/civic`。

## 错误分类

```text
invalid_plan
invalid_query
no_evidence
graphql_error
network_error
timeout
rate_limited
authentication_error
remote_error
invalid_response
cache_error
```

GraphQL `errors` 不会作为部分成功数据继续处理，也不会写入正常缓存。无结果、请求错误、网络失败、超时、限流、凭据失败、上游错误、响应结构异常和缓存损坏分别返回不同错误码。

## 测试

普通测试完全使用 MockTransport，不访问外网：

```powershell
python -m pytest backend/tests/test_civic_adapter.py backend/tests/test_civic_api.py
```

真实乳腺癌 CIViC 集成测试：

```powershell
$env:RUN_CIVIC_INTEGRATION='1'
python -m pytest backend/tests/test_civic_integration.py
```

真实测试不硬编码证据答案，验证当前公开查询返回的 EID、`ACCEPTED` 状态、乳腺癌疾病上下文、Variant 关系、publication ID、逐 EID 原始文件 SHA-256 和缓存命中。
