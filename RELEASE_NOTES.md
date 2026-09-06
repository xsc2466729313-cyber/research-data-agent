# v2.2.0

发布日期：2026-09-05

这是当前整合主线的 v2.2.0 仓库版本，面向后续 v3 通用科研数据智能体升级保留清晰边界。

## 本次整合

- 研究规划工作台改为“发送并开始研究”主入口，支持研究意图识别、规划会话隔离、后台数据集构建与 CSV/Excel 下载。
- 增加 Giiisp 凭据配置状态与安全边界；未配置或官方协议不可用时，文献扫描明确回落 Europe PMC，不调用未知端点。
- 保留 GDC、GEO、cBioPortal、AACT、CIViC、DepMap、Europe PMC 等真实来源与 `source_id`、`raw_field`、`raw_value` 追溯要求。
- 纳入项目架构审计报告、V3 升级架构设计和证据驱动 Agent 架构图，作为后续升级依据。
- 健康接口和发布入口版本升级为 `2.2.0-qwen-agent`。
- 发布阅读包：`deliverables/cancer-precision-data-agent-v2.2.0-reading-pack.zip`。

## 版本边界

- `configs/canonical_schema.yaml`、`configs/medical_rules.yaml` 与 `docs/06_评测指标与SDTI.md` 未修改。
- 历史 v2.0.0 报告、观测值和阅读包保留原版本标识，不将历史结果改写成 v2.2.0 成绩。
- 不提交 `.env`、API Key 或其他运行时凭据。

## 验证

```powershell
python -m pytest backend/tests -q
node --check frontend\app.js
git diff --check
```

当前测试结果以本次仓库提交前实际运行输出为准；未新增或虚构 benchmark 成绩。

---

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
