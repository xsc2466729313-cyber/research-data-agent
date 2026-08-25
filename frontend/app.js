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
  modelEvaluationReport: null,
  modelSessions: {},
  modelConfigs: [
    { targetId: "qwen-qwen-plus", provider: "qwen", model: "qwen-plus", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", apiKey: "", workspaceId: "", sessionId: null, status: "未连接" },
    { targetId: "qwen-qwen-max", provider: "qwen", model: "qwen-max", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", apiKey: "", workspaceId: "", sessionId: null, status: "未连接" },
    { targetId: "qwen-qwen-turbo", provider: "qwen", model: "qwen-turbo", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", apiKey: "", workspaceId: "", sessionId: null, status: "未连接" },
    { targetId: "deepseek-deepseek-chat", provider: "deepseek", model: "deepseek-chat", baseUrl: "https://api.deepseek.com", apiKey: "", workspaceId: "", sessionId: null, status: "未连接" },
    { targetId: "deepseek-deepseek-reasoner", provider: "deepseek", model: "deepseek-reasoner", baseUrl: "https://api.deepseek.com", apiKey: "", workspaceId: "", sessionId: null, status: "未连接" },
  ],
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
const METRIC_LABELS_ZH = {
  "Research Relevance": "研究相关性",
  "Analytical Adequacy": "分析充分性",
  "Traceability & Reliability": "可追溯性与可靠性",
  Reusability: "可复用性",
  "Fitness Score": "科研适配度",
  fitness_score: "科研适配度",
  source_audit: "来源审计完整度",
  outcome_completeness: "结局完整率",
  field_completeness: "字段完整率",
  question_fit: "问题匹配度",
  exploratory_usability: "科研探索可用性",
  "结构化解析通过": "结构化解析通过率",
  "问题字段响应率": "问题字段响应率",
  "基因字段数量": "基因字段数量",
  "结局字段数量": "结局字段数量",
  "问题长度": "问题长度",
  "综合可观察分": "综合可观察分",
};
const STRATUM_LABELS_ZH = {
  disease_subtype: "疾病亚型",
  source_type: "来源类型",
  response_domain: "响应数据域",
  evidence_level: "证据等级",
  patient_sample_link_confidence: "患者-样本关联置信度",
  risk_level: "风险等级",
};
const VALUE_LABELS_ZH = {
  "HER2-positive": "HER2 阳性",
  clinical: "临床响应",
  preclinical_cell_line: "细胞系药敏",
  clinical_trial: "临床试验",
  knowledge_evidence: "知识证据",
  official_accession: "官方数据编号",
  pmid_or_doi: "PMID / DOI",
  curated_database: "人工整理数据库",
  secondary_or_unknown: "次级或未知",
  unresolved: "未解决",
  review_required: "需要复核",
};
const SOURCE_STATUS_TRANSLATIONS = { cached: "缓存命中", discovered: "已发现", downloaded: "已下载", fetched: "已获取", failed: "失败" };
const ARGUMENT_LABELS = {
  study_id: "研究编号", gene_symbols: "基因", max_records: "最大记录数",
  project_id: "项目编号", data_types: "数据类型", max_files: "最大文件数",
  accession: "数据编号", condition: "疾病", query_terms: "检索词",
  max_trials: "最大试验数", disease_name: "疾病", molecular_profile_name: "分子特征",
  therapy_name: "治疗方案", max_items: "最大条目数",
};

function localApiOrigins() {
  if (!window.location.hostname || !["127.0.0.1", "localhost"].includes(window.location.hostname)) return [];
  const ports = [window.location.port, "8000", "8001", "8002"].filter(Boolean);
  return [...new Set(ports)].map((port) => `${window.location.protocol}//${window.location.hostname}:${port}`);
}

// Same-origin routes such as /api/agent/configuration, /api/research/task and /api/agent/tasks
// are routed through fetchApi so a stale local tab can recover on the other dev port.

let pinnedApiOrigin = null;

function isUnimplementedApi(response) {
  if (response.status === 405) return true;
  if (response.status !== 404) return false;
  const type = (response.headers.get("content-type") || "").toLowerCase();
  return type.includes("text/html") || type.includes("text/plain");
}

function originOfApiUrl(url) {
  if (url.startsWith("http://") || url.startsWith("https://")) return new URL(url).origin;
  return window.location.origin;
}

function candidateApiUrls(path) {
  if (pinnedApiOrigin) return [`${pinnedApiOrigin}${path}`];
  return [path, ...localApiOrigins().map((origin) => `${origin}${path}`)];
}

async function originHasResearchTask(origin) {
  try {
    const response = await fetch(`${origin}/api/research/task`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: "x" }),
    });
    return response.status === 422 || response.status === 401;
  } catch {
    return false;
  }
}

async function pinPreferredApiOrigin() {
  const origins = [window.location.origin, ...localApiOrigins()].filter(Boolean);
  for (const origin of [...new Set(origins)]) {
    if (await originHasResearchTask(origin)) {
      pinnedApiOrigin = origin;
      return origin;
    }
  }
  return pinnedApiOrigin;
}

async function fetchApi(path, options = {}) {
  const uniqueUrls = [...new Set(candidateApiUrls(path))];
  let lastError = null;
  let lastResponse = null;
  for (const url of uniqueUrls) {
    try {
      const response = await fetch(url, options);
      lastResponse = response;
      if (isUnimplementedApi(response)) continue;
      pinnedApiOrigin = originOfApiUrl(url);
      return response;
    } catch (error) {
      lastError = error;
    }
  }
  if (lastResponse) {
    pinnedApiOrigin = originOfApiUrl(uniqueUrls[0]);
    return lastResponse;
  }
  const detail = lastError?.message || "浏览器未返回具体网络错误";
  throw new Error(`本机后端不可达：已尝试 8000/8001。请确认页面使用 http://127.0.0.1:8000/ 或 http://127.0.0.1:8001/，并关闭旧标签页后强制刷新。原始错误：${detail}`);
}

