# v2.0.0

发布日期：2026-09-04

这是当前可分享的整理版，统一了项目入口、评测口径和发布文件名，并保留可复核的公开运行证据。

## 分享入口

- Web 演示：https://cancer-precision-data-agent.onrender.com/
- GitHub：https://github.com/xsc2466729313-cyber/cancer-precision-data-agent
- 发布阅读包：`deliverables/cancer-precision-data-agent-v2.0.0-reading-pack.zip`

## 统一口径

- 严格千问在线候选卷观察值：SDTI `98.1118`。
- 同卷确定性消融：SDTI `100.00`。
- 两者均为 `publish_allowed=false`，不是封存 `frozen_test` 正式成绩，也不代表自动发布许可。
- 问题解析、检索、字段匹配、实体匹配和清洗结果分别报告，不合并成总准确率。

## 验证

```powershell
python -m pytest -q
node --check frontend\app.js
```
