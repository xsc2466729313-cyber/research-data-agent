# 多癌种扩展边界

当前系统采用“通用肿瘤数据底座 + 癌种专项规则”。乳腺癌仍是已建立专项 Gold Set、pCR/HER2 闭环和固定队列提示的主癌种；不将乳腺癌评测成绩外推到其他癌种。

## 已配置癌种

| 癌种 | cBioPortal 种子队列 | GDC 种子项目 | 状态 |
|---|---|---|---|
| 乳腺癌 | `brca_metabric` / `brca_tcga_pan_can_atlas_2018` | `TCGA-BRCA` | 专项规则与专项评测 |
| 肺腺癌 | `luad_tcga_pan_can_atlas_2018` | `TCGA-LUAD` | 通用队列、突变、生存与证据链路 |
| 肺鳞癌 | `lusc_tcga_pan_can_atlas_2018` | `TCGA-LUSC` | 通用队列、突变、生存与证据链路 |
| 结直肠癌 | `coadread_tcga_pan_can_atlas_2018` | `TCGA-COAD` / `TCGA-READ` | 通用队列、突变、生存与证据链路 |
| 前列腺腺癌 | `prad_tcga_pan_can_atlas_2018` | `TCGA-PRAD` | 通用队列、突变、生存与证据链路 |
| 肝细胞癌 | `lihc_tcga_pan_can_atlas_2018` | `TCGA-LIHC` | 通用队列、突变、生存与证据链路 |
| 胃腺癌 | `stad_tcga_pan_can_atlas_2018` | `TCGA-STAD` | 通用队列、突变、生存与证据链路 |
| 胰腺腺癌 | `paad_tcga_pan_can_atlas_2018` | `TCGA-PAAD` | 通用队列、突变、生存与证据链路 |
| 卵巢浆液性癌 | `ov_tcga_pan_can_atlas_2018` | `TCGA-OV` | 通用队列、突变、生存与证据链路 |
| 肾透明细胞癌 | `kirc_tcga_pan_can_atlas_2018` | `TCGA-KIRC` | 通用队列、突变、生存与证据链路 |
| 膀胱尿路上皮癌 | `blca_tcga_pan_can_atlas_2018` | `TCGA-BLCA` | 通用队列、突变、生存与证据链路 |
| 子宫内膜癌 | `ucec_tcga_pan_can_atlas_2018` | `TCGA-UCEC` | 通用队列、突变、生存与证据链路 |
| 头颈鳞癌 | `hnsc_tcga_pan_can_atlas_2018` | `TCGA-HNSC` | 通用队列、突变、生存与证据链路 |
| 胶质母细胞瘤 | `gbm_tcga_pan_can_atlas_2018` | `TCGA-GBM` | 通用队列、突变、生存与证据链路 |
| 甲状腺癌 | `thca_tcga_pan_can_atlas_2018` | `TCGA-THCA` | 通用队列、突变、生存与证据链路 |
| 皮肤黑色素瘤 | `skcm_tcga_pan_can_atlas_2018` | `TCGA-SKCM` | 通用队列、突变、生存与证据链路 |
| 宫颈癌 | `cesc_tcga_pan_can_atlas_2018` | `TCGA-CESC` | 通用队列、突变、生存与证据链路 |
| 食管癌 | `esca_tcga_pan_can_atlas_2018` | `TCGA-ESCA` | 通用队列、突变、生存与证据链路 |

以上入口已通过 GDC 和 cBioPortal 官方 API 核验标识符，但种子能力仍标记为 `seed_requires_runtime_verification`；每次任务必须由 Adapter 重新核验实际返回。常用宽泛名称（如胃癌、胰腺癌、卵巢癌）用于选择代表性的 TCGA 项目入口，不代表系统已从用户问题中确认了病理亚型；正式分析应以队列实际纳入标准为准。

## 其他癌种

任务解析会保留问题中明确给出的癌种，并可使用 GEO 目录、Europe PMC、ClinicalTrials.gov、CIViC 等通用发现入口。未配置癌种不会默认回退成乳腺癌，也不会自动选用乳腺癌队列。如需将某癌种提升为可直接取患者级队列的“配置癌种”，需增加经官方接口核验的队列配置和独立测试。

## 安全与评测口径

- 冻结 Canonical Schema 和现有医学安全规则不变。
- HER2 IHC 2+、ERBB2 CNA、跨域 response 和低置信度关联规则继续适用。
- 不同癌种、不同队列只能作独立分析或外部验证，不得按同名患者编号横向合并。
- 除乳腺癌外，其余配置癌种目前没有独立 sealed Gold Set，不宣称乳腺癌 SDTI 成绩可代表其他癌种。
