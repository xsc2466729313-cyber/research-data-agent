# 千问科研数据 Agent v2

## 目标

主产品不再停留在数据源目录、Evidence 记录或两行 Mock 表，而是将科研问题转化为可以交给统计软件和机器学习代码使用的患者/样本级数据集。

内部治理层仍保留 Canonical Schema、来源证据、冲突检测和医学安全规则；这些能力负责“数据不能被整错”。新增科研数据产品层负责“数据能够直接被研究者使用”。

## Agent 主链

```text
用户科研问题
  ↓
千问 JSON Mode：生成 ResearchSpec
  ↓
千问函数调用（Function Calling）：选择真实数据工具与参数
  ↓
受控工具注册表：校验来源、accession、记录上限
  ↓
GDC / GEO / cBioPortal / ClinicalTrials.gov / CIViC
  ↓
患者/样本级队列构建器
  ↓
科研数据宽表 + 中文字段字典 + 可科研性报告 + 来源清单
  ↓
千问基于确定性统计事实生成中文总结
```

## 千问职责

千问负责：

- 从自然语言中抽取疾病、亚型、基因、变异、药物和结局；
- 根据研究问题从允许列表中选择真实数据工具；
- 为工具生成 accession、研究编号、基因列表和查询上限；
- 在工具完成后，根据系统提供的确定性数据统计生成中文总结。

千问不负责：

- 生成患者、样本或疗效事实；
- 修改冻结 Canonical Schema；
- 覆盖 HER2、ERBB2 CNA、response domain 等硬规则；
- 将知识证据或临床试验行伪装成患者级队列；
- 决定没有真实 Gold Set 支持的系统成绩。

## Function Calling 工具

| 工具 | 中文名称 | 主要输出 |
|---|---|---|
| `search_gdc` | 检索 GDC / TCGA | 项目、开放文件、来源登记 |
| `search_geo` | 检索 NCBI GEO | Series Matrix、SOFT、Supplement 资源 |
| `search_cbioportal` | 检索 cBioPortal 患者队列 | 临床、突变、离散 CNA 原始表 |
| `search_trials` | 检索 ClinicalTrials.gov | 试验、干预、结局关系表 |
| `search_civic` | 检索 CIViC 医学证据 | 基因-变异-药物-疾病证据 |

所有工具参数都会重新通过 Pydantic 和 Adapter 自身的格式、域名、记录上限与缓存规则校验。模型不能调用未注册函数。

## 科研数据集

当前可直接构建患者/样本宽表的数据源包括 cBioPortal 与指定 GEO Series Matrix：

1. 将 `clinical_patient` 按 `patientId + clinicalAttributeId` 透视；
2. 将 `clinical_sample` 按 `sampleId + clinicalAttributeId` 透视；
3. 通过 `patientId` 将患者属性补充到对应样本；
4. 将突变记录转换为 `{gene}_mutation` 与 `{gene}_variants`；
5. 将离散 CNA 转换为 `{gene}_cna`；
6. 只选择与科研问题匹配的 pCR、response、OS 或 DFS 结局，不再把 OS 回退为治疗响应；
7. 生成中文字段字典和逐字段实际定义。

临床样本表是 cBioPortal 宽表的队列锚点。无法连接到临床样本的 mutation/CNA 记录进入排除计数，不会扩成大量结局缺失的新患者。`{gene}_mutation = 0` 只表示本次完整返回窗口内没有观察到该事件；上游表截断时不得解释为确定野生型。

对于 HER2 治疗响应问题，受控 accession 解析器会下载并校验 GSE76360 Series Matrix，解析 subject id、HER2 队列状态、baseline/post、术后响应、ER 和 PR；主表保留 50 个基线患者样本，将 50 个治疗后配对样本分离，以避免按行切分时泄漏。原始 `characteristics_ch1` 同时保留用于审计。该队列的术后响应缺失率为从真实文件计算得到的 4%，不是填补结果。

前端科研宽表默认隐藏 `source_id`、`raw_characteristics` 等审计字段，使患者编号、疾病状态、时间点、受体状态和治疗响应成为主要浏览内容。研究者可切换到“含原始信息”视图；其中 `raw_characteristics` 会按原始键值拆分为中文可展开表格，底层原文和下载文件保持不变。

多源检索不会把不同数据库中的患者按编号强行拼接。例：GSE76360 可以支持治疗响应与 ER/PR 分层，但不含 PIK3CA 突变；METABRIC 含 PIK3CA 分子变量但不含匹配的治疗响应。系统会把这种情况报告为“研究变量待补充”，而不是伪造一个完整队列。

数据溯源图支持鼠标悬停高亮、点击或键盘选择数据库节点、来源表联动筛选、仅查看主数据路径，以及暂停/播放路径动画。所有节点计数、数据编号、状态和官方地址均来自当前任务结果；图中的连接只表示检索与主数据集选择关系，不表示跨患者拼接。

## 可科研性检查

系统至少检查：

- 数据行数是否达到基本分析规模；
- 是否存在明确研究结局字段；
- 研究结局是否与科研问题匹配；
- 研究结局缺失率；
- 全表字段完整率；
- 请求基因变量覆盖率；
- 研究结局是否只有单一类别；
- 上游表是否截断；
- 同一患者是否对应多个样本；
- 自动归一化值、重复样本行和孤立分子记录排除数量；
- 不同分析分区是否需要按患者分组；
- 知识证据和患者数据是否保持语义分层。

报告的 `analysis_ready=false` 不是系统失败，而是表示当前真实数据尚不足以支持可靠科研分析。

## 凭据安全

- 后端只从环境变量读取千问 Key；
- Key 不写入缓存、API 响应、任务结果和工具调用日志；
- `scripts/docker_up_qwen.ps1` 可以从百炼凭据 CSV 临时注入环境变量；
- 前端配置接口只返回“是否已配置”、模型名和业务空间状态；
- 若凭据曾出现在聊天、终端截图或版本库中，应在百炼控制台轮换。

## 官方接口依据

千问调用使用阿里云百炼 OpenAI 兼容 `chat/completions` 接口：

- API Key：`DASHSCOPE_API_KEY`
- 业务空间专属地址：`QWEN_BASE_URL`
- 默认模型：`qwen-plus`
- 结构化解析：`response_format={"type":"json_object"}`
- 工具选择：`tools + tool_choice=auto`
- 多工具支持：`parallel_tool_calls=true`

业务空间专属地址优先于旧的公共 DashScope 地址。

## 前端 API 交互入口

页面提供中文开发者 API 交互台，可直接选择并调用以下真实后端接口：

- `POST /api/agent/tasks`：编辑 JSON 并创建科研数据任务；成功响应自动同步到可视化结果区；
- `GET /api/agent/configuration`：检查千问模型与服务器配置状态；
- `GET /api/agent/tasks/{task_id}`：读取当前任务的完整结果；
- `GET /health`：检查服务健康状态。

交互台支持载入当前科研问题、显示 HTTP 状态与耗时、格式化 JSON 响应以及复制 cURL 命令。为避免凭据泄露，前端不接收、不保存也不回显千问 API Key；Key 仍只从后端环境变量读取。
