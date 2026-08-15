# 千问乳腺癌科研数据智能体

当前主产品是一个由阿里云百炼千问驱动的科研数据 Agent。用户输入自然语言科研问题后，系统执行：

```text
千问解析科研问题
→ 函数调用（Function Calling）选择真实数据库工具
→ 调用 GDC / GEO / cBioPortal / ClinicalTrials.gov / CIViC
→ 构建患者/样本级科研宽表
→ 识别研究变量与研究结局
→ 检查记录规模、缺失、截断、结局分布和重复患者
→ 导出 CSV / Parquet / Excel + 中文字段字典 + 来源清单
```

阶段 00 的 Mock 接口仍保留作历史回归测试，但前端和主 API 不再使用 Mock 数据。

## 当前核心能力

- 千问 `qwen-plus` 结构化解析乳腺癌科研问题；
- 千问函数调用自主选择真实数据工具；
- 真实公开数据库 Adapter 与来源登记；
- cBioPortal 患者临床、突变和离散 CNA 的患者/样本级宽表构建；
- 基因突变指示变量、蛋白变异和 CNA 研究变量；
- 自动识别 pCR、治疗响应、生存状态等研究结局；
- 按患者分组提醒，防止同一患者跨不同分析分区；
- 上游截断、结局缺失、单类别和样本量不足检查；
- 中文前端、中文字段字典、中文可科研性报告和指标可视化；
- 中文开发者 API 交互台，可发送真实请求、查看 JSON 响应并复制 cURL；
- CSV、Snappy Parquet 与多工作表 Excel 导出；
- 冻结 Canonical Schema、Evidence、HER2 安全规则、Repair 和 SDTI 评测能力继续保留。

## 配置千问

系统使用阿里云百炼 OpenAI 兼容接口。必需变量：

```env
DASHSCOPE_API_KEY=
QWEN_BASE_URL=https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
QWEN_WORKSPACE_ID=
QWEN_TIMEOUT_SECONDS=120
```

不要把真实 Key 提交到仓库。若使用百炼下载的凭据 CSV，可通过安全启动脚本直接注入进程：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\docker_up_qwen.ps1 `
  -CredentialCsv "C:\path\默认业务空间-apiKey.csv" `
  -Model "qwen-plus"
```

脚本读取 CSV 中的 `apiKey`、`openAiCompatible` 与 `workspaceId`，仅通过当前进程传给 Docker Compose，不创建包含密钥的 `.env` 文件。

未配置千问时，系统可以使用确定性规划兜底，但前端会明确标注“千问未配置”，不会把兜底模式冒充千问 Agent。

详细设计见 [千问科研数据 Agent 文档](docs/QWEN_RESEARCH_AGENT.md)。

## 启动

使用千问凭据 CSV 启动：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\docker_up_qwen.ps1 `
  -CredentialCsv "C:\path\默认业务空间-apiKey.csv"
```

不配置千问、仅运行确定性兜底模式：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\docker_up.ps1
```

启动后访问：

- 中文前端：http://localhost:8888
- 后端健康检查：http://localhost:8000/health
- API 文档：http://localhost:8000/docs
- 千问配置状态：http://localhost:8000/api/agent/configuration

停止服务：

```powershell
docker compose down
```

## 主 API

### 运行科研数据 Agent

`POST /api/agent/tasks`

```json
{
  "question": "研究 HER2 阳性乳腺癌中 PIK3CA 突变与新辅助治疗响应的关系，并整理患者级科研数据集",
  "use_qwen": true,
  "allow_deterministic_fallback": true,
  "data_mode": "live",
  "preferred_sources": [],
  "max_sources": 3,
  "max_records": 500
}
```

响应包含：

- 千问解析后的 `research_spec`；
- 中文执行计划；
- 每次函数调用的参数、状态、记录数和来源数；
- 真实候选数据集与官方地址；
- `modeling_dataset` 患者/样本级宽表；
- 中文字段字典；
- `readiness` 可科研性报告；
- 千问的受约束数据总结。

### 导出科研数据

```text
GET /api/agent/tasks/{task_id}/export/csv
GET /api/agent/tasks/{task_id}/export/parquet
GET /api/agent/tasks/{task_id}/export/xlsx
```

Excel 包含：

1. `科研数据集`
2. `字段字典`
3. `可科研性报告`
4. `数据来源`

## 数据语义边界

- 患者临床数据、细胞系药敏、临床试验和知识证据不会暴力拼成同一患者表；
- ERBB2 CNA 不等同于临床 HER2 IHC 阳性；
- HER2 IHC 2+ 不自动判为 HER2 Positive；
- cBioPortal 结果表如被 `max_records` 截断，缺失突变不能自动解释为确定阴性；
- 同一患者多个样本必须按 `patient_id` 分组，避免跨不同分析分区；
- 千问可以规划和总结，但不能覆盖确定性医学安全规则或把模型输出当作 Ground Truth。

## 本地开发与测试

Python 3.11 或更高版本：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.app.main:app --reload
```

运行全部测试：

```powershell
python -m pytest -ra
```

## 关键目录

```text
backend/app/agent/          千问客户端、Function Calling、Agent 编排、宽表与导出
backend/app/sources/        GDC、GEO、cBioPortal、AACT、CIViC 真实数据工具
backend/app/normalization/  医学实体和冻结 Schema 标准化
backend/app/integration/    患者/样本关联、冲突检测和 Evidence 融合
backend/app/repair/         确定性错误修复与医学安全门
backend/app/evaluation/     Gold Set、指标与 SDTI
frontend/                   中文 Agent 前端
scripts/                    Docker 与千问安全启动脚本
configs/                    冻结 Schema、医学和质量规则
mock/                       历史阶段 00 回归资产，不是主产品数据
```

## 依赖说明

- `fastapi` / `uvicorn`：REST API 与服务；
- `httpx`：千问与真实数据库 HTTPS 调用；
- `pydantic`：输入、工具参数、模型输出和医学规则校验；
- `pyarrow`：真实 Parquet 导出；
- `openpyxl`：生成包含中文字段字典、可科研性报告和来源清单的 Excel；
- `PyYAML`：读取冻结配置；
- `pytest`：业务测试。

## 兼容保留接口

- `/api/adapters/gdc|geo|cbioportal|aact|civic`
- `/api/integration/normalize`
- `/api/evaluation/*`
- `/api/goldset/*`
- `/api/repair/*`
- `/api/tasks/mock`（仅历史回归与演示资产）