const translateTerm = (value) => TERM_TRANSLATIONS[String(value)] || String(value ?? "—");
const listText = (values) => values?.length ? values.map(translateTerm).join("、") : "未指定";
const statusClass = (status) => ["完成", "可支持科研分析", "达标", "已覆盖", "已记录", "已计算", "PASS", "MATCH", "PARTIAL"].includes(status) ? (status === "PARTIAL" ? "is-review" : "is-success") : ["失败", "部分失败", "REJECT", "FAIL", "UNMATCH"].includes(status) ? "is-error" : "is-review";
const metricPercentValue = (metric) => {
  if (!metric) return null;
  const value = Number(metric.value);
  if (Number.isFinite(value)) return value * 100;
  const parsed = Number(String(metric.display_value || "").replace("%", ""));
  return Number.isFinite(parsed) ? parsed : null;
};
const clampPercent = (value) => {
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.min(100, number)) : null;
};
const precisePercent = (value) => {
  const percent = clampPercent(value);
  return percent == null ? "待评测" : `${percent.toFixed(1)}%`;
};
const score100 = (value) => {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(1)}` : "待实测";
};
const metricValueText = (value) => {
  if (value == null || value === "") return "待实测";
  if (typeof value === "number") return Number.isFinite(value) ? (value <= 1 ? `${(value * 100).toFixed(1)}%` : value.toFixed(1)) : "待实测";
  return String(value);
};
const metricLabelZh = (value) => METRIC_LABELS_ZH[String(value)] || String(value ?? "—");
const stratumLabelZh = (value) => STRATUM_LABELS_ZH[String(value)] || String(value ?? "—");
const valueLabelZh = (value) => VALUE_LABELS_ZH[String(value)] || translateValue(value);
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
    if (response.status === 405) {
      throw new Error("当前后端没有这条接口（HTTP 405）。请重启后端后强制刷新页面。");
    }
    const detail = body.detail;
    const message = typeof detail === "string"
      ? detail
      : detail?.message || detail?.detail || body.message || response.statusText || `请求失败（HTTP ${response.status}）`;
    throw new Error(message);
  }
  return body;
}

async function postAgentTask(payload) {
  return readJson(await fetchApi("/api/agent/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }));
}

async function runResearchTaskOnce(payload) {
  const createdResponse = await fetchApi("/api/research/task", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (isUnimplementedApi(createdResponse)) {
    setProgress(18, "当前后端尚未加载异步任务接口，改为同步执行…");
    return postAgentTask(payload);
  }
  const created = await readJson(createdResponse);
  if (created.modeling_dataset && created.plan) return created;
  const taskId = created.task_id;
  if (!taskId) throw new Error("后端没有返回任务编号。");
  setProgress(12, `任务 ${taskId} 已创建，正在理解科研问题…`);
  while (true) {
    const status = await readJson(await fetchApi(`/api/task/status/${encodeURIComponent(taskId)}`));
    setProgress(Math.max(12, Number(status.progress || 12)), status.message || status.stage || "科研任务执行中…");
    if (status.status === "completed") break;
    if (status.status === "failed") throw new Error(status.error || status.message || "科研任务执行失败。");
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
  }
  return readJson(await fetchApi(`/api/agent/tasks/${encodeURIComponent(taskId)}`));
}

async function runResearchTask(payload) {
  await pinPreferredApiOrigin();
  try {
    return await runResearchTaskOnce(payload);
  } catch (error) {
    const message = String(error.message || "");
    if (payload.qwen_session_id && (message.includes("临时会话不存在") || message.includes("已过期"))) {
      clearStaleQwenSession();
      const retry = { ...payload };
      delete retry.qwen_session_id;
      setProgress(16, "千问临时会话已失效，改用当前后端配置继续…");
      return runResearchTaskOnce(retry);
    }
    throw error;
  }
}

async function checkConfiguration() {
  const system = document.querySelector("#system-status");
  try {
    await pinPreferredApiOrigin();
    const [health, configuration] = await Promise.all([
      fetchApi("/health").then(readJson),
      fetchApi("/api/agent/configuration").then(readJson),
    ]);
    system.className = "system-status is-online";
    system.innerHTML = `<span class="status-dot"></span><span>在线 · ${escapeHtml(health.version)}</span>`;
    const badge = document.querySelector("#configuration-badge");
    badge.textContent = configuration.configured ? "千问已连接" : "千问未配置";
    badge.className = `status-badge ${configuration.configured ? "is-success" : "is-review"}`;
    document.querySelector("#configuration-title").textContent = configuration.configured ? "模型规划可用" : "当前使用确定性规划";
    document.querySelector("#configuration-message").textContent = configuration.message;
    document.querySelector("#configuration-model").textContent = configuration.model;
    if (!state.qwenSessionId) {
      const openConfig = document.querySelector("#qwen-open-config");
      if (openConfig) {
        openConfig.textContent = configuration.configured ? "更换临时连接（可选）" : "连接千问 API";
      }
    }
  } catch (error) {
    system.className = "system-status is-error";
    system.innerHTML = '<span class="status-dot"></span><span>后端未连接</span>';
    document.querySelector("#configuration-title").textContent = "无法读取模型配置";
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
    [18, "正在解析研究问题（PICO）…"],
    [32, "正在生成研究方案与数据源规划…"],
    [48, "正在检索并解析公开数据库…"],
    [63, "正在执行 Schema 匹配与实体对齐…"],
    [76, "正在执行四层质量门…"],
    [86, "正在生成分析矩阵、字段字典与质量报告…"],
  ];
  let index = 0;
  setProgress(8, "正在创建研究任务…");
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
  if (success) setProgress(100, "任务已完成，可审查结果并导出。");
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
    iterative_collection: true,
    max_collection_rounds: Number(document.querySelector("#collection-rounds")?.value || 8),
  };
  if (state.qwenSessionId && !isQwenSessionExpired()) payload.qwen_session_id = state.qwenSessionId;
  return payload;
}

function isQwenSessionExpired() {
  if (!state.qwenSessionExpiresAt) return false;
  const expires = Date.parse(state.qwenSessionExpiresAt);
  return Number.isFinite(expires) && expires <= Date.now();
}

function clearStaleQwenSession() {
  state.qwenSessionId = null;
  state.qwenSessionExpiresAt = null;
  const disconnect = document.querySelector("#qwen-disconnect");
  if (disconnect) disconnect.hidden = true;
  const openConfig = document.querySelector("#qwen-open-config");
  if (openConfig) openConfig.textContent = "连接千问 API";
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
  document.querySelector("#qwen-connect-status").textContent = "已从本机 CSV 读取连接字段，尚未提交。";
}

function renderTemporaryQwenConnection(session) {
  state.qwenSessionId = session.session_id;
  state.qwenSessionExpiresAt = session.expires_at;
  const badge = document.querySelector("#configuration-badge");
  badge.textContent = "会话已启用";
  badge.className = "status-badge is-success";
  document.querySelector("#configuration-title").textContent = "千问 API 内存会话已启用";
  document.querySelector("#configuration-message").textContent = `连接已验证，将于 ${new Date(session.expires_at).toLocaleString("zh-CN")} 前有效；服务重启会立即清除。`;
  document.querySelector("#configuration-model").textContent = session.model;
  document.querySelector("#qwen-open-config").textContent = "更换千问 API";
  document.querySelector("#qwen-disconnect").hidden = false;
  document.querySelector("#use-qwen").checked = true;
}

async function connectQwenSession(event) {
  event.preventDefault();
  const button = document.querySelector("#qwen-connect");
  const status = document.querySelector("#qwen-connect-status");
  button.disabled = true;
  status.textContent = "正在验证千问 API…";
  try {
    const previousSessionId = state.qwenSessionId;
    const response = await fetchApi("/api/agent/qwen-sessions", {
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
      fetchApi(`/api/agent/qwen-sessions/${encodeURIComponent(previousSessionId)}`, { method: "DELETE" }).catch(() => null);
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
  if (sessionId) await fetchApi(`/api/agent/qwen-sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" }).catch(() => null);
  document.querySelector("#qwen-disconnect").hidden = true;
  document.querySelector("#qwen-open-config").textContent = "连接千问 API";
  await checkConfiguration();
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
    const result = await runResearchTask(buildAgentTaskPayload());
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
    renderParsedQuestion(result.parsed_question, result.study_design);
    renderPlan(result.plan);
  renderTools(result.tool_calls);
  renderCandidates(result.candidate_sources);
  renderDataset(result.modeling_dataset);
  renderReadiness(result.readiness, result.modeling_dataset, result.source_items, result.candidate_sources);
    renderStudyDesign(result.study_design, result.modeling_dataset);
    renderCohortConstruction(result.cohort_construction, result.readiness, result.quality_gate_report);
  renderCollectionAgent(result.collection_agent);
    renderDataAlignment(result.data_alignment);
    renderQualityGates(result.quality_gate_report);
    renderDictionary(result.modeling_dataset.columns);
  renderSources(result.source_items, result.candidate_sources, result.modeling_dataset);
  renderCompetitionReport(result.competition_report);
}

function renderParsedQuestion(parsed, design) {
  const container = document.querySelector("#parsed-question");
  if (!container) return;
  const source = parsed || {};
  const cards = [
    ["Disease", source.disease || "—"],
    ["Population", source.population || design?.population || "—"],
    ["Exposure", source.exposure || design?.exposure || "—"],
    ["Outcome", source.outcome || design?.outcome || "—"],
    ["Required Variables", (source.required_variables || []).join("、") || "—"],
  ];
  container.innerHTML = cards.map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(localizeNarrative(value))}</strong></article>`).join("");
}

function renderQualityGates(report) {
  const overall = document.querySelector("#quality-gate-overall");
  const note = document.querySelector("#quality-gate-note");
  const metrics = document.querySelector("#quality-gate-metrics");
  const layers = document.querySelector("#quality-gate-layers");
  if (!overall || !note || !metrics || !layers) return;
  if (!report) {
    overall.textContent = "待检查";
    overall.className = "status-badge is-review";
    note.textContent = "当前任务未返回四层质量门报告。";
    metrics.innerHTML = "";
    layers.innerHTML = "";
    return;
  }
  overall.textContent = report.overall || "REVIEW";
  overall.className = `status-badge ${statusClass(report.overall)}`;
  note.textContent = localizeNarrative(report.note || "");
  const metricCards = [
    ["Cohort F1", report.cohort_f1 == null ? "未评测" : report.cohort_f1.toFixed(3)],
    ["Variable Coverage", report.variable_coverage == null ? "未计算" : `${(report.variable_coverage * 100).toFixed(1)}%`],
    ["Traceability", report.traceability == null ? "未计算" : `${(report.traceability * 100).toFixed(1)}%`],
    ["Research Fitness", report.research_fitness == null ? "未计算" : `${(report.research_fitness * 100).toFixed(1)}%`],
  ];
  metrics.innerHTML = metricCards.map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`).join("");
  layers.innerHTML = (report.layers || []).map((layer) => `<article class="${statusClass(layer.decision)}">
    <div><strong>${escapeHtml(layer.label)}</strong><span class="status-badge ${statusClass(layer.decision)}">${escapeHtml(layer.decision)}</span></div>
    <small>${escapeHtml((layer.checks || []).join(" · "))}</small>
    <p>${escapeHtml(localizeNarrative(layer.evidence))}</p>
  </article>`).join("");
}

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
  document.querySelector("#tool-count").textContent = `${tools.length} 个检索入口`;
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
  document.querySelectorAll(".export-button").forEach((button) => {
    const format = button.dataset.format;
    const needsRows = ["csv", "parquet", "xlsx", "json"].includes(format);
    button.disabled = needsRows && dataset.rows.length === 0;
  });
  const head = document.querySelector("#dataset-table thead");
  const body = document.querySelector("#dataset-table tbody");
  const auditColumns = dataset.columns.filter((column) => column.role === "审计信息");
  const visibleColumns = state.datasetView === "audit" ? dataset.columns : dataset.columns.filter((column) => column.role !== "审计信息");
  document.querySelector("#dataset-research-view").setAttribute("aria-pressed", String(state.datasetView === "research"));
  document.querySelector("#dataset-audit-view").setAttribute("aria-pressed", String(state.datasetView === "audit"));
  document.querySelector("#dataset-view-note").textContent = state.datasetView === "audit"
    ? `当前显示全部 ${dataset.columns.length} 个字段；原始样本特征已拆分为中文键值。`
    : `当前显示 ${visibleColumns.length} 个分析字段，已隐藏 ${auditColumns.length} 个审计字段；导出文件保留全部字段。`;
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

