# GDC Adapter（阶段 01）

## 边界

输入：

```text
ResearchSpec
+ SearchPlan（必须包含 GDC task）
+ GDCAdapterOptions
```

输出：

```text
GDCProjectRecord
+ GDCFileRecord[]
+ SourceItem[]
+ cache_hit
```

Adapter 只负责发现、获取和登记 GDC 原始文件，不负责医学标准化、患者关联或跨源融合。

## 官方端点

- 项目检索：`https://api.gdc.cancer.gov/projects`
- 文件检索：`https://api.gdc.cancer.gov/files`
- 单文件下载：`https://api.gdc.cancer.gov/data/{file_uuid}`
- 项目页面：`https://portal.gdc.cancer.gov/projects/{project_id}`

参考：

- https://docs.gdc.cancer.gov/API/Users_Guide/Getting_Started/
- https://docs.gdc.cancer.gov/API/Users_Guide/Search_and_Retrieval/
- https://docs.gdc.cancer.gov/API/Users_Guide/Downloading_Files/

## API 请求示例

```json
{
  "research_spec": {
    "task_id": "task_gdc_001",
    "research_goal": "研究 TCGA-BRCA 乳腺癌临床与组学数据",
    "disease": "Breast Cancer",
    "subtype": null,
    "genes": ["ERBB2", "PIK3CA"],
    "variants": [],
    "drugs": [],
    "outcomes": [],
    "required_data_types": ["clinical", "mutation"],
    "target_fields": []
  },
  "search_plan": {
    "task_id": "task_gdc_001",
    "plans": [
      {
        "source": "GDC",
        "goal": "获取 TCGA-BRCA 临床与组学文件",
        "priority": 1,
        "mode": "live"
      }
    ]
  },
  "options": {
    "project_id": "TCGA-BRCA",
    "data_types": ["Clinical Supplement"],
    "max_files": 2,
    "download": false,
    "max_download_bytes": 25000000,
    "open_access_only": true,
    "refresh_cache": false
  }
}
```

## SourceItem 登记

每个 GDC 文件保留：

- `source_id = gdc:{file_uuid}`
- `accession = TCGA-BRCA`
- 官方 `/data/{file_uuid}` URL
- GDC `data_format`
- `md5:{checksum}`
- `discovered / downloaded / cached` 状态
- 下载后的本地缓存路径（若启用下载）

## 错误分类

```text
invalid_plan
network_error
timeout
auth_required
rate_limited
api_error
invalid_response
project_not_found
no_files
cache_error
download_too_large
download_error
checksum_mismatch
```

错误响应包含 `retryable`、上游 HTTP 状态和非敏感详情。GDC token 只从 `GDC_AUTH_TOKEN` 环境变量读取。
