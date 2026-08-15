# GEO Adapter（阶段 02）

## 边界

输入：

```text
SearchPlan（必须包含 GEO task）
+ GEOAdapterOptions
```

输出：

```text
GEOResourceAvailability[]
+ GEOResourceRecord[]
+ SourceItem[]
+ cache_hit
```

Adapter 只负责校验 GSE accession、发现 NCBI GEO 官方文件、按需下载和登记来源；不解析表达值，不执行字段标准化、样本关联或医学推断。

## 官方目录规则

GEO Series 归档以 accession 末三位替换为 `nnn` 后分桶。例如：

- `GSE25066` → `GSE25nnn/GSE25066/`
- `GSE76360` → `GSE76nnn/GSE76360/`

Adapter 使用 NCBI 官方 HTTPS 归档：

- Series Matrix：`https://ftp.ncbi.nlm.nih.gov/geo/series/{bucket}/{accession}/matrix/`
- SOFT：`https://ftp.ncbi.nlm.nih.gov/geo/series/{bucket}/{accession}/soft/`
- Supplement：`https://ftp.ncbi.nlm.nih.gov/geo/series/{bucket}/{accession}/suppl/`
- Accession 页面：`https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={accession}`

官方说明：

- https://www.ncbi.nlm.nih.gov/geo/info/download.html
- https://www.ncbi.nlm.nih.gov/geo/info/geo_paccess.html
- https://www.ncbi.nlm.nih.gov/geo/info/soft.html

## API 请求示例

```json
{
  "search_plan": {
    "task_id": "task_geo_001",
    "plans": [
      {
        "source": "GEO",
        "goal": "获取乳腺癌队列的表达矩阵和原始来源文件",
        "priority": 1,
        "mode": "live"
      }
    ]
  },
  "options": {
    "accession": "GSE25066",
    "resource_types": ["series_matrix", "soft", "supplement"],
    "max_files_per_type": 10,
    "download": false,
    "max_download_bytes": 25000000,
    "refresh_cache": false
  }
}
```

端点：`POST /api/adapters/geo`

## 下载与缓存安全

- 默认 `download=false`，只登记官方文件，不拉取大型原始包。
- `max_download_bytes` 是单文件硬限制；若响应头已表明超限，会在写盘前拒绝。
- 下载采用临时 `.part` 文件，成功后原子替换正式缓存文件。
- 下载后计算 SHA-256，并写入本地完整性清单；复用缓存前重新计算并比对。
- 目录元数据默认缓存 24 小时；`refresh_cache=true` 可强制刷新。
- Docker 使用独立命名卷 `geo_cache`，挂载到 `/workspace/data/cache/geo`。

GEO 目录在发现阶段未提供逐文件校验值，因此未下载的 `SourceItem.checksum` 保持 `null`，不会伪造校验值。

## SourceItem 登记

每个文件保留：

- 真实 `GSE` accession
- NCBI GEO 官方 HTTPS 文件 URL
- 原始文件名（在 `GEOResourceRecord.file_name`）
- `series_matrix / soft / supplement` 类型
- `discovered / downloaded / cached` 状态
- 下载后的本地缓存路径和 `sha256:{digest}`（若启用下载）

内部 `source_id` 使用 `geo:{accession}:{official_url_hash}`，由真实 accession 和官方 URL 确定性生成。

## 错误分类

```text
invalid_plan
invalid_accession
accession_not_found
resource_not_found
network_error
timeout
rate_limited
remote_error
invalid_response
cache_error
download_too_large
download_error
checksum_mismatch
```

`accession_not_found` / `resource_not_found` 与 `network_error` / `timeout` 明确分离；错误响应还包含 `retryable`、上游 HTTP 状态和非敏感详情。

## 测试

普通测试使用 `httpx.MockTransport`，不依赖外网：

```powershell
python -m pytest backend/tests/test_geo_adapter.py backend/tests/test_geo_api.py
```

真实集成测试访问 NCBI 官方归档，并覆盖 `GSE25066` 与 `GSE76360`：

```powershell
$env:RUN_GEO_INTEGRATION='1'
python -m pytest backend/tests/test_geo_integration.py
```

`GSE25066` 集成测试仅下载小型 `GSE25066_Genelist_weights.txt.gz`；大型 RAW、Matrix 和 SOFT 文件只做发现，避免无意产生大流量。
