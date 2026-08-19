const form = document.querySelector("#research-form");
const submitButton = document.querySelector("#submit-button");
const progressPanel = document.querySelector("#progress");
const progressBar = document.querySelector("#progress-bar");
const progressPercent = document.querySelector("#progress-percent");
const progressLabel = document.querySelector("#progress-label");
const errorPanel = document.querySelector("#error-panel");
const resultsPanel = document.querySelector("#results");
const downloadStatus = document.querySelector("#download-status");

const state = {
  result: null,
  progressTimer: null,
  datasetView: "research",
  qwenSessionId: null,
  qwenSessionExpiresAt: null,
  lineage: { sources: [], candidates: [], primary: "", selected: null, hover: null, view: "all", paused: false },
};

const escapeHtml = (value) => String(value ?? "—")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const TERM_TRANSLATIONS = {
  "Breast Cancer": "乳腺癌",
  "Breast Carcinoma": "乳腺癌",
  "breast cancer": "乳腺癌",
  "breast carcinoma": "乳腺癌",
  "HER2-positive": "HER2 阳性",
  "HER2-positive breast carcinoma": "HER2 阳性乳腺癌",
  "HER2-positive breast cancer": "HER2 阳性乳腺癌",
  trastuzumab: "曲妥珠单抗",
  Trastuzumab: "曲妥珠单抗",
  pertuzumab: "帕妥珠单抗",
  Pertuzumab: "帕妥珠单抗",
  docetaxel: "多西他赛",
  paclitaxel: "紫杉醇",
  carboplatin: "卡铂",
  epirubicin: "表柔比星",
  cyclophosphamide: "环磷酰胺",
  pathological_complete_response: "病理完全缓解（pCR）",
  "pathological complete response (pCR)": "病理完全缓解（pCR）",
  "pathological complete response": "病理完全缓解（pCR）",
  residual_cancer_burden: "残余肿瘤负荷（RCB）",
  "residual cancer burden (RCB)": "残余肿瘤负荷（RCB）",
  "residual cancer burden": "残余肿瘤负荷（RCB）",
  "neoadjuvant treatment response (binary or categorical)": "新辅助治疗响应（二分类或多分类）",
  "tumor downstaging": "肿瘤降期",
  clinical_response_rate: "临床缓解率",
  "clinical response rate": "临床缓解率",
  "radiological response (RECIST)": "影像学疗效（RECIST）",
  treatment_response: "治疗响应",
  survival: "生存结局",
  clinical: "临床资料",
  mutation: "基因突变",
  expression: "基因表达",
  evidence: "医学证据",
  clinical_trial: "临床试验",
};

const VALUE_TRANSLATIONS = {
  MASTECTOMY: "乳房切除术",
  "BREAST CONSERVING": "保乳手术",
  "Breast Invasive Ductal Carcinoma": "浸润性导管癌",
  "Breast Mixed Ductal and Lobular Carcinoma": "混合性导管-小叶癌",
  "Breast Invasive Lobular Carcinoma": "浸润性小叶癌",
  High: "高",
  Moderate: "中",
  Low: "低",
  YES: "是",
  NO: "否",
  Positive: "阳性",
  Positve: "阳性",
  Pos: "阳性",
  Negative: "阴性",
  Neg: "阴性",
  Equivocal: "临界/不确定",
  Unknown: "未知",
  NEUTRAL: "拷贝数中性",
  Right: "右侧",
  Left: "左侧",
  Post: "绝经后",
  Pre: "绝经前",
  Primary: "原发肿瘤",
  Female: "女性",
  Male: "男性",
  Living: "生存",
  "Died of Disease": "因病死亡",
  "0:LIVING": "生存",
  "1:DECEASED": "死亡",
  "0:Not Recurred": "未复发",
  "1:Recurred": "复发",
  "Ductal/NST": "导管型/非特殊型",
  Mixed: "混合型",
  IDC: "浸润性导管癌",
  ILC: "浸润性小叶癌",
  MDLC: "混合性导管-小叶癌",
  LumA: "管腔 A 型",
  LumB: "管腔 B 型",
  "claudin-low": "低 Claudin 型",
  GAIN: "拷贝数增加",
  LOSS: "拷贝数缺失",
  AMPLIFICATION: "拷贝数扩增",
  "ER-/HER2-": "ER 阴性 / HER2 阴性",
  "ER+/HER2- High Prolif": "ER 阳性 / HER2 阴性（高增殖）",
  "ER+/HER2- Low Prolif": "ER 阳性 / HER2 阴性（低增殖）",
  "HER2+": "HER2 阳性",
  baseline: "基线",
  post: "治疗后",
  pCR: "病理完全缓解（pCR）",
  OBJR: "客观缓解",
  NOR: "未达客观缓解",
  "HER2+ Breast Cancer": "HER2 阳性乳腺癌",
  "<缺失>": "缺失",
};

const TYPE_TRANSLATIONS = { string: "文本", number: "数值", boolean: "布尔值" };
const SOURCE_STATUS_TRANSLATIONS = { cached: "缓存命中", discovered: "已发现", downloaded: "已下载", fetched: "已获取", failed: "失败" };
const ARGUMENT_LABELS = {
  study_id: "研究编号", gene_symbols: "基因", max_records: "最大记录数",
  project_id: "项目编号", data_types: "数据类型", max_files: "最大文件数",
  accession: "数据编号", condition: "疾病", query_terms: "检索词",
  max_trials: "最大试验数", disease_name: "疾病", molecular_profile_name: "分子特征",
  therapy_name: "治疗方案", max_items: "最大条目数",
};

const translateTerm = (value) => TERM_TRANSLATIONS[String(value)] || String(value ?? "—");
const listText = (values) => values?.length ? values.map(translateTerm).join("、") : "未指定";
const statusClass = (status) => ["完成", "可支持科研分析", "达标", "已覆盖", "已记录", "已计算"].includes(status) ? "is-success" : status === "失败" || status === "部分失败" ? "is-error" : "is-review";
const canonicalDatabaseName = (value) => {
  const text = String(value || "");
  const lower = text.toLowerCase();
  if (lower.includes("cbio")) return "cBioPortal";
  if (lower.includes("geo")) return "NCBI GEO";
  if (lower.includes("gdc")) return "GDC";
  if (lower.includes("civic")) return "CIViC";
  if (lower.includes("clinicaltrials") || lower.includes("aact")) return "ClinicalTrials.gov";
  return text;
};

