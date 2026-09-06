# Autonomous Workspace 实施与验收报告

验证日期：2026-09-05—2026-09-06，Asia/Shanghai。本文记录本轮实际执行，不替代旧报告，不将历史测试数量计作本轮结果。

## 1. 交付结论

新的自主研究工作区已可在本地使用：一句问题提交后由后端运行，前端展示真实进度；支持独立研究、运行版本、对话、持久历史、真实数据资产、证据血缘可视化和原件回查。旧表单工具不再作为主产品入口，真实 Evidence Graph / Source Lineage 已直接放到当前 Run 的结果区。

本轮不是“完整通用科研 Agent 已全部完成”的声明。新工作区专项、真实浏览器和全后端非 integration 回归均已通过；Docker 实机运行尚未验证，跨领域自动创建关联项目仍未实现。详见第 8 节。

本轮本地预览：[自主工作区](http://127.0.0.1:8891/v31/#/workspace)。原有 8000 进程未被停止；若使用原服务地址，需要重启原后端才能加载新增 API。8891 是本轮单独启动的本地验收服务，不是外网部署。

## 2. 已落地的产品链

| 层面 | 本轮实现 | 明确边界 |
|---|---|---|
| 左栏 | 后端研究历史、新建研究、切换当前研究 | 不再用阶段列表作新工作区主导航 |
| 中栏 | 原问题、理解/假设、计划、真实事件、阶段结果、资产、追问 | 普通阶段无需连续确认，不采用计时器伪造阶段 |
| 右栏 | 研究对象、目标、当前状态、已确认内容、风险、下一步 | 路由/ID/原始状态置于折叠详情 |
| Run | 后端线程池执行、暂停/取消/恢复、失败/预览/真实结果区分 | 暂停是协作式检查点；在途 HTTP 不保证立刻终止，但不能再提交结果 |
| 持久化 | SQLite 保存 Project / Run / Session 引用 / Brief / 对话 / 事件 / Asset 元数据；文件保存资产及原件 | 单用户、单后端进程，不是多租户权限系统 |
| 版本 | 同领域修改产生新 Run 和独立 Session；旧资产不覆盖 | 跨领域明确要求新建研究，不把问题混入当前项目 |
| 结果阅读 | CSV、Metadata、Quality、Evidence、Lineage 专注阅读视图；独立医学来源表另标待复核 | 解释投影图不冒充观测事实，来源表不冒充合并患者主表 |
| 原材料 | PDF 文本层、UTF-8 文本/CSV/TSV/HTML/XML、PNG/JPEG 登记；论文与图像位置关联 | 手动上传内容只是候选证据，不能自动进入观测 CSV |
| 模型 | 配置检测、临时 Key 连接、真实规划调用、失败规则降级 | 规划建议不授权工具；Key 不进入 localStorage、研究历史或导出 |

前端只调用 Workspace 查询和生命周期接口。保存的浏览器网络记录中，没有用前端 POST `/api/v30/*` 串联自主运行阶段。

资产展示保留字段细节；原始记录具有 `source_id`、`raw_field`、`raw_value`、逐字段 `provenance`。Metadata/Lineage 可以下载本次运行归档的原始响应，下载前复核 SHA-256。归档文件路径由后端清单解析，客户端不能指定任意文件路径。

## 3. 实际科研数据验证

### 3.1 Ia 型超新星

| 路径 | 实际结果 | 科学语义 |
|---|---|---|
| CfA4 live | 5,485 条观测、92 个 SN；五类资产全部下载并验证字节数/hash | `table6` 精确 trim(SN) LEFT JOIN 同目录 `table1`；92/92 对象匹配，不增加观测行 |
| KSP live 子 Run | 1,056 条观测、1 个对象 | SN 2021aefx 独立 provenance；不与 CfA4 强行跨源合并 |
| KSP cached_real 子 Run | 1,056 条真实缓存观测，明确显示回放模式 | normalized scientific hash 与 live 相同；不是本次联网 |
| 版本与重启 | 原 CfA4 Run/资产在实际后端重启、换源、缓存回放之后仍可读取且 hash 不变 | 新 Run 使用不同 session_id；旧版本不可被新采集覆盖 |

实际入口：

- [CfA4 官方目录](https://cdsarc.cds.unistra.fr/viz-bin/cat/J/ApJS/200/12)
- [CfA4 table6 TSV](https://vizier.cds.unistra.fr/viz-bin/asu-tsv?-source=J/ApJS/200/12/table6&-out.all&-out.max=100000)
- [CfA4 table1 TSV](https://vizier.cds.unistra.fr/viz-bin/asu-tsv?-source=J/ApJS/200/12/table1&-out.all&-out.max=100000)
- [KSP 官方目录](https://cdsarc.cds.unistra.fr/viz-bin/cat/J/ApJ/959/132)

首轮 CfA4 Workspace 实际运行：21:27:19–21:27:47 +08:00。之后又完成一次真实浏览器重跑，验收记录时间 21:48:40 +08:00。KSP 与缓存/旧资产验证结束于 21:48:28 +08:00。耗时仅是本机当次结果，不是性能承诺。

稳定科学校验值（不包含动态请求 banner、获取时间与原始响应 hash）：

```text
CfA4 80cd21ed716ab9d140c1e05d91c5808b00460591f2709275b969a4c67327e3c3
KSP  e8e23e5c12d623ef3dbae1c4c6df4116adb85392817815a19f130e647b9872c1
```

真实字段、原始响应 URL/时间/Content-Type/hash、抽查单元格回查见 `../../../tmp/source_validation/PHASE_B1_PLUGIN_VALIDATION.md`。机器结果见 `../../../tmp/workspace_acceptance_live/secondary-result.json`。

不可混淆的边界：

- 没有源 flux 就保持空值，不从星等擅自推导。
- MJD 单位为日，源未声明时钟尺度，不标作 UTC/TDB。
- CfA4 日心 z 与 zCMB 分开保留原值，按显式策略选择参考系。
- KSP 目录红移参考系未声明，本次不传播到观测行。
- metadata 未匹配保留观测、z 为空并记录原因；右表重复键会阻断，不做名称相似度关联。
- 质量合格仅允许本地分析/导出；再分发许可未独立核验，公开发布仍为禁止状态。

### 3.2 HER2 真实旧能力复用

问题：“我想研究 HER2 阳性乳腺癌耐药机制，只使用公开数据”。

新 Workspace 后端实际调用原 Agent，110.62 秒结束；保存两张独立来源表，共 517 条来源记录（508 + 9），不能将其相加解读为独立患者数。六个资产的下载 hash 均匹配。来源包括 GEO 和 cBioPortal；本次来源状态同时包含既有缓存和真实检索，不声称所有文件都是当次新下载。

结果级别 `source_data`，页面为“独立来源数据已保存 · 待复核”。旧医学质量门为 REVIEW；未生成新的统一患者 CSV、未执行跨来源患者合并、未授权发布。详情：`../../../tmp/workspace_acceptance_live/her2-live-result.json`。

### 3.3 论文和真实图像

从 [CfA4 原论文](https://arxiv.org/abs/1205.4493) 的公开 PDF 验证原材料链。实际 PDF SHA-256：

```text
807d6b86ce376f2ee1218c273c88b22f25a6236799de8326ad446baa69e2f1fd
```

使用实际文本层生成逐页候选摘录，明确标注只读前 20/43 页。使用 Poppler 将第 35 页 Figure 4 渲染为 PNG，经本次 Qwen3-VL-Plus 临时会话读取真实像素，返回存在光变图、轴标签等辅助信息。该图保留父论文 ID 和页码；没有数字化观测点，也没有修改任何已有观测资产。21:40:03 +08:00 验证通过。

机器证据：`../../../tmp/material_validation/actual-material-result.json`。浏览器另验证默认不勾选图像解读时不调用视觉模型，以及不同研究之间材料隔离。扫描件 OCR、任意 PDF 表格复原与自动图数字化未实现。

## 4. 多模型交叉检查与修复闭环

实际使用三个代码工作模型，不将一次审查改名为“多模型”：

- GPT-5.6-Sol：真实来源插件、join/provenance/cache 正确性；随后独立重算 Workspace 原件和 CSV 的校验值。
- GPT-6-Astra：后端持久执行与生命周期、模型边界、资产安全；真实 HER2 调用检查。
- GPT-5.6-Terra：旧页面异步隔离修复、新前端契约独立审查、原材料安全解析。

主任务负责产品衔接、代码整合和真实 Edge 浏览器复核。生产运行另实际验证 Qwen3.8-Max 规划及 Qwen3-VL-Plus 图像调用；不代表产品会把同一科研问题默认发送给上述三个代码模型。

已复现并修正的主要问题：

1. 真实 `real_data` 被显示为普通完成、实际 Qwen 调用被显示为规则运行。
2. 暂停/取消/待审查误用绿色成功样式；高风险等待缺少明确修改范围入口。
3. 切换研究后旧响应污染全局 store/共享 DOM；同页并发刷新可能回退状态。
4. 改来源/模式后幂等键不更新；KSP 禁用红移字段后 FormData 丢失其值。
5. 全量结果重复进入轮询快照，以及截断 Metadata 时丢掉后部 `field_mapping`。
6. 旧回复展开巨量 JSON、资产阅读重复整个 Run，影响主产品阅读。
7. 后续下载覆盖历史原件；现在采用内容寻址缓存及 Run 独立归档。
8. 缺失 z 原先导致整个批次失败；改为保持 LEFT JOIN 和缺失原因，重复键仍阻断。
9. “换用 KSP 来源，独立研究…”误判为跨领域；原文复现、修正、live 子 Run 验证。
10. 图片 JSON 字符串被布尔强制转换而误报成功；现在要求真实 boolean，异常为 unknown/error。
11. 图像模型调用阻塞异步上传路由；移入线程池，其他研究可继续轮询。
12. 辅助跳转正文链接覆盖 hash 路由；改为聚焦正文，保持研究地址。
13. 长追问静默截断原问题；现在明确拒绝超长上下文，旧记录不变。
14. 结果反馈只能依赖自由输入，比赛演示不易看出修正闭环；现在提供字段映射、换来源和收紧范围快捷入口，并验证反馈会创建子 Run、保留旧 provenance。

数据质量审查技能影响了观测粒度、确定性关联、缺失处理和逐字段证据测试；PDF 验证流程要求核对真实文本与渲染页面，而不是用图注假称像素理解。Context7/Firecrawl 工具不可用时使用现有代码与官方文档，没有伪称调用成功。

## 5. 测试结果

以下集合有重叠，不相加为“总通过数”。

| 验证集合 | 实际结果 | 证据 |
|---|---|---|
| 新 Workspace、自主 Run、来源、材料、旧 V3.1 衔接与 session artifacts | 130 passed，2 skipped | `../../../tmp/workspace_acceptance/workspace-final.xml` |
| 全后端，排除 integration 标记 | 746 passed，2 skipped，8 deselected | `../../../tmp/workspace_acceptance/backend-regression-contest-final2.xml` |
| 新前端 Node 逻辑/隔离 | 12 passed | `frontend/v31/tests/run-view.test.mjs`、`legacy-isolation.test.mjs` |
| 保留根页面的现有 Node 测试 | 13 passed | `frontend/tests/planner-sessions.test.cjs`、`astronomy.test.cjs` |
| 本轮 Workspace/前端契约目标回归 | 129 passed，2 skipped | `../../../tmp/workspace_acceptance/contest-final-targeted.xml` |
| 来源插件外网 opt-in | 2 passed | CfA4、KSP 实际下载；不是把 skipped 计为通过 |
| 真实浏览器自主 Run 主路径 | 预览 8 项、实时 8 项场景检查通过，均 0 JS 错误；含预览转真实数据与反馈创建子 Run | `../../../tmp/workspace_acceptance_contest_final3/browser-result.json`、`../../../tmp/workspace_acceptance_contest_live/browser-result.json` |
| 原材料浏览器 | 6 项场景检查通过、0 JS 错误 | `../../../tmp/material_validation/materials-browser-result.json` |
| 专注资产/归档原件/键盘/医学来源表浏览器 | 3 项场景检查通过、0 JS 错误 | `../../../tmp/workspace_acceptance_final/asset-browser-result.json` |
| 实际重启、KSP 换源、缓存、旧资产不可变 | 7 项检查通过 | `../../../tmp/workspace_acceptance_live/secondary-result.json` |
| Compose 配置、差异空白检查 | 通过 | `docker compose config --quiet`；`git diff --check` |

首轮整仓检查发现根页面静态断言仍绑定旧闭环条件和旧资源版本；测试已改为校验当前实际语义：有迭代才展示、动态轮次以及静态资源具有缓存版本。第二轮又发现旧 Agent 的迭代收集测试会隐式调用默认 GEO 外网/缓存；现已注入固定的 40 行 GEO Series Matrix 夹具。该测试文件 38 项全部通过，随后全后端非 integration 回归通过。

## 6. 代码与启动衔接

主要新增：

- `backend/app/v31/astronomy.py`、`workspace.py`、`workspace_store.py`、`workspace_api.py`、`materials.py`
- `frontend/v31/app/api/research.js`、`run-view.js`、`pages/workspace.js`、`components/research-materials.js`
- `frontend/v31/styles/pages/workspace.css` 及本轮专项/浏览器测试

必要衔接修改：`backend/app/main.py` 挂载；V3.1 router/main/store 及旧工具响应作用域；根页面增加入口；前端 Docker 复制 V3.1；Compose 增加研究持久卷；Nginx 允许 10MB 材料请求。

新增依赖仅 `pypdf==6.14.2`：原 Parser 只接受预先提取的 PDF 文本，不能读取实际 PDF 字节；该依赖用于真实文本层逐页摘录，已用本机同版本测试。未安装的旧环境仍会返回明确降级状态。[包版本](https://pypi.org/project/pypdf/6.14.2/)、[文本提取边界](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)。不新增 React/Vue、数据库服务或前端构建依赖。

常规启动（仓库根目录）：

```powershell
python -m pip install -r backend/requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
# 打开 http://127.0.0.1:8000/v31/#/workspace
```

本轮验收数据位于 `C:/Users/xsc/AppData/Local/scientific-research-agent/workspace-acceptance-20260905`，与默认研究目录隔离；原代码仓库、B0 快照没有被当作运行数据库。常规默认目录为 `%LOCALAPPDATA%/scientific-research-agent/workspace`；可用 `RESEARCH_WORKSPACE_DIR` 指定。Docker 对应具名卷 `research_workspace`。备份时停止写入后备份整个目录，不能只备份 SQLite 而丢失资产原件。

模型 Key 可通过后端环境配置或页面临时连接。图像检查必须显式勾选并连接支持的视觉模型；临时凭据不跨服务重启恢复。没有模型时采用明示的规则模式，没有真实缓存时不伪造缓存。

## 7. 冻结与来源自检

下列文件与实施前 SHA-256 一致：

```text
canonical_schema.yaml 3014ED3CDFE710A9F77E73C1780B31A72ECA6FFAD42A6EAD7AF7760FCC6F4B70
medical_rules.yaml    C607C503AFAA2C694A689F9B91F57308D028E5E30BB19D6FFB88A17FEDB6BCD3
quality_rules.yaml    56EAA807439396E5036CF4C30675C431D4B2B3CEF904B1167D8BBD60363C6316
06_评测指标与SDTI.md  D285926B0D80384F6145B9EBA54FD5D9C6609C8A69F2302440671D5B685D592D
```

未改医学安全判定，未合成科研数据填补结果，未捏造 SDTI 或系统成绩。异常响应只存在于明确的测试 fixture；演示资产来自真实来源。没有执行 Git reset/覆盖其他工作、删除原功能、外网部署或数据发布。

## 8. 尚未完成的发布条件

1. Docker Desktop Linux 引擎本机不可连接，只完成构建配置校验，未跑真实镜像构建/容器 E2E；不能宣称干净比赛环境已验收。
2. 跨领域修改会安全拒绝并提示新建，不会自动创建相互关联的项目；多用户登录/权限/多进程调度未实现，当前仅本地单用户部署。
3. 自主工具仍限已支持领域和来源；不实现任意网站发现/接入、超新星拟合或因果研究结论。
4. PDF 摘录有页数/大小上限，扫描 OCR、图数字化、复杂附件表格复原需要后续验收。
5. 公开再分发仍需许可/引用复核及明确用户授权。

结论：可以演示本轮真实的自主数据工作区闭环；不能据此将整个最终架构所有 P0 门全部勾选完成。比赛演示操作见 `AUTONOMOUS_WORKSPACE_DEMO.md`。
