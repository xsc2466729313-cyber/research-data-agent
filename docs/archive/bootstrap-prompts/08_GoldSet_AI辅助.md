# Codex 任务 08：AI 辅助 Gold Set

实现：
- retrieval gold 初标
- field gold 初标
- error case 自动构造
- 第二模型复核接口
- 规则 validator
- review queue

原则：
- 单一 AI 输出不得直接冻结为 Gold。
- 所有数据源标识必须真实验证。
- 高风险/分歧案例进入人工 review。
