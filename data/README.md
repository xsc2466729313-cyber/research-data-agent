# data/

本启动包不携带 GB 级真实数据。

原因：
- 保持仓库轻量；
- 避免第三方数据许可/版本混乱；
- 让 Adapter 负责可复现获取；
- 比赛现场可以预缓存重点数据。

建议：
- `data/cache/`：公开数据缓存
- `data/raw/`：原始数据
- `data/normalized/`：标准化数据
- `data/gold/`：冻结 Gold Set
- `data/output/`：最终结果
- `data/output/evaluation/<evaluation_id>/`：阶段 07 的 `metrics.json` 与 `report.md`

数据清单见 `dataset_manifest.csv`。
