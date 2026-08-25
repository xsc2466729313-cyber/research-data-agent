# 乳腺癌 Agent 检索评测

`retrieval_gold.template.jsonl` 是待人工审核的模板，不是正式 Gold Set。正式评测前请确认每条问题的 `expected_sources`，再将 `review_status` 改为 `approved`。

先启动本地服务：

```powershell
.\start_local.bat
```

仅验证检索指标和报告格式：

```powershell
python .\scripts\run_deepseek_evaluation.py `
  --benchmark .\evaluation\retrieval_gold.template.jsonl `
  --allow-provisional `
  --skip-judge `
  --max-cases 3
```

正式使用 DeepSeek Judge：

```powershell
$env:DEEPSEEK_API_KEY = "你的 DeepSeek API Key"
python .\scripts\run_deepseek_evaluation.py `
  --qwen-csv "C:\path\默认业务空间-apiKey.csv" `
  --benchmark .\evaluation\retrieval_gold.template.jsonl `
  --allow-provisional `
  --max-cases 3
```

凭据只在当前进程内使用，不写入评测结果。报告输出到 `evaluation/results_deepseek/`，包括 `comparison.json`、`comparison.csv` 和 `comparison.md`。
