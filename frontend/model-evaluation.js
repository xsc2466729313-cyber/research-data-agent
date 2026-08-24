const escapeHtml = (value) => String(value ?? "—")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const MODEL_PROVIDER_LABELS = {
  qwen: "千问",
  deepseek: "DeepSeek",
  openai_compatible: "OpenAI 兼容",
};

const MODEL_PROVIDER_DEFAULTS = {
  qwen: { model: "qwen-plus", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
  deepseek: { model: "deepseek-chat", baseUrl: "https://api.deepseek.com" },
  openai_compatible: { model: "自定义模型", baseUrl: "https://你的兼容接口/v1" },
};

const EVALUATION_METRICS = {
  "问题要素覆盖率": {
    label: "问题要素覆盖率",
    definition: "根据问题文本与模型结构化结果核对疾病、基因、结局和数据域；不是 Gold Set 准确率。",
    format: "percent",
  },
  "结构化完整率": {
    label: "结构化完整率",
    definition: "科研问题、疾病、结局、数据域和目标字段是否完整返回；反映能否进入后续 Agent 流程。",
    format: "percent",
  },
  "目标字段输出率": {
    label: "目标字段输出率",
    definition: "模型是否返回可供后续数据搜集使用的目标字段列表；不等于字段语义正确率。",
    format: "percent",
  },
  "响应时延_ms": {
    label: "响应时延（相对柱高）",
    definition: "真实 API 调用耗时，表格显示毫秒值；柱高只表示相对量级，不能当作质量分。",
    format: "latency",
  },
  "输出字段数量": {
    label: "输出字段数量（相对柱高）",
    definition: "结构化结果实际返回的字段数量，只是输出规模观察，不代表回答质量。",
    format: "count",
  },
};

const state = {
  report: null,
  modelSessions: {},
  modelConfigs: [
    { targetId: "qwen-qwen-plus", provider: "qwen", model: "qwen-plus", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", apiKey: "", sessionId: null, status: "未连接" },
    { targetId: "qwen-qwen-max", provider: "qwen", model: "qwen-max", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", apiKey: "", sessionId: null, status: "未连接" },
    { targetId: "qwen-qwen-turbo", provider: "qwen", model: "qwen-turbo", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", apiKey: "", sessionId: null, status: "未连接" },
    { targetId: "deepseek-deepseek-chat", provider: "deepseek", model: "deepseek-chat", baseUrl: "https://api.deepseek.com", apiKey: "", sessionId: null, status: "未连接" },
    { targetId: "deepseek-deepseek-reasoner", provider: "deepseek", model: "deepseek-reasoner", baseUrl: "https://api.deepseek.com", apiKey: "", sessionId: null, status: "未连接" },
  ],
};

const statusClass = (status) => {
  if (["完成", "已完成", "PASS", "通过", "已连接"].includes(status)) return "is-success";
  if (["失败", "FAIL", "REJECT", "连接失败"].includes(status)) return "is-error";
  return "is-review";
};

const metricValueText = (key, value) => {
  if (value == null || value === "") return "未测";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  if (EVALUATION_METRICS[key]?.format === "percent") return `${(number * 100).toFixed(1)}%`;
  if (key === "响应时延_ms") return `${number.toFixed(1)} ms`;
  return number.toFixed(1);
};

async function readJson(response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof body.detail === "string"
      ? body.detail
      : body.detail?.message || `请求失败（HTTP ${response.status}）`;
    throw new Error(message);
  }
  return body;
}

function modelConfigTargetId(provider, model) {
  return `${provider}-${String(model).trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-")}`;
}

function showToast(message) {
  const toast = document.querySelector("#toast");
  if (!toast) return;
  toast.textContent = message;
  toast.hidden = false;
  window.setTimeout(() => { toast.hidden = true; }, 2600);
}

function renderApiCheckResult(result) {
  const container = document.querySelector("#api-check-result");
  if (!container) return;
  const facts = [
    ["网络可达", result.reachable ? "是" : "否"],
    ["鉴权成功", result.authenticated ? "是" : "否"],
    ["模型可用", result.model_available ? "是" : "否"],
    ["函数调用", result.function_calling_available ? "已支持" : "未确认"],
    ["Agent 探测", result.agent_ready ? "通过" : "未通过/未执行"],
    ["状态", result.status],
  ];
  container.innerHTML = facts.map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong class="${statusClass(result.status)}">${escapeHtml(value)}</strong></article>`).join("")
    + `<p>${escapeHtml(result.message)} · ${escapeHtml(result.model)}</p>`;
}

async function checkApiAgent() {
  const button = document.querySelector("#api-check-submit");
  const input = document.querySelector("#api-check-key");
  if (!button || !input) return;
  if (!input.value.trim()) {
    renderApiCheckResult({
      status: "连接失败",
      message: "请输入新的临时 Key。",
      model: "—",
      reachable: false,
      authenticated: false,
      model_available: false,
      function_calling_available: false,
      agent_ready: false,
    });
    return;
  }
  button.disabled = true;
  try {
    const result = await readJson(await fetch("/api/agent/api-check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: document.querySelector("#api-check-provider").value,
        api_key: input.value,
        base_url: document.querySelector("#api-check-base-url").value,
        model: document.querySelector("#api-check-model").value || "qwen-plus",
        run_agent_probe: document.querySelector("#api-check-agent-probe").checked,
      }),
    }));
    renderApiCheckResult(result);
  } catch (error) {
    renderApiCheckResult({
      status: "连接失败",
      message: error.message,
      model: "—",
      reachable: false,
      authenticated: false,
      model_available: false,
      function_calling_available: false,
      agent_ready: false,
    });
  } finally {
    input.value = "";
    button.disabled = false;
  }
}

function renderModelConfigList() {
  const container = document.querySelector("#evaluation-model-configs");
  if (!container) return;
  container.innerHTML = state.modelConfigs.map((config, index) => {
    const connected = Boolean(config.sessionId);
    return `<article class="model-config-row" data-model-index="${index}">
      <div class="model-config-fields">
        <label>提供商
          <select data-model-field="provider">
            ${Object.entries(MODEL_PROVIDER_LABELS).map(([value, label]) => `<option value="${value}" ${config.provider === value ? "selected" : ""}>${label}</option>`).join("")}
          </select>
        </label>
        <label>模型名称
          <input data-model-field="model" type="text" value="${escapeHtml(config.model)}" />
        </label>
        <label class="model-config-wide">接口地址
          <input data-model-field="baseUrl" type="url" value="${escapeHtml(config.baseUrl)}" />
        </label>
        <label class="model-config-wide">临时 API Key
          <input data-model-field="apiKey" type="password" autocomplete="new-password" placeholder="${connected ? "已清空，仅保留内存会话" : "连接前输入临时 Key"}" value="${escapeHtml(config.apiKey)}" />
        </label>
      </div>
      <div class="model-config-actions">
        <span class="model-config-status ${connected ? "is-success" : "is-review"}">${connected ? "已连接" : escapeHtml(config.status || "未连接")}</span>
        <button class="button button-primary model-connect-button" type="button">${connected ? "重新连接" : "连接并加入"}</button>
        <button class="button button-secondary model-remove-button" type="button" ${state.modelConfigs.length <= 1 ? "disabled" : ""}>删除</button>
      </div>
    </article>`;
  }).join("");
}

function updateModelConfigFromField(row, field, value) {
  const config = state.modelConfigs[Number(row.dataset.modelIndex)];
  if (!config) return;
  config[field] = value;
  if (field === "provider") {
    const defaults = MODEL_PROVIDER_DEFAULTS[value];
    config.model = defaults.model;
    config.baseUrl = defaults.baseUrl;
    config.targetId = modelConfigTargetId(value, config.model);
    config.sessionId = null;
    config.status = "未连接";
    renderModelConfigList();
  } else if (field === "model") {
    config.targetId = modelConfigTargetId(config.provider, value);
  }
}

async function connectEvaluationModel(row) {
  const config = state.modelConfigs[Number(row.dataset.modelIndex)];
  const button = row.querySelector(".model-connect-button");
  const status = row.querySelector(".model-config-status");
  if (!config || !button || !status) return;
  if (!config.apiKey.trim()) {
    status.textContent = "请输入临时 Key";
    status.className = "model-config-status is-error";
    return;
  }
  button.disabled = true;
  status.textContent = "验证中";
  try {
    const session = await readJson(await fetch("/api/agent/qwen-sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: config.provider,
        api_key: config.apiKey,
        base_url: config.baseUrl,
        model: config.model,
        timeout_seconds: 120,
      }),
    }));
    config.targetId = modelConfigTargetId(config.provider, config.model);
    config.sessionId = session.session_id;
    config.status = "已连接";
    config.apiKey = "";
    state.modelSessions[config.targetId] = {
      sessionId: session.session_id,
      provider: config.provider,
      modelId: config.model,
      modelLabel: `${MODEL_PROVIDER_LABELS[config.provider]} ${config.model}`,
    };
    renderModelConfigList();
    renderReport(state.report);
    showToast(`${session.provider} / ${session.model} 已加入模型评价`);
  } catch (error) {
    config.status = error.message;
    status.textContent = error.message;
    status.className = "model-config-status is-error";
  } finally {
    button.disabled = false;
  }
}

async function removeEvaluationModel(index) {
  const config = state.modelConfigs[index];
  if (!config) return;
  if (config.sessionId) {
    await fetch(`/api/agent/qwen-sessions/${encodeURIComponent(config.sessionId)}`, { method: "DELETE" }).catch(() => null);
    delete state.modelSessions[config.targetId];
  }
  state.modelConfigs.splice(index, 1);
  renderModelConfigList();
  renderReport(state.report);
}

function aggregateRows(report) {
  const grouped = new Map();
  (report?.model_rows || []).forEach((row) => {
    const current = grouped.get(row.target_id) || {
      targetId: row.target_id,
      provider: row.provider,
      modelId: row.model_id,
      label: row.model_label,
      rows: [],
    };
    current.rows.push(row);
    grouped.set(row.target_id, current);
  });
  return [...grouped.values()].map((group) => {
    const aggregate = {};
    Object.keys(EVALUATION_METRICS).forEach((key) => {
      const values = group.rows
        .map((row) => row.metrics?.[key])
        .filter((value) => typeof value === "number" && Number.isFinite(value));
      aggregate[key] = values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
    });
    return {
      ...group,
      aggregate,
      measured: group.rows.filter((row) => row.status === "已完成").length,
      total: group.rows.length,
      status: group.rows.some((row) => row.status === "已完成") ? "已观测" : group.rows.some((row) => row.status === "失败") ? "失败" : "待运行",
    };
  });
}

function renderEvaluationChart(aggregates) {
  const container = document.querySelector("#model-evaluation-chart");
  const selector = document.querySelector("#evaluation-chart-metric");
  const definition = document.querySelector("#evaluation-metric-definition");
  if (!container || !selector || !definition) return;
  const key = selector.value;
  const metric = EVALUATION_METRICS[key];
  definition.textContent = metric.definition;
  const values = aggregates.map((item) => ({ item, raw: item.aggregate[key] }));
  const numeric = values.map(({ raw }) => raw).filter((raw) => typeof raw === "number" && Number.isFinite(raw));
  if (numeric.length < 2) {
    const measuredModels = numeric.length;
    const current = measuredModels === 1
      ? `当前只有 1 个模型完成真实测试（${metricValueText(key, numeric[0])}）。`
      : "当前还没有模型完成真实测试。";
    container.classList.remove("is-bar-chart");
    container.innerHTML = `<div class="comparison-not-ready"><strong>暂不构成横向对比</strong><p>${current} 至少需要 2 个模型使用同一批问题完成测试后，才绘制柱状图和差异结论。未连接、失败和未运行模型不参与比较。</p></div>`;
    return;
  }
  const max = Math.max(...numeric, 1);
  const isPercent = metric.format === "percent";
  const distinct = [...new Set(numeric.map((value) => value.toFixed(4)))].length;
  const bars = values.map(({ item, raw }) => {
    const pending = raw == null;
    const height = pending ? 0 : (isPercent ? raw * 100 : raw / max * 100);
    const display = pending ? "未测" : metricValueText(key, raw);
    return `<article class="model-evaluation-bar${pending ? " is-pending" : ""}">
      <strong>${escapeHtml(display)}</strong>
      <div class="model-evaluation-bar-track"><i style="height:${height.toFixed(1)}%"></i></div>
      <strong>${escapeHtml(item.label)}</strong>
      <span>${escapeHtml(item.measured)}/${escapeHtml(item.total)} 题</span>
    </article>`;
  }).join("");
  const axis = isPercent
    ? "<span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span>"
    : `<span>0</span><span>相对柱高</span><span>${escapeHtml(metric.format === "latency" ? "ms" : "数量")}</span>`;
  const note = numeric.length === 0
    ? "当前没有真实观测值；未连接、未运行和失败模型不参与图表。"
    : distinct === 1
      ? "当前指标在已测样本中没有形成差异；这不代表模型能力相同，需增加问题、统一 Gold Set 或更换指标。"
      : "柱高来自真实观测值；未测项保持空白，不填 100%。";
  container.innerHTML = bars
    ? `<div class="model-evaluation-bars">${bars}</div><div class="model-evaluation-axis">${axis}</div><p class="evaluation-chart-note">${escapeHtml(note)}</p>`
    : '<p class="muted-visual">暂无模型对比结果。</p>';
}

function renderAggregateTable(aggregates) {
  const table = document.querySelector("#model-evaluation-aggregate-table");
  if (!table) return;
  const metricKeys = ["结构化完整率", "问题要素覆盖率", "目标字段输出率", "响应时延_ms", "输出字段数量"];
  table.querySelector("thead").innerHTML = `<tr><th>模型</th><th>已测题数</th>${metricKeys.map((key) => `<th>${escapeHtml(EVALUATION_METRICS[key].label)}</th>`).join("")}<th>状态</th></tr>`;
  table.querySelector("tbody").innerHTML = aggregates.length
    ? aggregates.map((item) => `<tr>
      <td><strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.provider)} / ${escapeHtml(item.modelId)}</small></td>
      <td>${escapeHtml(item.measured)}/${escapeHtml(item.total)}</td>
      ${metricKeys.map((key) => `<td>${escapeHtml(metricValueText(key, item.aggregate[key]))}</td>`).join("")}
      <td><span class="status-badge ${statusClass(item.status)}">${escapeHtml(item.status)}</span></td>
    </tr>`).join("")
    : '<tr><td colspan="8" class="muted-cell">尚未生成模型评价报告。</td></tr>';
}

function renderSummaryCards(aggregates) {
  const container = document.querySelector("#evaluation-model-summary-cards");
  if (!container) return;
  const measured = aggregates.reduce((sum, item) => sum + item.measured, 0);
  const total = aggregates.reduce((sum, item) => sum + item.total, 0);
  const connected = aggregates.filter((item) => item.measured > 0).length;
  const comparisonReady = connected >= 2 ? "已具备" : "需至少 2 个模型";
  container.innerHTML = [
    ["模型目标", aggregates.length],
    ["真实观测行", `${measured}/${total}`],
    ["横向对比资格", comparisonReady],
    ["正式总分", "未评测"],
  ].map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`).join("");
  document.querySelector("#evaluation-measured-rows").textContent = String(measured);
  document.querySelector("#evaluation-connected-models").textContent = String(connected);
}

