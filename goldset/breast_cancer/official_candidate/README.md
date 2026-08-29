# Official candidate Gold Set（已写入正式入口）

本目录是 **held-out 正式考卷**。独立审核人 **xsc** 于 2026-08-29 审核通过，并写入 `goldset/templates/`。

- `gold_set_id`：`breast-cancer-official-candidate-20260829`
- 版本：`official-candidate-v1`
- `copied_to_templates=true`
- `frozen=false`（尚未做来源/规则复验后的 checksum 冻结，不能当 sealed `frozen_test`）
- **不是** `frozen_test`
- 列格式与 templates / `GoldSetCsvLoader` 一致；`review_status=approved`

已对本卷跑正式评测：`evaluation_runs/official-candidate-20260829T132222Z/`，**SDTI = 63.36**，安全门 FAIL，`publish_allowed=false`。重跑：

```powershell
python goldset\breast_cancer\official_candidate\collect_official_sdti.py --retrieval planner
```

或 `POST /api/evaluation/official-run`。不要把 `goldset/breast_cancer/development/` 整份当作正式 Gold Set。development 已用于千问 LIVE 与检索改版（非正式 66.94），再当期末考则成绩不可信。

生成脚本：`build_candidate.py`（仅重写本目录草案，绝不写 templates；写入后会拒再生成）。
写入脚本：`promote_to_templates.py`（只允许从本目录拷入 templates，拒绝 development）。
