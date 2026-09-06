# V3.1 Phase 5-A 报告

- 完成日期：2026-09-05
- 分支：`feat/v31-phase1-copilot`
- 基线 HEAD：`8e023e1ee2b37abf0f9b114ddf53661444d97f7c`
- 范围：Figure Understanding Demo
- 未做：图像数字化入库、主表生成、Integrate、Adapter 新增、`POST /api/v30/extract`、前端卡片、EvidenceBuilder / Quality Gate 修改

这是图理解展示能力，不是数据提取入库。

---

## 1. 修改文件列表

- `backend/app/v30/api.py`：增加 `POST /api/v30/figures/understand`
- `backend/app/v30/models.py`：增加 `FigureUnderstandRequest` / `FigureUnderstandingResult`
- `backend/app/v30/graph/service.py`：允许 `FigureUnderstanding` / `Paper` / `File` 节点与 `EXTRACTED_FROM` 边

未修改：

- `configs/canonical_schema.yaml`
- `configs/medical_rules.yaml`
- `backend/app/evidence/evidence_builder.py`
- Quality Gate / Quality V2
- Adapter / SchemaMatcher / ParserRegistry
- `ResearchAgentService`

---

## 2. 新增文件列表

```text
backend/app/v30/figures/__init__.py
backend/app/v30/figures/service.py
backend/tests/v30/test_figure_understanding.py
PHASE5_STEP1_REPORT.md
```

---

## 3. API 说明

`POST /api/v30/figures/understand`

输入：

```json
{
  "source_id": "paper:sn-ia-demo",
  "figure_id": "Figure 3",
  "caption": "Ia型超新星论文 Figure 3 光变曲线",
  "optional_image_reference": null
}
```

`source_id` 必填。缺失或空白返回 422：

```json
{"error": "source_id_required"}
```

输出 `FigureUnderstandingResult`：

| 字段 | 说明 |
|---|---|
| `figure_type` | `light_curve` / `kaplan_meier` / `heatmap` / `scatter` / `workflow` / `unknown` |
| `x_axis` / `y_axis` | 轴语义假说，不是观测序列 |
| `legend_summary` | 图例文字摘要 |
| `extractability` | `none` / `caption_only` / `axes_only` / `digitization_possible` |
| `digitization_possible` | 是否看起来可人工数字化 |
| `confidence` | 0–1 |
| `status` | `UNDERSTOOD` / `REVIEW` / `FAILED` |
| `enters_primary_table` | 恒为 `false` |
| `row_count` | 恒为 `0` |
| `generates_data` | 恒为 `false` |

超新星 Figure 3 示例：`figure_type=light_curve`，`x_axis=phase_day`，`y_axis=magnitude`，`digitization_possible=true`，`confidence=0.85`，仍不进主表。

可选图片引用只作说明，不读像素，不生成 CSV / CanonicalRecord。

---

## 4. Figure Understanding 设计

服务根据 `figure_id` + `caption` 做类型假说，不打开图像文件。

- 能描述图类型、坐标轴、图例、可提取性。
- `digitization_possible=true` 只表示可以进一步人工数字化。
- 当前没有数字化成功路径，没有观测点数组，没有写主表的字段。

边界：

```text
JATS / 图注文本     → caption 输入
Figure Understanding → 类型 / 轴 / 可提取性
像素数字化           → 本阶段不提供
主表                 → 仍只来自 Adapter 或表格解析
```

---

## 5. Evidence Graph 连接方式

理解成功后写入同一进程内图：

```text
FigureUnderstanding  --EXTRACTED_FROM-->  Paper 或 File
```

节点只保存 `figure_type`、轴名、`extractability`、`status`、`enters_primary_table=false`。

不保存观测数据、`raw_value`、`canonical_value` 或患者记录。

返回体带 `graph_id`，可继续用 `GET /api/v30/graphs/{graph_id}` 查询。

---

## 6. 测试结果

`backend/tests/v30`：**57 passed / 0 failed**

`test_figure_understanding.py`：

1. 有 `source_id` 可以理解（超新星 Figure 3 → light_curve）
2. 无 `source_id` 拒绝 422
3. 结果 `enters_primary_table=false`，不含观测数据
4. 不调用 Adapter（模块不导入 sources / GEOAdapter / GDCAdapter）
5. 不修改 EvidenceBuilder（文件哈希不变）

Phase 0 固定回归：**234 passed / 0 failed**。

---

## 7. 医学链路影响分析

**未影响。** 图理解不取数、不写 CanonicalRecord、不进 Quality Gate、不改 EvidenceBuilder。Kaplan-Meier 等医学图也只产出理解卡。旧 Parser / Adapter / 导出主表路径不变，主表不会出现图估读数。

---

## 8. 下一步

Integrate / 数字化入库 / Extraction 门面属于后续阶段。本任务到此停止。
