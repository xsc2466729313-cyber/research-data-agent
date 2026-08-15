# 06 评测指标与 SDTI

## 数据检索

### Precision

\[
P_r=\frac{TP}{TP+FP}
\]

### Recall

\[
R_r=\frac{TP}{TP+FN}
\]

### F1

\[
F_{1,r}=\frac{2P_rR_r}{P_r+R_r}
\]

## 数据整合

### Faithfulness

\[
F_a=
\frac{N_{\text{忠实保持原始医学语义的字段}}}
{N_{\text{抽检关键字段}}}
\]

### Traceability

\[
T=
\frac{N_{\text{存在完整有效 Evidence 的关键非空字段}}}
{N_{\text{全部关键非空字段}}}
\]

## 错误检测

\[
P_e=\frac{TP_e}{TP_e+FP_e}
\]

\[
R_e=\frac{TP_e}{TP_e+FN_e}
\]

\[
F_{1,e}=\frac{2P_eR_e}{P_e+R_e}
\]

## Repair Accuracy

\[
A_r=
\frac{N_{\text{修复后正确}}}
{N_{\text{自动执行修复}}}
\]

## 科研数据可信整合指数 SDTI

\[
SDTI=
100\sqrt[5]{
F_{1,r}\times F_a\times T\times F_{1,e}\times A_r
}
\]

采用几何平均体现短板效应。

## 建议验收阈值

| 指标 | 目标 |
|---|---:|
| Retrieval Precision | ≥ 90% |
| Retrieval Recall | ≥ 90% |
| Retrieval F1 | ≥ 90% |
| Faithfulness | ≥ 95% |
| Traceability | 100% |
| Error F1 | ≥ 90% |
| Repair Accuracy | ≥ 90% |
| SDTI | 建议 ≥ 90 |

## 安全红线

- 虚假来源率 > 1%：任务失败
- Faithfulness < 90%：任务失败
- Traceability < 95%：不得自动发布

未运行真实 Gold Set 前，禁止生成虚假的指标成绩。
