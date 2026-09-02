# 最新评委阅读包

本包只保留最终正文、核心图示和当前最佳结果。

## 阅读入口

1. `docs/乳腺癌精准治疗科研数据智能体_专业叙事与规范图示终稿_20260831.md`
2. `阅读说明.md`
3. `docs/05_医学安全规则.md`

## 怎么启动前后端

FastAPI 同时托管前端。本地：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

打开 <http://127.0.0.1:8000/>。Docker 见根目录 `README.md`。

千问凭据只在用户端会话或本机环境变量中配置，**不要写入仓库、README 或提交 `.env`。**

## 核心结果

| 指标 | 结果 |
|---|---:|
| 当前最佳综合结果 | **SDTI 100.00** |
| 真实 Qwen 字段匹配 | **Macro F1 0.9018** |

## 启动

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