function renderReport(report) {
  state.report = report;
  const status = document.querySelector("#model-evaluation-status");
  const summary = document.querySelector("#model-evaluation-summary");
  const reportId = document.querySelector("#model-evaluation-report-id");
  const runButton = document.querySelector("#evaluation-run");
  const exportButton = document.querySelector("#evaluation-export");
  const tableBody = document.querySelector("#model-evaluation-table tbody");
  if (!status || !summary || !reportId || !runButton || !exportButton || !tableBody) return;
  if (!report) {
    status.textContent = "待运行";
    status.className = "status-badge is-review";
    summary.textContent = "生成报告后，这里显示逐模型的真实观测结果。";
    reportId.textContent = "—";
    runButton.disabled = true;
    exportButton.disabled = true;
    return;
  }
  const questions = new Map((report.questions || []).map((item) => [item.question_id, item.question]));
  const aggregates = aggregateRows(report);
  const measuredRows = (report.model_rows || []).filter((row) => row.status === "已完成").length;
  status.textContent = report.status;
  status.className = `status-badge ${statusClass(report.status)}`;
  summary.textContent = `${report.summary_zh} 当前只展示结构化输出、字段覆盖和时延等可观察指标；正式综合成绩：未评测。`;
  reportId.textContent = report.report_id;
  document.querySelector("#evaluation-report-state").textContent = report.status;
  runButton.disabled = !Object.keys(state.modelSessions).length;
  exportButton.disabled = false;
  tableBody.innerHTML = (report.model_rows || []).map((row) => {
    const metrics = Object.entries(row.metrics || {}).map(([key, value]) => `${escapeHtml(EVALUATION_METRICS[key]?.label || key)}=${escapeHtml(metricValueText(key, value))}`).join("；") || "未测";
    return `<tr><td><strong>${escapeHtml(row.question_id)}</strong><small>${escapeHtml(questions.get(row.question_id) || "—")}</small></td>
      <td>${escapeHtml(MODEL_PROVIDER_LABELS[row.provider] || row.provider)}</td>
      <td>${escapeHtml(row.model_label)}<small>${escapeHtml(row.model_id)}</small></td>
      <td><span class="status-badge ${statusClass(row.status)}">${escapeHtml(row.status)}</span></td>
      <td>${escapeHtml(metrics)}</td>
      <td><span class="status-badge ${statusClass(row.quality_gate)}">${escapeHtml(row.quality_gate === "REVIEW" ? "待复核" : row.quality_gate)}</span></td>
      <td>${escapeHtml(row.note)}</td></tr>`;
  }).join("") || '<tr><td colspan="7" class="muted-cell">暂无测试行。</td></tr>';
  renderSummaryCards(aggregates);
  renderAggregateTable(aggregates);
  renderEvaluationChart(aggregates);
  if (!measuredRows) {
    document.querySelector("#evaluation-workbench-message").textContent = "当前报告还没有真实观测值；请连接模型后运行测试。";
  }
}

