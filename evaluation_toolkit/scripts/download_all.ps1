# Windows PowerShell
# 评测资源下载入口。建议在空目录执行。
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path external, datasets, datasets\retrieval, datasets\entity | Out-Null

Write-Host "[1/8] Clone cleaning baselines..."
if (!(Test-Path external\raha)) { git clone --depth 1 https://github.com/BigDaMa/raha.git external/raha }
if (!(Test-Path external\holoclean)) { git clone --depth 1 https://github.com/HoloClean/holoclean.git external/holoclean }
if (!(Test-Path external\cocoon)) { git clone --depth 1 https://github.com/Cocoon-Data-Transformation/cocoon.git external/cocoon }
if (!(Test-Path external\rein-benchmark)) { git clone --depth 1 --recurse-submodules https://github.com/mohamedyd/rein-benchmark.git external/rein-benchmark }

Write-Host "[2/8] Clone retrieval baselines..."
if (!(Test-Path external\beir)) { git clone --depth 1 https://github.com/beir-cellar/beir.git external/beir }
if (!(Test-Path external\contriever)) { git clone --depth 1 https://github.com/facebookresearch/contriever.git external/contriever }
if (!(Test-Path external\FlagEmbedding)) { git clone --depth 1 https://github.com/FlagOpen/FlagEmbedding.git external/FlagEmbedding }

Write-Host "[3/8] Download BEIR SciFact..."
Invoke-WebRequest "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/scifact.zip" -OutFile "datasets\retrieval\scifact.zip"
Expand-Archive -Force "datasets\retrieval\scifact.zip" "datasets\retrieval"

Write-Host "[4/8] Download BEIR NFCorpus..."
Invoke-WebRequest "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/nfcorpus.zip" -OutFile "datasets\retrieval\nfcorpus.zip"
Expand-Archive -Force "datasets\retrieval\nfcorpus.zip" "datasets\retrieval"

Write-Host "[5/8] Clone schema matching framework..."
if (!(Test-Path external\valentine)) { git clone --depth 1 https://github.com/delftdata/valentine.git external/valentine }
if (!(Test-Path external\valentine-data-fabricator)) { git clone --depth 1 https://github.com/delftdata/valentine-data-fabricator.git external/valentine-data-fabricator }

Write-Host "[6/8] Clone entity matching baselines..."
if (!(Test-Path external\deepmatcher)) { git clone --depth 1 https://github.com/anhaidgroup/deepmatcher.git external/deepmatcher }
if (!(Test-Path external\ditto)) { git clone --depth 1 https://github.com/megagonlabs/ditto.git external/ditto }

Write-Host "[7/8] Download DBLP-ACM..."
Invoke-WebRequest "https://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data/Structured/DBLP-ACM/dblp_acm_exp_data.zip" -OutFile "datasets\entity\dblp_acm.zip"
Expand-Archive -Force "datasets\entity\dblp_acm.zip" "datasets\entity\DBLP-ACM"

Write-Host "[8/8] Download Walmart-Amazon..."
Invoke-WebRequest "https://pages.cs.wisc.edu/~anhai/data1/deepmatcher_data/Structured/Walmart-Amazon/walmart_amazon_exp_data.zip" -OutFile "datasets\entity\walmart_amazon.zip"
Expand-Archive -Force "datasets\entity\walmart_amazon.zip" "datasets\entity\Walmart-Amazon"

Write-Host ""
Write-Host "下载完成。"
Write-Host "Valentine 原论文完整 datasets archive 较大且来自 SURFdrive，请按 docs/02_Benchmark与Baseline链接.md 手动下载。"
Write-Host "ScienceAgentBench 完整 benchmark 有官方访问/再分发要求，本脚本不自动下载。"
