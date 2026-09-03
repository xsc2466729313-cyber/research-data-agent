# Guided Research Planning Workspace

## 定位

新版默认首页服务于“只有一个宽泛研究方向”的用户。界面采用左侧阶段导航、中间一条龙研究向导、右侧研究依据与方案详情的三栏工作台。原有完整科研数据生产页面仅保留为技术详情页，并从默认滚动区域隐藏。

参考页面只用于信息架构与交互密度启发；本项目没有复制其品牌、内容或未公开接口。

## 真实业务链路

1. `POST /api/research/topics`：结构化宽泛 Topic。
2. `POST /api/research/topics/{topic_id}/literature-scan`：检索真实论文并保留 `source_id`、provider 与来源链接。
3. `GET /api/research/topics/{topic_id}/question-candidates`：生成带暂定可行性和论文证据的候选科研问题。
4. `POST /api/research/questions/{candidate_id}/select`：生成 Research Blueprint，包括 Required、Recommended、Optional 字段与指标要求。
5. `POST /api/research/contracts/{contract_id}/source-plan`：输出 DatasetCandidate、字段覆盖、fallback 与 Join Policy。

界面不会把未验证的 seed capability 表述为已采集数据；失败时明确显示错误，不生成替代论文、数据集或成绩。

## 使用方式

- 访问 `http://127.0.0.1:8888/`。
- 首次点击“开始完整规划”时，若尚未连接千问 API，先在提示框中选择“去配置 API”。默认模型为 `Qwen3.8-Max`（`qwen3.8-max`）；网页填写的凭据仅保存在当前后端进程的临时内存中，最长两小时，不写入项目文件。
- 点击任一示例问题，或输入稍宽泛的研究方向后按 `Ctrl + Enter`。
- 系统自动采用论文依据最充分的问题，并继续完成研究方案和数据可用性检查；其他研究角度默认折叠，仅在用户想调整时展示。
- 规划完成后点击“开始生成数据集”，系统继续执行采集、标准化、对齐和质量检查，不需要跳转到旧页面。
- 右上角“查看技术详情”仅供需要检查完整过程、质量门和溯源信息的用户使用，并提供明确的“返回研究向导”入口。

## 验证

- JavaScript 语法：`node --check frontend/app.js`
- 静态连线测试：`pytest backend/tests/test_api.py -q`
- 浏览器验收：Topic → 自动查找论文 → 自动确定研究问题 → 自动形成方案 → 自动检查数据 → 用户确认生成科研数据集；并验证技术详情页可往返。