async function generateModelEvaluationPlan() {
  const button = document.querySelector("#evaluation-generate");
  const message = document.querySelector("#evaluation-workbench-message");
  button.disabled = true;
  try {
    const qwenSessionId = state.modelSessions["qwen-qwen-plus"]?.sessionId || null;
    const targets = state.modelConfigs.map((config) => ({
      target_id: config.targetId || modelConfigTargetId(config.provider, config.model),
      provider: config.provider,
      model_id: config.model,
      model_label: `${MODEL_PROVIDER_LABELS[config.provider]} ${config.model}`,
    }));
    const report = await readJson(await fetch("/api/evaluation/model-tests/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question_count: Number(document.querySelector("#evaluation-question-count").value),
        seed_question: document.querySelector("#evaluation-seed-question").value,
        targets,
        run_mode: qwenSessionId ? "live" : "dry_run",
        ...(qwenSessionId ? { qwen_session_id: qwenSessionId } : {}),
      }),
    }));
    renderReport(report);
    message.textContent = qwenSessionId
      ? "已用千问生成测试问题；请运行已连接模型。"
      : "已生成规则测试问题；当前没有模型能力成绩。";
  } catch (error) {
    message.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function runModelEvaluation() {
  const button = document.querySelector("#evaluation-run");
  const message = document.querySelector("#evaluation-workbench-message");
  if (!state.report || !Object.keys(state.modelSessions).length) {
    message.textContent = "请先生成测试问题并连接至少一个模型。";
    return;
  }
  button.disabled = true;
  try {
    const sessionIds = Object.fromEntries(
      Object.entries(state.modelSessions).map(([targetId, session]) => [targetId, session.sessionId]),
    );
    const updated = await readJson(await fetch("/api/evaluation/model-tests/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ report_id: state.report.report_id, session_ids: sessionIds }),
    }));
    renderReport(updated);
    message.textContent = updated.summary_zh;
  } catch (error) {
    message.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function exportModelEvaluationReport() {
  if (!state.report) return;
  const response = await fetch(`/api/evaluation/model-tests/${encodeURIComponent(state.report.report_id)}/export/xlsx`);
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "对比报告导出失败。");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${state.report.report_id}-多模型对比报告.xlsx`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

async function checkHealth() {
  const system = document.querySelector("#evaluation-system-status");
  try {
    const health = await readJson(await fetch("/health"));
    system.className = "system-status is-online";
    system.innerHTML = `<span class="status-dot"></span><span>在线 · ${escapeHtml(health.version)}</span>`;
  } catch (error) {
    system.className = "system-status is-error";
    system.innerHTML = `<span class="status-dot"></span><span>后端未连接</span>`;
  }
}

document.querySelector("#api-check-submit")?.addEventListener("click", checkApiAgent);
document.querySelector("#api-check-provider")?.addEventListener("change", (event) => {
  const defaults = MODEL_PROVIDER_DEFAULTS[event.target.value];
  document.querySelector("#api-check-model").value = defaults.model;
  document.querySelector("#api-check-base-url").value = defaults.baseUrl;
});
document.querySelector("#evaluation-generate")?.addEventListener("click", generateModelEvaluationPlan);
document.querySelector("#evaluation-run")?.addEventListener("click", runModelEvaluation);
document.querySelector("#evaluation-export")?.addEventListener("click", () => exportModelEvaluationReport().catch((error) => {
  document.querySelector("#evaluation-workbench-message").textContent = error.message;
}));
document.querySelector("#evaluation-chart-metric")?.addEventListener("change", () => {
  renderEvaluationChart(aggregateRows(state.report));
});
document.querySelector("#evaluation-add-model")?.addEventListener("click", () => {
  state.modelConfigs.push({
    targetId: `custom-${Date.now()}`,
    provider: "openai_compatible",
    model: "自定义模型",
    baseUrl: "https://你的兼容接口/v1",
    apiKey: "",
    sessionId: null,
    status: "未连接",
  });
  renderModelConfigList();
});
document.querySelector("#evaluation-model-configs")?.addEventListener("input", (event) => {
  const row = event.target.closest("[data-model-index]");
  const field = event.target.dataset.modelField;
  if (row && field) updateModelConfigFromField(row, field, event.target.value);
});
document.querySelector("#evaluation-model-configs")?.addEventListener("change", (event) => {
  const row = event.target.closest("[data-model-index]");
  const field = event.target.dataset.modelField;
  if (row && field) updateModelConfigFromField(row, field, event.target.value);
});
document.querySelector("#evaluation-model-configs")?.addEventListener("click", (event) => {
  const row = event.target.closest("[data-model-index]");
  if (!row) return;
  const index = Number(row.dataset.modelIndex);
  if (event.target.closest(".model-connect-button")) connectEvaluationModel(row);
  if (event.target.closest(".model-remove-button")) removeEvaluationModel(index);
});

checkHealth();
renderModelConfigList();
renderReport(null);
