# 发布交付索引（v2.0.0，2026-09-04）

本页是仓库的统一入口，只保留最终正文、最新评委阅读包和当前最佳结果。

## 推荐入口

在线演示：[打开科研规划工作台](https://cancer-precision-data-agent.onrender.com/)

该地址为当前 Render 公网部署入口；免费实例休眠后首次访问可能需要等待几十秒。

Agent 架构评分说明：[Agent 系统架构说明](AGENT_ARCHITECTURE.md)

| 内容 | 文件 |
|---|---|
| 项目正文报告 | [PROJECT_REPORT.md](PROJECT_REPORT.md) |
| 评委讲解稿 | [REVIEWER_STORY.md](REVIEWER_STORY.md) |
| 发布阅读包 ZIP | [下载 v2.0.0](../deliverables/cancer-precision-data-agent-v2.0.0-reading-pack.zip) |
| 项目使用说明 | [README.md](../README.md) |

## 核心对照结果

| 能力 | 本项目 | 对照方法 | 差值 |
|---|---:|---:|---:|
| 问题解析 | **0.5522** | 项目词典 0.4662 | **+0.0860** |
| 科学检索 | **0.3915**（五任务名次融合） | BGE 单路 0.3880 | **+0.0035** |
| 字段匹配 | **0.9018** | 项目原方法 0.7994 | **+0.1024** |
| 实体匹配 | **0.7449** | RecordLinkage 0.7440 | **+0.0009** |
| 数据清洗 | **0.9169**（六项） | Raha 0.8159（共同五项） | **+0.0870** |
| 乳腺癌专项完整链路（候选卷观察） | **SDTI 98.1118** | 确定性消融 100.00 | 均 `publish_allowed=false`，不是封存正式成绩 |

说明：公开结果分别对应不同能力和数据集，不相加为一个总准确率。`98.1118` 是严格千问在线候选卷观察值，`100.00` 是确定性消融值；两者都不是封存 `frozen_test` 正式成绩，也不代表自动发布许可。

## 启动

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
