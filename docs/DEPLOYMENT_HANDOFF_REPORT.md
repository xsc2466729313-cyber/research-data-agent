# 当前版本部署交付与旧页面诊断报告

## 结论

同学部署后仍看到旧页面的首要原因不是前端代码没有更新，而是部署入口仍使用远端默认分支 `main`。

诊断时仓库状态为：

| 项目 | 值 |
|---|---|
| 原仓库默认分支 | `main` |
| 原仓库默认分支提交 | `d1e8d3e` |
| 当前新版所在分支 | `agent/qwen-api-interaction` |
| 诊断时新版提交 | `2ab7e6e` |
| 默认分支落后新版 | 30 个提交 |

原 README 的克隆命令没有指定分支，因此 `git clone` 后自动检出 `main`，得到旧页面是可重复出现的必然结果。

## 新仓库交付原则

新仓库以当前完整版本重新初始化：

- 默认分支直接使用 `main`；
- 不携带原仓库容易混淆的旧分支历史；
- 包含当前科研规划工作台、系统评测、项目报告、评测产物和部署脚本；
- 不包含 `.env`、API Key、本地缓存、运行日志、虚拟环境和临时输出；
- 冻结 Schema、医学安全规则和 SDTI 公式保持不变。

## 推荐部署步骤

首次部署或切换仓库时执行：

```powershell
git clone <新仓库地址>
cd cancer-precision-data-agent
Copy-Item .env.example .env
docker compose down --remove-orphans
docker compose build --pull --no-cache
docker compose up -d --force-recreate
docker compose ps
```

访问：

- 科研规划工作台：<http://localhost:8888/>
- 后端健康检查：<http://localhost:8000/health>
- API 文档：<http://localhost:8000/docs>

## 部署后核验

不要只检查 HTTP 200。至少验证：

```powershell
git branch --show-current
git log -1 --oneline
docker compose ps
curl.exe http://localhost:8000/health
curl.exe http://localhost:8888/ | Select-String "科研规划工作台"
```

正确结果应满足：

1. 当前分支是 `main`；
2. 首页源码包含“科研规划工作台”；
3. 系统评测只展示真实任务观测值；无 Gold Set 时正式指标保持未评测；
4. 前后端容器均为 `healthy` 或 `running`；
5. 浏览器强制刷新后页面与仓库截图一致。

## 若仍显示旧页面

按以下顺序排查：

1. 确认部署平台绑定的是新仓库和 `main` 分支；
2. 确认构建目录为仓库根目录，Dockerfile 为 `frontend/Dockerfile`；
3. 删除平台旧构建缓存并重新构建，不要只重启旧容器；
4. 执行 `docker compose images` 检查镜像创建时间；
5. 使用浏览器无痕窗口或硬刷新，排除浏览器缓存；
6. 检查端口 `8888` 是否仍由另一套旧容器占用；
7. 确认反向代理/CDN 的源站指向新容器，并清理 CDN 缓存。

当前 Nginx 已对首页、JavaScript 和 CSS 设置 `Cache-Control: no-store, no-cache, must-revalidate`，因此在正确重建镜像后，浏览器缓存通常不是首要原因。

## 报告与证据入口

- `docs/徐士诚_方向1A_P5-P7-P12-P16-P18_报告稿.md`
- `docs/MODEL_EVALUATION_AND_SELECTION_REPORT.md`
- `docs/CURRENT_LIMITATIONS_AND_UPGRADE_BRIEF.md`
- `docs/PUBLIC_BENCHMARK_COMPARISON.md`
- `docs/FRONTEND_PLANNING_WORKSPACE.md`
- `evaluation/`

评测结果只代表已实际运行的对应能力层，不得合并或表述为未经正式 Gold Set 验证的系统总成绩。
