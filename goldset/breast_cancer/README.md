# Breast Cancer Gold Set Workspace

This directory is the domain-specific curation workspace for the VNext system. It is not a frozen Gold Set yet.

## Required splits

- `development`: paper-grounded questions and source candidates used while building prompts and adapters.
- `validation`: independently reviewed cases used for threshold and prompt selection.
- `frozen_test`: sealed cases used exactly once for the final report.

Every case must retain a real `source_id`, accession/URL or PMID/DOI, raw field/value where applicable, label source, reviewer, and review status. A model draft or consensus snapshot is a proposal only. It cannot be copied into a frozen CSV without independent review, deterministic medical-rule validation, source verification, and a checksum manifest.

## Breast-cancer strata

The curation checklist must cover HER2-positive, HR-positive/HER2-negative, triple-negative, and mixed/unknown disease subtypes; clinical, preclinical cell-line, clinical-trial, and knowledge-evidence response domains; and low/medium/high identity confidence. Include explicit negative cases for `HER2 IHC 2+`, `ERBB2 CNA amplification`, cross-study patient IDs, and cell-line AUC/IC50 versus patient response.

The existing `evaluation/retrieval_gold.template.jsonl` and model consensus snapshots remain provisional inputs. They must be independently verified before entering this workspace's frozen test split.
