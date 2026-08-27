# Phase 4 Source Broker 完成报告

## 实现内容

本阶段按《Scientific Data Agent 终局完整设计包》将旧的“数据库调用顺序”升级为 Contract-driven Source Broker：

```text
ResearchContract
→ Source Discovery
→ Dataset Discovery
→ Capability Profiling
→ Field Coverage Matrix
→ Greedy Portfolio Selection
→ SourcePlan + JoinPolicy + Fallback
```

核心决策对象是具体 Dataset/Resource，不是笼统的“哪个网站最好”。Source Broker 只读已选定的 Research Contract，不重新解释原始 Topic。

## 新增文件

```text
backend/app/source_broker/
    models.py
    source_catalog.py
    source_discovery.py
    dataset_discovery.py
    capability_profiler.py
    source_matcher.py
    source_selector.py
    service.py

configs/source_capabilities/seed_datasets.yaml
backend/tests/test_source_broker.py
```

## Source / Dataset / Resource 分层

每个候选必须保留真实 `source_id` 和 `source_url`：

```text
Source: NCBI GEO
Dataset: GSE25066
Resource: Series Matrix
```

当前 seed catalog 覆盖已有 Adapter 正在使用的 cBioPortal、NCBI GEO 和 GDC 候选。旧 `search_planner._STUDY_PROFILES` 不再自带另一份硬编码真相，而是通过 `SeedSourceCatalog.legacy_study_profiles()` 读取同一版本化目录，从而保留旧 Agent 行为。

新目录不是实时数据真相。所有记录都显式标记：

```text
capability_status = seed_requires_runtime_verification
runtime_verified = false
```

论文新发现的 accession 只标记为 `literature_hint_requires_profiling`，不会因为“属于 GEO”就推断其拥有 expression、pCR 或 patient-level 数据。

## Field Coverage Matrix

覆盖单元格包含：

```text
field_id
priority
dataset_id
coverage
match_basis
runtime_verified
```

完全匹配为 `1.0`。如 Dataset 只声明泛化 mutation 能力，而 Contract 要求 `pik3ca_mutation`，规划分数最多为 `0.75`，并标记需要 gene-specific 运行时验证。`pCR` 不会被泛化 `treatment_response` 自动当成完全覆盖。

## 最小数据源组合

选择器先按单 cohort 的 Required Field Coverage、Recommended Coverage、权威性、可溯源性、粒度、结构化和访问成本排名，再使用 greedy set cover 增加能补充缺口的独立 cohort。

SourcePlan 同时返回两个不同口径：

- `required_field_coverage`：主分析单 cohort 覆盖率。
- `portfolio_required_field_coverage`：多个独立 cohort 的规划联合覆盖率。

联合覆盖率不代表可以进行 patient-level join。不同 Dataset 没有可核验 crosswalk 时必须输出：

```text
FORBIDDEN_PATIENT_JOIN
```

对 PIK3CA + pCR 这类高风险组合，GEO 的 pCR cohort 和 cBioPortal 的 mutation cohort 可以同时进入 portfolio，但只能分别分析、外部验证或纵向追加，禁止把不同患者拼成一张宽表。

## API 变化

### 生成 Source Plan

```http
POST /api/research/contracts/{contract_id}/source-plan
Content-Type: application/json

{
  "max_selected_datasets": 3,
  "preferred_dataset_ids": [],
  "public_data_only": true
}
```

返回：

```text
SourceCapability[]
DatasetCandidate[]
FieldCoverageMatrix
SourcePlan
JoinPolicy[]
Fallback datasets
```

### 读取已生成计划

```http
GET /api/research/source-plans/{source_plan_id}
```

## 兼容方式

- 旧 `/api/agent/*` 与 Adapter API 不变。
- `FieldDrivenSearchPlanner` 继续返回原有 tool calls。
- 旧 planner 从新 seed catalog 读取 legacy profile，不改函数签名。
- 本阶段不执行数据获取，不改 Integration、Repair 或冻结 Schema。

## 测试结果

```powershell
python -m pytest backend/tests/test_source_broker.py
python -m pytest backend/tests/test_research_brief.py backend/tests/test_research_planning.py backend/tests/test_planning_rag.py
python -m pytest
```

测试不只验证 HTTP 200，还验证：

- Source/Dataset/Resource 引用一致。
- 论文 accession 可回链到 paper ID。
- PIK3CA 与 pCR 不被误判为同 cohort 完整覆盖。
- 多 cohort 明确输出 `FORBIDDEN_PATIENT_JOIN`。
- 非乳腺癌 Topic 不会被硬塞乳腺癌 seed dataset。
- Source Plan 可按 ID 精确读回。

## 未解决问题与风险

- Dataset Capability 仍是 seed/hint，尚未用 Adapter 对每个候选执行实时 schema/sample-count 验证。
- Source Plan 与 Contract 仍是进程内状态，服务重启后 ID 失效。
- 本阶段没有使用 Credential，也不处理 OAuth/Login/Upload。
- `PARTIAL` 是对当前单 cohort 字段缺口的真实表达，不会为 Demo 将其伪装成 READY。

## 下一阶段建议

按终局设计顺序，下一阶段是 Phase 5 Access Broker：

```text
OPEN_API
API_KEY
MANUAL_DOWNLOAD
CredentialVault
WAITING_FOR_CREDENTIAL
```

在进入 Phase 5 前，SourcePlan 不应直接触发付费、登录或受控资源的自动采集。