function localizeNarrative(value) {
  let text = String(value ?? "—");
  const replacements = {
    "科研建模数据集": "科研数据集",
    "患者级建模数据集": "患者级科研数据集",
    "建模数据": "科研数据",
    "直接建模要求": "直接科研分析要求",
    "建模要求": "科研分析要求",
    "可建模性": "可科研性",
    "结果标签": "研究结局字段",
    "标签缺失率": "结局缺失率",
    "1:DECEASED": "死亡",
    "0:LIVING": "生存",
    "HER2-positive breast carcinoma": "HER2 阳性乳腺癌",
    "Breast Invasive Ductal Carcinoma": "浸润性导管癌",
    "Breast Mixed Ductal and Lobular Carcinoma": "混合性导管-小叶癌",
    "Breast Invasive Lobular Carcinoma": "浸润性小叶癌",
    "Breast Carcinoma": "乳腺癌",
    "Breast Cancer": "乳腺癌",
    pathological_complete_response: "病理完全缓解（pCR）",
    residual_cancer_burden: "残余肿瘤负荷（RCB）",
    clinical_response_rate: "临床缓解率",
    treatment_response: "治疗响应",
    trastuzumab: "曲妥珠单抗",
    pertuzumab: "帕妥珠单抗",
    docetaxel: "多西他赛",
    paclitaxel: "紫杉醇",
    carboplatin: "卡铂",
    epirubicin: "表柔比星",
    cyclophosphamide: "环磷酰胺",
    "HER2-positive breast cancer": "HER2 阳性乳腺癌",
    "breast carcinoma": "乳腺癌",
    "pathological complete response (pCR)": "病理完全缓解（pCR）",
    "pathological complete response": "病理完全缓解（pCR）",
    "residual cancer burden (RCB)": "残余肿瘤负荷（RCB）",
    "residual cancer burden": "残余肿瘤负荷（RCB）",
    "clinical response rate": "临床缓解率",
    "radiological response (RECIST)": "影像学疗效（RECIST）",
    "neoadjuvant treatment response (binary or categorical)": "新辅助治疗响应（二分类或多分类）",
    "tumor downstaging": "肿瘤降期",
    "OS status": "总生存状态",
    "OS 状态": "总生存状态",
    neoadjuvant_regimen: "新辅助治疗方案（neoadjuvant_regimen）",
    treatment_duration: "治疗持续时间（treatment_duration）",
    surgical_pathology_report_date: "术后病理报告日期（surgical_pathology_report_date）",
    PIK3CA_variant_annotation: "PIK3CA 变异注释（PIK3CA_variant_annotation）",
    PIK3CA_variant_allele_frequency: "PIK3CA 变异等位基因频率（PIK3CA_variant_allele_frequency）",
    RCB_score: "残余肿瘤负荷评分（RCB_score）",
    os_status: "总生存状态（os_status）",
    dfs_status: "无病生存状态（dfs_status）",
    pik3ca_mutation: "PIK3CA 突变状态（pik3ca_mutation）",
    pik3ca_variants: "PIK3CA 蛋白变异（pik3ca_variants）",
    her2_status: "HER2 状态（her2_status）",
    er_status: "ER 状态（er_status）",
    pr_status: "PR 状态（pr_status）",
  };
  Object.entries(replacements).forEach(([source, target]) => { text = text.replaceAll(source, target); });
  text = text
    .replaceAll("总生存状态（总生存状态（os_status））", "总生存状态（os_status）")
    .replaceAll("无病生存状态（无病生存状态（dfs_status））", "无病生存状态（dfs_status）")
    .replaceAll("PIK3CA 突变状态（PIK3CA 突变状态（pik3ca_mutation））", "PIK3CA 突变状态（pik3ca_mutation）")
    .replaceAll("PIK3CA 突变状态（PIK3CA 突变状态（pik3ca_mutation） 字段）", "PIK3CA 突变状态字段（pik3ca_mutation）")
    .replaceAll("PIK3CA 蛋白变异（PIK3CA 蛋白变异（pik3ca_variants））", "PIK3CA 蛋白变异（pik3ca_variants）")
    .replaceAll("HER2 状态（HER2 状态（her2_status））", "HER2 状态（her2_status）")
    .replaceAll("ER 状态（ER 状态（er_status））", "ER 状态（er_status）")
    .replaceAll("PR 状态（PR 状态（pr_status））", "PR 状态（pr_status）");
  return text;
}

function translateValue(value) {
  if (value == null || value === "") return "—";
  if (Array.isArray(value)) return value.map(translateValue).join("、");
  if (typeof value !== "string") return value;
  return VALUE_TRANSLATIONS[value] || TERM_TRANSLATIONS[value] || value;
}

function fieldLabel(dataset, name) {
  if (!name) return "未识别";
  const column = dataset.columns.find((item) => item.name === name);
  return column ? `${column.label_zh}（${name}）` : name;
}

function renderArguments(argumentsObject) {
  return Object.entries(argumentsObject || {}).map(([key, value]) => {
    const rendered = Array.isArray(value) ? value.map(translateTerm).join("、") : translateTerm(value);
    return `<span class="argument-item"><strong>${escapeHtml(ARGUMENT_LABELS[key] || key)}</strong>${escapeHtml(rendered)}</span>`;
  }).join("");
}

async function readJson(response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = typeof body.detail === "string" ? body.detail : body.detail?.message || `请求失败（HTTP ${response.status}）`;
    throw new Error(message);
  }
  return body;
}

async function checkConfiguration() {
  const system = document.querySelector("#system-status");
  try {
    const [health, configuration] = await Promise.all([
      fetch("/health").then(readJson),
      fetch("/api/agent/configuration").then(readJson),
    ]);
    system.className = "system-status is-online";
    system.innerHTML = `<span class="status-dot"></span><span>在线 · ${escapeHtml(health.version)}</span>`;
    const badge = document.querySelector("#configuration-badge");
    badge.textContent = configuration.configured ? "千问已连接" : "千问未配置";
    badge.className = `status-badge ${configuration.configured ? "is-success" : "is-review"}`;
    document.querySelector("#configuration-title").textContent = configuration.configured ? "千问智能体可以运行" : "当前将使用确定性兜底";
    document.querySelector("#configuration-message").textContent = configuration.message;
    document.querySelector("#configuration-model").textContent = configuration.model;
  } catch (error) {
    system.className = "system-status is-error";
    system.innerHTML = '<span class="status-dot"></span><span>后端未连接</span>';
    document.querySelector("#configuration-title").textContent = "无法读取智能体配置";
    document.querySelector("#configuration-message").textContent = error.message;
  }
}

function setProgress(percent, label) {
  progressPanel.hidden = false;
  progressBar.style.width = `${percent}%`;
  progressPercent.textContent = `${percent}%`;
  progressLabel.textContent = label;
}

function startProgress() {
  const phases = [
    [18, "千问正在解析疾病、基因、药物和结局…"],
    [32, "千问正在通过函数调用选择真实数据工具…"],
    [48, "正在访问 GDC、GEO 或 cBioPortal 官方接口…"],
    [63, "正在把临床、突变和拷贝数记录整理成宽表…"],
    [76, "正在识别研究变量、研究结局与重复患者…"],
    [86, "正在生成中文字段字典和可科研性报告…"],
  ];
  let index = 0;
  setProgress(8, "正在创建科研数据任务…");
  state.progressTimer = window.setInterval(() => {
    if (index < phases.length) {
      setProgress(phases[index][0], phases[index][1]);
      index += 1;
    }
  }, 2600);
}