function renderModelMetricComparison(report) {
  const container = document.querySelector("#metric-compare-bars");
  const values = document.querySelector("#metric-compare-values");
  const topline = document.querySelector("#metric-compare-topline");
  if (!container || !values || !topline) return;
  const metricMap = new Map((report?.metrics || []).map((metric) => [metric.name, metric]));
  const metricValue = (name) => {
    const metric = metricMap.get(name);
    const value = metricPercentValue(metric);
    return value == null ? null : clampPercent(value);
  };
  const actualRows = [
    { name: "来源审计完整度", value: metricValue("来源审计完整度") ?? metricValue("来源可追溯率") },
    { name: "结局完整率", value: metricValue("结局完整率") },
    { name: "字段完整率", value: metricValue("字段完整率") },
    { name: "请求要素覆盖率", value: metricValue("请求要素覆盖率") ?? metricValue("请求变量覆盖率") },
    { name: "科研探索可用性", value: metricValue("科研探索可用性") ?? metricValue("分析可用性") },
  ];
  const actualValues = actualRows.map((item) => item.value).filter((value) => value != null);
  const average = actualValues.length ? actualValues.reduce((sum, value) => sum + value, 0) / actualValues.length : null;
  topline.textContent = average == null ? "正式模型 · 待评测" : `正式模型当前诊断均值 · ${precisePercent(average)}`;

  const comparisonRows = [
    {
      model: "正式模型 Ours",
      label: "当前任务真实结果",
      note: "已接入本次任务的真实可观测指标",
      color: "#0f766e",
      value: average,
      filled: true,
    },
    {
      model: "普通 LLM",
      label: "待实测",
      note: "需要同一 Gold Set 的真实运行",
      color: "#64748b",
      value: null,
      filled: false,
    },
    {
      model: "单源检索模型",
      label: "待实测",
      note: "需要同一 Gold Set 的真实运行",
      color: "#2563eb",
      value: null,
      filled: false,
    },
    {
      model: "多源无规则 / 无 Repair",
      label: "待实测",
      note: "需要同一 Gold Set 的真实消融",
      color: "#d97706",
      value: null,
      filled: false,
    },
  ];
  container.innerHTML = comparisonRows.map((row) => {
    const width = clampPercent(row.value) ?? 0;
    const emphasis = row.filled ? " is-primary" : "";
    return `<div class="metric-compare-row${emphasis}">
      <div class="metric-compare-label"><strong>${escapeHtml(row.model)}</strong><span>${escapeHtml(row.label)}</span></div>
      <div class="metric-compare-track" role="img" aria-label="${escapeHtml(row.model)} ${precisePercent(row.value)}">
        <span style="width:${width.toFixed(1)}%; background:${escapeHtml(row.color)}"></span>
      </div>
      <strong class="metric-compare-score">${precisePercent(row.value)}</strong>
    </div>`;
  }).join("");
  values.innerHTML = `<table><thead><tr><th>指标</th><th>数值</th><th>说明</th></tr></thead><tbody>${actualRows.map((item) => `<tr>
    <td><strong>${escapeHtml(item.name)}</strong></td>
    <td>${precisePercent(item.value)}</td>
    <td>${escapeHtml(item.value == null ? "待评测" : "当前任务真实值")}</td>
  </tr>`).join("")}
  <tr class="is-primary"><td><strong>综合诊断均值</strong></td><td>${precisePercent(average)}</td><td>正式模型当前可观测效果</td></tr>
  <tr><td><strong>普通 LLM / 单源 / 消融</strong></td><td>待实测</td><td>同一 Gold Set 上填入真实结果后再对比</td></tr></tbody></table>
  <p>说明：正式模型行来自本次任务的真实可观测结果；其他配置必须在同一 Gold Set 上实际运行后填入，不自动生成比较分数。以上不是 Gold Set 官方 Precision/Recall/SDTI 成绩。</p>`;
}

function renderStudyDesign(report, dataset) {
  const status = document.querySelector("#study-design-status");
  const summary = document.querySelector("#study-design-summary");
  const expression = document.querySelector("#study-model-expression");
  const rules = document.querySelector("#study-cohort-rules");
  const coverage = document.querySelector("#study-variable-coverage");
  const variableBody = document.querySelector("#study-variable-table tbody");
  const sources = document.querySelector("#study-source-recommendations");
  const limitations = document.querySelector("#study-design-limitations");
  if (!status || !summary || !expression || !rules || !coverage || !variableBody || !sources || !limitations) return;
  if (!report) {
    status.textContent = "待生成";
    status.className = "status-badge is-review";
    summary.innerHTML = '<p class="muted-visual">当前任务未返回研究方案报告。</p>';
    expression.textContent = "—";
    rules.innerHTML = "";
    coverage.innerHTML = "";
    variableBody.innerHTML = "";
    sources.innerHTML = "";
    limitations.innerHTML = "";
    return;
  }
  status.textContent = report.status || "已生成";
  status.className = `status-badge ${statusClass(report.status)}`;
  const cards = [
    ["研究类型", `${report.research_type || "—"} · ${report.research_type_id || "—"}`],
    ["研究人群", report.population],
    ["核心暴露", report.exposure],
    ["研究结局", report.outcome],
    ["协变量", (report.covariates || []).join("、") || "未指定"],
    ["分析单位", report.analysis_unit || dataset?.unit_of_analysis || "—"],
  ];
  summary.innerHTML = cards.map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(localizeNarrative(value))}</strong></article>`).join("");
  expression.textContent = localizeNarrative(report.model_expression || "—");
  if (report.generation_note) {
    summary.insertAdjacentHTML("afterend", `<p class="section-note study-generation-note">${escapeHtml(localizeNarrative(report.generation_note))}</p>`);
  }
  rules.innerHTML = (report.cohort_rules || []).map((rule) => `<li>${escapeHtml(localizeNarrative(rule))}</li>`).join("");
  const variables = report.required_variables || [];
  const available = variables.filter((variable) => variable.available).length;
  const required = variables.filter((variable) => variable.required).length;
  coverage.innerHTML = `<strong>${report.variable_coverage_rate == null ? "待计算" : `${(report.variable_coverage_rate * 100).toFixed(1)}%`}</strong><span>当前字段覆盖 · ${available}/${variables.length} 个字段可见，必需变量 ${required} 个</span>`;
  variableBody.innerHTML = variables.length ? variables.map((variable) => `<tr>
    <td><strong>${escapeHtml(variable.label)}</strong><small>${escapeHtml(variable.variable_id)}</small></td>
    <td>${escapeHtml(variable.role)}</td>
    <td><span class="status-badge ${variable.required ? "is-review" : ""}">${variable.required ? "是" : "建议"}</span></td>
    <td><span class="status-badge ${variable.available ? "is-success" : "is-error"}">${variable.available ? "可用" : "缺失"}</span></td>
    <td>${escapeHtml((variable.matched_fields || []).join("、") || "—")}</td>
    <td>${escapeHtml(localizeNarrative(variable.note))}</td>
  </tr>`).join("") : '<tr><td colspan="6" class="muted-cell">尚未形成变量协议。</td></tr>';
  sources.innerHTML = (report.data_source_recommendations || []).map((source) => `<article class="${source.selected ? "is-selected" : ""}">
    <div><strong>${escapeHtml(source.database)}</strong><span class="status-badge ${source.selected ? "is-success" : statusClass(source.availability)}">${escapeHtml(source.availability)}</span></div>
    <p>${escapeHtml(localizeNarrative(source.purpose))}</p>
    <small>${escapeHtml((source.data_domains || []).join(" · "))}</small>
    <em>${escapeHtml(localizeNarrative(source.note))}</em>
  </article>`).join("");
  limitations.innerHTML = (report.limitations || []).map((item) => `<li>${escapeHtml(localizeNarrative(item))}</li>`).join("");
}

function renderCohortConstruction(report, readiness, qualityGate) {
  const gate = document.querySelector("#cohort-gate");
  const count = document.querySelector("#cohort-count");
  const summary = document.querySelector("#cohort-summary-cards");
  const funnel = document.querySelector("#cohort-funnel");
  const stageFunnel = document.querySelector("#cohort-stage-funnel");
  const inclusion = document.querySelector("#cohort-inclusion-list");
  const exclusion = document.querySelector("#cohort-exclusion-list");
  const body = document.querySelector("#cohort-step-table tbody");
  const notes = document.querySelector("#cohort-notes");
  if (!gate || !count || !summary || !funnel || !inclusion || !exclusion || !body || !notes) return;
  if (!report) {
    gate.textContent = "待构建";
    gate.className = "status-badge is-review";
    count.textContent = "无队列";
    summary.innerHTML = "";
    if (stageFunnel) stageFunnel.innerHTML = "";
    funnel.innerHTML = '<p class="muted-visual">真实数据任务完成后显示筛选计数。</p>';
    inclusion.innerHTML = "";
    exclusion.innerHTML = "";
    body.innerHTML = "";
    notes.innerHTML = "";
    return;
  }
  gate.textContent = report.quality_gate || "REVIEW";
  gate.className = `status-badge ${statusClass(report.quality_gate)}`;
  count.textContent = report.execution_mode === "plan_only"
    ? "规则已生成，待真实筛选"
    : `${report.final_row_count || 0} 行最终队列`;
  summary.innerHTML = [
    ["来源行数", report.source_row_count],
    ["最终队列", report.final_row_count],
    ["患者数", report.patient_count],
    ["样本数", report.sample_count],
    ["变量覆盖", report.variable_coverage_rate == null ? "待计算" : `${(report.variable_coverage_rate * 100).toFixed(1)}%`],
    ["患者 Linkage F1", report.patient_linkage_f1 == null ? "未评测" : report.patient_linkage_f1.toFixed(3)],
  ].map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`).join("");
  if (stageFunnel) {
    const raw = Number(report.source_row_count || 0);
    const target = Number(report.final_row_count || 0);
    const analysisReady = Boolean(readiness?.analysis_ready) && (qualityGate?.overall === "PASS" || report.quality_gate === "PASS");
    const analysis = analysisReady ? target : 0;
    const maxStage = Math.max(1, raw, target, analysis);
    const stages = [
      ["Raw Samples", raw, "原始样本/记录"],
      ["Target Cohort", target, "目标队列"],
      ["Analysis Dataset", analysis, "通过质量门的分析数据集"],
    ];
    stageFunnel.innerHTML = stages.map(([label, count, note]) => {
      const width = Math.max(8, count / maxStage * 100);
      return `<article>
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(count)}</strong>
        <div class="cohort-funnel-track" role="img" aria-label="${escapeHtml(note)} ${escapeHtml(count)}"><i style="width:${width.toFixed(1)}%"></i></div>
        <small>${escapeHtml(note)}</small>
      </article>`;
    }).join("");
  }
  const steps = report.filter_steps || [];
  const maxCount = Math.max(1, ...steps.map((step) => Number(step.before_count || 0)));
  funnel.innerHTML = steps.map((step, index) => {
    const width = Math.max(3, Number(step.after_count || 0) / maxCount * 100);
    return `<article class="cohort-funnel-step ${step.status === "待复核" ? "is-review" : ""}">
      <div class="cohort-funnel-label"><span>${String(index + 1).padStart(2, "0")} · ${escapeHtml(step.label)}</span><strong>${escapeHtml(step.after_count)} / ${escapeHtml(step.before_count)}</strong></div>
      <div class="cohort-funnel-track" role="img" aria-label="${escapeHtml(step.label)} 保留 ${escapeHtml(step.after_count)} 条"><i style="width:${width.toFixed(1)}%"></i></div>
      <small>排除 ${escapeHtml(step.excluded_count)} · ${escapeHtml(step.status)}</small>
    </article>`;
  }).join("");
  inclusion.innerHTML = (report.inclusion_criteria || []).map((item) => `<li>${escapeHtml(localizeNarrative(item))}</li>`).join("");
  exclusion.innerHTML = (report.exclusion_criteria || []).map((item) => `<li>${escapeHtml(localizeNarrative(item))}</li>`).join("");
  body.innerHTML = steps.map((step) => `<tr>
    <td><strong>${escapeHtml(step.label)}</strong><small>${escapeHtml(step.step_id)}</small></td>
    <td>${escapeHtml(step.rule_type)}</td><td>${escapeHtml(localizeNarrative(step.criterion))}</td>
    <td>${escapeHtml(step.before_count)}</td><td>${escapeHtml(step.after_count)}</td><td>${escapeHtml(step.excluded_count)}</td>
    <td><span class="status-badge ${statusClass(step.status)}">${escapeHtml(step.status)}</span></td>
    <td>${escapeHtml(localizeNarrative(step.note))}</td>
  </tr>`).join("");
  const modeNote = report.not_run_reason ? [report.not_run_reason] : [];
  notes.innerHTML = [...modeNote, ...(report.notes || [])].map((item) => `<li>${escapeHtml(localizeNarrative(item))}</li>`).join("");
}

