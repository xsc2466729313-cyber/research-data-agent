# 正式 Gold Set 入口

本目录是看板与评测加载器读取的**正式考卷入口**。

- 来源：`goldset/breast_cancer/official_candidate/`（held-out，不是 development 练习册）
- `gold_set_id`：`breast-cancer-official-candidate-20260829`
- 版本：`official-candidate-v1`
- 独立审核人：**xsc**（2026-08-29 审核通过并写入）
- 行数：retrieval 50 / field 26 / error 18
- `frozen=false`，**不是** sealed `frozen_test`
- 已对本卷跑正式评测：`official-candidate-20260829T132222Z`，**SDTI = 63.36**，`publish_allowed=false`（Faithfulness < 90%；5 个高风险问题未解决）

禁止把 `goldset/breast_cancer/development/` 拷进本目录。禁止把 development 观察分（66.94）填入正式栏。
