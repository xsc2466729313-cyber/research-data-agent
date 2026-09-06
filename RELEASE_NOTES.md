# v2.2.1

发布日期：2026-09-06

这是 v2.2.0 运行主线的视觉与交付资料修订版。后端 API、冻结 Schema、医学规则和质量规则未改动；健康接口运行时仍报告 `2.2.0-qwen-agent`。

## 本次交付

- 重新采集科研助手首页、移动端首页、科研助手（科研兔）面板和内核实验室桌面/移动端前端。
- 将原先相互覆盖的标注改为画布外的红色框、红色箭头和中文文字说明；干净原图与讲解版同时保留。
- 单独标注科研助手（科研兔）、内核实验室、Agent 架构流程图和任务入口。
- 新增 `docs/FRONTEND_SCREENSHOT_INDEX.md`，集中列出 UI、空闲内核、真实运行、历史结果和 Agent 流程图，并明确截图证据边界。
- 纳入同一后端任务 `loop-91ef39cffd32:r3` 的真实运行截图：156 行 × 19 列、69 名患者、156 个样本、24 个来源、Agent Runtime 7/7、四层质量门 PASS。该运行是可复核快照，不是新的统一 benchmark 成绩。
- 按参考样式新增两张当前版本红框讲解图：质量门与结构化数据合并视口，以及原始样本特征弹窗（标准化值、原始值、可回查说明）；弹窗保持完整记录可滚动复核。
- 发布新的阅读包：`deliverables/research-data-agent-v2.2.1-reading-pack.zip`，同时保留 v2.2.0 包供历史复核。

可用 `Get-FileHash -Algorithm SHA256 deliverables\research-data-agent-v2.2.1-reading-pack.zip` 校验阅读包完整性。

## 版本边界

- `configs/canonical_schema.yaml`、`configs/medical_rules.yaml`、`configs/quality_rules.yaml` 与 `docs/06_评测指标与SDTI.md` 未修改。
- 不提交 `.env`、API Key 或其他运行时凭据。
- 截图中的 PASS/REVIEW 只描述对应任务返回的状态，不替代封存评测，也不构成临床诊断或治疗建议。

## 验证

```powershell
node --check scripts\capture_frontend_screenshots.js
python -m py_compile scripts\annotate_frontend_screenshots.py
python -m py_compile scripts\annotate_reference_style_screenshots.py
node --check frontend\app.js
python -m pytest backend/tests -q
git diff --check
```

---

# v2.2.0

发布日期：2026-09-06

这是当前整合主线的 v2.2.0 仓库版本，面向后续 v3 通用科研数据智能体升级保留清晰边界。

## 本次整合

- 研究规划工作台改为“发送并开始研究”主入口，支持研究意图识别、规划会话隔离、后台数据集构建与 CSV/Excel 下载。
- 增加 Giiisp 凭据配置状态与安全边界；未配置或官方协议不可用时，文献扫描明确回落 Europe PMC，不调用未知端点。
- 保留 GDC、GEO、cBioPortal、AACT、CIViC、DepMap、Europe PMC 等真实来源与 `source_id`、`raw_field`、`raw_value` 追溯要求。
- 纳入项目架构审计报告、V3 升级架构设计和证据驱动 Agent 架构图，作为后续升级依据。
- 健康接口和发布入口版本升级为 `2.2.0-qwen-agent`。
- 发布阅读包：`deliverables/research-data-agent-v2.2.0-reading-pack.zip`。

## 版本边界

- `configs/canonical_schema.yaml`、`configs/medical_rules.yaml` 与 `docs/06_评测指标与SDTI.md` 未修改。
- 历史 v2.0.0 报告与观测值保留原版本标识，不将历史结果改写成 v2.2.0 成绩；旧压缩包已删除，避免与当前阅读包重复。
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
