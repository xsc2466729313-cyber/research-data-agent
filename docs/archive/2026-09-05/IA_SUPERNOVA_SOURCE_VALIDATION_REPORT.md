# Ia Supernova Source Validation Report

> 阶段：Phase B0
>
> 目标：验证真实公开 Ia 型超新星光变曲线来源是否可稳定获取、解析，并支持后续观测级 CSV。
>
> 本阶段没有编写 Astronomy Adapter，没有修改业务代码，没有生成 CSV 或示例数据。

## 1. 结论摘要

本次对两个候选来源进行了真实 HTTP 访问，并同时验证了 VizieR 的 TSV 和 VOTable 机器接口。

结论：

- Primary source：CDS VizieR CfA4 source family：`J/ApJS/200/12/table6` + 同目录 `table1`。
- Secondary source：CDS VizieR `J/ApJ/959/132/table1`，KSP photometry of SN 2021aefx。
- 两个来源均能在无需认证的情况下返回 HTTP 200，并返回 TSV 与 VOTable。
- CfA4 table6 单独包含完整的观测级光变字段，但不含 redshift；同目录 table1 提供唯一 `SN` 标识和 `z`/`zCMB`，可以做确定性关联。
- CfA4 table6 的 5485 条观测记录涉及 92 个 SN；同目录 table1 的 92/92 个对应 SN 均可匹配，匹配率为 100%。
- KSP table1 有 1056 条观测记录，但没有 `SN` 列；单对象身份和 redshift 只在 ReadMe 的 Objects 元数据中，不存在可用的同目录 metadata table。
- KSP 适合作为独立单对象 photometry secondary source，但不应与 CfA4 自动合并，也不应使用名称相似度猜测 redshift。
- 两个来源都没有 `flux` 字段。不能在没有零点、滤镜系统和转换规则的情况下从 magnitude 静默生成 flux。

因此，满足进入 Phase B1 的条件，但 Phase B1 应先实现 CfA4 source family 的 source binding 和 adapter；KSP 作为独立 secondary provenance/test path 实施，不做跨来源观测行 Join。

## 2. 实际访问时间与验证材料

访问时间为 2026-09-05 19:11:04–19:11:41（Asia/Shanghai），对应 UTC 11:11:04–11:11:41。

官方入口：