function stopProgress(success = true) {
  if (state.progressTimer) window.clearInterval(state.progressTimer);
  state.progressTimer = null;
  if (success) setProgress(100, "科研数据任务已完成，可以检查和下载结果。");
}

function buildAgentTaskPayload() {
  const payload = {
    question: document.querySelector("#question").value,
    use_qwen: document.querySelector("#use-qwen").checked,
    allow_deterministic_fallback: document.querySelector("#allow-fallback").checked,
    data_mode: document.querySelector("#data-mode").value,
    preferred_sources: [],
    max_sources: Number(document.querySelector("#max-sources").value),
    max_records: Number(document.querySelector("#max-records").value),
  };
  if (state.qwenSessionId) payload.qwen_session_id = state.qwenSessionId;
  return payload;
}

function parseCsvRows(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (character === '"') {
      if (quoted && text[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (character === "," && !quoted) {
      row.push(cell.trim());
      cell = "";
    } else if ((character === "\n" || character === "\r") && !quoted) {
      if (character === "\r" && text[index + 1] === "\n") index += 1;
      row.push(cell.trim());
      if (row.some(Boolean)) rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += character;
    }
  }
  row.push(cell.trim());
  if (row.some(Boolean)) rows.push(row);
  return rows;
}

function importQwenCredentialCsv(text) {
  const rows = parseCsvRows(text);
  if (rows.length < 2) throw new Error("凭据 CSV 为空或格式不正确。");
  const headers = rows[0].map((item) => item.replace(/^\uFEFF/, ""));
  const idIndex = headers.findIndex((item) => item === "id");
  const valueIndexes = headers.map((_, index) => index).filter((index) => index !== idIndex);
  if (idIndex < 0 || !valueIndexes.length) throw new Error("凭据 CSV 需要包含 id 列和一个值列。");
  const mapping = {};
  rows.slice(1).forEach((values) => {
    const key = values[idIndex];
    const value = valueIndexes.map((index) => values[index]).find(Boolean);
    if (key && value) mapping[key] = value;
  });
  if (!mapping.apiKey || !mapping.openAiCompatible) throw new Error("CSV 中缺少 apiKey 或 openAiCompatible。");
  document.querySelector("#qwen-api-key").value = mapping.apiKey;
  document.querySelector("#qwen-base-url").value = mapping.openAiCompatible;
  document.querySelector("#qwen-workspace-id").value = mapping.workspaceId || "";
  document.querySelector("#qwen-connect-status").textContent = "已从本机 CSV 读取连接字段，尚未发送。";
}

function renderTemporaryQwenConnection(session) {
  state.qwenSessionId = session.session_id;
  state.qwenSessionExpiresAt = session.expires_at;
  const badge = document.querySelector("#configuration-badge");
  badge.textContent = "临时千问已连接";
  badge.className = "status-badge is-success";
  document.querySelector("#configuration-title").textContent = "千问 API 内存会话已启用";
  document.querySelector("#configuration-message").textContent = `连接已验证，将于 ${new Date(session.expires_at).toLocaleString("zh-CN")} 前有效；服务重启会立即清除。`;
  document.querySelector("#configuration-model").textContent = session.model;
  document.querySelector("#qwen-open-config").textContent = "更换千问 API";
  document.querySelector("#qwen-disconnect").hidden = false;
  document.querySelector("#use-qwen").checked = true;
  applyApiPreset(document.querySelector("#api-preset").value);
}

async function connectQwenSession(event) {
  event.preventDefault();
  const button = document.querySelector("#qwen-connect");
  const status = document.querySelector("#qwen-connect-status");
  button.disabled = true;
  status.textContent = "正在验证千问 API，请稍候…";
  try {
    const previousSessionId = state.qwenSessionId;
    const response = await fetch("/api/agent/qwen-sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_key: document.querySelector("#qwen-api-key").value,
        base_url: document.querySelector("#qwen-base-url").value,
        model: document.querySelector("#qwen-model").value,
        workspace_id: document.querySelector("#qwen-workspace-id").value || null,
        timeout_seconds: 120,
      }),
    });
    const session = await readJson(response);
    document.querySelector("#qwen-api-key").value = "";
    document.querySelector("#qwen-credential-file").value = "";
    renderTemporaryQwenConnection(session);
    if (previousSessionId && previousSessionId !== session.session_id) {
      fetch(`/api/agent/qwen-sessions/${encodeURIComponent(previousSessionId)}`, { method: "DELETE" }).catch(() => null);
    }
    status.textContent = session.message;
    document.querySelector("#qwen-connection-dialog").close();
    showToast("千问 API 已连接，本次任务将使用临时会话");
  } catch (error) {
    status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function disconnectQwenSession() {
  const sessionId = state.qwenSessionId;
  state.qwenSessionId = null;
  state.qwenSessionExpiresAt = null;
  if (sessionId) await fetch(`/api/agent/qwen-sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" }).catch(() => null);
  document.querySelector("#qwen-disconnect").hidden = true;
  document.querySelector("#qwen-open-config").textContent = "连接千问 API";
  await checkConfiguration();
  applyApiPreset(document.querySelector("#api-preset").value);
  showToast("临时千问连接已清除");
}

document.querySelector("#qwen-open-config").addEventListener("click", () => document.querySelector("#qwen-connection-dialog").showModal());
document.querySelector("#qwen-dialog-close").addEventListener("click", () => document.querySelector("#qwen-connection-dialog").close());
document.querySelector("#qwen-cancel-config").addEventListener("click", () => document.querySelector("#qwen-connection-dialog").close());
document.querySelector("#qwen-connection-form").addEventListener("submit", connectQwenSession);
document.querySelector("#qwen-disconnect").addEventListener("click", disconnectQwenSession);
document.querySelector("#qwen-credential-file").addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    importQwenCredentialCsv(await file.text());
  } catch (error) {
    document.querySelector("#qwen-connect-status").textContent = error.message;
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  submitButton.disabled = true;
  errorPanel.hidden = true;
  resultsPanel.hidden = true;
  state.result = null;
  startProgress();
  try {
    const response = await fetch("/api/agent/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(buildAgentTaskPayload()),
    });
    const result = await readJson(response);
    state.result = result;
    renderResult(result);
    resultsPanel.hidden = false;
    stopProgress(true);
    resultsPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    stopProgress(false);
    progressPanel.hidden = true;
    errorPanel.textContent = error.message;
    errorPanel.hidden = false;
  } finally {
    submitButton.disabled = false;
  }
});

function renderResult(result) {
  document.querySelector("#result-status").textContent = result.status;
  document.querySelector("#agent-mode").textContent = result.agent_mode;
  document.querySelector("#model-name").textContent = result.used_qwen ? result.model_name : `${result.model_name}（未调用）`;
  document.querySelector("#dataset-size").textContent = `${result.modeling_dataset.row_count} 行 × ${result.modeling_dataset.columns.length} 列`;
  document.querySelector("#task-id").textContent = result.task_id;
  document.querySelector("#agent-summary").textContent = localizeNarrative(result.summary_zh);
  document.querySelector("#agent-notice").textContent = localizeNarrative(result.notice);
  renderSpec(result.research_spec);
  renderPlan(result.plan);
  renderTools(result.tool_calls);
  renderCandidates(result.candidate_sources);
  renderDataset(result.modeling_dataset);
  renderReadiness(result.readiness, result.modeling_dataset, result.source_items, result.candidate_sources);
  renderDictionary(result.modeling_dataset.columns);
  renderSources(result.source_items, result.candidate_sources, result.modeling_dataset);
  renderCompetitionReport(result.competition_report);
  if (document.querySelector("#api-preset").value === "task-result") applyApiPreset("task-result");
}

const API_PRESETS = {
  "create-task": { method: "POST", path: "/api/agent/tasks", body: () => buildAgentTaskPayload() },
  configuration: { method: "GET", path: "/api/agent/configuration" },
  "task-result": { method: "GET", path: () => state.result ? `/api/agent/tasks/${state.result.task_id}` : "/api/agent/tasks/{task_id}" },
  health: { method: "GET", path: "/health" },
};

function applyApiPreset(presetName = document.querySelector("#api-preset").value) {
  const preset = API_PRESETS[presetName];
  const method = preset.method;
  const path = typeof preset.path === "function" ? preset.path() : preset.path;
  const body = typeof preset.body === "function" ? preset.body() : null;
  document.querySelector("#api-method").textContent = method;
  document.querySelector("#api-endpoint").value = path;
  const editor = document.querySelector("#api-request-body");
  editor.disabled = method === "GET";
  editor.value = body ? JSON.stringify(body, null, 2) : "";
}

function validateApiPath(path) {
  if (path === "/health" || path.startsWith("/api/")) return path;
  throw new Error("仅允许调用当前站点的 /health 或 /api/ 接口。");
}

async function sendApiConsoleRequest() {
  const sendButton = document.querySelector("#api-send");
  const status = document.querySelector("#api-response-status");
  const output = document.querySelector("#api-response-output");
  const method = document.querySelector("#api-method").textContent.trim();
  const path = validateApiPath(document.querySelector("#api-endpoint").value.trim());
  if (path.includes("{task_id}")) throw new Error("请先创建科研任务，再读取当前任务结果。");
  const options = { method, headers: { Accept: "application/json" } };
  if (method === "POST") {
    const payload = JSON.parse(document.querySelector("#api-request-body").value || "{}");
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(payload);
  }
  sendButton.disabled = true;
  status.textContent = "请求中";
  status.className = "status-badge is-review";
  output.textContent = "正在等待服务器响应…";
  const startedAt = performance.now();
  try {
    const response = await fetch(path, options);
    const data = await response.json().catch(() => ({ message: "服务器没有返回 JSON。" }));
    const elapsed = Math.round(performance.now() - startedAt);
    output.textContent = JSON.stringify(data, null, 2);
    status.textContent = `HTTP ${response.status} · ${elapsed} ms`;
    status.className = `status-badge ${response.ok ? "is-success" : "is-error"}`;
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `请求失败（HTTP ${response.status}）`);
    if (method === "POST" && path === "/api/agent/tasks" && data.task_id) {
      state.result = data;
      renderResult(data);
      resultsPanel.hidden = false;
    }
  } finally {
    sendButton.disabled = false;
  }
}

function buildCurlCommand() {
  const method = document.querySelector("#api-method").textContent.trim();
  const path = validateApiPath(document.querySelector("#api-endpoint").value.trim());
  let command = `curl -X ${method} '${window.location.origin}${path}' -H 'Accept: application/json'`;
  if (method === "POST") {
    const normalizedBody = JSON.stringify(JSON.parse(document.querySelector("#api-request-body").value || "{}"));
    command += ` -H 'Content-Type: application/json' -d '${normalizedBody.replaceAll("'", "'\\\"'\\\"'")}'`;
  }
  return command;
}

