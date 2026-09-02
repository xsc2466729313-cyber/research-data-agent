# 最终交付索引（2026-09-02）

本页是仓库的统一入口，只保留最终正文、最新评委阅读包和当前最佳结果。

## 推荐入口

| 内容 | 文件 |
|---|---|
| 最终正文报告 | [专业叙事与规范图示终稿](乳腺癌精准治疗科研数据智能体_专业叙事与规范图示终稿_20260831.md) |
| 最新评委阅读包 | [README_START_HERE.md](../deliverables/乳腺癌精准治疗科研数据智能体_最新评委阅读包_20260902/README_START_HERE.md) |
| 项目使用说明 | [README.md](../README.md) |

## 核心结果

| 指标 | 结果 |
|---|---:|
| 当前最佳综合结果 | **SDTI 100.00** |
| 真实 Qwen 字段匹配 | **Macro F1 0.9018** |

## 启动

```powershell
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
