# Repair 质量闭环

阶段 09 实现了一个面向冻结 `CanonicalRecord` 粒度的、默认拒绝不确定修改的 Repair 闭环：

```text
error_classifier
→ repair_policy
→ repair_executor
→ revalidator
→ repair_log
```

它不会修改冻结 Schema、医学安全规则或评测公式。

## API

- `POST /api/repair/classify`：只运行错误分类，不改变记录。
- `POST /api/repair/run`：运行分类、策略、执行、重验证和审计的完整闭环。

最小请求：

```json
{
  "task_id": "repair-demo-001",
  "records": [
    {
      "record_id": "record-001",
      "source_authority": "standard",
      "record": {
        "study_id": "TCGA-BRCA",
        "disease": "Breast Cancer",
        "drug": "Herceptin",
        "source_id": "fixture:source-1",
        "raw_field": "drug_name",
        "raw_value": "Herceptin",
        "confidence": 1.0
      }
    }
  ]
}
```

`record_id` 是本次 Repair 任务中的稳定记录标识；`record` 必须以冻结 Canonical Schema 为目标结构。`source_authority` 只用于判断高权威来源冲突，不写入 CanonicalRecord。

## 质量检查粒度

分类器在 CanonicalRecord 粒度运行以下高信号检查：

- 必填字段、类型、允许值、数值范围和冻结字段集合；
- `source_id/raw_field/raw_value` 来源完整性；
- 完全重复记录；
- 确定性 Gene/Drug alias 与大小写；
- gene/drug 维度错放；
- `HER2 IHC 2+ → Positive`；
- `ERBB2 CNA → HER2 IHC Positive`；
- 同一样本对应多个患者；
- 同一实体和 assay/domain 下的高权威来源冲突；
- `AUC/IC50/viability` 错入临床 response domain。

分类输出为确定性 `finding_id`，包含错误类型、规则、受影响记录、风险等级、观测值和候选修复。候选修复不等于执行授权。

## Repair Policy

自动修复允许列表直接读取 `configs/medical_rules.yaml`：

| 错误 | 行为 |
|---|---|
| 完全重复 | 保留第一条，将后续副本设为 `quarantined`；原记录不删除 |
| 明确 Gene Symbol alias | 自动替换 canonical `gene` |
| 确定性药物 alias | 自动替换 canonical `drug` |
| 确定性大小写 | 自动替换对应 canonical 字段 |
| 缺失来源或冻结必填值 | `blocked`，不编造值 |
| HER2/assay、ERBB2 CNA、response domain、身份或高权威冲突 | `review`，不自动改值 |
| Schema 语义错放或其他非允许项 | `review`，不静默删改 |

若同一记录同时存在高风险问题，即使还存在可确定修复的 alias，该 alias 也会被抑制并随整条记录进入 review，避免部分修复制造“已安全”的假象。

## 修改、回滚与审计

每个 finding 都产生策略决策和 Repair Log。实际修改项保存：

- 修改前完整记录与 disposition；
- 修改后完整记录与 disposition；
- `replace/quarantine` 字段差异；
- policy rule/version；
- 执行状态；
- 重验证状态；
- 基于上述稳定内容计算的 SHA-256 审计摘要。

`source_id`、`raw_field`、`raw_value` 不在自动替换目标中。完全重复也只隔离副本，不丢弃它的来源记录。

执行后，`revalidator` 会再次运行同一分类器，并用 Pydantic `CanonicalRecord` 复核冻结接口。若自动修复后仍失败，相关修改回滚，记录转入 review，再运行一次验证。`validation_history` 保留每次验证结果。

## 输出状态

- `publishable_records`：修复并验证通过的记录；
- `review_records`：医学语义、身份或冲突待人工复核；
- `blocked_records`：缺失真实证据或不满足冻结接口；
- `quarantined_records`：非破坏性隔离的完全重复副本；
- `safety_gate`：`PASS/REVIEW/FAIL`；
- `quality_before/quality_after`：修复前后的质量检查证据；
- `repair_log`：完整修复审计。

对 `publishable_records` 再运行 Repair，若输入已无错误，将得到零 finding、零 repair log，体现幂等性。

## 评测边界

Repair 运行成功不等于 Repair Accuracy 已达标。API 固定返回：

```json
{
  "repair_accuracy_evaluation_status": "NOT_EVALUATED",
  "repair_accuracy": null
}
```

只有通过冻结真实 Gold Set 的阶段 07 评测服务，才能按既定公式计算 Repair Accuracy；本闭环不会用规则样例生成虚假成绩。

## 测试

```powershell
python -m pytest backend\tests\test_repair_loop.py backend\tests\test_repair_api.py -ra
python -m pytest -ra
```

测试覆盖安全 alias、大小写、重复隔离、幂等性、前后快照、来源保留、再次验证、缺失来源阻断、HER2/CNA/domain/患者关联/高权威冲突 review，以及 API 业务值。