document.querySelector("#api-preset").addEventListener("change", (event) => applyApiPreset(event.target.value));
document.querySelector("#api-load-question").addEventListener("click", () => {
  document.querySelector("#api-preset").value = "create-task";
  applyApiPreset("create-task");
});
document.querySelector("#api-copy-curl").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(buildCurlCommand());
    showToast("cURL 命令已复制");
  } catch (error) {
    document.querySelector("#api-response-output").textContent = error.message;
  }
});
document.querySelector("#api-send").addEventListener("click", async () => {
  try {
    await sendApiConsoleRequest();
  } catch (error) {
    const status = document.querySelector("#api-response-status");
    status.textContent = "请求失败";
    status.className = "status-badge is-error";
    if (document.querySelector("#api-response-output").textContent === "正在等待服务器响应…") document.querySelector("#api-response-output").textContent = error.message;
  }
});

applyApiPreset("create-task");

function renderSpec(spec) {
  const cards = [
    ["疾病 / 亚型", `${translateTerm(spec.disease)} / ${spec.subtype ? translateTerm(spec.subtype) : "未指定"}`],
    ["基因", listText(spec.genes)],
    ["药物", listText(spec.drugs)],
    ["研究结局", listText(spec.outcomes)],
    ["所需数据", listText(spec.required_data_types)],
  ];
  document.querySelector("#spec-grid").innerHTML = cards.map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`).join("");
}

function renderPlan(plan) {
  document.querySelector("#plan-list").innerHTML = plan.map((step, index) => `<article class="plan-step">
    <span>${String(index + 1).padStart(2, "0")}</span>
    <div><strong>${escapeHtml(step.label)}</strong><p>${escapeHtml(localizeNarrative(step.detail))}</p></div>
    <em class="${statusClass(step.status)}">${escapeHtml(step.status)}</em>
  </article>`).join("");
}

function renderTools(tools) {
  document.querySelector("#tool-count").textContent = `${tools.length} 次调用`;
  const body = document.querySelector("#tool-table tbody");
  body.innerHTML = tools.length ? tools.map((tool) => `<tr>
    <td><strong>${escapeHtml(tool.tool_label)}</strong><small>${escapeHtml(tool.tool_name)}</small></td>
    <td><div class="argument-list">${renderArguments(tool.arguments)}</div></td>
    <td><span class="status-badge ${statusClass(tool.status)}">${escapeHtml(tool.status)}</span></td>
    <td>${tool.record_count}</td><td>${tool.source_count}</td><td>${escapeHtml(tool.message)}</td>
  </tr>`).join("") : '<tr><td colspan="6" class="muted-cell">仅规划模式没有执行外部工具。</td></tr>';
}

function renderCandidates(candidates) {
  document.querySelector("#candidate-count").textContent = `${candidates.length} 个候选`;
  document.querySelector("#candidate-empty").hidden = candidates.length > 0;
  document.querySelector("#candidate-table tbody").innerHTML = candidates.map((item) => `<tr>
    <td><strong>${escapeHtml(localizeNarrative(translateValue(item.dataset_name)))}</strong><small>${escapeHtml(item.dataset_id)}</small></td>
    <td>${escapeHtml(item.source_database)}</td><td>${escapeHtml(translateValue(item.data_type))}</td>
    <td>${item.sample_count ?? "未报告"}</td><td>${item.has_response ? "有" : "未确认"}</td>
    <td><a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">打开官方页面 ↗</a></td>
  </tr>`).join("");
}

function renderDataset(dataset) {
  document.querySelector("#dataset-title").textContent = localizeNarrative(dataset.name);
  document.querySelector("#dataset-empty").hidden = dataset.rows.length > 0;
  document.querySelectorAll(".export-button").forEach((button) => { button.disabled = dataset.rows.length === 0; });
  const head = document.querySelector("#dataset-table thead");
  const body = document.querySelector("#dataset-table tbody");
  const auditColumns = dataset.columns.filter((column) => column.role === "审计信息");
  const visibleColumns = state.datasetView === "audit" ? dataset.columns : dataset.columns.filter((column) => column.role !== "审计信息");
  document.querySelector("#dataset-research-view").setAttribute("aria-pressed", String(state.datasetView === "research"));
  document.querySelector("#dataset-audit-view").setAttribute("aria-pressed", String(state.datasetView === "audit"));
  document.querySelector("#dataset-view-note").textContent = state.datasetView === "audit"
    ? `正在显示全部 ${dataset.columns.length} 个字段；原始样本特征已拆成中文键值。`
    : `正在显示 ${visibleColumns.length} 个科研字段；已隐藏 ${auditColumns.length} 个审计字段，下载文件仍保留全部字段。`;
  document.querySelector("#dataset-note").textContent = `分析单位：${dataset.unit_of_analysis}；患者 ${dataset.patient_count} 名，样本 ${dataset.sample_count} 个；研究结局字段：${fieldLabel(dataset, dataset.target_column)}。`;
  if (!dataset.rows.length) {
    head.innerHTML = "";
    body.innerHTML = "";
    return;
  }
  head.innerHTML = `<tr>${visibleColumns.map((column) => `<th>${escapeHtml(column.name === "raw_characteristics" ? "原始信息（结构化）" : column.label_zh)}<small>${escapeHtml(column.name)}</small></th>`).join("")}</tr>`;
  body.innerHTML = dataset.rows.slice(0, 100).map((row) => `<tr>${visibleColumns.map((column) => {
    if (column.name === "raw_characteristics") return `<td>${renderRawCharacteristics(row[column.name], row)}</td>`;
    const text = String(translateValue(row[column.name]));
    const shortened = column.role === "审计信息" && text.length > 88 ? `${text.slice(0, 88)}…` : text;
    const css = column.role === "审计信息" ? "audit-value" : "";
    return `<td class="${css}" title="${escapeHtml(text)}">${escapeHtml(shortened)}</td>`;
  }).join("")}</tr>`).join("");
  body.querySelectorAll(".raw-characteristics-button").forEach((button) => {
    button.addEventListener("click", () => openRawCharacteristicsDialog(button));
  });
}

const RAW_CHARACTERISTIC_LABELS = {
  "subject id": "受试者编号",
  "patient status": "疾病状态",
  timepoint: "采样时间点",
  "response at surgery": "术后疗效",
  "er status": "ER 状态",
  "pr status": "PR 状态",
};

function parseRawCharacteristics(value) {
  return String(value || "").split(/[；;]/).map((item) => item.trim()).filter(Boolean).map((item) => {
    const separator = item.search(/[:：]/);
    if (separator < 0) return ["原始记录", item];
    return [item.slice(0, separator).trim(), item.slice(separator + 1).trim()];
  });
}

function renderRawCharacteristics(value, row) {
  const items = parseRawCharacteristics(value);
  if (!items.length) return '<span class="muted-cell">未提供</span>';
  const context = row.sample_id || row.patient_id || "当前记录";
  return `<button class="raw-characteristics-button" type="button" data-raw="${escapeHtml(encodeURIComponent(String(value)))}" data-context="${escapeHtml(context)}">查看 ${items.length} 项原始记录</button>`;
}

function openRawCharacteristicsDialog(button) {
  const items = parseRawCharacteristics(decodeURIComponent(button.dataset.raw || ""));
  document.querySelector("#raw-dialog-context").textContent = `样本/患者：${button.dataset.context || "当前记录"}；以下同时展示中文标准化值与原始值。`;
  document.querySelector("#raw-dialog-body").innerHTML = items.map(([key, rawValue]) => `<tr><td>${escapeHtml(RAW_CHARACTERISTIC_LABELS[key.toLowerCase()] || key)}</td><td>${escapeHtml(translateValue(rawValue))}</td><td>${escapeHtml(rawValue)}</td></tr>`).join("");
  document.querySelector("#raw-characteristics-dialog").showModal();
}

document.querySelector("#dataset-research-view").addEventListener("click", () => {
  state.datasetView = "research";
  if (state.result) renderDataset(state.result.modeling_dataset);
});

document.querySelector("#dataset-audit-view").addEventListener("click", () => {
  state.datasetView = "audit";
  if (state.result) renderDataset(state.result.modeling_dataset);
});

document.querySelector("#raw-dialog-close").addEventListener("click", () => {
  document.querySelector("#raw-characteristics-dialog").close();
});

function renderReadiness(readiness, dataset, sources, candidates) {
  const badge = document.querySelector("#readiness-status");
  badge.textContent = readiness.status;
  badge.className = `status-badge ${statusClass(readiness.status)}`;
  const outcomeCompleteness = readiness.target_missing_rate == null ? null : (1 - readiness.target_missing_rate) * 100;
  const traceableCount = sources.filter((source) => source.source_id && source.url).length;
  const traceabilityRate = sources.length ? (traceableCount / sources.length) * 100 : null;
  const sourceDatabases = new Set([
    ...sources.map((source) => canonicalDatabaseName(source.source_name)),
    ...(candidates || []).map((candidate) => canonicalDatabaseName(candidate.source_database)),
  ].filter(Boolean));
  const fieldCompleteness = readiness.field_completeness_rate == null ? null : readiness.field_completeness_rate * 100;
  const variableCoverage = readiness.requested_variable_coverage_rate == null ? null : readiness.requested_variable_coverage_rate * 100;
  const metricCards = [
    { label: "数据记录", value: readiness.row_count, suffix: "条", detail: "清洗后的患者/样本级记录" },
    { label: "结局匹配", value: readiness.target_match ? "匹配" : "不匹配", suffix: "", detail: readiness.target_match ? fieldLabel(dataset, readiness.target_column) : "没有用其他结局替代" },
    { label: "结局完整率", percent: outcomeCompleteness, detail: readiness.target_column ? fieldLabel(dataset, readiness.target_column) : "尚未识别结局字段" },
    { label: "全表字段完整率", percent: fieldCompleteness, detail: "基于主科研数据集的非审计字段计算" },
    { label: "请求变量覆盖率", percent: variableCoverage, detail: variableCoverage == null ? "科研问题未指定基因" : "请求基因在主数据集中的覆盖" },
    { label: "数据源多样性", value: sourceDatabases.size, suffix: "类", detail: [...sourceDatabases].join("、") || "尚无来源" },
    { label: "来源可追溯率", percent: traceabilityRate, detail: sources.length ? `${traceableCount}/${sources.length} 个来源具备官方地址` : "尚无来源记录" },
    { label: "自动清洗", value: readiness.cleaned_value_count, suffix: "处", detail: `另排除 ${readiness.excluded_orphan_record_count} 条孤立分子记录` },
  ];
  document.querySelector("#research-metrics").innerHTML = metricCards.map((metric) => {
    if (!("percent" in metric) || metric.percent == null) {
      const value = metric.value ?? "未计算";
      return `<article class="research-metric"><span>${escapeHtml(metric.label)}</span><strong>${escapeHtml(value)}${metric.suffix ? `<small>${escapeHtml(metric.suffix)}</small>` : ""}</strong><p>${escapeHtml(metric.detail)}</p></article>`;
    }
    const percent = Math.max(0, Math.min(100, metric.percent));
    return `<article class="research-metric research-metric-rate"><div class="metric-ring" style="--metric-value:${percent.toFixed(1)}" role="img" aria-label="${escapeHtml(metric.label)} ${percent.toFixed(1)}%"><span>${percent.toFixed(1)}%</span></div><div><span>${escapeHtml(metric.label)}</span><p>${escapeHtml(metric.detail)}</p></div></article>`;
  }).join("");

  const distribution = Object.entries(dataset.class_distribution || {});
  const distributionTotal = distribution.reduce((sum, [, count]) => sum + Number(count || 0), 0);
  document.querySelector("#outcome-total").textContent = distributionTotal ? `共 ${distributionTotal} 条` : "暂无可统计结局";
  document.querySelector("#outcome-bars").innerHTML = distribution.length ? distribution.map(([label, count]) => {
    const percent = distributionTotal ? Number(count) / distributionTotal * 100 : 0;
    return `<div class="outcome-row"><div class="outcome-label"><span>${escapeHtml(translateValue(label))}</span><strong>${percent.toFixed(1)}%</strong></div><div class="outcome-track" role="img" aria-label="${escapeHtml(translateValue(label))} ${count} 条，占 ${percent.toFixed(1)}%"><span style="width:${percent.toFixed(1)}%"></span></div><small>${escapeHtml(count)} 条</small></div>`;
  }).join("") : '<p class="muted-visual">未识别到可统计的研究结局字段。</p>';

  const facts = [
    ["患者数量", dataset.patient_count],
    ["样本数量", dataset.sample_count],
    ["研究结局字段", fieldLabel(dataset, readiness.target_column)],
    ["结局缺失率", readiness.target_missing_rate == null ? "—" : `${(readiness.target_missing_rate * 100).toFixed(1)}%`],
    ["全表字段完整率", readiness.field_completeness_rate == null ? "—" : `${(readiness.field_completeness_rate * 100).toFixed(1)}%`],
    ["请求变量覆盖率", readiness.requested_variable_coverage_rate == null ? "未指定基因变量" : `${(readiness.requested_variable_coverage_rate * 100).toFixed(1)}%`],
    ["重复患者", readiness.repeated_patient_count],
    ["重复样本行", readiness.duplicate_row_count],
    ["分析分组建议", readiness.split_strategy],
  ];
  document.querySelector("#readiness-facts").innerHTML = facts.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  document.querySelector("#cleaning-action-list").innerHTML = (readiness.cleaning_actions?.length ? readiness.cleaning_actions : ["本次没有可执行的患者级清洗动作。"]).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  document.querySelector("#warning-list").innerHTML = (readiness.warnings.length ? readiness.warnings : ["未发现阻断性风险。 "]).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  document.querySelector("#recommendation-list").innerHTML = readiness.recommendations.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function renderCompetitionReport(report) {
  const section = document.querySelector("#competition-report");
  if (!section) return;
  if (!report) {
    section.hidden = true;
    const spotlight = document.querySelector("#competition-spotlight");
    if (spotlight) spotlight.hidden = true;
    return;
  }
  section.hidden = false;
  const spotlight = document.querySelector("#competition-spotlight");
  if (spotlight) spotlight.hidden = false;
  document.querySelector("#competition-direction").textContent = report.direction || "方向1A";
  const inlineDirection = document.querySelector("#competition-direction-inline");
  if (inlineDirection) inlineDirection.textContent = report.direction || "方向1A";
  const quickSummary = document.querySelector("#competition-quick-summary");
  if (quickSummary) quickSummary.textContent = `${report.metrics?.length || 0} 个指标` ;
  const quickStats = document.querySelector("#competition-quick-stats");
  if (quickStats) quickStats.textContent = `${report.rag_layers?.length || 0} 层混合 RAG · ${report.ablation_rows?.length || 0} 个消融`;
  document.querySelector("#competition-summary").textContent = localizeNarrative(report.summary);
  const spotlightMetrics = document.querySelector("#competition-spotlight-metrics");
  if (spotlightMetrics) {
    const byName = new Map((report.metrics || []).map((metric) => [metric.name, metric]));
    const graph = report.knowledge_graph || {};
    const cards = [
      byName.get("内部综合诊断分") || { name: "内部综合诊断分", display_value: "未计算", status: "待补充", detail: "仅作任务诊断" },
      byName.get("来源可追溯率") || { name: "来源可追溯率", display_value: "未计算", status: "待补充", detail: "来源审计" },
      byName.get("请求变量覆盖率") || { name: "请求变量覆盖率", display_value: "未计算", status: "待补充", detail: "变量匹配" },
      { name: "混合 RAG", display_value: `${report.rag_layers?.length || 0} 层`, status: "已覆盖", detail: "词法、语义、结构化规则与图谱证据" },
      { name: "知识图谱", display_value: `${graph.node_count ?? 0} 节点 / ${graph.edge_count ?? 0} 边`, status: graph.enabled ? "已覆盖" : "待补充", detail: "来源-数据集-字段-质量反馈关系" },
      { name: "消融实验", display_value: `${report.ablation_rows?.length || 0} 组`, status: "已覆盖", detail: "千问、多源融合、来源图谱对比" },
    ];
    spotlightMetrics.innerHTML = cards.map((metric) => `<article class="spot-metric"><span>${escapeHtml(metric.name)}</span><strong>${escapeHtml(metric.display_value)}</strong><em class="${statusClass(metric.status)}">${escapeHtml(metric.status)}</em><small>${escapeHtml(localizeNarrative(metric.detail))}</small></article>`).join("");
  }
  document.querySelector("#competition-metrics").innerHTML = (report.metrics || []).map((metric) => {
    const detail = metric.target ? `${metric.detail} 目标：${metric.target}` : metric.detail;
    return `<article class="competition-metric"><span>${escapeHtml(metric.name)}</span><strong>${escapeHtml(metric.display_value)}</strong><em class="${statusClass(metric.status)}">${escapeHtml(metric.status)}</em><p>${escapeHtml(localizeNarrative(detail))}</p></article>`;
  }).join("");
  document.querySelector("#rag-layer-list").innerHTML = (report.rag_layers || []).map((layer) => `<div class="rag-layer"><span>${escapeHtml(layer.layer)}</span><strong>${escapeHtml(layer.implementation)}</strong><p>${escapeHtml(layer.why_it_matters)}</p><small>${escapeHtml(layer.observable_effect)}</small></div>`).join("");
  const graph = report.knowledge_graph || {};
  document.querySelector("#knowledge-graph-summary").innerHTML = `<div><span>节点</span><strong>${escapeHtml(graph.node_count ?? 0)}</strong></div><div><span>边</span><strong>${escapeHtml(graph.edge_count ?? 0)}</strong></div><div><span>实体类型</span><strong>${escapeHtml((graph.entity_types || []).join("、") || "暂无")}</strong></div><div><span>关系类型</span><strong>${escapeHtml((graph.relation_types || []).join("、") || "暂无")}</strong></div><p>${escapeHtml(graph.note || "尚未形成知识图谱摘要。")}</p>`;
  document.querySelector("#ablation-table tbody").innerHTML = (report.ablation_rows || []).map((row) => `<tr><td>${escapeHtml(row.variant)}</td><td>${escapeHtml(row.removed_component)}</td><td>${escapeHtml(row.expected_effect)}</td><td>${escapeHtml(row.observed_effect)}</td><td>${escapeHtml(row.note)}</td></tr>`).join("");
  document.querySelector("#improvement-list").innerHTML = (report.improvement_highlights || []).map((item) => `<li>${escapeHtml(localizeNarrative(item))}</li>`).join("");
  document.querySelector("#submission-checklist").innerHTML = (report.submission_checklist || []).map((item) => `<li><strong>${escapeHtml(item.label)} · ${escapeHtml(item.status)}</strong><br><span>${escapeHtml(item.detail)}</span></li>`).join("");
}

function renderDictionary(columns) {
  document.querySelector("#dictionary-count").textContent = `${columns.length} 个字段`;
  document.querySelector("#dictionary-table tbody").innerHTML = columns.map((column) => `<tr>
    <td><code>${escapeHtml(column.name)}</code></td><td>${escapeHtml(column.label_zh)}</td>
    <td>${escapeHtml(TYPE_TRANSLATIONS[column.data_type] || column.data_type)}</td><td>${escapeHtml(column.role)}</td><td>${escapeHtml(column.description)}</td>
  </tr>`).join("");
}

function renderSources(sources, candidates, dataset) {
  document.querySelector("#source-count").textContent = `${sources.length} 个来源`;
  document.querySelector("#source-table tbody").innerHTML = sources.length ? sources.map((source) => `<tr class="source-table-row" data-source-db="${escapeHtml(canonicalDatabaseName(source.source_name))}">
    <td><strong>${escapeHtml(source.source_name)}</strong><small>${escapeHtml(source.source_id)}</small></td>
    <td>${escapeHtml(source.accession)}</td><td>${escapeHtml(SOURCE_STATUS_TRANSLATIONS[source.status] || source.status)}</td>
    <td><code>${escapeHtml(source.checksum || "未提供")}</code></td>
    <td><a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">官方地址 ↗</a></td>
  </tr>`).join("") : '<tr><td colspan="5" class="muted-cell">当前没有已登记来源。</td></tr>';
  renderLineage(sources, candidates || [], dataset);
}

function renderLineage(sources, candidates, dataset) {
  const graph = document.querySelector("#lineage-graph");
  const counts = new Map();
  sources.forEach((source) => {
    const name = canonicalDatabaseName(source.source_name);
    counts.set(name, (counts.get(name) || 0) + 1);
  });
  candidates.forEach((candidate) => {
    const name = canonicalDatabaseName(candidate.source_database);
    if (!counts.has(name)) counts.set(name, 0);
  });
  const sourceNodes = [...counts.entries()].slice(0, 6);
  if (!sourceNodes.length) {
    graph.innerHTML = '<p class="muted-visual">运行真实数据模式后，这里会显示来源到主数据集的点线关系。</p>';
    document.querySelector("#lineage-detail").innerHTML = '<article class="lineage-detail-main"><span>交互说明</span><strong>暂无可展示来源</strong></article>';
    return;
  }
  const activeSourceId = String(dataset.rows?.[0]?.source_id || "").toLowerCase();
  const isPrimary = (name) => {
    const lower = name.toLowerCase();
    return (activeSourceId.startsWith("geo:") && lower.includes("geo"))
      || (activeSourceId.startsWith("cbioportal:") && lower.includes("cbio"));
  };
  const primary = sourceNodes.find(([name]) => isPrimary(name))?.[0] || sourceNodes[0][0];
  state.lineage = { sources, candidates, primary, selected: null, hover: null, view: "all", paused: false };
  const height = Math.max(250, sourceNodes.length * 76 + 56);
  const middle = height / 2;
  const yStart = middle - ((sourceNodes.length - 1) * 64) / 2;
  const edges = sourceNodes.map(([name], index) => {
    const y = yStart + index * 64;
    const css = isPrimary(name) ? "lineage-edge is-primary" : "lineage-edge";
    const firstPath = `M 145 ${middle} C 225 ${middle}, 235 ${y}, 315 ${y}`;
    const secondPath = `M 415 ${y} C 610 ${y}, 690 ${middle}, 850 ${middle}`;
    const flow = isPrimary(name) ? `<path class="lineage-flow" data-db="${escapeHtml(name)}" d="${firstPath}"/><path class="lineage-flow" data-db="${escapeHtml(name)}" d="${secondPath}"/>` : "";
    return `<path class="${css}" data-db="${escapeHtml(name)}" d="${firstPath}"/><path class="${css}" data-db="${escapeHtml(name)}" d="${secondPath}"/>${flow}`;
  }).join("");
  const nodes = sourceNodes.map(([name, count], index) => {
    const y = yStart + index * 64;
    const css = isPrimary(name) ? "lineage-node is-primary" : "lineage-node";
    return `<g class="${css}" data-db="${escapeHtml(name)}" role="button" tabindex="0" aria-label="查看 ${escapeHtml(name)} 的 ${count || 0} 个已登记来源项" transform="translate(365 ${y})"><rect class="lineage-hit-area" x="-18" y="-27" width="230" height="54" rx="12"></rect><circle r="12"></circle><text x="20" y="-2">${escapeHtml(name)}</text><text class="lineage-count" x="20" y="15">${count || "候选"}${count ? " 个来源项" : "数据集"}</text><title>点击筛选 ${escapeHtml(name)} 来源；按 Enter 或空格键也可操作</title></g>`;
  }).join("");
  graph.innerHTML = `<svg viewBox="0 0 1050 ${height}" role="group" aria-label="可交互数据溯源图：科研问题经过多个公开数据库，选择形成主科研数据集">
    ${edges}
    <g class="lineage-terminal" transform="translate(105 ${middle})"><circle r="38"></circle><text text-anchor="middle" y="-3">科研</text><text text-anchor="middle" y="15">问题</text></g>
    ${nodes}
    <g class="lineage-terminal lineage-dataset" transform="translate(900 ${middle})"><circle r="50"></circle><text text-anchor="middle" y="-5">主科研</text><text text-anchor="middle" y="14">数据集</text></g>
  </svg>`;
  graph.querySelectorAll(".lineage-node").forEach((node) => {
    node.addEventListener("pointerenter", () => { state.lineage.hover = node.dataset.db; updateLineageVisual(); });
    node.addEventListener("pointerleave", () => { state.lineage.hover = null; updateLineageVisual(); });
    node.addEventListener("click", () => selectLineageSource(node.dataset.db));
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectLineageSource(node.dataset.db);
      }
    });
  });
  wireLineageControls();
  updateLineageInteraction();
}

function selectLineageSource(databaseName) {
  state.lineage.view = "all";
  state.lineage.selected = state.lineage.selected === databaseName ? null : databaseName;
  updateLineageInteraction();
}

function updateLineageVisual() {
  const focus = state.lineage.hover || (state.lineage.view === "primary" ? state.lineage.primary : state.lineage.selected);
  document.querySelectorAll("#lineage-graph [data-db]").forEach((element) => {
    const matches = !focus || element.dataset.db === focus;
    element.classList.toggle("is-related", Boolean(focus && matches));
    element.classList.toggle("is-dimmed", Boolean(focus && !matches));
    if (element.classList.contains("lineage-node")) element.classList.toggle("is-selected", element.dataset.db === state.lineage.selected);
  });
}

function updateLineageInteraction() {
  const panel = document.querySelector(".lineage-panel");
  const filterName = state.lineage.view === "primary" ? state.lineage.primary : state.lineage.selected;
  panel.classList.toggle("is-paused", state.lineage.paused);
  updateLineageVisual();
  const rows = [...document.querySelectorAll("#source-table tbody .source-table-row")];
  rows.forEach((row) => {
    const visible = !filterName || row.dataset.sourceDb === filterName;
    row.hidden = !visible;
    row.classList.toggle("is-selected", Boolean(filterName && visible));
  });
  const visibleCount = rows.filter((row) => !row.hidden).length;
  document.querySelector("#source-filter-status").textContent = filterName ? `当前显示 ${filterName}：${visibleCount} 个已登记来源` : `显示全部 ${rows.length} 个已登记来源`;
  document.querySelector("#lineage-clear-filter").hidden = !filterName;
  document.querySelector("#lineage-show-all").setAttribute("aria-pressed", String(state.lineage.view === "all" && !state.lineage.selected));
  document.querySelector("#lineage-show-primary").setAttribute("aria-pressed", String(state.lineage.view === "primary"));
  document.querySelector("#lineage-toggle-animation").setAttribute("aria-pressed", String(state.lineage.paused));
  document.querySelector("#lineage-toggle-animation").textContent = state.lineage.paused ? "播放动画" : "暂停动画";
  renderLineageDetail(filterName);
}

function renderLineageDetail(databaseName) {
  const detail = document.querySelector("#lineage-detail");
  const databases = new Set([
    ...state.lineage.sources.map((source) => canonicalDatabaseName(source.source_name)),
    ...state.lineage.candidates.map((candidate) => canonicalDatabaseName(candidate.source_database)),
  ].filter(Boolean));
  if (!databaseName) {
    detail.innerHTML = `<article class="lineage-detail-main"><span>交互说明</span><strong>点击或使用键盘选择数据库节点</strong></article><article><span>数据库类型</span><strong>${databases.size} 类</strong></article><article><span>已登记来源</span><strong>${state.lineage.sources.length} 项</strong></article><article><span>主数据路径</span><strong>${escapeHtml(state.lineage.primary)}</strong></article>`;
    return;
  }
  const sources = state.lineage.sources.filter((source) => canonicalDatabaseName(source.source_name) === databaseName);
  const candidates = state.lineage.candidates.filter((candidate) => canonicalDatabaseName(candidate.source_database) === databaseName);
  const accessions = [...new Set([...sources.map((source) => source.accession), ...candidates.map((candidate) => candidate.accession || candidate.dataset_id)].filter(Boolean))];
  const traceable = sources.filter((source) => source.source_id && source.url).length;
  const statusSummary = [...new Set(sources.map((source) => SOURCE_STATUS_TRANSLATIONS[source.status] || source.status).filter(Boolean))].join("、") || "仅候选，尚未登记";
  const pathRole = databaseName === state.lineage.primary ? "主科研数据路径" : "辅助检索或证据来源";
  detail.innerHTML = `<article class="lineage-detail-main"><span>当前节点</span><strong>${escapeHtml(databaseName)} · ${pathRole}</strong></article><article><span>来源 / 候选</span><strong>${sources.length} 项 / ${candidates.length} 个</strong></article><article><span>数据编号</span><strong>${escapeHtml(accessions.slice(0, 4).join("、") || "未报告")}</strong></article><article><span>状态与溯源</span><strong>${escapeHtml(statusSummary)} · ${traceable}/${sources.length || 0} 可回溯</strong></article>`;
}

function wireLineageControls() {
  document.querySelector("#lineage-show-all").onclick = () => {
    state.lineage.view = "all";
    state.lineage.selected = null;
    updateLineageInteraction();
  };
  document.querySelector("#lineage-show-primary").onclick = () => {
    state.lineage.view = "primary";
    state.lineage.selected = null;
    updateLineageInteraction();
  };
  document.querySelector("#lineage-toggle-animation").onclick = () => {
    state.lineage.paused = !state.lineage.paused;
    updateLineageInteraction();
  };
  document.querySelector("#lineage-clear-filter").onclick = () => {
    state.lineage.view = "all";
    state.lineage.selected = null;
    updateLineageInteraction();
  };
}

document.querySelectorAll(".export-button").forEach((button) => {
  button.addEventListener("click", async () => {
    if (!state.result) return;
    const format = button.dataset.format;
    button.disabled = true;
    downloadStatus.textContent = `正在生成 ${format.toUpperCase()} 文件…`;
    try {
      const response = await fetch(`/api/agent/tasks/${encodeURIComponent(state.result.task_id)}/export/${format}`);
      if (!response.ok) await readJson(response);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${state.result.task_id}-科研数据集.${format}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      downloadStatus.textContent = `${format.toUpperCase()} 已生成并下载。`;
      showToast("科研数据集下载成功");
    } catch (error) {
      downloadStatus.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });
});

function showToast(message) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.hidden = false;
  window.setTimeout(() => { toast.hidden = true; }, 2600);
}

checkConfiguration();
