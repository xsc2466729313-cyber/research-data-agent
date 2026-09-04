param(
    [string]$OutputName = "cancer-precision-data-agent-v2.0.0-reading-pack.zip"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$stage = Join-Path $root ".tmp\paper-package"
$archive = Join-Path $root "deliverables\$OutputName"

if (Test-Path -LiteralPath $stage) {
    Remove-Item -LiteralPath $stage -Recurse -Force
}
New-Item -ItemType Directory -Path $stage | Out-Null

$files = @(
    "docs\论文阅读包说明.md",
    "docs\FINAL_DELIVERY_INDEX.md",
    "docs\PROJECT_REPORT.md",
    "docs\REVIEWER_STORY.md",
    "docs\CURRENT_MAINLINE.md",
    "docs\FRONTEND_COMPLETE.md",
    "docs\05_医学安全规则.md",
    "docs\06_评测指标与SDTI.md",
    "docs\阅读样式.css",
    "evaluation\PUBLIC_DATASET_COMPARISON_20260902.md",
    "evaluation\PUBLIC_DATASET_COMPARISON_20260902.json",
    "evaluation\PUBLIC_RETRIEVAL_MATRIX_20260903.md",
    "evaluation\public_benchmarks\retrieval_matrix_20260903.json",
    "evaluation\source_health_20260901.json",
    "configs\canonical_schema.yaml",
    "configs\medical_rules.yaml",
    "configs\quality_rules.yaml",
    "scripts\build_chinese_paper_figures.py"
)

foreach ($relativePath in $files) {
    $source = Join-Path $root $relativePath
    $destination = Join-Path $stage $relativePath
    New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination
}

Copy-Item -LiteralPath (Join-Path $root "docs\论文阅读包说明.md") -Destination (Join-Path $stage "README.md")
Copy-Item -LiteralPath (Join-Path $root "docs\images") -Destination (Join-Path $stage "docs\images") -Recurse

$evidenceDirectories = @(
    "evaluation\public_benchmarks\runs\20260902T063818Z_ebm_nlp_2_00",
    "evaluation\public_benchmarks\runs\20260902T103645Z_qwen_public_benchmark",
    "evaluation\public_benchmarks\runs\20260902T180539Z_beir_trec_covid",
    "evaluation\public_benchmarks\runs\20260902T181810Z_beir_scifact",
    "evaluation\public_benchmarks\runs\20260902T182532Z_beir_nfcorpus",
    "evaluation\public_benchmarks\runs\20260902T182937Z_beir_scidocs",
    "evaluation\public_benchmarks\runs\20260902T183906Z_beir_arguana",
    "evaluation\public_benchmarks\runs\20260902T203113Z_beir_fiqa",
    "evaluation\public_benchmarks\runs\20260902T210341Z_beir_quora",
    "evaluation\public_benchmarks\runs\20260902T210847Z_beir_quora",
    "evaluation\public_benchmarks\runs\20260902T212521Z_beir_scifact",
    "evaluation\public_benchmarks\runs\20260902T212546Z_beir_nfcorpus",
    "evaluation\public_benchmarks\runs\20260902T212603Z_beir_scidocs",
    "evaluation\public_benchmarks\runs\20260902T212641Z_beir_arguana",
    "evaluation\public_benchmarks\runs\20260902T212752Z_beir_fiqa",
    "evaluation\public_benchmarks\runs\20260902T110023Z_qwen_valentine_education_covid_meals",
    "evaluation\public_benchmarks\runs\20260902T110029Z_qwen_valentine_capital_projects",
    "evaluation\public_benchmarks\runs\20260902T110038Z_qwen_valentine_dcm_street_centerline",
    "evaluation\public_benchmarks\runs\20260902T110050Z_qwen_valentine_dpr_athletic_facilities",
    "evaluation\public_benchmarks\runs\20260902T110200Z_qwen_valentine_energy_benchmarking",
    "evaluation\public_benchmarks\runs\20260902T110208Z_qwen_valentine_swim_for_life",
    "evaluation\public_benchmarks\runs\20260902T110217Z_qwen_valentine_street_resurfacing",
    "evaluation\public_benchmarks\runs\20260902T110229Z_qwen_valentine_housing_maintenance",
    "evaluation\public_benchmarks\runs\20260902T110247Z_qwen_valentine_public_art_inventory",
    "evaluation\public_benchmarks\runs\20260902T110554Z_qwen_valentine_dsny_disposal_assignments",
    "evaluation\public_benchmarks\runs\20260902T130928Z_holoclean_hospital",
    "evaluation\public_benchmarks\runs\20260902T130929Z_raha_beers",
    "evaluation\public_benchmarks\runs\20260902T130929Z_raha_flights",
    "evaluation\public_benchmarks\runs\20260902T130933Z_raha_movies_1",
    "evaluation\public_benchmarks\runs\20260902T130934Z_raha_rayyan",
    "evaluation\public_benchmarks\runs\20260902T131059Z_raha_tax",
    "evaluation\github_competitor_benchmark_20260830",
    "goldset\breast_cancer\official_candidate\evaluation_runs\official-candidate-current-deterministic-baseline-20260902",
    "goldset\breast_cancer\official_candidate\evaluation_runs\official-candidate-qwen-live-user-request-20260902"
)

foreach ($relativePath in $evidenceDirectories) {
    $source = Join-Path $root $relativePath
    $destination = Join-Path $stage $relativePath
    New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Recurse
}

$pandoc = Get-Command pandoc -ErrorAction SilentlyContinue
if ($pandoc) {
    $paper = Join-Path $stage "docs\PROJECT_REPORT.md"
    $html = Join-Path $stage "docs\论文_浏览器版.html"
    & $pandoc.Source $paper --standalone --from gfm --to html5 --mathml --css "阅读样式.css" --metadata "lang=zh-CN" --output $html
}

if (Test-Path -LiteralPath $archive) {
    Remove-Item -LiteralPath $archive -Force
}
New-Item -ItemType Directory -Path (Split-Path $archive) -Force | Out-Null
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $archive -CompressionLevel Optimal

Write-Output $archive