function renderCollectionAgent(report) {
  const gate = document.querySelector("#collection-agent-gate");
  const rounds = document.querySelector("#collection-agent-rounds");
  const note = document.querySelector("#collection-agent-note");
  const goalsBox = document.querySelector("#collection-agent-goals");
  const summary = document.querySelector("#collection-agent-summary");
  const iterations = document.querySelector("#collection-agent-iterations");
  const gaps = document.querySelector("#collection-agent-gaps");
  const actions = document.querySelector("#collection-agent-next-actions");
  if (!gate || !rounds || !note || !summary || !iterations || !gaps || !actions) return;
  if (!report) {
    gate.textContent = "待检测";
    gate.className = "status-badge is-review";
    rounds.textContent = "未执行";
    note.textContent = "当前任务未返回 Agent 闭环报告。";
    if (goalsBox) goalsBox.innerHTML = "";
    summary.innerHTML = "";
    iterations.innerHTML = "";
    gaps.innerHTML = "";
    actions.innerHTML = "";
    return;
  }
  const gateLabel = report.quality_gate === "PASS" ? "已通过质量门" : report.quality_gate === "PARTIAL" ? "主目标已达成" : "需继续换方法";
  gate.textContent = gateLabel;
  gate.className = `status-badge ${statusClass(report.quality_gate)}`;
  rounds.textContent = `${report.completed_rounds}/${report.max_rounds} 轮`;
  note.textContent = localizeNarrative(report.stop_reason || report.note || "观察缺口后更换尚未尝试的方法。");
  if (goalsBox) {
    goalsBox.innerHTML = (report.goals || []).map((goal) => `<article class="${goal.met ? "is-met" : ""}">
      <span>${goal.required ? "必需目标" : "可选目标"} · ${goal.met ? "已达成" : "未达成"}</span>
      <strong>${escapeHtml(goal.label)}</strong>
      <small>${escapeHtml(goal.evidence || "")}</small>
    </article>`).join("");
  }
  const critical = report.critical_gaps || [];
  const recommended = report.recommended_gaps || [];
  summary.innerHTML = [
    ["状态", report.status],
    ["诊断", report.diagnosis || "未记录"],
    ["关键缺口", critical.length],
    ["已试方法", (report.strategies_tried || []).length],
    ["下一步动作", (report.next_actions || []).length],
  ].map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`).join("");
  iterations.innerHTML = (report.iterations || []).map((item) => `<article class="collection-iteration ${item.quality_gate === "PASS" ? "is-pass" : "is-review"}">
    <div class="collection-iteration-head"><strong>第 ${escapeHtml(item.round_number)} 轮 · ${escapeHtml(item.diagnosis_label || item.phase)}</strong><span class="status-badge ${statusClass(item.quality_gate)}">${escapeHtml(item.decision || item.quality_gate)}</span></div>
    <p>${escapeHtml(item.note)}</p>
    <small>来源 ${escapeHtml(item.source_count)} 类 · ${escapeHtml(item.row_count)} 行 · ${escapeHtml(item.column_count)} 列 · 已达成 ${escapeHtml((item.goals_met || []).length)} · 未闭合 ${escapeHtml((item.goals_open || []).length)}</small>
    <small>本轮可见字段：${escapeHtml((item.available_fields || []).map((field) => fieldLabel(state.result?.modeling_dataset, field)).slice(0, 14).join("、") || "尚未形成患者/样本宽表")}</small>
    ${(item.actions || []).length ? `<ul>${item.actions.map((action) => `<li>${escapeHtml(action)}</li>`).join("")}</ul>` : ""}
  </article>`).join("") || '<p class="muted-visual">尚未形成迭代记录。</p>';
  const renderGap = (gap, kind) => `<article class="collection-gap ${kind === "critical" ? "is-critical" : "is-recommended"}">
    <div><strong>${escapeHtml(gap.label)}</strong><span>${kind === "critical" ? "关键" : "建议"}</span></div>
    <small>${escapeHtml(gap.variable_id)} · 覆盖率 ${gap.coverage_rate == null ? "未计算" : `${(gap.coverage_rate * 100).toFixed(1)}%`}</small>
    <p>${escapeHtml(gap.reason)}</p>
    <em>建议来源：${escapeHtml((gap.suggested_sources || []).join("、") || "待规则匹配")}</em>
    ${(gap.field_evidence || []).length ? `<small class="collection-evidence">已登记证据：${gap.field_evidence.map((item) => `${item.source_name}（${item.status}）`).join("、")}</small>` : '<small class="collection-evidence">尚未登记可核验的字段来源。</small>'}
  </article>`;
  gaps.innerHTML = critical.map((gap) => renderGap(gap, "critical")).join("")
    + recommended.map((gap) => renderGap(gap, "recommended")).join("")
    || '<p class="muted-visual">当前没有待补充字段。</p>';
  actions.innerHTML = (report.next_actions || []).map((action) => `<article>
    <div><strong>${escapeHtml(action.strategy_label || action.source_name)}</strong><span class="status-badge ${statusClass(action.status)}">${escapeHtml(action.status)}</span></div>
    <small>${escapeHtml(action.tool_name)} · 优先级 ${escapeHtml(action.priority)} · ${escapeHtml(JSON.stringify(action.arguments || {}, null, 0))}</small>
    <p>${escapeHtml(action.rationale)}</p>
  </article>`).join("") || '<p class="muted-visual">没有可继续缩小缺口的合法方法，或质量门已通过。</p>';
}

function renderDataAlignment(report) {
  const status = document.querySelector("#data-alignment-status");
  const note = document.querySelector("#data-alignment-note");
  const summary = document.querySelector("#data-alignment-summary");
  const namespace = document.querySelector("#data-alignment-namespace");
  const basis = document.querySelector("#data-alignment-basis");
  const limitations = document.querySelector("#data-alignment-limitations");
  const sources = document.querySelector("#data-alignment-sources");
  if (!status || !note || !summary || !namespace || !basis || !limitations || !sources) return;
  if (!report) {
    status.textContent = "待判定";
    status.className = "status-badge is-review";
    note.textContent = "当前任务未返回实体对齐审计。";
    summary.innerHTML = "";
    namespace.textContent = "";
    basis.innerHTML = "";
    limitations.innerHTML = "";
    sources.innerHTML = "";
    return;
  }
  status.textContent = report.entity_match_status
    ? `${report.entity_match_status} · ${report.status || "待判定"}`
    : (report.status || "待判定");
  status.className = `status-badge ${statusClass(report.entity_match_status || report.status)}`;
  note.textContent = report.entity_match_note || report.note || "仅在可审计身份空间内对齐患者与样本。";
  const percent = (value) => value == null ? "未计算" : `${(Number(value) * 100).toFixed(1)}%`;
  const yesNo = (value) => value == null ? "未判定" : value ? "是" : "否";
  summary.innerHTML = [
    ["主表行数", report.row_count],
    ["患者数量", report.patient_count],
    ["样本数量", report.sample_count],
    ["患者编号覆盖", percent(report.patient_id_coverage_rate)],
    ["样本编号覆盖", percent(report.sample_id_coverage_rate)],
    ["研究编号一致", yesNo(report.same_study)],
    ["行级来源一致", yesNo(report.same_source)],
    ["跨来源患者合并", report.cross_source_join_status || "未判定"],
    ["实体匹配", report.entity_match_status || "REVIEW"],
  ].map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></article>`).join("");
  namespace.textContent = `身份命名空间：${report.identity_namespace || "研究编号 + 来源内原始编号"}`;
  basis.innerHTML = (report.alignment_basis || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  limitations.innerHTML = (report.limitations || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  sources.innerHTML = (report.sources || []).map((item) => `<article class="${item.role === "主数据集来源" ? "is-primary" : "is-unselected"}">
    <div><strong>${escapeHtml(item.source_name)}</strong><span>${escapeHtml(item.role)}</span></div>
    <small><code>${escapeHtml(item.source_id)}</code>${item.accession ? ` · ${escapeHtml(item.accession)}` : ""}</small>
    <p>${escapeHtml(item.row_count)} 行 · ${escapeHtml(item.patient_count)} 位患者 · ${escapeHtml(item.sample_count)} 个样本</p>
    <em>${escapeHtml(item.note)}</em>
  </article>`).join("") || '<p class="muted-visual">尚无来源身份记录。</p>';
}

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
  const sourceEntries = new Set([
    ...sources.map((source) => `${canonicalDatabaseName(source.source_name)}:${source.accession || source.source_id}`),
    ...(candidates || []).map((candidate) => `${canonicalDatabaseName(candidate.source_database)}:${candidate.accession || candidate.dataset_id}`),
  ]);
  const reportMetrics = new Map((state.result?.competition_report?.metrics || []).map((metric) => [metric.name, metric]));
  const sourceAuditMetric = reportMetrics.get("来源审计完整度") || reportMetrics.get("来源可追溯率");
  const questionFitMetric = reportMetrics.get("请求要素覆盖率") || reportMetrics.get("请求变量覆盖率");
  const explorationMetric = reportMetrics.get("科研探索可用性") || reportMetrics.get("分析可用性");
  const sourceAuditPercent = metricPercentValue(sourceAuditMetric);
  const questionFitPercent = metricPercentValue(questionFitMetric);
  const explorationPercent = metricPercentValue(explorationMetric);
  const fieldCompleteness = readiness.field_completeness_rate == null ? null : readiness.field_completeness_rate * 100;
  const variableCoverage = readiness.requested_variable_coverage_rate == null ? null : readiness.requested_variable_coverage_rate * 100;
  const metricCards = [
    { label: "数据记录", value: readiness.row_count, suffix: "条", detail: "清洗后的患者/样本级记录" },
    { label: "结局匹配", value: readiness.target_match ? "匹配" : "不匹配", suffix: "", detail: readiness.target_match ? fieldLabel(dataset, readiness.target_column) : "没有用其他结局替代" },
    { label: "结局完整率", percent: outcomeCompleteness, detail: readiness.target_column ? fieldLabel(dataset, readiness.target_column) : "尚未识别结局字段" },
    { label: "全表字段完整率", percent: fieldCompleteness, detail: "基于主科研数据集的非审计字段计算" },
    {
      label: "主表基因变量覆盖",
      percent: variableCoverage,
      detail: variableCoverage == null
        ? "科研问题未指定基因"
        : "只看同一患者级主表是否含请求基因；不把外部候选库硬拼成患者变量",
    },
    {
      label: "请求要素覆盖率",
      percent: questionFitPercent ?? variableCoverage,
      detail: questionFitMetric?.detail || "综合疾病、结局、基因/分子证据、治疗和数据类型匹配",
    },
    { label: "数据库类型数", value: sourceDatabases.size, suffix: "类", detail: [...sourceDatabases].join("、") || "尚无来源" },
    { label: "实际检索入口", value: sourceEntries.size, suffix: "个", detail: "按数据库类型 + accession / study_id / project_id 去重" },
    {
      label: "来源审计完整度",
      percent: sourceAuditPercent ?? traceabilityRate,
      detail: sourceAuditMetric?.detail || (sources.length ? `${traceableCount}/${sources.length} 个来源具备 source_id 与官方地址` : "尚无来源记录"),
    },
    {
      label: "科研探索可用性",
      percent: explorationPercent,
      detail: explorationMetric?.detail || "综合样本量、结局完整性、字段完整性、问题匹配和类别分布",
    },
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
  renderModelMetricComparison(state.result?.competition_report);

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
    ["主表基因变量覆盖", readiness.requested_variable_coverage_rate == null ? "未指定基因变量" : `${(readiness.requested_variable_coverage_rate * 100).toFixed(1)}%`],
    ["请求要素覆盖率", questionFitPercent == null ? "未计算" : `${questionFitPercent.toFixed(1)}%`],
    ["来源审计完整度", sourceAuditPercent == null ? "未计算" : `${sourceAuditPercent.toFixed(1)}%`],
    ["重复患者", readiness.repeated_patient_count],
    ["重复样本行", readiness.duplicate_row_count],
    ["分析分组建议", readiness.split_strategy],
  ];
  document.querySelector("#readiness-facts").innerHTML = facts.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  document.querySelector("#cleaning-action-list").innerHTML = (readiness.cleaning_actions?.length ? readiness.cleaning_actions : ["本次没有可执行的患者级清洗动作。"]).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  document.querySelector("#warning-list").innerHTML = (readiness.warnings.length ? readiness.warnings : ["未发现阻断性风险。 "]).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  document.querySelector("#recommendation-list").innerHTML = readiness.recommendations.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function renderUnifiedEvaluation(report) {
  const unified = report?.unified_evaluation;
  const status = document.querySelector("#unified-evaluation-status");
  const version = document.querySelector("#unified-evaluation-version");
  const notice = document.querySelector("#unified-evaluation-notice");
  const layers = document.querySelector("#evaluation-layer-grid");
  const flow = document.querySelector("#evaluation-flow-visual");
  const fitnessScore = document.querySelector("#fitness-score");
  const fitnessGate = document.querySelector("#fitness-gate");
  const dimensions = document.querySelector("#fitness-dimensions");
  const gaps = document.querySelector("#fitness-gaps");
  const modelVisual = document.querySelector("#model-comparison-visual");
  const modelBody = document.querySelector("#unified-model-table tbody");
  const horizontal = document.querySelector("#horizontal-comparison-list");
  const stratifiedVisual = document.querySelector("#stratified-visual");
  const stratifiedBody = document.querySelector("#stratified-table tbody");
  if (!status || !version || !notice || !layers || !flow || !fitnessScore || !fitnessGate || !dimensions || !gaps || !modelVisual || !modelBody || !horizontal || !stratifiedVisual || !stratifiedBody) return;
  if (!unified) {
    status.textContent = "待接入";
    version.textContent = "v2";
    notice.textContent = "当前任务尚未返回统一评价体系结果。";
    layers.innerHTML = "";
    flow.innerHTML = "";
    dimensions.innerHTML = "";
    modelVisual.innerHTML = "";
    modelBody.innerHTML = "";
    horizontal.innerHTML = "";
    stratifiedVisual.innerHTML = "";
    stratifiedBody.innerHTML = "";
    return;
  }
  status.textContent = unified.status;
  version.textContent = unified.version;
  notice.textContent = unified.no_fake_scores_notice;
  layers.innerHTML = (unified.layers || []).map((layer) => `<article class="evaluation-layer-card">
    <span>${escapeHtml(layer.layer_id)}</span>
    <strong>${escapeHtml(layer.label)}</strong>
    <em class="${statusClass(layer.status)}">${escapeHtml(layer.status)}</em>
    <small>${escapeHtml(localizeNarrative(layer.purpose))}</small>
  </article>`).join("");
  renderEvaluationFlow(unified.layers || []);
  const fitness = unified.task_adaptive_fitness || {};
  fitnessScore.textContent = score100(fitness.fitness_score);
  fitnessScore.parentElement?.style.setProperty("--fitness-score", String(clampPercent(fitness.fitness_score) ?? 0));
  fitnessGate.textContent = fitness.quality_gate || "—";
  fitnessGate.className = `status-badge ${statusClass(fitness.quality_gate || "REVIEW")}`;
  dimensions.innerHTML = (fitness.dimensions || []).map((dimension) => `<article class="fitness-dimension">
    <span>${escapeHtml(metricLabelZh(dimension.name))}</span>
    <strong>${escapeHtml(dimension.display_value)}</strong>
    <i style="width:${(metricPercentValue(dimension) ?? 0).toFixed(1)}%"></i>
    <small>${escapeHtml(localizeNarrative(dimension.detail))}</small>
  </article>`).join("");
  gaps.innerHTML = (fitness.gap_feedback || []).length
    ? fitness.gap_feedback.map((item) => `<li>${escapeHtml(localizeNarrative(item))}</li>`).join("")
    : '<li>当前任务级科研适配度未发现需要单独列出的缺口；正式横向比较仍需批量重跑。</li>';
  modelBody.innerHTML = (unified.model_comparison || []).map((row) => {
    const current = row.status === "当前任务真实运行" ? " class=\"is-current\"" : "";
    return `<tr${current}>
      <td><strong>${escapeHtml(row.method_label)}</strong><small>${escapeHtml(row.method_id)}</small></td>
      <td>${escapeHtml(row.base_model_id || "未指定")}</td>
      <td>${escapeHtml(score100(row.fitness_score))}</td>
      <td>${escapeHtml(row.sdti_status === "NOT_EVALUATED" ? "未评测" : row.sdti_status)}</td>
      <td><span class="status-badge ${statusClass(row.quality_gate)}">${escapeHtml(row.quality_gate)}</span></td>
      <td>${escapeHtml(localizeNarrative(row.note))}</td>
    </tr>`;
  }).join("");
  renderModelComparisonVisual(unified.model_comparison || []);
  horizontal.innerHTML = (unified.horizontal_comparisons || []).map((table) => {
    const totalRows = (table.rows || []).length;
    const filledRows = (table.rows || []).filter((row) => Object.values(row).some((value) => value != null && value !== "" && value !== "待实测" && value !== "NOT_EVALUATED")).length;
    const completion = totalRows ? filledRows / totalRows * 100 : 0;
    return `<article class="comparison-item">
      <strong>${escapeHtml(table.title)}</strong>
      <span>${escapeHtml(table.status)} · ${filledRows}/${(table.rows || []).length} 行有可展示状态</span>
      <i style="width:${completion.toFixed(1)}%"></i>
      <small>${escapeHtml(localizeNarrative(table.note))}</small>
    </article>`;
  }).join("");
  renderStratifiedVisual(unified.stratified_comparisons || []);
  stratifiedBody.innerHTML = (unified.stratified_comparisons || []).map((row) => {
    const metrics = Object.entries(row.metrics || {}).map(([key, value]) => `${metricLabelZh(key)}=${metricValueText(value)}`).join("；") || "—";
    return `<tr>
      <td>${escapeHtml(row.stratum_label_zh || stratumLabelZh(row.stratum_name))}<small>${escapeHtml(row.stratum_name)}</small></td>
      <td>${escapeHtml(row.stratum_value_label_zh || valueLabelZh(row.stratum_value))}</td>
      <td>${escapeHtml(row.n)}</td>
      <td>${escapeHtml(metrics)}</td>
      <td><span class="status-badge ${statusClass(row.quality_gate)}">${escapeHtml(row.quality_gate)}</span></td>
      <td>${escapeHtml(localizeNarrative(row.note))}</td>
    </tr>`;
  }).join("");
}

function renderEvaluationFlow(layers) {
  const container = document.querySelector("#evaluation-flow-visual");
  if (!container) return;
  if (!layers.length) {
    container.innerHTML = '<p class="muted-visual">运行任务后会显示评价体系从外部基准评测到质量门的路径。</p>';
    return;
  }
  const arrows = layers.map((layer, index) => `<article class="evaluation-flow-node">
    <b>${String(index + 1).padStart(2, "0")}</b>
    <strong>${escapeHtml(layer.label)}</strong>
    <span class="${statusClass(layer.status)}">${escapeHtml(layer.status)}</span>
  </article>`).join('<em aria-hidden="true">→</em>');
  container.innerHTML = arrows;
}

function renderModelComparisonVisual(rows) {
  const container = document.querySelector("#model-comparison-visual");
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = '<p class="muted-visual">暂无模型对比结果。</p>';
    return;
  }
  const metric = document.querySelector("#model-chart-metric")?.value || "fitness_score";
  const metricLabel = metricLabelZh(metric);
  const values = rows.map((row) => {
    const raw = metric === "fitness_score"
      ? row.fitness_score
      : row.observed_metrics?.[metric];
    const score = raw == null ? null : (metric === "fitness_score" ? Number(raw) : Number(raw) * 100);
    return { row, score: Number.isFinite(score) ? Math.max(0, Math.min(100, score)) : null };
  });
  const measured = values.filter(({ score }) => score != null);
  if (measured.length < 2) {
    const current = measured.length === 1
      ? `当前只有 1 个真实观测值（${measured[0].score.toFixed(1)}%）。`
      : "当前没有真实横向观测值。";
    container.classList.remove("is-bar-chart");
    container.innerHTML = `<div class="comparison-not-ready"><strong>暂不构成横向对比</strong><p>${escapeHtml(current)} 任务级科研适配度不能替代模型对比；请在独立模型评价页用同一批问题完成至少两个模型/变体的真实运行。</p></div>`;
    return;
  }
  container.classList.add("is-bar-chart");
  container.innerHTML = `<div class="model-bar-chart" role="img" aria-label="${escapeHtml(metricLabel)}模型柱状图">${values.map(({ row, score }) => {
    const current = row.status === "当前任务真实运行" ? " is-current" : "";
    const pending = score == null ? " is-pending" : "";
    return `<article class="model-bar-column${current}${pending}">
      <strong>${escapeHtml(score == null ? "待实测" : `${score.toFixed(1)}%`)}</strong>
      <div class="model-bar-track"><i style="height:${(score ?? 0).toFixed(1)}%" aria-hidden="true"></i></div>
      <strong>${escapeHtml(row.method_label)}</strong>
      <small>${escapeHtml(row.status === "当前任务真实运行" ? "当前任务" : row.status)}</small>
    </article>`;
  }).join("")}</div><div class="model-evaluation-axis"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div>`;
}

