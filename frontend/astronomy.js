// Astronomy uses the same conversation history, but never the patient-table renderer.
function astronomyStatus(result) {
  return ({ running: "天文数据获取中", completed: "观测数据已生成", partial: "部分完成，需查看缺口",
    failed: "获取失败", interrupted: "运行已中断" })[result?.status] || "等待获取结果";
}

function astronomyArtifact(result) {
  return { taskId: result.task_id, rowCount: result.row_count,
    pending: result.status === "running",
    sourceRows: result.sources.reduce((total, source) => total + (source.row_count || 0), 0),
    status: astronomyStatus(result), message: result.errors.join("；") };
}

function acceptAstronomyResult(run, result) {
  run.astroResults ||= new Map();
  run.astroResults.set(result.task_id, result);
  const artifact = astronomyArtifact(result);
  run.artifacts = [...(run.artifacts || []).filter((item) => item.taskId !== result.task_id), artifact];
  if (run.build?.taskId === result.task_id) {
    run.astronomy = result;
    run.build = artifact;
    run.running = result.status === "running";
    run.status = artifact.status;
  }
  persistPlannerRun(run);
}

async function loadAstronomyResult(run, taskId) {
  try {
    const result = await readJson(await fetchApi(`/api/astronomy/tasks/${encodeURIComponent(taskId)}`));
    if (result.task_id !== taskId) throw new Error("返回任务与当前对话不一致");
    acceptAstronomyResult(run, result);
    run.loadError = "";
    if (result.status === "running") watchAstronomyRun(run, taskId);
    return result;
  } catch (error) {
    run.loadError = error.message;
    run.running = false;
    return null;
  }
}

async function watchAstronomyRun(run, taskId) {
  run.watching ||= new Set();
  if (run.watching.has(taskId)) return;
  run.watching.add(taskId);
  try {
    while (true) {
      const result = await loadAstronomyResult(run, taskId);
      if (isActivePlannerSession(run.sessionId)) renderAstronomyRun(run);
      if (!result || result.status !== "running") break;
      await new Promise((resolve) => window.setTimeout(resolve, 2000));
    }
  } finally {
    run.watching.delete(taskId);
  }
}

async function executeAstronomyRun(run, sources) {
  if (run.running) return;
  if (typeof ensureResearchProvidersConfigured === "function" && !(await ensureResearchProvidersConfigured())) return;
  run.running = true;
  run.loadError = "";
  run.status = "天文数据获取中";
  plannerMessage(run, "assistant", sources.length > 1
    ? "按选定的 CfA4 和 KSP 两个已接入目录重新获取，并按统一观测字段纵向拼接。旧结果保留，不跨目录猜测对象关联。"
    : "先获取 CfA4 光变观测表与对象元数据，以目录内的 SN 编号精确关联。运行前需先连接千问 API；数据仍直接来自公开目录。", "真实数据获取");
  persistPlannerRun(run);
  if (isActivePlannerSession(run.sessionId)) renderAstronomyRun(run);
  try {
    const result = await readJson(await fetchApi("/api/astronomy/tasks", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic: run.inputTopic, sources }),
    }));
    run.build = { taskId: result.task_id };
    acceptAstronomyResult(run, result);
    await watchAstronomyRun(run, result.task_id);
  } catch (error) {
    run.running = false;
    run.loadError = error.message;
    persistPlannerRun(run, "获取失败");
    if (isActivePlannerSession(run.sessionId)) renderAstronomyRun(run);
  }
}

async function cleanAstronomyExisting(run, taskId) {
  if (!run || run.running) return;
  if (typeof ensureResearchProvidersConfigured === "function" && !(await ensureResearchProvidersConfigured())) return;
  run.running = true;
  if (isActivePlannerSession(run.sessionId)) renderAstronomyRun(run);
  try {
    const result = await readJson(await fetchApi(`/api/astronomy/tasks/${encodeURIComponent(taskId)}/clean`, { method: "POST" }));
    run.build = { taskId: result.task_id };
    acceptAstronomyResult(run, result);
    await watchAstronomyRun(run, result.task_id);
  } catch (error) {
    run.running = false;
    run.loadError = error.message;
    persistPlannerRun(run, "清洗失败");
    if (isActivePlannerSession(run.sessionId)) renderAstronomyRun(run);
  }
}

