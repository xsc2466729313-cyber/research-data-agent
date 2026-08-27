# Research Planning Phase 1

## 本阶段结果

本阶段把系统入口从“必须输入明确科研问题”扩展为：

```text
宽泛研究方向
→ Topic Spec
→ 可替换文献 Provider 检索
→ 带 Evidence 的候选科研问题
→ Required / Recommended / Optional 字段
→ Research Contract
→ 兼容现有 ResearchBriefBuilder
```

本阶段只实现科研问题形成层，不引入 RAG、Source Broker、前端静态演示或新的患者数据合并逻辑。

## 新模块

### `backend/app/research_planning/`

- `ResearchIntentAgent`：识别领域、疾病、已知研究维度和歧义程度。
- `ResearchFormulationAgent`：形成至少 3 个候选问题，并按 E/D/F/N/T 生成明确标记为 `provisional` 的可行性分数。
- `FieldPlanningAgent`：生成 Required / Recommended / Optional 字段需求。
- `MetricPlanningAgent`：按 association、prediction、survival 等研究范式选择指标。
- `ResearchContractBuilder`：生成结构化 Research Contract；Required 字段缺少论文 Evidence 时状态为 `NEEDS_EVIDENCE`。
- `ResearchPlanningService`：提供 Topic、扫描、候选问题和 Contract 的阶段状态。

### `backend/app/literature/`

- `LiteratureProvider`：可替换 Provider 协议。
- `EuropePMCProvider`：复用已有 `DiscoveryAdapter.search_europe_pmc()`，统一为 `PaperRecord`。
- `GiiispProvider`：安全骨架。只读取进程环境中的 `GIIISP_API_KEY` / `GIIISP_BASE_URL`；在官方端点和响应 Schema 未配置前不会猜测接口或发出请求。
- `LiteratureAgent`：Provider fallback、去重、调用审计和失败隔离。

论文记录只进入 planning/evidence 层，不进入患者主表。每条论文记录包含 `source_id`、真实 `source_url` 和原始 metadata；Provider 调用记录 query、时间、状态、URL 与结果数。

## API

### 创建宽泛研究主题

```http
POST /api/research/topics
Content-Type: application/json

{
  "topic": "乳腺癌新辅助治疗"
}
```

### 扫描论文并形成候选问题

```http
POST /api/research/topics/{topic_id}/literature-scan
Content-Type: application/json

{
  "max_records": 20
}
```

### 获取候选问题

```http
GET /api/research/topics/{topic_id}/question-candidates
```

### 选择问题并生成 Research Contract

```http
POST /api/research/questions/{candidate_id}/select
Content-Type: application/json

{}
```

如果用户通过 override 修改问题、人群、暴露或结局，系统不会自动继承旧问题的 Literature Evidence，Contract 会要求重新核验。

### 读取 Contract

```http
GET /api/research/contracts/{contract_id}
```

## 与旧流程兼容

原有 `/api/agent/tasks`、`/api/research/task` 和所有 Adapter API 保持不变。

`ResearchBriefBuilder.build_from_contract(contract)` 将新契约映射到旧优先级：

| Research Contract | 旧 ResearchBrief |
|---|---|
| Required | primary |
| Recommended | important |
| Optional | secondary |

冻结的 `configs/canonical_schema.yaml`、`configs/medical_rules.yaml`、`configs/quality_rules.yaml` 和 SDTI 公式均未修改。

## 状态与迁移

- 本阶段状态保存在进程内，服务重启后 Topic/Contract ID 失效。
- 无数据库迁移。
- 无新增依赖。
- 下一阶段若需要持久化，应先定义 Topic/Contract 版本表，不应把自然语言重新解析结果当作稳定主键。

## 测试

```powershell
python -m pytest backend\tests\test_research_planning.py
python -m pytest
```

测试覆盖宽泛主题、真实来源字段、Europe PMC 复用、Evidence 门控、字段分层、指标匹配、集思谱 Secret 安全、旧 Brief 兼容和完整 API 链路。

后续的 Planning RAG 和 Scientific KG MVP 已在总方案 Phase 3 落地，见 `docs/PLANNING_RAG_PHASE3.md`。