function renderStratifiedVisual(rows) {
  const container = document.querySelector("#stratified-visual");
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = '<p class="muted-visual">暂无分层对比结果。</p>';
    return;
  }
  const gateRank = { PASS: 3, REVIEW: 2, REJECT: 1, FAIL: 1 };
  const grouped = new Map();
  rows.forEach((row) => {
    const current = grouped.get(row.stratum_name) || { n: 0, pass: 0, review: 0, fail: 0, values: [] };
    current.n += Number(row.n || 0);
    if (row.quality_gate === "PASS") current.pass += 1;
    else if (["REJECT", "FAIL"].includes(row.quality_gate)) current.fail += 1;
    else current.review += 1;
    current.values.push(row);
    grouped.set(row.stratum_name, current);
  });
  container.innerHTML = [...grouped.entries()].map(([name, group]) => {
    const worst = group.values.reduce((selected, row) => (gateRank[row.quality_gate] || 2) < (gateRank[selected.quality_gate] || 2) ? row : selected, group.values[0]);
    const status = group.fail ? "REJECT" : group.review ? "REVIEW" : "PASS";
    const total = group.pass + group.review + group.fail || 1;
    return `<article class="stratum-card is-${status.toLowerCase()}">
      <div><strong>${escapeHtml(stratumLabelZh(name))}</strong><span>样本数=${escapeHtml(group.n)} · ${escapeHtml(status)}</span></div>
      <div class="stratum-stack" role="img" aria-label="${escapeHtml(name)} PASS ${group.pass} REVIEW ${group.review} REJECT ${group.fail}">
        <i class="pass" style="width:${(group.pass / total * 100).toFixed(1)}%"></i>
        <i class="review" style="width:${(group.review / total * 100).toFixed(1)}%"></i>
        <i class="fail" style="width:${(group.fail / total * 100).toFixed(1)}%"></i>
      </div>
      <small>最弱层：${escapeHtml(worst.stratum_value_label_zh || valueLabelZh(worst.stratum_value))}｜${escapeHtml(localizeNarrative(worst.note))}</small>
    </article>`;
  }).join("");
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
  renderUnifiedEvaluation(report);
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
      byName.get("来源审计完整度") || byName.get("来源可追溯率") || { name: "来源审计完整度", display_value: "未计算", status: "待补充", detail: "来源审计" },
      byName.get("请求要素覆盖率") || byName.get("请求变量覆盖率") || { name: "请求要素覆盖率", display_value: "未计算", status: "待补充", detail: "变量匹配" },
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
  renderScientificUsability(report.scientific_usability);
}