function startAstronomyResearch(topic) {
  plannerElement("#planner-topic").value = "";
  const sessionId = `planner_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const run = { sessionId, inputTopic: topic, domain: "astronomy", messages: [], artifacts: [], running: false };
  plannerRuns.set(sessionId, run);
  plannerState.sessionId = sessionId;
  plannerMessage(run, "user", topic, "刚刚");
  plannerMessage(run, "assistant", "按 Ia 型超新星光变曲线理解本次需求。输出粒度是一条观测，包含对象、MJD、滤镜、星等及误差和来源；当前从已接入目录取数，并非任意领域的全网自动检索。", "研究范围");
  return executeAstronomyRun(run, ["cfa4"]);
}

const ASTRONOMY_SOURCE_NAMES = {
  "J/ApJS/200/12/table1": "CfA4 · 超新星对象目录",
  "J/ApJS/200/12/table6": "CfA4 · 多波段光变观测",
  "J/ApJ/959/132/table1": "KSP · 多波段光变观测",
  "ksp-ReadMe.txt": "KSP · 对象说明文档",
};

function astronomyLineageLines(label, maxLength = 18) {
  const text = String(label || "未命名来源");
  if (text.length <= maxLength) return [text];
  return [text.slice(0, maxLength), `${text.slice(maxLength, maxLength * 2 - 1)}…`];
}

function astronomySourceFamily(sourceId) {
  if (/J\/ApJS/i.test(sourceId)) return "cfa4";
  if (/J\/ApJ|ksp/i.test(sourceId)) return "ksp";
  return sourceId;
}

function astronomyLineage(result, { prefix = "astro-lineage" } = {}) {
  const sources = (result?.sources || []).filter((source) => source?.source_id).slice(0, 6);
  const workflow = result?.workflow || [];
  const count = (value) => Number(value || 0).toLocaleString("zh-CN");
  const safePrefix = String(prefix).replace(/[^a-zA-Z0-9_-]/g, "-");
  const width = 1120;
  const rowHeight = 96;
  const height = Math.max(286, sources.length * rowHeight + 94);
  const sourceX = 360;
  const sourceWidth = 330;
  const sourceStart = (height - ((sources.length - 1) * rowHeight + 72)) / 2;
  const sourceNodes = sources.length ? sources.map((source, index) => {
    const sourceId = String(source.source_id);
    const family = astronomySourceFamily(sourceId);
    const step = workflow.find((item) => item.source === family);
    const label = ASTRONOMY_SOURCE_NAMES[sourceId] || sourceId;
    const lines = astronomyLineageLines(label);
    const cy = sourceStart + index * rowHeight + 36;
    const rowCount = source.row_count == null ? "等待解析" : `${count(source.row_count)} 行来源响应`;
    const outputCount = step?.output_rows == null ? "" : ` · ${count(step.output_rows)} 行对齐`;
    const lineMarkup = lines.map((line, lineIndex) => `<tspan x="${sourceX + 24}" dy="${lineIndex ? 18 : 0}">${escapeHtml(line)}</tspan>`).join("");
    return `<path class="astro-lineage-edge" marker-end="url(#${safePrefix}-lineage-arrow)" d="M 166 ${height / 2} C 232 ${height / 2}, 276 ${cy}, ${sourceX} ${cy}" />
      <path class="astro-lineage-edge astro-lineage-edge-output" marker-end="url(#${safePrefix}-lineage-arrow)" d="M ${sourceX + sourceWidth} ${cy} C 760 ${cy}, 824 ${height / 2}, 954 ${height / 2}" />
      <g class="astro-lineage-source" aria-label="${escapeHtml(`${label}，${rowCount}`)}">
        <rect x="${sourceX}" y="${cy - 36}" width="${sourceWidth}" height="72" rx="16" />
        <circle cx="${sourceX + 18}" cy="${cy - 16}" r="5" />
        <text class="astro-lineage-source-label" x="${sourceX + 24}" y="${cy - 10}">${lineMarkup}</text>
        <text class="astro-lineage-source-meta" x="${sourceX + 24}" y="${cy + 25}">${escapeHtml(`${rowCount}${outputCount}`)}</text>
      </g>`;
  }).join("") : `<g class="astro-lineage-empty"><rect x="${sourceX}" y="${height / 2 - 36}" width="${sourceWidth}" height="72" rx="16" /><text x="${sourceX + sourceWidth / 2}" y="${height / 2 + 5}" text-anchor="middle">等待来源响应</text></g>`;
  const sourceCards = sources.map((source) => {
    const sourceId = String(source.source_id);
    const family = astronomySourceFamily(sourceId);
    const step = workflow.find((item) => item.source === family);
    const label = ASTRONOMY_SOURCE_NAMES[sourceId] || sourceId;
    return `<article class="astro-lineage-source-card"><strong>${escapeHtml(label)}</strong><code>${escapeHtml(sourceId)}</code><span>${source.row_count == null ? "等待解析" : `${count(source.row_count)} 行来源响应`}${step?.output_rows == null ? "" : ` → ${count(step.output_rows)} 行对齐`}</span></article>`;
  }).join("");
  return `<section id="${safePrefix}" class="astro-lineage" aria-labelledby="${safePrefix}-title">
    <div class="astro-lineage-heading"><div><p class="section-kicker">02 · 数据血缘图</p><h3 id="${safePrefix}-title">数据血缘图</h3></div><span class="count-tag">${count(sources.length)} 份真实来源</span></div>
    <p class="detail-caption">从研究问题到来源响应，再到观测矩阵；每条连线都对应本次任务实际返回的来源和解析步骤。</p>
    <div class="astro-lineage-legend" aria-label="血缘图图例"><span><i class="is-question"></i>研究问题</span><span><i class="is-source"></i>来源响应</span><span><i class="is-output"></i>观测矩阵</span></div>
    <div class="astro-lineage-canvas" role="img" aria-label="研究问题、真实天文来源与观测矩阵之间的数据血缘关系">
      <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" focusable="false" aria-hidden="true">
        <defs><linearGradient id="${safePrefix}-lineage-gradient" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#93c5fd" /><stop offset="1" stop-color="#2563eb" /></linearGradient><marker id="${safePrefix}-lineage-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#60a5fa" /></marker></defs>
        <path class="astro-lineage-edge astro-lineage-edge-main" d="M 166 ${height / 2} C 238 ${height / 2}, 824 ${height / 2}, 954 ${height / 2}" />
        ${sourceNodes}
        <g class="astro-lineage-terminal astro-lineage-question"><rect x="28" y="${height / 2 - 32}" width="138" height="64" rx="18" /><text x="97" y="${height / 2 - 2}" text-anchor="middle">研究问题</text><text x="97" y="${height / 2 + 17}" text-anchor="middle" class="astro-lineage-terminal-meta">Ia 型光变曲线</text></g>
        <g class="astro-lineage-terminal astro-lineage-output"><rect x="954" y="${height / 2 - 32}" width="138" height="64" rx="18" /><text x="1023" y="${height / 2 - 2}" text-anchor="middle">观测矩阵</text><text x="1023" y="${height / 2 + 17}" text-anchor="middle" class="astro-lineage-terminal-meta">${count(result?.row_count)} 条</text></g>
      </svg>
    </div>
    ${sourceCards ? `<div class="astro-lineage-source-list">${sourceCards}</div>` : '<p class="detail-empty astro-lineage-empty-note">暂无来源响应，血缘图会在获取完成后更新。</p>'}
  </section>`;
}

function astronomyDetails(result, { prefix = "astro-preview", downloads = false, includeLineage = true } = {}) {
  if (!result) return '<div class="panel detail-empty"><strong>暂未取得任务结果</strong><p>请返回当前对话检查连接后重试，已有版本仍会保留。</p></div>';
  const sources = result.sources || [];
  const workflow = result.workflow || [];
  const preview = result.preview || [];
  const errors = result.errors || [];
  const families = [...new Set(workflow.filter((step) => step.operation === "parse_and_align").map((step) => step.source))];
  const running = result.status === "running";
  const count = (value) => Number(value || 0).toLocaleString("zh-CN");
  const section = (id, number, title, aside = "") => `<div class="section-heading"><div><p class="section-kicker">${number} · ${title}</p><h2 id="${prefix}-${id}-title">${title}</h2></div>${aside}</div>`;
  const actions = (formats) => downloads ? `<div class="button-group">${formats.map(([format, label], index) => `<button type="button" class="button ${index ? "button-secondary" : "button-primary"}" data-astronomy-download="${format}" data-task-id="${escapeHtml(result.task_id)}">${label}</button>`).join("")}</div>` : "";
  const fields = [["object_id", "观测对象"], ["mjd", "观测时间", "MJD · 天"], ["band", "滤镜"], ["magnitude", "星等", "mag"], ["magnitude_error", "星等误差", "mag"], ["redshift_heliocentric", "日心红移"], ["source_id", "观测来源"]];
  return `<div class="research-detail">
    ${downloads ? `<nav class="results-toc" aria-label="结果章节"><a href="#${prefix}-overview">摘要</a><a href="#${prefix}-workflow">工作流程</a>${includeLineage ? `<a href="#${prefix}-lineage">数据血缘</a>` : ""}<a href="#${prefix}-data">数据矩阵</a><a href="#${prefix}-sources">来源溯源</a><a href="#${prefix}-quality">质量与边界</a></nav>` : ""}
    <section id="${prefix}-overview" class="result-overview" aria-label="任务概览">
      <article><span>有效观测</span><strong>${count(result.row_count)}<small> 条</small></strong></article>
      <article><span>已解析观测目录</span><strong>${count(families.length)}<small> 个</small></strong></article>
      <article><span>待复核观测</span><strong>${count(result.cleaning_report?.review_rows ?? result.rejected_count)}<small> 条</small></strong></article>
      <article><span>本次执行状态</span><strong class="detail-status-text">${escapeHtml(astronomyStatus(result))}</strong></article>
    </section>
    <section id="${prefix}-workflow" class="panel" aria-labelledby="${prefix}-workflow-title">
      ${section("workflow", "01", "研究工作流程", '<span class="count-tag">观测级整合</span>')}
      <ol class="detail-workflow">
        <li><span class="detail-step-number">01</span><div><strong>明确研究对象</strong><p>Ia 型超新星光变曲线<br>一行对应一次观测</p></div></li>
        <li><span class="detail-step-number">02</span><div><strong>获取真实来源</strong><p>${escapeHtml((result.requested_sources || []).map((name) => name.toUpperCase()).join("、"))}<br>已保存 ${sources.length} 份来源响应</p></div></li>
        <li><span class="detail-step-number">03</span><div><strong>解析与字段对齐</strong><p>统一时间、滤镜、星等与误差<br>对象仅在目录内精确关联</p></div></li>
        <li class="${result.row_count ? "is-complete" : "is-pending"}"><span class="detail-step-number">04</span><div><strong>${running ? "正在汇总观测" : result.row_count ? "清洗、隔离并生成矩阵" : "等待有效观测"}</strong><p>${count(result.row_count)} 条可用观测<br>重复、无效和冲突行另列审计</p></div></li>
      </ol>
      <details class="report-drawer"><summary>查看原始执行记录与关联规则</summary><div class="detail-audit">${workflow.length ? workflow.map((step) => `<p><strong>${escapeHtml(step.source || "汇总")}</strong> · <code>${escapeHtml(step.operation)}</code> · 输出 ${count(step.output_rows)} 行${step.identity_rule ? `<br>原始关联规则：<code>${escapeHtml(step.identity_rule)}</code>` : ""}</p>`).join("") : "<p>尚未取得阶段记录，不将等待状态视为完成。</p>"}</div></details>
    </section>
    ${includeLineage ? astronomyLineage(result, { prefix: `${prefix}-lineage` }) : ""}
    <section id="${prefix}-data" class="panel" aria-labelledby="${prefix}-data-title">
      ${section("data", "03", "观测数据矩阵", result.row_count > 0 ? actions([["csv", "下载 CSV"], ["xlsx", "下载 Excel"]]) : "")}
      <p class="detail-caption">${running ? "阶段性结果 · " : ""}预览前 ${preview.length} 条，共 ${count(result.row_count)} 条。主表只放可分析字段；原始字段、原始值与哈希在来源包和独立原始工作表中。</p>
      ${preview.length ? `<div class="table-wrap detail-data-table" role="region" aria-label="可横向滚动的观测矩阵" tabindex="0"><table><thead><tr>${fields.map(([, label, unit]) => `<th scope="col">${label}${unit ? `<small>${unit}</small>` : ""}</th>`).join("")}</tr></thead><tbody>${preview.map((row) => `<tr>${fields.map(([field]) => `<td>${field === "source_id" ? escapeHtml(ASTRONOMY_SOURCE_NAMES[row[field]] || row[field] || "未提供") : escapeHtml(row[field] ?? "未提供")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : '<div class="detail-empty"><strong>暂无可预览的观测</strong><p>只有取得有效数据后才会提供 CSV 和 Excel。</p></div>'}
      <details class="report-drawer"><summary>查看原始字段映射与单位</summary><div class="detail-audit"><p>MJD → mjd；Filt / Band → band；mag → magnitude；e_mag / emagTot → magnitude_error。</p><p>z 与 zCMB 分开保存；时间尺度未注明时不推定 UTC / TDB。CSV 保留原始字段名与值，完整字段定义在来源包中。</p></div></details>
    </section>
    <section id="${prefix}-sources" class="panel" aria-labelledby="${prefix}-sources-title">
      ${section("sources", "04", "数据来源与溯源", sources.length ? actions([["sources", "下载来源包"]]) : "")}
      <div class="detail-source-grid">${sources.map((source) => {
        const url = safePlannerUrl(source.url);
        const date = new Date(source.retrieved_at);
        const time = Number.isNaN(date.getTime()) ? "时间未提供" : date.toLocaleString("zh-CN", { hour12: false });
        const countLabel = source.row_count != null ? `${count(source.row_count)} 行` : /ReadMe/i.test(source.source_id) ? "说明文档" : "未完成解析";
        return `<article class="detail-source-card"><div class="detail-source-heading"><strong>${escapeHtml(ASTRONOMY_SOURCE_NAMES[source.source_id] || source.source_id)}</strong><span class="count-tag">${countLabel}</span></div><p class="detail-caption">获取时间 · ${escapeHtml(time)}</p>${url ? `<a class="detail-source-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">查看原始来源 ↗</a>` : '<span class="detail-caption">来源链接不可用</span>'}<details class="report-drawer"><summary>来源编号、引用与校验信息</summary><dl class="detail-audit"><dt>来源编号</dt><dd>${escapeHtml(source.source_id)}</dd><dt>论文与数据引用</dt><dd>${escapeHtml([source.publication?.cites, source.publication?.citation].filter(Boolean).join(" · ") || "来源未提供引用标识")}</dd><dt>文件校验 · SHA256</dt><dd><code>${escapeHtml(source.sha256 || "未提供")}</code></dd></dl></details></article>`;
      }).join("") || '<p class="detail-caption">尚未取得来源响应。</p>'}</div>
    </section>
    <section id="${prefix}-quality" class="panel" aria-labelledby="${prefix}-quality-title">
      ${section("quality", "05", "质量检查与使用边界", `${actions([["quality_report", "下载质量报告"]])}${downloads && !result.pipeline_version && !running ? `<button type="button" class="button button-secondary" data-astronomy-clean data-task-id="${escapeHtml(result.task_id)}">按原始证据执行清洗</button>` : ""}`)}
      <div class="detail-quality-note ${errors.length || result.rejected_count || result.cleaning_report?.review_rows ? "is-review" : ""}"><strong>${errors.length || result.rejected_count || result.cleaning_report?.review_rows ? "本次存在需要复核的内容" : running ? "检查随获取过程更新" : result.row_count ? "已完成字段清洗；不等于科学分析已就绪" : "未形成可用观测表"}</strong><p>${count(result.cleaning_report?.review_rows ?? result.rejected_count)} 条观测待复核，${count(result.cleaning_report?.duplicate_rows)} 条完全重复已隔离，${count(errors.length)} 条获取或解析异常。测光校准、光变拟合和物理解释仍需后续分析。</p></div>
      ${result.cleaning_report ? `<div class="detail-quality-note"><strong>清洗对账：${count(result.cleaning_report.input_rows)} 条输入 → ${count(result.cleaning_report.usable_rows)} 条可用</strong><p>完全重复 ${count(result.cleaning_report.duplicate_rows)} 条；无效隔离 ${count(result.cleaning_report.invalid_rows)} 条；待复核 ${count(result.cleaning_report.review_rows)} 条。未填补任何缺失值，未按科学离群规则删除观测。</p></div>` : ""}
      ${result.quality_gate?.layers?.length ? `<div class="detail-audit quality-gate-list">${result.quality_gate.layers.map((gate) => `<p><strong>${escapeHtml(gate.label)} · ${escapeHtml(gate.decision)}</strong><br>${escapeHtml(gate.evidence)}</p>`).join("")}</div>` : ""}
      ${errors.length ? `<ul class="detail-error-list">${errors.map((error) => `<li>${escapeHtml(error)}</li>`).join("")}</ul>` : ""}
      <ul class="detail-limitations">${(result.limitations || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    </section></div>`;
}

function renderAstronomyRun(run) {
  syncPlannerStateFromRun(run);
  plannerElement("#planner-submit").disabled = false;
  plannerElement("#planner-welcome").hidden = true;
  plannerElement("#planner-progress").hidden = true;
  plannerElement("#planner-results").hidden = false;
  plannerElement("#planner-header-title").textContent = run.inputTopic;
  plannerElement("#planner-header-subtitle").textContent = "天文观测数据 · 独立于患者数据工作流";
  plannerElement("#planner-result-title").textContent = run.status;
  plannerElement("#planner-question-list").innerHTML = "";
  clearPlannerContractSurfaces();
  const result = run.astronomy;
  const requestedSources = result?.requested_sources || ["cfa4"];
  plannerElement("#planner-result-summary").textContent = `当前结果来自 ${requestedSources.map((source) => source.toUpperCase()).join(" 与 ")}；每次运行与下载均绑定当前对话。`;
  const sources = result?.sources || [];
  plannerElement("#planner-panel-evidence").innerHTML = `<div class="planner-panel-heading"><span>研究依据</span><h3>本次真实来源</h3><p>仅展示当前任务实际取得的公开观测入口。</p></div>${sources.length ? `<div class="planner-evidence-list">${sources.map((source) => `<article class="planner-evidence-card"><header><span>${escapeHtml(source.source_id)}</span><span>机器可读</span></header><h4>${escapeHtml(ASTRONOMY_SOURCE_NAMES[source.source_id] || source.source_id)}</h4><p>${escapeHtml(source.publication?.cites || "机器可读数据与目录元数据")}</p>${safePlannerUrl(source.url) ? `<a href="${escapeHtml(safePlannerUrl(source.url))}" target="_blank" rel="noopener noreferrer">查看真实来源 ↗</a>` : ""}</article>`).join("")}</div>` : plannerEmpty("…", "正在连接公开天文目录", "收到响应后才展示已获取来源。 ")}`;
  plannerElement("#planner-panel-contract").innerHTML = `<div class="planner-panel-heading"><span>研究方案</span><h3>天文观测方案</h3><p>${escapeHtml(run.inputTopic)}</p></div><div class="planner-status-note">一行对应一次观测，保留对象、MJD、滤镜、星等、误差及来源。不使用患者表，不在此阶段拟合光变或推断物理结论。</div>`;
  plannerElement("#planner-panel-sources").innerHTML = `<div class="planner-panel-heading"><span>数据准备</span><h3>本次数据准备</h3></div><div class="planner-status-note">${escapeHtml(run.status)}<br>范围：${escapeHtml((result?.requested_sources || ["cfa4"]).join("、"))}</div><p class="detail-caption">来源原文、字段定义、抓取时间和哈希可下载核验。</p>${(result?.errors || []).map((error) => `<div class="planner-status-note is-error">${escapeHtml(error)}</div>`).join("")}`;
  plannerElement("#planner-panel-coverage").innerHTML = `<div class="planner-panel-heading"><span>字段覆盖</span><h3>观测字段覆盖</h3></div><div class="planner-status-note">${result?.row_count || 0} 条有效观测；${result?.rejected_count || 0} 条异常行另列质量报告。</div><p class="detail-caption">MJD、滤镜、星等及误差必须通过解析和单位检查；红移未匹配保留空值，flux 未提供。</p>`;
  setPlannerStage(run.running ? "literature" : "sources", { completedThrough: run.running ? "topic" : "sources" });
  renderPlannerChat(run);
  const sourceList = requestedSources.join(",");
  const primaryAction = run.running ? "正在获取真实观测…" : result?.task_id ? "生成当前观测数据集" : "开始生成数据集";
  plannerElement("#planner-flow-summary").innerHTML = `${plannerOutputs(run)}
    ${result ? astronomyLineage(result, { prefix: "astro-planner-lineage" }) : ""}
    <div class="planner-next-action astronomy-next-action">
      <div class="planner-next-copy"><strong>下一步：生成科研数据集</strong><small>沿用当前已核验的观测来源，生成可下载的数据集版本；每个版本独立保留，不覆盖已有结果。</small></div>
      <button type="button" data-astronomy-retry data-sources="${escapeHtml(sourceList)}" ${run.running ? "disabled" : ""}>${primaryAction}</button>
    </div>
    <details class="astronomy-supplement"><summary>补充来源（可选）</summary><p>需要更多观测时，再加入 KSP 目录；它会作为新的结果版本保存。</p><button type="button" class="button button-secondary" data-astronomy-retry data-sources="cfa4,ksp" ${run.running ? "disabled" : ""}>补充 KSP 并继续</button></details>
    <details><summary>数据来源、工作流程与观测预览</summary>${astronomyDetails(run.astronomy, { includeLineage: false })}</details>`;
  renderPlannerRecent();
}

async function openAstronomyTechnical(run, taskId) {
  const requested = taskId || run.build?.taskId;
  const token = {};
  state.technicalRequest = token;
  document.body.classList.add("is-advanced-workbench");
  resultsPanel.hidden = true;
  state.result = null;
  const context = document.querySelector("#technical-context");
  const output = document.querySelector("#astronomy-results");
  output.hidden = true;
  output.innerHTML = "";
  context.hidden = false;
  context.innerHTML = `<div class="section-heading"><div><p class="section-kicker">研究工作台 · 天文观测</p><h2>${escapeHtml(run.inputTopic)}</h2></div><span class="status-badge is-pending">正在加载</span></div><p class="detail-caption">正在载入当前对话的流程与结果…</p>`;
  const result = run.astroResults?.get(requested) || (requested ? await loadAstronomyResult(run, requested) : run.astronomy);
  if (!isActivePlannerSession(run.sessionId) || state.technicalRequest !== token) return;
  context.innerHTML = `<div class="section-heading"><div><p class="section-kicker">研究工作台 · 天文观测</p><h2>${escapeHtml(run.inputTopic)}</h2></div><span class="status-badge ${result?.status === "completed" ? "is-primary" : "is-pending"}">${escapeHtml(astronomyStatus(result))}</span></div><p class="detail-caption">本页对应当前选中的结果版本。数据按观测组织，不跨目录猜测对象关联。</p><details class="detail-task-id"><summary>查看本次任务编号</summary><code>${escapeHtml(requested || "任务尚未创建")}</code></details>${run.loadError ? `<p class="detail-error-list">${escapeHtml(run.loadError)}</p>` : ""}`;
  output.innerHTML = astronomyDetails(result, { prefix: "astro-detail", downloads: true });
  output.hidden = false;
  context.scrollIntoView({ behavior: "smooth", block: "start" });
}
