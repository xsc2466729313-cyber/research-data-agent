# 08 Demo 与验收

## 主 Demo

问题：

> 研究 HER2 阳性乳腺癌中 PIK3CA 突变与治疗响应的关系。

## 展示顺序

1. 输入问题
2. 展示识别出的 disease/gene/outcome
3. 展示候选数据集
4. 展示统一后的表格
5. 点击字段查看 Evidence
6. 展示质量指标
7. 演示错误修复

## 必演错误

### 高风险案例
`HER2 IHC 2+ → Positive`

正确行为：
- 拦截
- 保留 assay
- 标为 Equivocal/Unresolved
- 请求补充证据或人工复核

### 确定性案例
`Herceptin → Trastuzumab`

正确行为：
- 自动标准化
- 保留 raw value
- 记录修复日志

## 验收

- Docker 一键启动
- FastAPI health 200
- 前端可打开
- Mock 端到端链路通过
- 所有 Adapter 有独立测试
- Evidence 完整性测试通过
- 指标代码有单元测试