function renderRagFlow(nodes, edges) {
  const container = document.querySelector("#rag-flow-visual");
  if (!container) return;
  if (!nodes.length) {
    container.innerHTML = '<p class="muted-visual">运行任务后会显示混合 RAG 从问题到数据集的完整路径。</p>';
    return;
  }
  const ordered = [...nodes].sort((a, b) => (a.order || 0) - (b.order || 0));
  const width = Math.max(920, ordered.length * 150);
  const height = 190;
  const gap = width / (ordered.length + 1);
  const positions = new Map(ordered.map((node, index) => [node.node_id, { x: gap * (index + 1), y: 84 }]));
  const edgeMarkup = (edges || []).map((edge) => {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (!source || !target) return "";
    const mid = (source.x + target.x) / 2;
    return `<path class="rag-flow-edge" d="M ${source.x + 44} ${source.y} C ${mid} ${source.y - 34}, ${mid} ${target.y - 34}, ${target.x - 44} ${target.y}"/><text class="rag-flow-edge-label" x="${mid}" y="${source.y - 46}">${escapeHtml(edge.label)}</text>`;
  }).join("");
  const nodeMarkup = ordered.map((node, index) => {
    const position = positions.get(node.node_id);
    const palette = ["teal", "blue", "amber", "indigo", "rose", "slate"][index % 6];
    return `<g class="rag-flow-node rag-${palette}" transform="translate(${position.x},${position.y})" tabindex="0" role="img" aria-label="${escapeHtml(node.layer)} ${escapeHtml(node.label)} ${escapeHtml(node.status)}"><circle r="35"></circle><text class="rag-flow-order" y="-42">${escapeHtml(node.layer)}</text><text class="rag-flow-label" y="2">${escapeHtml(node.label)}</text><text class="rag-flow-status" y="22">${escapeHtml(node.status)}</text><title>${escapeHtml(localizeNarrative(node.detail))}</title></g>`;
  }).join("");
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="混合 RAG 流程图"><defs><marker id="rag-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 8 4 L 0 8 z"></path></marker></defs><g>${edgeMarkup}</g><g>${nodeMarkup}</g></svg>`;
}

function renderRagMatching(matches) {
  const status = document.querySelector("#rag-matching-status");
  const summary = document.querySelector("#rag-matching-summary");
  const visual = document.querySelector("#rag-matching-visual");
  if (!status || !summary || !visual) return;
  if (!matches.length) {
    status.textContent = "待运行";
    summary.innerHTML = '<p class="muted-visual">运行任务后会显示候选数据库与科研问题的匹配热力图。</p>';
    visual.innerHTML = "";
    return;
  }
  const selectedCount = matches.filter((item) => item.selected).length;
  const avgScore = matches.reduce((sum, item) => sum + Number(item.match_score || 0), 0) / matches.length;
  status.textContent = `${selectedCount}/${matches.length} 已选用`;
  summary.innerHTML = [
    ["候选库/数据集", `${matches.length} 个`],
    ["已进入结果", `${selectedCount} 个`],
    ["平均匹配分", `${(avgScore * 100).toFixed(1)}%`],
    ["最高匹配库", matches[0]?.database || "—"],
  ].map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  const facets = ["检索相关度", "疾病语义", "分子数据", "治疗字段", "结局字段", "数据类型", "公开访问"];
  const cell = (value) => {
    const score = Math.max(0, Math.min(1, Number(value || 0)));
    const level = score >= .85 ? "high" : score >= .5 ? "mid" : score > 0 ? "low" : "none";
    return `<td><span class="rag-match-cell is-${level}" style="--match:${(score * 100).toFixed(1)}%"><b>${Math.round(score * 100)}</b></span></td>`;
  };
  visual.innerHTML = `<div class="rag-match-table-wrap"><table class="rag-match-table"><thead><tr><th>候选库</th><th>匹配分</th>${facets.map((facet) => `<th>${escapeHtml(facet)}</th>`).join("")}<th>解释</th></tr></thead><tbody>${matches.map((item) => {
    const score = Math.max(0, Math.min(1, Number(item.match_score || 0)));
    const selected = item.selected ? " is-selected" : "";
    return `<tr class="${selected}"><td><strong>${escapeHtml(item.database)}</strong><span>${escapeHtml(item.dataset_name)}</span><small>${escapeHtml(item.accession || item.dataset_id)} · ${escapeHtml(item.data_type)}</small></td><td><div class="rag-match-score"><i style="width:${(score * 100).toFixed(1)}%"></i><b>${escapeHtml(item.display_score)}</b><em class="${statusClass(item.status)}">${escapeHtml(item.status)}</em></div></td>${facets.map((facet) => cell(item.signals?.[facet])).join("")}<td><p>${escapeHtml(localizeNarrative(item.rationale))}</p><small>${escapeHtml((item.matched_facets || []).join("、") || "待复核")}</small></td></tr>`;
  }).join("")}</tbody></table></div>`;
}

function renderKnowledgeGraph(nodes, edges, summary) {
  const container = document.querySelector("#knowledge-graph-visual");
  if (!container) return;
  if (!nodes.length) {
    container.innerHTML = '<p class="muted-visual">运行真实数据任务后会显示科研问题、来源和主数据集的图谱关系。</p>';
    return;
  }
  const width = 760;
  const height = 390;
  const center = { x: 470, y: 195 };
  const question = { x: 130, y: 195 };
  const databaseNodes = nodes.filter((node) => node.node_type === "database");
  const top = 70;
  const step = databaseNodes.length > 1 ? (height - 140) / (databaseNodes.length - 1) : 0;
  const positions = new Map();
  positions.set("dataset", center);
  positions.set("question", question);
  databaseNodes.forEach((node, index) => {
    positions.set(node.node_id, { x: 300, y: databaseNodes.length === 1 ? 195 : top + step * index });
  });
  nodes.filter((node) => !positions.has(node.node_id)).forEach((node, index) => {
    positions.set(node.node_id, { x: 610, y: 95 + index * 80 });
  });
  const edgeMarkup = (edges || []).map((edge) => {
    const source = positions.get(edge.source);
    const target = positions.get(edge.target);
    if (!source || !target) return "";
    const curve = edge.relation_type === "retrieval" ? -34 : 34;
    const midX = (source.x + target.x) / 2;
    const strength = Math.max(1.4, 1.2 + Number(edge.strength || 0.4) * 3);
    return `<path class="kg-edge kg-${escapeHtml(edge.relation_type)}" stroke-width="${strength.toFixed(1)}" d="M ${source.x} ${source.y} C ${midX} ${source.y + curve}, ${midX} ${target.y - curve}, ${target.x} ${target.y}"><title>${escapeHtml(edge.label)}：${escapeHtml(edge.detail || "")}</title></path>`;
  }).join("");
  const nodeMarkup = nodes.map((node) => {
    const position = positions.get(node.node_id);
    if (!position) return "";
    const radius = node.node_type === "dataset" ? 50 : node.node_type === "question" ? 42 : 32 + Math.min(Number(node.weight || 1), 5);
    const detail = [node.group, node.status, localizeNarrative(node.detail)].filter(Boolean).join("｜");
    return `<g class="kg-node kg-node-${escapeHtml(node.node_type)}" transform="translate(${position.x},${position.y})" tabindex="0" role="img" aria-label="${escapeHtml(node.label)} ${escapeHtml(detail)}"><circle r="${radius}"></circle><text class="kg-label" y="-3">${escapeHtml(node.label)}</text><text class="kg-status" y="17">${escapeHtml(node.status || node.group)}</text><title>${escapeHtml(detail)}</title></g>`;
  }).join("");
  const stats = `${summary?.node_count ?? nodes.length} 节点 · ${summary?.edge_count ?? edges.length} 边`;
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="知识图谱可视化"><defs><marker id="kg-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 8 4 L 0 8 z"></path></marker></defs><text class="kg-caption" x="24" y="32">来源-问题-主科研数据集图谱</text><text class="kg-caption kg-caption-stat" x="24" y="54">${escapeHtml(stats)}</text><g>${edgeMarkup}</g><g>${nodeMarkup}</g></svg>`;
}

