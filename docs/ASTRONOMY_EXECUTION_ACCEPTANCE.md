# 首页 Ia 型超新星观测链路验收

## 修复范围

首页原先用医学词汇判断科研意图，非医学问题在检索前被拒绝。现在题目原句
“我希望研究 Ia 型超新星光变曲线”和“Ia 型曲线”简写进入独立天文适配器。
后端直接访问公开目录，前端首次运行仍需先连接千问 API；这一路径的数据获取本身是确定性的，并非大模型自主全网发现。
其他领域未接入时明确报告能力边界，不能以患者数据替代。

- 初次运行：CfA4 观测 table6 与对象元数据 table1。
- “扩展到两个目录”：重新获取 CfA4，加上 KSP 观测表及 ReadMe，生成新任务；旧任务不覆盖。
- 各对话保存自己的任务编号和版本，详情、CSV、Excel、原始来源 ZIP、质量报告按编号读取。
- 浏览器刷新后可从历史恢复；完成结果保存在后端，重启后仍可下载。
- 输入发送后清空；后台状态更新不覆盖下一条草稿。

## 数据边界

独立观测 schema，不修改冻结患者 CanonicalRecord、医学规则或 SDTI。
VOTable 校验表名、TABLEDATA、字段和单位；错误或截断响应不能充当成功结果。
CfA4 仅按本目录唯一 SN 精确关联，多对一；不匹配保留 unresolved。
KSP 对象身份从本次获取的 ReadMe.Objects 解析，不能猜测跨目录身份。
跨目录仅按字段纵向拼接，不自动校准不同滤镜或测光系统，不做跨目录实体 Join。
MJD 保留天单位、时间尺度 unspecified；z/zCMB 分开，未注明参考系的红移不填入二者。
没有 flux 时不从星等擅自推导；不拟合曲线、不自动推断物理结论。
每行保留 raw_field/raw_value；来源包包含完整字段定义、原始响应、请求 URL、时间和 SHA256。
数值/必要字段异常行放入质量报告，获取失败来源如实列出；0 行不能下载空的成功数据表。

## 真实联网证据（2026-09-05）

运行 `python -m scripts.validate_astronomy_live`，任务
`astro-e8ea92b79b64476fa7f7de4c34a7ed14`：

| 输入来源 | 真实获取行数 | 用途 |
|---|---:|---|
| J/ApJS/200/12/table1 | 94 | CfA4 对象元数据 |
| J/ApJS/200/12/table6 | 5,485 | CfA4 观测 |
| J/ApJ/959/132/table1 | 1,056 | KSP 观测 |
| J/ApJ/959/132/ReadMe | 文档 | KSP 单对象身份 |

合并观测 6,541 行。CSV 实际解析行数与结果相等；Excel 和原始 ZIP 的完整性检查通过。
CfA4 此次 5,485 条观测均匹配目录内对象元数据。以上是本次获取的结果，非硬编码目标或系统成绩。
首页点击官方示例真实生成任务 `astro-639480dbb157419eb9a4443092ae82d0`，显示 5,485 行并出现下载按钮。
随后在该对话点击扩展，生成 `astro-75f41e5ab6674164b06682bca76cf9bb`，显示 6,541 行、0 条待复核、无获取错误。
浏览器同时触发第一版 CSV 与第二版 Excel，实际得到两个不同任务命名的文件；技术详情显示第二版任务编号及两个目录的完整工作流程。
实际打开下载文件核验：CSV 5,485 行，Excel 6,541 行且包含两个独立观测 source_id。
切换回医学历史对话时，其技术详情恢复本身的 `loop-b24fd406cc49:r1`（566 行），未混入天文数据。

## 自动验证

```powershell
node --test frontend/tests/planner-sessions.test.cjs frontend/tests/astronomy.test.cjs
.venv/Scripts/python.exe -m pytest backend/tests/test_astronomy.py backend/tests/test_session_artifacts.py backend/tests/test_api.py backend/tests/test_research_agent.py backend/tests/test_closed_loop.py -q -p no:cacheprovider
```

覆盖真实格式解析、字段/单位漂移、错误/截断响应、重复主键、异常数值、来源失败、无数据导出拒绝、
重启恢复、两任务独立导出、输入清空、领域路由与切换对话时后台响应隔离；测试数据仅为明确的合成夹具。

## 详情页展示修订

2026-09-05 详情页展示修订：复用工作台 `.results`、`.results-toc`、`.result-overview`、`.panel`、`.section-heading`、`.table-wrap` 和按钮样式；增加中文流程卡与来源卡，原始证据默认折叠。详情页下载质量报告经浏览器验证，文件对应任务 `astro-75f41e5ab6674164b06682bca76cf9bb`、6,541 行；没有重跑或修改数据。新增展示与异步切换测试，前端 13 项、相关后端 22 项通过。

用户截图中的 `astro-5b1b22f5ea95448a83188052e3a3817e` 已在新版详情页视觉验收，保留原有 5,485 行。切回医学对话后，仅显示其自己的 `loop-91ef39cffd32:r3` 结果，天文矩阵隐藏。

## 未覆盖的赛道能力

尚未实现任意领域的开放式来源发现、任意 PDF/附件解析及论文图像数字化/校验。
天文当前只接入上述两个目录家族；增加其他数据集需要新的、经过真实验证的 source binding。
现有 `/v31/` 预览框架未改写，本次接通的是用户截图中的首页入口。
这次修复不等于整个赛道的通用数据整合能力已经完成。
