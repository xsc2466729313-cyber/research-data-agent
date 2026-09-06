# Codex 任务 01：GDC Adapter

实现 GDC/TCGA 数据 Adapter。

输入：ResearchSpec/SearchPlan 中 GDC 任务。
输出：统一 SourceItem 与下载文件登记。

要求：
- 首个集成测试使用 TCGA-BRCA。
- 保留 accession、真实 URL、文件类型和获取状态。
- 失败必须有明确错误分类。
- 支持缓存。
- 写单元/集成测试。
- 不修改 Canonical Schema。