function renderScientificUsability(analysis) {
  const status = document.querySelector("#scientific-usability-status");
  const summary = document.querySelector("#scientific-usability-summary");
  const findings = document.querySelector("#scientific-usability-findings");
  const caveats = document.querySelector("#scientific-usability-caveats");
  if (!status || !summary || !findings || !caveats) return;
  if (!analysis) {
    status.textContent = "待运行";
    summary.innerHTML = '<p class="muted-visual">运行任务后会基于主科研数据集展示探索性科研适用性分析。</p>';
    findings.innerHTML = "";
    caveats.innerHTML = "";
    return;
  }
  status.textContent = analysis.status || "已分析";
  summary.innerHTML = [
    ["样本量", analysis.sample_size],
    ["结局字段", analysis.target_column || "未识别"],
    ["可用特征", `${analysis.feature_count || 0} 个`],
    ["方法", (analysis.methods || []).join("、") || "结构检查"],
  ].map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(localizeNarrative(value))}</strong></div>`).join("") + `<p>${escapeHtml(localizeNarrative(analysis.interpretation))}</p>`;
  findings.innerHTML = (analysis.findings || []).length ? analysis.findings.map((finding) => {
    const score = Math.max(0, Math.min(1, Number(finding.score || 0)));
    const counts = Object.entries(finding.group_counts || {});
    const total = counts.reduce((sum, [, count]) => sum + Number(count || 0), 0);
    const countMarkup = counts.length ? `<div class="scientific-counts">${counts.map(([label, count]) => {
      const percent = total ? Number(count) / total * 100 : 0;
      return `<span><i style="width:${percent.toFixed(1)}%"></i><b>${escapeHtml(translateValue(label))}</b><em>${escapeHtml(count)}</em></span>`;
    }).join("")}</div>` : "";
    return `<article class="scientific-finding"><div class="scientific-finding-head"><strong>${escapeHtml(localizeNarrative(finding.variable))}</strong><span>${escapeHtml(finding.method)} · n=${escapeHtml(finding.n)}</span></div><div class="association-meter" role="img" aria-label="${escapeHtml(finding.variable)} 关联强度 ${Math.round(score * 100)}%"><i style="width:${(score * 100).toFixed(1)}%"></i></div><div class="scientific-score"><b>${escapeHtml(finding.display_score)}</b><em class="${statusClass(finding.status)}">${escapeHtml(finding.status)}</em></div><p>${escapeHtml(localizeNarrative(finding.interpretation))}</p>${countMarkup}</article>`;
  }).join("") : '<p class="muted-visual">当前数据尚未形成足够稳定的相关性/类别关联条目，页面仍保留样本量、结局和字段结构检查。</p>';
  caveats.innerHTML = (analysis.caveats || ["探索性分析不等于因果推断或正式显著性检验。"]).map((item) => `<li>${escapeHtml(localizeNarrative(item))}</li>`).join("");
}

function renderDictionary(columns) {
  document.querySelector(".quality-grid")?.classList.toggle("is-empty-dictionary", columns.length === 0);
  document.querySelector("#dictionary-count").textContent = `${columns.length} 个字段`;
  document.querySelector("#dictionary-table tbody").innerHTML = columns.length ? columns.map((column) => `<tr>
    <td><code>${escapeHtml(column.name)}</code></td><td>${escapeHtml(column.label_zh)}</td>
    <td>${escapeHtml(TYPE_TRANSLATIONS[column.data_type] || column.data_type)}</td><td>${escapeHtml(column.role)}</td><td>${escapeHtml(column.description)}</td>
  </tr>`).join("") : '<tr><td colspan="5" class="muted-cell">当前任务尚未形成字段字典。</td></tr>';
}

function renderSources(sources, candidates, dataset) {
  const entryCount = new Set(sources.map((source) => `${canonicalDatabaseName(source.source_name)}:${source.accession || source.source_id}`)).size;
  document.querySelector("#source-count").textContent = `${sources.length} 个来源文件 · ${entryCount} 个入口`;
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
      const response = await fetchApi(`/api/agent/tasks/${encodeURIComponent(state.result.task_id)}/export/${format}`);
      if (!response.ok) await readJson(response);
      const filenames = {
        csv: `${state.result.task_id}-科研数据集.csv`,
        parquet: `${state.result.task_id}-科研数据集.parquet`,
        xlsx: `${state.result.task_id}-科研数据集.xlsx`,
        json: `${state.result.task_id}-科研数据集.json`,
        metadata: `${state.result.task_id}-元数据.json`,
        quality_report: `${state.result.task_id}-质量报告.json`,
      };
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filenames[format] || `${state.result.task_id}-科研数据集.${format}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      downloadStatus.textContent = `${format.toUpperCase()} 已生成并下载。`;
      showToast("科研数据集下载成功");
    } catch (error) {
      downloadStatus.textContent = error.message;
    } finally {
      const hasRows = Boolean(state.result?.modeling_dataset?.rows?.length);
      const needsRows = ["csv", "parquet", "xlsx", "json"].includes(format);
      button.disabled = needsRows && !hasRows;
    }
  });
});

function renderApiCheckResult(result) {
  const container = document.querySelector("#api-check-result");
  if (!container) return;
  const statusClassName = result.status === "连接失败" ? "is-error" : "is-success";
  const facts = [
    ["网络可达", result.reachable ? "是" : "否"],
    ["鉴权成功", result.authenticated ? "是" : "否"],
    ["模型可用", result.model_available ? "是" : "否"],
    ["函数调用", result.function_calling_available ? "已支持" : "未确认"],
    ["Agent 探测", result.agent_ready ? "通过" : "未通过/未执行"],
    ["状态", result.status],
  ];
  container.innerHTML = facts.map(([label, value]) => `<article><span>${escapeHtml(label)}</span><strong class="${statusClassName}">${escapeHtml(value)}</strong></article>`).join("")
    + `<p>${escapeHtml(result.message)} · ${escapeHtml(result.model)}</p>`;
}

async function checkApiAgent() {
  const button = document.querySelector("#api-check-submit");
  const input = document.querySelector("#api-check-key");
  const message = document.querySelector("#evaluation-workbench-message");
  if (!button || !input) return;
  if (!input.value.trim()) {
    renderApiCheckResult({ status: "连接失败", message: "请输入已轮换的新 Key；聊天中出现的旧 Key 不会被使用。", model: "—", reachable: false, authenticated: false, model_available: false, function_calling_available: false, agent_ready: false });
    return;
  }
  button.disabled = true;
  try {
    const response = await fetchApi("/api/agent/api-check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: document.querySelector("#api-check-provider").value,
        api_key: input.value,
        base_url: document.querySelector("#api-check-base-url").value,
        model: document.querySelector("#api-check-model").value || "qwen-plus",
        run_agent_probe: document.querySelector("#api-check-agent-probe").checked,
      }),
    });
    const result = await readJson(response);
    renderApiCheckResult(result);
    if (message) message.textContent = result.agent_ready ? "API 检测通过，可以运行当前会话。" : result.message;
  } catch (error) {
    renderApiCheckResult({ status: "连接失败", message: error.message, model: "—", reachable: false, authenticated: false, model_available: false, function_calling_available: false, agent_ready: false });
  } finally {
    input.value = "";
    button.disabled = false;
  }
}

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

