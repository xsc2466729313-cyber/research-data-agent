# Frontend Phase 0 报告

- 完成日期：2026-09-05
- 依据：`docs/v31_baseline/FRONTEND_IMPLEMENTATION_PLAN.md`
- 范围：V3.1 前端基础壳
- 未做：Home 业务页、Copilot、Timeline 业务、Sources、Mapping、Graph、Preview、Dataset、任何 `/api/v30` 调用

本阶段只证明：新入口 `/v31/` 能和旧工作台共存。

---

## 1. 新增文件列表

```text
frontend/v31/index.html
frontend/v31/app/main.js
frontend/v31/app/router.js
frontend/v31/app/session-store.js
frontend/v31/app/api/health.js
frontend/v31/app/api/v30.js
frontend/v31/styles/tokens.css
frontend/v31/styles/base.css
frontend/v31/styles/shell.css
frontend/v31/styles/components/badges.css
frontend/v31/styles/components/gates.css
frontend/v31/copy/honesty.zh.js
frontend/v31/copy/medical-constraints.zh.js
backend/tests/v31_frontend/__init__.py
backend/tests/v31_frontend/test_phase0_shell.py
docs/v31_baseline/FRONTEND_PHASE0_REPORT.md
```

`v30.js` 只导出未接线函数名，调用会抛错，不发请求。  
文案目录按本阶段指令放在 `frontend/v31/copy/`（不是 `app/copy/`）。

---

## 2. 修改文件列表

本刀**没有修改**任何已有文件。

未改：

- `frontend/index.html`
- `frontend/app.js`
- `frontend/styles.css`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `backend/app/main.py`
- 任何 `/api/v30` 后端模块
- 冻结配置与旧 Adapter / Quality Gate

`main.py` 已有 `StaticFiles(directory=frontend, html=True)`，`/v31/` 无需改后端即可映射到 `frontend/v31/index.html`。

---

## 3. 旧 frontend 未修改

| 检查 | 结果 |
|---|---|
| 本刀未写入 `frontend/index.html` / `app.js` / `styles.css` | 是 |
| `GET /` 仍是旧规划工作台 | 是，含「发送并开始研究」 |
| `frontend/app.js` 不含 `/api/v30` | 是 |
| 旧页未引用 `/v31/` 作为主入口 | 是 |
| 未删除旧工作台 | 是 |

说明：工作区里这三份旧文件可能仍有**更早阶段留下的未提交改动**，但不是本 Phase 0 引入的。本阶段只新增 `frontend/v31/` 与新测试。

---

## 4. 测试结果

| 套件 | 结果 |
|---|---|
| `backend/tests/v31_frontend/test_phase0_shell.py` | **8 passed** |
| `backend/tests/v30` | **75 passed** |
| Phase 0 固定回归 234 | **234 passed** |

Phase 0 壳测试覆盖：

1. `GET /` 仍返回旧前端
2. `GET /v31/` 与 `GET /v31/index.html` 返回新工作台
3. 旧 `app.js` 无 `/api/v30`
4. `frontend/v31/` 不引用 `/app.js`
5. `tokens.css` 含 `--paper` / `--ink` / `--review` / `--pass`
6. v31 JS 无 `localStorage`、无 `/api/v30` / `/api/agent` / `/api/v3` 的 `fetch`

浏览器核对（本地 `uvicorn`）：

- `http://127.0.0.1:8000/v31/`：标题「科研数据工作台」，顶栏健康点为「系统已连接」，左轨 8 门均为 idle，中列「本阶段尚未开放」
- `http://127.0.0.1:8000/v31/#/r/test/copilot`：中列显示会话 `test` 与 copilot，仍为「本阶段尚未开放」，无假数据
- `http://127.0.0.1:8000/`：仍是「千问肿瘤科研数据智能体」，主按钮仍是「发送并开始研究」

---

## 5. `/v31/` 访问方式

本地：

```powershell
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

打开：

- 新工作台：<http://127.0.0.1:8000/v31/>
- Hash 示例：<http://127.0.0.1:8000/v31/#/home>、<http://127.0.0.1:8000/v31/#/r/test/copilot>
- 旧内核实验室：<http://127.0.0.1:8000/> 或新壳顶栏「内核实验室」→ `/#task-entry`

技术栈：原生 ES Module，无 React / Vue / Vite / webpack / npm。

Docker 前端镜像（`frontend/Dockerfile`）本阶段**尚未**追加复制 `v31/`。后端镜像整目录拷贝 `frontend/`，用 uvicorn 托管时可以使用 `/v31/`。拆开的 Nginx 前端镜像若要带上新入口，需另开任务只追加 `COPY` 与 `location /v31/`，不得改 `GET /`。

---

## 6. 是否满足进入 Frontend Phase 1

**可以进入 Phase 1。**

已具备：独立入口、壳布局、hash 路由、空 Session Store、`GET /health`、诚实文案、医学限制文案、新旧隔离测试。

Phase 1 才应实现 Home + Copilot，并首次调用：

- `POST /api/v30/sessions`
- `POST /api/v30/route`
- `POST /api/v30/copilot/turn`
- `GET /api/v30/sessions/{id}/memory`

本阶段到此停止，未开发 Copilot。
