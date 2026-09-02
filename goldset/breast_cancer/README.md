# Breast Cancer Gold Set Workspace

This directory is the domain-specific curation workspace. The development split is frozen after independent review and remains unofficial. `templates/` holds the held-out official-candidate paper (xsc, 2026-08-29). It is still not sealed `frozen_test`.

Official score on this paper: **SDTI 63.36** (`official-candidate-20260829T132222Z`), `publish_allowed=false`. Development 千问 LIVE 66.94 must not be copied into the official column.

## Required splits

- `development`: paper-grounded questions and source candidates used while building prompts and adapters.
- `validation`: independently reviewed cases used for threshold and prompt selection.
- `frozen_test`: sealed cases used exactly once for the final report.

Every case must retain a real `source_id`, accession/URL or PMID/DOI, raw field/value where applicable, label source, reviewer, and review status. A model draft or consensus snapshot is a proposal only. It cannot be copied into a frozen CSV without independent review, deterministic medical-rule validation, source verification, and a checksum manifest.

## Breast-cancer strata

The curation checklist must cover HER2-positive, HR-positive/HER2-negative, triple-negative, and mixed/unknown disease subtypes; clinical, preclinical cell-line, clinical-trial, and knowledge-evidence response domains; and low/medium/high identity confidence. Include explicit negative cases for `HER2 IHC 2+`, `ERBB2 CNA amplification`, cross-study patient IDs, and cell-line AUC/IC50 versus patient response.

`development/` 已由独立审核人 `xsc` 批准并写入 `MANIFEST.json`（2026-08-29）。这是 development 分册，不是 `frozen_test`，也没有拷进 `goldset/templates/`。千问 LIVE 观察见 `development/FROZEN.md`（`development-xsc-qwen-live-20260829`，非正式 SDTI 66.94）。

`official_candidate/` 是 held-out 正式考卷。独立审核人 **xsc** 于 2026-08-29 审核通过并写入 `goldset/templates/`。题面与金标准行未整份复制 development。`frozen=false`，不是 `frozen_test`。正式评测路径：`POST /api/evaluation/official-run` 或 `collect_official_sdti.py`。审核记录见 `official_candidate/AUDIT.md`。当前结果口径见 `docs/CURRENT_MAINLINE.md`。