function modelConfigTargetId(provider, model) {
  return `${provider}-${String(model).trim().toLowerCase().replace(/[^a-z0-9_-]+/g, "-")}`;
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
  const index = Number(row.dataset.modelIndex);
  const config = state.modelConfigs[index];
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
  const index = Number(row.dataset.modelIndex);
  const config = state.modelConfigs[index];
  if (!config) return;
  const button = row.querySelector(".model-connect-button");
  const status = row.querySelector(".model-config-status");
  if (!config.apiKey.trim()) {
    status.textContent = "请输入临时 Key";
    status.className = "model-config-status is-error";
    return;
  }
  button.disabled = true;
  status.textContent = "验证中";
  status.className = "model-config-status is-review";
  try {
    const response = await fetchApi("/api/agent/qwen-sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: config.provider,
        api_key: config.apiKey,
        base_url: config.baseUrl,
        model: config.model,
        workspace_id: config.workspaceId || null,
        timeout_seconds: 120,
      }),
    });
    const session = await readJson(response);
    config.targetId = modelConfigTargetId(config.provider, config.model);
    config.sessionId = session.session_id;
    config.status = "已连接";
    config.apiKey = "";
    state.modelSessions[config.targetId] = {
      sessionId: session.session_id,
      provider: config.provider,
      modelId: config.model,
      modelLabel: `${MODEL_PROVIDER_LABELS[config.provider]} ${config.model}`,
      expiresAt: session.expires_at,
    };
    renderModelConfigList();
    if (state.modelEvaluationReport) renderModelEvaluationReport(state.modelEvaluationReport);
    showToast(`${session.provider} / ${session.model} 已加入多模型测试`);
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
    await fetchApi(`/api/agent/qwen-sessions/${encodeURIComponent(config.sessionId)}`, { method: "DELETE" }).catch(() => null);
    delete state.modelSessions[config.targetId];
  }
  state.modelConfigs.splice(index, 1);
  renderModelConfigList();
  if (state.modelEvaluationReport) renderModelEvaluationReport(state.modelEvaluationReport);
}

function renderModelEvaluationReport(report) {
  state.modelEvaluationReport = report;
  const status = document.querySelector("#model-evaluation-status");
  const summary = document.querySelector("#model-evaluation-summary");
  const reportId = document.querySelector("#model-evaluation-report-id");
  const tableBody = document.querySelector("#model-evaluation-table tbody");
  const chart = document.querySelector("#model-evaluation-chart");
  const runButton = document.querySelector("#evaluation-run");
  const exportButton = document.querySelector("#evaluation-export");
  if (!status || !summary || !reportId || !tableBody || !chart) return;
  status.textContent = report.status;
  status.className = `status-badge ${statusClass(report.status)}`;
  summary.textContent = report.summary_zh;
  reportId.textContent = report.report_id;
  runButton.disabled = !Object.keys(state.modelSessions).length;
  exportButton.disabled = false;
  const questions = new Map((report.questions || []).map((item) => [item.question_id, item.question]));
  tableBody.innerHTML = (report.model_rows || []).map((row) => {
    const metrics = Object.entries(row.metrics || {}).map(([key, value]) => `${metricLabelZh(key)}=${metricValueText(value)}`).join("；") || "待实测";
    return `<tr><td><strong>${escapeHtml(row.question_id)}</strong><small>${escapeHtml(questions.get(row.question_id) || "—")}</small></td>
      <td>${escapeHtml(MODEL_PROVIDER_LABELS[row.provider] || row.provider)}</td>
      <td>${escapeHtml(row.model_label)}<small>${escapeHtml(row.model_id)}</small></td>
      <td>${escapeHtml(row.status)}</td><td>${escapeHtml(metrics)}</td>
      <td><span class="status-badge ${statusClass(row.quality_gate)}">${escapeHtml(row.quality_gate === "REVIEW" ? "待复核" : row.quality_gate)}</span></td>
      <td>${escapeHtml(localizeNarrative(row.note))}</td></tr>`;
  }).join("") || '<tr><td colspan="7" class="muted-cell">暂无测试行。</td></tr>';
  const grouped = new Map();
  (report.model_rows || []).forEach((row) => {
    const current = grouped.get(row.model_id) || { label: row.model_label, values: [] };
    const score = row.metrics?.["综合可观察分"];
    if (typeof score === "number") current.values.push(score);
    grouped.set(row.model_id, current);
  });
  const bars = [...grouped.values()].map((item) => {
    const score = item.values.length ? item.values.reduce((sum, value) => sum + value, 0) / item.values.length * 100 : null;
    return `<article class="model-evaluation-bar${score == null ? " is-pending" : ""}">
      <strong>${score == null ? "待实测" : `${score.toFixed(1)}%`}</strong>
      <div class="model-evaluation-bar-track"><i style="height:${(score || 0).toFixed(1)}%"></i></div>
      <strong>${escapeHtml(item.label)}</strong><span>${score == null ? "未运行" : "已观测"}</span>
    </article>`;
  }).join("");
  chart.innerHTML = bars ? `<div class="model-evaluation-bars">${bars}</div><div class="model-evaluation-axis"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div>` : '<p class="muted-visual">暂无可视化指标。</p>';
}

async function generateModelEvaluationPlan() {
  const button = document.querySelector("#evaluation-generate");
  const message = document.querySelector("#evaluation-workbench-message");
  button.disabled = true;
  try {
    const targets = state.modelConfigs.map((config) => ({
      target_id: config.targetId || modelConfigTargetId(config.provider, config.model),
      provider: config.provider,
      model_id: config.model,
      model_label: `${MODEL_PROVIDER_LABELS[config.provider]} ${config.model}`,
    }));
    const questionSessionId = state.qwenSessionId
      || state.modelSessions["qwen-qwen-plus"]?.sessionId
      || null;
    const payload = {
      question_count: Number(document.querySelector("#evaluation-question-count").value),
      seed_question: document.querySelector("#evaluation-seed-question").value,
      targets,
      run_mode: questionSessionId ? "live" : "dry_run",
    };
    if (questionSessionId) payload.qwen_session_id = questionSessionId;
    const report = await readJson(await fetchApi("/api/evaluation/model-tests/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }));
    renderModelEvaluationReport(report);
    message.textContent = questionSessionId ? "已使用千问会话生成问题；请点击“运行已连接模型”开始并行观测。" : "已生成规则测试问题；连接一个或多个模型后可运行真实测试。";
  } catch (error) {
    message.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function runModelEvaluation() {
  const report = state.modelEvaluationReport;
  const button = document.querySelector("#evaluation-run");
  const message = document.querySelector("#evaluation-workbench-message");
  if (!report || !Object.keys(state.modelSessions).length) {
    message.textContent = "请先连接至少一个模型临时会话，再运行真实测试。";
    return;
  }
  button.disabled = true;
  try {
    const session_ids = Object.fromEntries(
      Object.entries(state.modelSessions).map(([targetId, session]) => [targetId, session.sessionId]),
    );
    const updated = await readJson(await fetchApi("/api/evaluation/model-tests/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ report_id: report.report_id, session_ids }),
    }));
    renderModelEvaluationReport(updated);
    message.textContent = updated.summary_zh;
  } catch (error) {
    message.textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function exportModelEvaluationReport() {
  const report = state.modelEvaluationReport;
  if (!report) return;
  const response = await fetchApi(`/api/evaluation/model-tests/${encodeURIComponent(report.report_id)}/export/xlsx`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || "对比报告导出失败。");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${report.report_id}-多模型对比报告.xlsx`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

document.querySelector("#api-check-submit")?.addEventListener("click", checkApiAgent);
document.querySelector("#api-check-provider")?.addEventListener("change", (event) => {
  const defaults = MODEL_PROVIDER_DEFAULTS[event.target.value];
  document.querySelector("#api-check-model").value = defaults.model;
  document.querySelector("#api-check-base-url").value = defaults.baseUrl;
});
document.querySelector("#evaluation-generate")?.addEventListener("click", generateModelEvaluationPlan);
document.querySelector("#evaluation-run")?.addEventListener("click", runModelEvaluation);
document.querySelector("#evaluation-add-model")?.addEventListener("click", () => {
  state.modelConfigs.push({
    targetId: `custom-${Date.now()}`,
    provider: "openai_compatible",
    model: "自定义模型",
    baseUrl: "https://你的兼容接口/v1",
    apiKey: "",
    workspaceId: "",
    sessionId: null,
    status: "未连接",
  });
  renderModelConfigList();
});
document.querySelector("#evaluation-model-configs")?.addEventListener("input", (event) => {
  const field = event.target.dataset.modelField;
  const row = event.target.closest("[data-model-index]");
  if (field && row) updateModelConfigFromField(row, field, event.target.value);
});
document.querySelector("#evaluation-model-configs")?.addEventListener("change", (event) => {
  const field = event.target.dataset.modelField;
  const row = event.target.closest("[data-model-index]");
  if (field && row) updateModelConfigFromField(row, field, event.target.value);
});
document.querySelector("#evaluation-model-configs")?.addEventListener("click", (event) => {
  const row = event.target.closest("[data-model-index]");
  if (!row) return;
  const index = Number(row.dataset.modelIndex);
  if (event.target.closest(".model-connect-button")) connectEvaluationModel(row);
  if (event.target.closest(".model-remove-button")) removeEvaluationModel(index);
});
document.querySelector("#evaluation-export")?.addEventListener("click", () => exportModelEvaluationReport().catch((error) => {
  document.querySelector("#evaluation-workbench-message").textContent = error.message;
}));
document.querySelector("#model-chart-metric")?.addEventListener("change", () => {
  renderModelComparisonVisual(state.result?.competition_report?.unified_evaluation?.model_comparison || []);
});

function showToast(message) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.hidden = false;
  window.setTimeout(() => { toast.hidden = true; }, 2600);
}

checkConfiguration();
renderModelConfigList();
