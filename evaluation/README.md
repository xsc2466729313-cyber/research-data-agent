# 乳腺癌 Agent 评测入口

`retrieval_gold.template.jsonl` 是待人工审核模板，不是正式 Gold Set。正式指标只能使用已审核并冻结的题目；临时使用 `--allow-provisional` 得到的结果必须标记为开发诊断。

## 千问生产链评测

先启动本地服务：

```powershell
.\start_local.bat
```

仅验证检索指标和报告格式，不调用模型评审：

```powershell
python .\scripts\run_qwen_review_evaluation.py `
  --benchmark .\evaluation\retrieval_gold.template.jsonl `
  --allow-provisional `
  --skip-judge `
  --max-cases 3
```

使用千问统一评审生产链输出：

```powershell
$env:DASHSCOPE_API_KEY = "你的千问 API Key"
python .\scripts\run_qwen_review_evaluation.py `
  --qwen-csv "C:\path\默认业务空间-apiKey.csv" `
  --benchmark .\evaluation\retrieval_gold.template.jsonl `
  --allow-provisional `
  --max-cases 3
```

默认输出到 `evaluation/results_qwen_review/`。千问评审分只用于辅助诊断，不替代人工 Gold Set、正式 Faithfulness 或 SDTI。

## 中间智能体替换消融

生产系统、两轮闭环、数据层总结和评审器始终使用千问。DeepSeek 只在独立进程中替换中间问题解析、规划和工具选择智能体，不通过生产任务接口运行。

将新申请并已轮换的 DeepSeek 凭据放入被 Git 忽略的 `evaluation/deepseek.local.env`：

```text
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

运行同题集、同预算、同轮数对照：

```powershell
python .\scripts\run_planner_replacement_ablation.py `
  --benchmark .\evaluation\retrieval_gold.template.jsonl `
  --allow-provisional `
  --repeats 3 `
  --max-cases 3
```

默认输出到 `evaluation/planner_replacement_ablation_local/`。输出明确区分 Qwen 对照组、DeepSeek 替换实验组和 Qwen 评审器，并且不写入 API Key。

## 历史产物

`evaluation/results_deepseek/` 是旧版 DeepSeek Judge 小样本产物，只保留历史审计，不能作为当前 Qwen/DeepSeek 中间智能体对比证据。`scripts/build_ai_provisional_core_metrics.py` 已停用，因为模型评审分不能换算为正式核心指标或 SDTI。