- CfA4 catalog 页面：[J/ApJS/200/12](https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J%2FApJS%2F200%2F12)
- CfA4 table6 页面：[J/ApJS/200/12/table6](https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J%2FApJS%2F200%2F12%2Ftable6)
- CfA4 ReadMe：[J/ApJS/200/12 ReadMe](https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/J/ApJS/200/12?format=html&tex=true)
- KSP catalog 页面：[J/ApJ/959/132](https://vizier.cds.unistra.fr/viz-bin/VizieR-3?-source=J%2FApJ%2F959%2F132)
- KSP ReadMe：[J/ApJ/959/132 ReadMe](https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/J/ApJ/959/132?format=html&tex=true)

临时验证脚本和原始响应保存在：

- `../../../tmp/source_validation/validate_vizier_sources.py`
- `../../../tmp/source_validation/vizier_validation_report.json`
- `../../../tmp/source_validation/*.html`
- `../../../tmp/source_validation/*.readme`
- `../../../tmp/source_validation/*.tsv`
- `../../../tmp/source_validation/*.xml`

这些是本阶段的验证证据，不是正式 Adapter，也不是应用运行时资产。

## 3. 实际程序化获取方式

VizieR 官方 ASU 接口支持 TSV、VOTable、FITS 等输出。此次实际测试使用：

### TSV

```text
https://vizier.cds.unistra.fr/viz-bin/asu-tsv?-source={catalog}&-out.all&-out.max=100000
```

### VOTable

```text
https://vizier.cds.unistra.fr/viz-bin/votable?-source={catalog}&-out.all&-out.max=100000
```

VOTable 适合后续 Adapter 的首选输入，因为它同时提供字段 datatype、unit、UCD 和 description；TSV 适合作为简单、可审查的 fallback。

VizieR 官方文档明确说明 `asu-tsv` 是 Tab-Separated-Values 输出，VOTable 是 XML 格式并携带表元数据；官方接口说明见 [VizieR ASU 文档](https://vizier.unistra.fr/doc/asu.html) 和 [VizieR query 文档](https://tapvizier1.cds.unistra.fr/vizier/doc/vizquery.htx)。

## 4. Candidate 1：CfA4 table6

### 4.1 来源身份

- Catalog：`J/ApJS/200/12`
- Table：`J/ApJS/200/12/table6`
- Title：CfA4: light curves for 94 type Ia SNe
- Original paper：Hicken et al. 2012，bibcode `2012ApJS..200...12H`
- Paper DOI：[10.1088/0067-0049/200/2/12](https://doi.org/10.1088/0067-0049/200/2/12)
- Official CfA data product：[CfA4 Data Products](https://lweb.cfa.harvard.edu/supernova/CfA4/)

### 4.2 HTTP 与返回格式

| 请求 | HTTP | Content-Type | bytes | SHA-256（本次响应） |
|---|---:|---|---:|---|
| 官方 catalog page | 200 | `text/html` | 71657 | `d2d400738716be9a1f58b0567473ebf8b4ab62d7d5935adaae40f0621f26b356` |
| ReadMe | 200 | `text/plain; charset=utf-8` | 11346 | `1e3f2efd018af38ff079fbcbdb86983b2a099cbf2f31ece06044cdeb2cff91f` |
| table6 TSV | 200 | `text/tab-separated-values` | 414007 | `bb55919043d06ed0b86668b0dc4f702c437f4c10ebbfc163b3f5877d0b1b0b95` |
| table6 VOTable | 200 | `application/x-votable+xml` | 833836 | `320751b002182a484fdf1fbf02244d7283abe5862818b7bd1f33270ec1635f4c` |

请求不需要认证，未发送 API key 或 cookie。

### 4.3 真实数据量级

官方 catalog 页面标注 table6 为 5485 rows；对 TSV 过滤掉 VizieR 的单位行和分隔线后，实际数据行也是 5485。

- 观测行：5485
- 原始 SN 标识唯一值：92
- table1 元数据对象：94
- table1 中没有 table6 光变记录的对象：`2009hp`、`PTF10bjs`

这说明 catalog 标题中的 94 个 SN 与 standard-system table6 的 92 个实际光变对象并不是同一个覆盖数，Adapter 不能只使用标题中的 94 做行数断言。

### 4.4 真实表头与前 3 条数据结构

TSV 表头：

```text
recno, SN, Filt, MJD, N, sigPip, sigPhot, mag, e_mag, Per
```

前 3 条观测记录的结构如下，值为真实返回内容的字段结构：

| recno | SN | Filt | MJD | N | sigPip | sigPhot | mag | e_mag | Per |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | 2006ct | B | 53903.25177 | 3 | 0.0600 | 0.1496 | 18.8889 | 0.1612 | 空 |
| 2 | 2006ct | B | 53928.18575 | 2 | 0.2065 | 0.0375 | 19.8833 | 0.2099 | 空 |
| 3 | 2006ct | V | 53903.24946 | 3 | 0.0380 | 0.0806 | 18.0464 | 0.0891 | 空 |

VOTable 字段元数据确认：

| 原字段 | datatype | unit | UCD/含义 |
|---|---|---|---|
| `SN` | char | — | `meta.id;meta.main` |
| `Filt` | char | — | observation filter |
| `MJD` | double | `d` | `time.epoch` |
| `N` | short | — | successful subtractions |
| `sigPip` | float | `mag` | pipeline-generated uncertainty |
| `sigPhot` | float | `mag` | surviving photometry standard deviation |
| `mag` | float | `mag` | observed magnitude |
| `e_mag` | float | `mag` | total uncertainty |
| `Per` | char | — | period code；table6 中为空 |

ReadMe 说明 `e_mag` 是由 `sigPip` 与 `sigPhot` 合成的总不确定度。`mag`、`sigPip`、`sigPhot`、`e_mag` 单位均为 magnitude。

### 4.5 时间、波段、magnitude、flux、error

- 时间：`MJD`，单位为 day。
- 时间尺度：返回字段和 ReadMe 明确给出 MJD 与单位，但没有在机器字段中编码 UTC、TDB 等更细时间标准。后续 Adapter 应保留 MJD 原值，并在 metadata 中记录 `time_unit=d`、`time_scale=unspecified_by_source`，不得静默转换。
- 波段：`Filt`，官方页面列出 `BUVi'r'u'` 范围。
- magnitude：`mag`，观测星等。
- error：`e_mag`，总星等不确定度。
- flux：不存在。

不能从 `mag` 直接生成 `flux`，因为还需要滤镜、零点和系统定义。若 Phase B1 需要 flux，应作为明确的派生字段和独立转换规则，不得把它当作来源原字段。

## 5. Candidate 1 的 redshift 验证与 Join

### 5.1 同 catalog metadata table

同一个 CfA4 catalog 的 `J/ApJS/200/12/table1` 是 SN discovery metadata table。

真实 table1 表头：

```text
recno, SN, CS, LC, RAJ2000, DEJ2000, Gal, z, zCMB, E(B-V), e_E(B-V), Ref, SNcat, Simbad
```

关键字段：

- `SN`：SN Ia identification，唯一标识。
- `z`：Heliocentric redshift。
- `zCMB`：CMB redshift。

### 5.2 Join key 与匹配率

Join key 是两个表的 exact trimmed string：

```text
table6.SN = table1.SN
```

不是 recno，也不是 galaxy name、坐标或名称相似度。

结果：

- table6 光变对象：92
- table1 元数据对象：94
- table6 对象在 table1 中匹配：92
- 光变对象匹配率：100%
- table1 的多余对象：2 个（`2009hp`、`PTF10bjs` 没有 table6 standard-system 光变记录）
- 已匹配的 92 个对象中，`z` 缺失：0
- 已匹配的 92 个对象中，`zCMB` 缺失：0

关系是：table6 多条观测记录 → table1 一个 SN 元数据记录，即多对一的 observation-to-object 关联。table1 的 `SN` 自身唯一，因此这个 Join 可稳定执行。

### 5.3 redshift 字段选择

来源同时给出 `z` 和 `zCMB`，两者语义不同，不能混成一个无上下文的 `redshift`：

- `z`：heliocentric frame。
- `zCMB`：CMB frame。

候选映射建议：

- 若目标是宇宙学比较，`redshift` 映射为 `zCMB`，并在 metadata 中声明 `redshift_frame=CMB`。
- 同时保留 `z` 为 raw/source field 或扩展字段，避免丢失 heliocentric 值。
- 如果最终 schema 只允许一个 `redshift`，必须把 frame 写入 metadata 和 lineage，不能根据字段名自动选择。

## 6. Candidate 2：KSP SN 2021aefx table1

### 6.1 来源身份

- Catalog：`J/ApJ/959/132`
- Table：`J/ApJ/959/132/table1`
- Title：KSP photometry of the Type Ia SN 2021aefx
- Original paper：Ni et al. 2023，bibcode `2023ApJ...959..132N`
- 官方 ReadMe 明确对象：`SN 2021aefx = KSP-SN-2021v`
- VizieR catalog DOI：由官方 catalog 页面提供的 VizieR DOI 为 `10.26093/cds/vizier/ba-xz-44`

### 6.2 HTTP 与返回格式

| 请求 | HTTP | Content-Type | bytes | SHA-256（本次响应） |
|---|---:|---|---:|---|
| 官方 catalog page | 200 | `text/html` | 30495 | `44a7cd5e2f58f92d589f7e1ca693fbe0187d5bd234e5c294c058678fe6504b40` |
| ReadMe | 200 | `text/plain; charset=utf-8` | 7884 | `4fa6e0a313f40dcafe4feb48b68b717b17d8660ee9bf6e15b2e168742038335f` |
| table1 TSV | 200 | `text/tab-separated-values` | 55172 | `a879437754de6814925a132ce8e07e2e1dc8c708b2f3ae312f6ae8167ebaf592` |
| table1 VOTable | 200 | `application/x-votable+xml` | 119357 | `bb3ad1bbcb1d964d19f504ff3c9af0868107671f2e7ee1fd2de657d25349d31f` |

请求不需要认证，未发送 API key 或 cookie。

### 6.3 真实数据量级与字段

- 观测行：1056
- 稳定 row-level SN 字段：不存在
- 时间字段：`MJD`
- 波段字段：`Band`
- magnitude：`mag`
- detection error：`emagDet`
- total error：`emagTot`
- signal-to-noise：`S/N`
- flux：不存在

TSV 表头：

```text
recno, MJD, Band, mag, emagDet, emagTot, S/N
```

前 3 条真实记录结构：

| recno | MJD | Band | mag | emagDet | emagTot | S/N |
|---:|---:|---|---:|---:|---:|---:|
| 1 | 59529.82709 | B | 16.678 | 0.016 | 0.019 | 69.3 |
| 2 | 59529.82859 | V | 16.506 | 0.014 | 0.017 | 79.3 |
| 3 | 59529.83008 | i | 16.842 | 0.012 | 0.017 | 91.7 |

VOTable 字段确认：

| 原字段 | datatype | unit | 含义 |
|---|---|---|---|
| `MJD` | double | `d` | Modified Julian Date |
| `Band` | char | — | observation band |
| `mag` | float | `mag` | apparent magnitude |
| `emagDet` | float | `mag` | 1-sigma detection uncertainty |
| `emagTot` | float | `mag` | 1-sigma total uncertainty |
| `S/N` | float | — | signal to noise |

ReadMe 说明：

- B、V 波段 magnitude 使用 Vega system。
- i 波段 magnitude 使用 AB system。
- `emagTot` 包含 detection、photometric calibration 和 S-correction error。

这意味着后续 schema 至少要保留 `magnitude_system` 或等价 metadata，不能把 B/V/i 的 magnitude 当成同一系统而不标注。

### 6.4 redshift 和稳定标识验证

`table1` 没有 `SN` 列，也没有 `redshift` 列。

同 catalog 的 `table2` 也进行了真实请求：

- HTTP：200
- TSV Content-Type：`text/tab-separated-values`
- VOTable Content-Type：`application/x-votable+xml`
- 解析后数据行：0
- 没有可用的 metadata fields

因此，KSP catalog 没有可用于自动 Join 的 metadata table。

ReadMe 的 Objects 区块提供：

```text
SN 2021aefx = KSP-SN-2021v (z=0.005284)
```

这不是 row-level machine-readable column，而是 catalog-level metadata。后续如果使用它，必须采用明确的 source binding：

- `sn_id = SN 2021aefx`，来自 ReadMe Objects 区块。
- `redshift = 0.005284`，来自 ReadMe Objects `z`。
- 对 1056 条该单对象观测记录复制这个 catalog-level 常量时，必须在每行保留 `raw_field=ReadMe.Objects.z`、`raw_value=0.005284`，并声明这是 catalog metadata propagation，不是 observation row 原字段。
- 不允许根据 table 行中的其他文本猜测 SN 名称或 redshift。

更保守的 Phase B1 方案是：KSP secondary 先只输出 photometry observation records，把 redshift 作为单独的 catalog metadata，不强行并入完整主表。

## 7. 目标 Schema 对照

### 7.1 CfA4 主来源映射候选

| 真实来源字段 | 任务字段候选 | 证据/处理规则 |
|---|---|---|
| `table6.SN` | `sn_id` | exact trim；官方定义为 SN Ia identification |
| `table6.MJD` | `observation_time` | 保留 numeric MJD，unit=`d`，不静默转日期 |
| `table6.Filt` | `band` | 保留来源字符串，如 B、V、r'、i'、u' |
| `table6.mag` | `magnitude` | unit=`mag` |
| 无 | `flux` | 缺失；不得从 magnitude 猜测或静默派生 |
| `table6.e_mag` | `error` | total uncertainty，unit=`mag` |
| `table1.zCMB` | `redshift` | 仅在 metadata 明确 `redshift_frame=CMB` 时采用 |
| `table6.SN` + `table1.SN` | `source object join` | exact deterministic many-to-one join |
| 固定 source binding | `source_id` | 例如 `vizier:J/ApJS/200/12/table6` |
| 每次字段转换 | `raw_field` | 例如 `MJD`、`mag`、`e_mag`、`table1.zCMB` |
| 每次字段转换 | `raw_value` | 保留原始字符串或原始 numeric lexical value |

### 7.2 KSP secondary 映射候选

| 真实来源字段/元数据 | 任务字段候选 | 证据/处理规则 |
|---|---|---|
| ReadMe Objects: `SN 2021aefx` | `sn_id` | catalog-level pinned identity，不是 table row column |
| `MJD` | `observation_time` | unit=`d`，time scale 未在字段中明确 |
| `Band` | `band` | B、V、i |
| `mag` | `magnitude` | B/V Vega，i AB，必须保留 system metadata |
| 无 | `flux` | 缺失，不派生 |
| `emagTot` | `error` | total photometric uncertainty，unit=`mag` |
| ReadMe Objects: `z=0.005284` | `redshift` | catalog-level constant；不做 table join |
| fixed table binding | `source_id` | `vizier:J/ApJ/959/132/table1` |
| original field/ReadMe path | `raw_field` | 例如 `MJD`、`emagTot`、`ReadMe.Objects.z` |
| raw returned value | `raw_value` | 保留原始值 |

### 7.3 flux 结论

两个已验证来源均不返回 flux。Phase B1 不应把 magnitude 转换成 flux，除非单独建立：

- magnitude system。
- filter-specific zero point。
- bandpass definition。
- conversion formula。
- error propagation rule。
- provenance 和版本。

这些条件在 B0 未被来源表直接提供，因此不纳入本次主表合同。

## 8. 来源可靠性评分

### CfA4 VizieR source family

- Authority：High
- MachineReadable：YES
- StableIdentifier：YES，`SN` 是官方 SN Ia identification；table1 也是 exact join key
- PublicAccess：YES，未认证 HTTP 200
- SuitableForAutomatedAdapter：YES
- Reason：CDS VizieR 机器接口稳定返回 TSV/VOTable；table6 有 5485 条观测记录；同 catalog table1 提供 `SN`、`z`、`zCMB`；Join key 明确且 92/92 光变对象匹配。

### KSP SN 2021aefx VizieR table1

- Authority：High
- MachineReadable：YES
- StableIdentifier：YES（catalog-level object identity）；NO（table row 内没有 SN 列）
- PublicAccess：YES，未认证 HTTP 200
- SuitableForAutomatedAdapter：YES（photometry-only）；完整目标 schema 为 conditional
- Reason：1056 条观测记录和字段定义清楚；但 SN 身份与 redshift 只在 ReadMe Objects 元数据中，没有 row-level metadata table，不能作为通用多对象表直接处理。

## 9. 许可、引用和访问限制

### CfA4 与 KSP 的来源引用

应同时记录：

- 原始论文 bibcode/DOI。
- VizieR catalog ID 和 table ID。
- CDS/VizieR 访问日期。
- 原始响应 checksum。
- 目录 ReadMe。

VizieR 页面要求在研究中使用其目录时进行 acknowledgement，并提供 VizieR DOI `10.26093/cds/vizier`。应在最终 metadata 和导出说明中保留该 acknowledgement。

### 访问限制

- 本次两个候选均无需认证。
- 机器接口返回成功，但 VizieR 官方页面提示服务正在经历 bot activity，建议使用合理速率、超时、重试和必要时官方 mirror。
- 接口默认结果数存在限制，验证请求显式使用 `-out.max=100000`；正式 Adapter 仍应设置任务级上限，不允许由用户/模型无限制拉取。
- TSV/VOTable 返回中包含 `request_date`、server software 等动态注释，因此同一数据的整包 SHA-256 可能随请求时间变化。正式 lineage 应同时保存 raw response hash、请求 URL、请求时间和解析后的 normalized data hash，不能只依赖单一整包 hash。
- 当前没有发现付费墙或登录要求，但仍需遵守 VizieR 数据使用和原始论文引用要求。

## 10. Primary / Secondary 推荐

### Primary

**CfA4 VizieR source family：`J/ApJS/200/12/table6` + `table1`。**

推荐原因：

1. 有真实观测级 5485 行光变数据。
2. 有明确稳定 `SN` 标识。
3. 有明确 `MJD`、滤镜、magnitude 和 total error。
4. 同一 catalog 的 table1 提供 `z`/`zCMB`。
5. exact `SN` Join 已通过实际 92/92 对象匹配验证。
6. TSV 与 VOTable 均可程序化访问。
7. 不需要认证。

Primary 不应只绑定 table6；必须把 table1 作为同 catalog metadata dependency 固定下来，或者明确把 redshift 设为 nullable。

### Secondary

**KSP VizieR `J/ApJ/959/132/table1`。**

推荐用途：

- 独立单对象 photometry 测试。
- 多波段、高 cadence 的 provenance 对照。
- 解析器和 uncertainty 处理的第二种字段形态测试。
- 后续与 Primary 做 source-level 交叉讨论，而不是把观测行自动合并。

不推荐用途：

- 与 CfA4 做无规则 row-level merge。
- 用 `SN 2021aefx` 名称相似度匹配其他 catalog。
- 把 ReadMe 的 `z=0.005284` 伪装成 table row 原始字段而不记录 metadata propagation。

## 11. Phase B1 Adapter 实施建议

本节只给建议，不在 B0 实现 Adapter。

### 11.1 先实现 CfA4

建议 source binding 固定：

- catalog：`J/ApJS/200/12`
- photometry table：`table6`
- metadata table：`table1`
- primary output：VOTable
- fallback output：TSV
- exact join key：`SN`
- redshift policy：显式选择 `z` 或 `zCMB`，默认不能隐式决定

### 11.2 获取和解析

Adapter 应：

1. 只访问固定 source binding，不让 LLM 拼接 URL。
2. 首选 VOTable，校验字段、datatype、unit、UCD。
3. TSV fallback 必须跳过 VizieR units/separator metadata rows。
4. 校验 `recno`、字段数量、字段类型和必需列。
5. 保留请求 URL、request time、Content-Type、server version 和 checksum。
6. 对 ReadMe 单独建立 provenance entry。
7. 精确 trim `SN` 并执行 deterministic many-to-one Join。
8. 每条输出记录保留 `source_id`、`raw_field`、`raw_value`。
9. 对 `MJD` 保留数值和单位，不自动转换时间尺度。
10. 对 missing flux 明确输出 schema status，而不是补值。

### 11.3 KSP 的独立绑定

KSP 应作为独立 source binding，不与 CfA4 共享 Join 逻辑：

- 绑定唯一对象 `SN 2021aefx`。
- 把 ReadMe Objects 区块作为 catalog metadata source。
- 将 magnitude system 按 band 记录。
- 将 `emagTot` 作为 total error。
- redshift 作为 metadata propagation 或 nullable 字段处理。
- 未经用户/规则批准，不将 KSP 行并入 CfA4 主表。

## 12. 风险

1. VizieR 服务存在 bot activity 和 mirror 提示，生产使用需要限速和重试。
2. VizieR TSV 含单位行、分隔行和动态注释，不能直接把第一个 header 后的所有行当数据。
3. CfA4 catalog 标题是 94 个 SN，但 table6 实际只有 92 个有 standard-system photometry 的 SN。
4. `z` 和 `zCMB` 不是同一语义，必须声明 frame。
5. MJD 的 day unit 已确认，但细时间尺度没有在返回字段中明确编码。
6. 两个来源都没有 flux。
7. KSP 没有 row-level SN 列，身份来自 ReadMe Objects 元数据。
8. KSP B/V 与 i 使用不同 magnitude system。
9. 整个 HTTP 响应 hash 会受到动态 request metadata 影响。
10. 本次只验证了访问和字段，不代表数据已经通过最终领域质量门禁，也不代表已完成真实资产发布。

## 13. 是否满足进入 Phase B1

**结论：满足，但应采用受限进入策略。**

Phase B1 可以开始：

- 实现 CfA4 source binding。
- 实现 table6 + table1 的真实数据 adapter。
- 实现 exact `SN` Join。
- 实现 MJD、band、magnitude、e_mag、z/zCMB 的 provenance。
- 实现真实数据夹具、字段检查、checksum 和失败处理。

Phase B1 暂不应：

- 把 KSP 与 CfA4 自动合并。
- 把 magnitude 转成 flux。
- 把 MJD 静默转换为未声明时间尺度。
- 把 KSP ReadMe redshift 当作普通 row-level 来源列。
- 修改冻结医疗配置或现有 v30/v31 业务链路。

B0 到此完成。没有写正式 Astronomy Adapter，没有修改现有业务代码，没有生成 CSV。
