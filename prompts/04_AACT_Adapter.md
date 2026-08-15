# Codex 任务 04：AACT / ClinicalTrials Adapter

目标：将乳腺癌临床试验多表结构映射成统一 trial 数据。

至少处理：
- studies
- conditions
- interventions
- eligibilities
- outcomes / outcome_measurements（若存在）

统一主键：
- nct_id / trial_id

不得把缺失结果理解成阴性结果。
