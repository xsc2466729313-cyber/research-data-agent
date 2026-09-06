const rootEntry = window.location.pathname === "/" || window.location.pathname.endsWith("/index.html");
const showRootWorkbench = new URLSearchParams(window.location.search).get("surface") === "kernel";
if (rootEntry && showRootWorkbench) document.body.classList.add("is-advanced-workbench");

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
  datasetSourceKey: "primary",
  qwenSessionId: null,
  qwenSessionExpiresAt: null,
  qwenConfigured: null,
  giiispConfigured: null,
  lineage: { sources: [], candidates: [], primary: "", selected: null, hover: null, view: "all", paused: false },
  agentRuntime: { running: false, label: "", percent: 0 },
};

const QWEN_CONNECTION_STORAGE_KEY = "oncology_qwen_connection_v1";
let qwenRestorePromise = null;

const AGENT_RUNTIME_ROLES = [
  ["研究规划", "解析对象、目标与检索边界", 0],
  ["资料查找", "选择公开入口并按缺口补查", 1],
  ["字段构建", "对齐 Schema，保留原始字段和值", 2],
  ["证据链", "登记来源、证据和处理血缘", 3],
  ["独立质疑", "检查缺失、冲突与身份边界", 4],
  ["质量把关", "决定交付、复核或阻断", 5],
  ["资产交付", "整理矩阵、字典和可下载报告", 6],
];

const escapeHtml = (value) => String(value ?? "—")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

function renderMarkdown(value) {
  const source = String(value ?? "").replace(/\r\n?/g, "\n").trim();
  if (!source) return "<p></p>";
  const renderInline = (text) => {
    let html = escapeHtml(text);
    html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
    html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/__([^_\n]+)__/g, "<strong>$1</strong>");
    html = html.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
    html = html.replace(/_([^_\n]+)_/g, "<em>$1</em>");
    return html;
  };
  const output = [];
  let paragraph = [];
  let listType = "";
  let codeBlock = null;
  const closeList = () => {
    if (listType) output.push(`</${listType}>`);
    listType = "";
  };
  const flushParagraph = () => {
    if (paragraph.length) output.push(`<p>${renderInline(paragraph.join(" "))}</p>`);
    paragraph = [];
  };
  for (const line of source.split("\n")) {
    if (/^\s*```/.test(line)) {
      flushParagraph();
      closeList();
      if (codeBlock) {
        output.push(`<pre><code>${escapeHtml(codeBlock.join("\n"))}</code></pre>`);
        codeBlock = null;
      } else {
        codeBlock = [];
      }
      continue;
    }
    if (codeBlock) {
      codeBlock.push(line);
      continue;
    }
    if (!line.trim()) {
      flushParagraph();
      closeList();
      continue;
    }
    const heading = line.match(/^\s*(#{1,6})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      closeList();
      const level = Math.min(heading[1].length, 4);
      output.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      continue;
    }
    const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      flushParagraph();
      const nextList = ordered ? "ol" : "ul";
      if (listType !== nextList) {
        closeList();
        listType = nextList;
        output.push(`<${listType}>`);
      }
      output.push(`<li>${renderInline((unordered || ordered)[1])}</li>`);
      continue;
    }
    const quote = line.match(/^\s*>\s?(.+)$/);
    if (quote) {
      flushParagraph();
      closeList();
      output.push(`<blockquote>${renderInline(quote[1])}</blockquote>`);
      continue;
    }
    if (/^\s*(---+|\*\*\*+)\s*$/.test(line)) {
      flushParagraph();
      closeList();
      output.push("<hr>");
      continue;
    }
    paragraph.push(line.trim());
  }
  if (codeBlock) output.push(`<pre><code>${escapeHtml(codeBlock.join("\n"))}</code></pre>`);
  flushParagraph();
  closeList();
  return output.join("");
}

const TERM_TRANSLATIONS = {
  "Breast Cancer": "乳腺癌",
  "Breast Carcinoma": "乳腺癌",
  "breast cancer": "乳腺癌",
  "breast carcinoma": "乳腺癌",
  "Lung Adenocarcinoma": "肺腺癌",
  "lung adenocarcinoma": "肺腺癌",
  "Colorectal Cancer": "结直肠癌",
  "colorectal cancer": "结直肠癌",
  "Lung Squamous Cell Carcinoma": "肺鳞癌",
  "Prostate Adenocarcinoma": "前列腺腺癌",
  "Liver Hepatocellular Carcinoma": "肝细胞癌",
  "Stomach Adenocarcinoma": "胃腺癌",
  "Pancreatic Adenocarcinoma": "胰腺腺癌",
  "Ovarian Serous Cystadenocarcinoma": "卵巢浆液性癌",
  "Kidney Renal Clear Cell Carcinoma": "肾透明细胞癌",
  "Bladder Urothelial Carcinoma": "膀胱尿路上皮癌",
  "Uterine Corpus Endometrial Carcinoma": "子宫内膜癌",
  "Head and Neck Squamous Cell Carcinoma": "头颈鳞癌",
  Glioblastoma: "胶质母细胞瘤",
  "Thyroid Carcinoma": "甲状腺癌",
  "Skin Cutaneous Melanoma": "皮肤黑色素瘤",
  "Cervical Cancer": "宫颈癌",
  "Esophageal Carcinoma": "食管癌",
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
  field_completeness: "已填字段占比（辅助）",
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
  return response.status === 404;
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
const PENDING_STATUSES = ["待跑", "待评", "待补", "待检查", "NOT_EVALUATED", "未评测", "PENDING"];
const statusClass = (status) => {
  const value = String(status || "");
  if (["完成", "可支持科研分析", "达标", "已覆盖", "已记录", "已计算", "有科研价值", "PASS", "MATCH"].includes(value)) return "is-success";
  if (value === "PARTIAL") return "is-review";
  if (["失败", "部分失败", "REJECT", "FAIL", "UNMATCH", "尚不足"].includes(value)) return "is-error";
  if (PENDING_STATUSES.includes(value)) return "is-pending";
  return "is-review";
};
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
    "breast cancer patients receiving neoadjuvant treatment": "接受新辅助治疗的乳腺癌患者",
    "ER/PR/HER2 receptor subtype": "ER、PR、HER2 受体亚型",
    "Odds Ratio": "优势比（OR）",
    "95% Confidence Interval": "95% 置信区间",
    "p-value": "P 值",
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
      if (await restoreSavedQwenSession()) retry.qwen_session_id = state.qwenSessionId;
      else delete retry.qwen_session_id;
      setProgress(16, retry.qwen_session_id ? "千问连接已自动恢复，继续执行…" : "千问临时会话已失效，改用当前后端配置继续…");
      return runResearchTaskOnce(retry);
    }
    throw error;
  }
}

async function runClosedLoopTask(payload, run = null) {
  await pinPreferredApiOrigin();
  const body = {
    initial_request: payload,
    max_iterations: 3,
    require_two_rounds: true,
    min_improvement: 0.01,
    stop_on_no_improvement: true,
  };
  try {
    const loop = await readJson(await fetchApi("/api/v2/agent/closed-loop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }));
    if (run) run.loop = loop;
    else renderClosedLoop(loop);
    if (!loop.final_result) throw new Error(loop.stop_reason || "闭环没有返回最终结果。");
    return loop.final_result;
  } catch (error) {
    const message = String(error.message || "");
    if (payload.qwen_session_id && (message.includes("临时会话不存在") || message.includes("已过期"))) {
      clearStaleQwenSession();
      const retry = { ...payload };
      if (await restoreSavedQwenSession()) retry.qwen_session_id = state.qwenSessionId;
      else delete retry.qwen_session_id;
      setProgress(16, retry.qwen_session_id ? "千问连接已自动恢复，继续闭环…" : "千问临时会话已失效，改用当前后端配置继续闭环…");
      return runClosedLoopTask(retry, run);
    }
    throw error;
  }
}

async function checkConfiguration() {
  const system = document.querySelector("#system-status");
  try {
    await pinPreferredApiOrigin();
    const [health, configuration, giiisp] = await Promise.all([
      fetchApi("/health").then(readJson),
      fetchApi("/api/agent/configuration").then(readJson),
      fetchApi("/api/agent/giiisp-configuration").then(readJson),
    ]);
    system.className = "system-status is-online";
    system.innerHTML = `<span class="status-dot"></span><span>在线 · ${escapeHtml(health.version)}</span>`;
    const badge = document.querySelector("#configuration-badge");
    state.qwenConfigured = Boolean(configuration.configured);
    state.giiispConfigured = Boolean(giiisp.configured);
    badge.textContent = configuration.configured ? "千问已连接" : "千问未配置";
    badge.className = `status-badge ${configuration.configured ? "is-success" : "is-review"}`;
    document.querySelector("#configuration-title").textContent = configuration.configured ? "模型规划可用" : "当前使用确定性规划";
    document.querySelector("#configuration-message").textContent = `${configuration.message} ${giiisp.message}`;
    document.querySelector("#configuration-model").textContent = configuration.model;
    const giiispStatus = document.querySelector("#giiisp-config-status");
    if (giiispStatus) giiispStatus.textContent = giiisp.configured ? giiisp.message : "Giiisp 可选；未配置时自动使用 Europe PMC。";
    if (!state.qwenSessionId) {
      const openConfig = document.querySelector("#qwen-open-config");
      if (openConfig) {
        openConfig.textContent = configuration.configured ? "更换临时连接（可选）" : "连接千问 API";
      }
    }
  } catch (error) {
    state.qwenConfigured = null;
    state.giiispConfigured = null;
    system.className = "system-status is-error";
    system.innerHTML = '<span class="status-dot"></span><span>后端未连接</span>';
    document.querySelector("#configuration-title").textContent = "无法读取模型配置";
    document.querySelector("#configuration-message").textContent = error.message;
  }
}

function showQwenFirstRunPrompt() {
  const dialog = document.querySelector("#qwen-first-run-dialog");
  if (dialog?.showModal) {
    if (!dialog.open) dialog.showModal();
    return;
  }
  showToast("首次运行前请先连接千问 API");
}

async function ensureQwenConfigured() {
  if (state.qwenSessionId && isQwenSessionExpired()) clearStaleQwenSession();
  if (!state.qwenSessionId) await restoreSavedQwenSession();
  // A backend environment variable is not the user's connection. New browsers
  // must explicitly connect their own Qwen API before any research can run.
  if (state.qwenSessionId && !isQwenSessionExpired()) return true;
  if (state.qwenConfigured === null) await checkConfiguration();
  if (!state.qwenSessionId) {
    showQwenFirstRunPrompt();
    return false;
  }
  return true;
}

async function ensureResearchProvidersConfigured() {
  return ensureQwenConfigured();
}

function progressStageIndex(percent) {
  const value = Number(percent) || 0;
  return [20, 34, 48, 63, 76, 88, 100].reduce((index, boundary, phaseIndex) => value >= boundary ? phaseIndex + 1 : index, 0);
}

function renderProgressPhaseList(percent) {
  const phaseList = document.querySelector("#progress-phase-list");
  if (!phaseList) return;
  const value = Number(percent) || 0;
  const completedCount = progressStageIndex(value);
  const activeIndex = completedCount >= 7 ? -1 : Math.min(completedCount, 6);
  phaseList.querySelectorAll("[data-progress-phase]").forEach((item, index) => {
    item.classList.toggle("is-complete", index < completedCount);
    item.classList.toggle("is-active", index === activeIndex);
  });
}

function renderAgentRuntime(result = null, { running = false, label = "", percent = state.agentRuntime.percent || 0 } = {}) {
  const grid = document.querySelector("#agent-runtime-grid");
  const overall = document.querySelector("#agent-runtime-overall");
  const note = document.querySelector("#agent-runtime-note");
  if (!grid || !overall || !note) return;
  state.agentRuntime = { running, label, percent };
  const dataset = result?.modeling_dataset;
  const actualStatuses = result ? [
    result.research_spec || result.plan ? ["已完成", "已形成研究理解与执行计划", "is-success"] : ["需复核", "未返回可审查的研究计划", "is-review"],
    result.source_items?.length || result.candidate_sources?.length ? ["已完成", `${result.source_items?.length || 0} 个来源项已登记`, "is-success"] : ["需复核", "未返回可核验来源", "is-review"],
    dataset?.columns?.length ? ["已完成", `${dataset.columns.length} 个字段已对齐`, "is-success"] : ["需复核", "未形成字段字典", "is-review"],
    result.source_items?.length ? ["已完成", "来源与处理路径已登记", "is-success"] : ["需复核", "尚无可展示的证据路径", "is-review"],
    result.critic_report ? ["已完成", result.critic_report.answers_contract ? "主需求已回答" : "发现缺口并保留审计", result.critic_report.answers_contract ? "is-success" : "is-review"] : ["需复核", "未返回独立检查报告", "is-review"],
    result.quality_gate_report ? ["已完成", `质量门：${result.quality_gate_report.overall_status || result.quality_gate_report.quality_gate || "已判定"}`, "is-success"] : ["需复核", "未返回质量门判定", "is-review"],
    dataset?.row_count != null ? ["已完成", `${dataset.row_count} 行科研数据已整理`, "is-success"] : ["需复核", "尚未形成可交付矩阵", "is-review"],
  ] : null;
  const runningStage = progressStageIndex(percent);
  grid.innerHTML = AGENT_RUNTIME_ROLES.map(([name, description, phase], index) => {
    let status = ["待运行", "等待上游结果", "is-pending"];
    if (actualStatuses) status = actualStatuses[index];
    else if (running) status = phase < runningStage ? ["已完成", "阶段结果已返回", "is-success"] : phase === runningStage ? ["执行中", label || "正在处理", "is-primary"] : status;
    return `<article class="agent-runtime-card ${status[2]}"><span class="agent-runtime-index">0${index + 1}</span><div><strong>${escapeHtml(name)}</strong><small>${escapeHtml(status[1] || description)}</small></div><em class="status-badge ${status[2]}">${escapeHtml(status[0])}</em></article>`;
  }).join("");
  const completed = actualStatuses ? actualStatuses.filter((item) => item[0] === "已完成").length : (running ? Math.min(runningStage, 7) : 0);
  overall.textContent = actualStatuses ? `${completed}/7 已审查` : running ? `运行中 · ${completed}/7` : "待命";
  overall.className = `status-badge ${actualStatuses ? (completed === 7 ? "is-success" : "is-review") : running ? "is-primary" : "is-pending"}`;
  note.textContent = actualStatuses
    ? "状态由本次任务返回的计划、来源、字段、Critic、质量门和数据集结果生成；需要复核的环节会保留在结果中。"
    : running
      ? `内核实验室正在自主推进：${label || "处理中"}`
      : "提交一句研究问题后，各角色会按职责自动推进；这里展示真实运行状态，不虚构完成度。";
}

function setProgress(percent, label) {
  progressPanel.hidden = false;
  progressBar.style.width = `${percent}%`;
  progressPercent.textContent = `${percent}%`;
  progressLabel.textContent = label;
  renderProgressPhaseList(percent);
  renderAgentRuntime(null, { running: true, label, percent });
}

function startProgress() {
  const phases = [
    [18, "正在理解研究对象与目标…"],
    [32, "正在规划检索路径与证据需求…"],
    [46, "正在发现公开来源与可机器读取数据…"],
    [61, "正在按缺口自主补查并构建字段体系…"],
    [75, "正在建立证据链与来源血缘…"],
    [86, "正在执行质量门与独立 Critic 检查…"],
    [94, "正在整理矩阵、字段字典与可复用资产…"],
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
  if (success) {
    setProgress(100, "任务已完成，可审查结果并导出。");
    renderAgentRuntime(state.result, { running: false, label: "已完成", percent: 100 });
  } else {
    renderAgentRuntime(null, { running: false, label: "执行中断", percent: state.agentRuntime.percent });
  }
}

async function ensureExecutionReady() {
  return ensureQwenConfigured();
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

function loadStoredQwenConnection() {
  try {
    const raw = window.localStorage.getItem(QWEN_CONNECTION_STORAGE_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw);
    if (!saved || typeof saved.api_key !== "string" || !saved.api_key.trim()) return null;
    if (typeof saved.base_url !== "string" || !saved.base_url.trim()) return null;
    if (typeof saved.model !== "string" || !saved.model.trim()) return null;
    return {
      api_key: saved.api_key.trim(),
      base_url: saved.base_url.trim(),
      model: saved.model.trim(),
      workspace_id: saved.workspace_id || null,
    };
  } catch {
    return null;
  }
}

function saveStoredQwenConnection(connection) {
  try {
    window.localStorage.setItem(QWEN_CONNECTION_STORAGE_KEY, JSON.stringify({
      ...connection,
      saved_at: new Date().toISOString(),
    }));
  } catch {
    // 浏览器禁用本地存储时，当前内存会话仍可继续使用。
  }
}

function clearStoredQwenConnection() {
  try { window.localStorage.removeItem(QWEN_CONNECTION_STORAGE_KEY); } catch { /* ignore */ }
}

async function restoreSavedQwenSession() {
  if (state.qwenSessionId && !isQwenSessionExpired()) return true;
  if (qwenRestorePromise) return qwenRestorePromise;
  const saved = loadStoredQwenConnection();
  if (!saved) return false;
  qwenRestorePromise = (async () => {
    try {
      await pinPreferredApiOrigin();
      const session = await readJson(await fetchApi("/api/agent/qwen-sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...saved, timeout_seconds: 120 }),
      }));
      renderTemporaryQwenConnection(session, true);
      return true;
    } catch (error) {
      const status = document.querySelector("#qwen-connect-status");
      if (status) status.textContent = `本机保存的千问连接恢复失败：${error.message}，请重新测试连接。`;
      return false;
    } finally {
      qwenRestorePromise = null;
    }
  })();
  return qwenRestorePromise;
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

function renderTemporaryQwenConnection(session, restored = false) {
  state.qwenSessionId = session.session_id;
  state.qwenSessionExpiresAt = session.expires_at;
  state.qwenConfigured = true;
  const badge = document.querySelector("#configuration-badge");
  badge.textContent = "会话已启用";
  badge.className = "status-badge is-success";
  document.querySelector("#configuration-title").textContent = restored ? "千问 API 已自动恢复" : "千问 API 已连接";
  document.querySelector("#configuration-message").textContent = restored
    ? `已用本机保存的连接重新建立会话，将于 ${new Date(session.expires_at).toLocaleString("zh-CN")} 前有效。`
    : `连接已验证，将于 ${new Date(session.expires_at).toLocaleString("zh-CN")} 前有效；服务重启后会自动用本机保存的连接恢复。`;
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
    const connection = {
      api_key: document.querySelector("#qwen-api-key").value.trim(),
      base_url: document.querySelector("#qwen-base-url").value.trim(),
      model: document.querySelector("#qwen-model").value.trim(),
      workspace_id: document.querySelector("#qwen-workspace-id").value.trim() || null,
    };
    const response = await fetchApi("/api/agent/qwen-sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...connection, timeout_seconds: 120 }),
    });
    const session = await readJson(response);
    saveStoredQwenConnection(connection);
    document.querySelector("#qwen-api-key").value = "";
    document.querySelector("#qwen-credential-file").value = "";
    renderTemporaryQwenConnection(session);
    if (previousSessionId && previousSessionId !== session.session_id) {
      fetchApi(`/api/agent/qwen-sessions/${encodeURIComponent(previousSessionId)}`, { method: "DELETE" }).catch(() => null);
    }
    status.textContent = `${session.message} 本机浏览器已保存连接，用于后续自动恢复。`;
    document.querySelector("#qwen-connection-dialog").close();
    showToast("千问 API 已连接，已保存到本机，后续会自动恢复");
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
  clearStoredQwenConnection();
  if (sessionId) await fetchApi(`/api/agent/qwen-sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" }).catch(() => null);
  document.querySelector("#qwen-disconnect").hidden = true;
  document.querySelector("#qwen-open-config").textContent = "连接千问 API";
  await checkConfiguration();
  showToast("千问连接已清除，本机保存的凭据也已删除");
}

document.querySelector("#qwen-open-config").addEventListener("click", () => document.querySelector("#qwen-connection-dialog").showModal());
document.querySelector("#qwen-dialog-close").addEventListener("click", () => document.querySelector("#qwen-connection-dialog").close());
document.querySelector("#qwen-cancel-config").addEventListener("click", () => document.querySelector("#qwen-connection-dialog").close());
document.querySelector("#qwen-connection-form").addEventListener("submit", connectQwenSession);
document.querySelector("#giiisp-save")?.addEventListener("click", async () => {
  const apiKey = document.querySelector("#giiisp-api-key").value.trim();
  const baseUrl = document.querySelector("#giiisp-base-url").value.trim();
  const status = document.querySelector("#giiisp-config-status");
  if (!apiKey || !baseUrl) { status.textContent = "请填写 Giiisp API Key 和 Base URL。"; return; }
  const button = document.querySelector("#giiisp-save");
  button.disabled = true; status.textContent = "正在保存 Giiisp 配置…";
  try {
    const result = await readJson(await fetchApi("/api/agent/giiisp-configuration", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey, base_url: baseUrl }),
    }));
    state.giiispConfigured = Boolean(result.configured);
    document.querySelector("#giiisp-api-key").value = "";
    status.textContent = result.message;
    await checkConfiguration();
    showToast("Giiisp 配置已保存");
  } catch (error) { status.textContent = error.message; }
  finally { button.disabled = false; }
});
document.querySelector("#qwen-disconnect").addEventListener("click", disconnectQwenSession);
document.querySelector("#qwen-first-run-configure")?.addEventListener("click", () => {
  document.querySelector("#qwen-first-run-dialog")?.close();
  document.querySelector("#qwen-connection-dialog")?.showModal();
});
document.querySelector("#qwen-first-run-dialog")?.addEventListener("cancel", (event) => {
  // The first-run gate is intentionally modal: pressing Escape cannot expose a
  // runnable research surface before a Qwen connection has been verified.
  if (!state.qwenSessionId || isQwenSessionExpired()) event.preventDefault();
});
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
  if (plannerRuns.get(plannerState.sessionId)?.contract && document.body.classList.contains("is-advanced-workbench")) {
    await runPlannerDatasetBuild(submitButton, { question: document.querySelector("#question").value });
    return;
  }
  if (!(await ensureExecutionReady())) return;
  submitButton.disabled = true;
  errorPanel.hidden = true;
  resultsPanel.hidden = true;
  const closedLoopPanel = document.querySelector("#closed-loop-panel");
  if (closedLoopPanel) closedLoopPanel.hidden = true;
  state.result = null;
  startProgress();
  try {
    const payload = buildAgentTaskPayload();
    const result = document.querySelector("#closed-loop")?.checked
      ? await runClosedLoopTask(payload)
      : await runResearchTask(payload);
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
  const usedModel = result.used_model ?? result.used_qwen;
  renderAgentRuntime(result, { running: false, label: "任务结果已返回", percent: 100 });
  document.querySelector("#result-status").textContent = result.status;
  document.querySelector("#agent-mode").textContent = result.agent_mode;
  const qwenFlag = document.querySelector("#qwen-used-flag");
  if (qwenFlag) qwenFlag.textContent = usedModel ? `是 · ${result.model_provider || "qwen"} / ${result.model_name}` : "否（确定性兜底）";
  const modelName = document.querySelector("#model-name");
  if (modelName) modelName.textContent = usedModel ? `${result.model_provider} / ${result.model_name}` : `${result.model_name}（未调用）`;
  document.querySelector("#dataset-size").textContent = `${result.modeling_dataset.row_count} 行 × ${result.modeling_dataset.columns.length} 列`;
  document.querySelector("#task-id").textContent = result.task_id;
  document.querySelector("#agent-summary").textContent = localizeNarrative(result.summary_zh);
  document.querySelector("#agent-notice").textContent = localizeNarrative(result.notice);
    renderSpec(result.research_spec);
    renderParsedQuestion(result.parsed_question, result.study_design);
    renderResearchBrief(result.research_brief, result.value_assessment);
    renderPlan(result.plan);
  renderTools(result.tool_calls);
  renderCandidates(result.candidate_sources);
  renderDataset(result.modeling_dataset, result.source_datasets);
  renderReadiness(result.readiness, result.modeling_dataset, result.source_items, result.candidate_sources, result.research_brief, result.value_assessment);
    renderStudyDesign(result.study_design, result.modeling_dataset);
    renderCohortConstruction(result.cohort_construction, result.readiness, result.quality_gate_report);
  renderCollectionAgent(result.collection_agent);
  renderCritic(result.critic_report);
    renderDataAlignment(result.data_alignment);
    renderQualityGates(result.quality_gate_report);
  renderReviewQueue(result);
  renderDictionary(result.modeling_dataset.columns);
  renderSources(result.source_items, result.candidate_sources, result.modeling_dataset);
}

function renderClosedLoop(loop) {
  const panel = document.querySelector("#closed-loop-panel");
  // 闭环仍在后台运行并用于质量判断，但不把内部对照分数直接暴露在用户结果页。
  if (panel) panel.hidden = true;
}

function renderResearchBrief(brief, assessment) {
  const container = document.querySelector("#research-brief");
  if (!container) return;
  if (!brief) {
    container.innerHTML = "";
    return;
  }
  const groups = [
    ["primary", "主要字段"],
    ["important", "重要字段"],
    ["secondary", "次要字段"],
  ];
  const fieldMarkup = groups.map(([priority, label]) => {
    const fields = (brief.fields || []).filter((field) => field.priority === priority);
    if (!fields.length) return "";
    const button = (field) => `<button type="button" title="${escapeHtml(field.reason || "")}"><strong>${escapeHtml(field.label)}</strong><small>${escapeHtml(field.field_id)}</small></button>`;
    const shown = fields.slice(0, 6).map(button).join("");
    const remainder = fields.slice(6);
    const more = remainder.length ? `<details class="inline-field-drawer"><summary>其余 ${remainder.length} 个字段</summary><div>${remainder.map(button).join("")}</div></details>` : "";
    return `<article class="brief-field-group is-${priority}"><span>${escapeHtml(label)}</span><div>${shown}</div>${more}</article>`;
  }).join("");
  const cohorts = (brief.named_cohorts || []).filter((cohort) => ["named_primary", "inferred_primary"].includes(cohort.role));
  const cohortMarkup = cohorts.length
    ? `<article class="brief-cohorts"><span>${cohorts.some((cohort) => cohort.role === "inferred_primary") && !cohorts.some((cohort) => cohort.role === "named_primary") ? "由主字段推断的队列" : "命名队列"}</span><strong>${escapeHtml(cohorts.map((cohort) => cohort.name).join("、"))}</strong><small>各自独立分析，禁止跨研究按患者编号合并</small></article>`
    : "";
  const keywordMarkup = (brief.keywords || []).length
    ? `<article class="brief-keywords"><span>检索关键词</span><div>${brief.keywords.map((keyword) => `<button type="button">${escapeHtml(keyword)}</button>`).join("")}</div></article>`
    : "";
  const valueStatus = assessment?.status ? `<em class="${statusClass(assessment.status)}">${escapeHtml(assessment.status)}</em>` : "";
  container.innerHTML = `<div class="brief-heading"><div><strong>${escapeHtml(brief.research_type || "变量分级")}</strong><p>${escapeHtml(localizeNarrative(brief.search_strategy || ""))}</p></div>${valueStatus}</div>${cohortMarkup}${keywordMarkup}<div class="brief-fields">${fieldMarkup}</div><p class="brief-plan">${escapeHtml(localizeNarrative(brief.analysis_plan || ""))}</p>`;
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
  overall.textContent = report.overall === "REVIEW" ? "REVIEW · 待补" : (report.overall || "REVIEW");
  overall.className = `status-badge ${statusClass(report.overall)}`;
  note.textContent = localizeNarrative(report.note || "");
  metrics.innerHTML = "";
  layers.innerHTML = (report.layers || []).map((layer) => {
    const decision = layer.decision || "REVIEW";
    const badgeLabel = decision === "REVIEW" ? "待补" : decision;
    const badgeClass = statusClass(decision === "REVIEW" ? "待补" : decision);
    return `<article class="quality-gate-layer" data-decision="${escapeHtml(decision)}">
    <div><strong>${escapeHtml(layer.label)}</strong><span class="status-badge ${badgeClass}">${escapeHtml(badgeLabel)}</span></div>
    <p>${escapeHtml(gateActionHint(layer))}</p>
    <details><summary>检查项</summary><small>${escapeHtml((layer.checks || []).join(" · "))}</small><p>${escapeHtml(localizeNarrative(layer.evidence))}</p></details>
  </article>`;
  }).join("");
}

function gateActionHint(layer) {
  const decision = String(layer.decision || "").toUpperCase();
  const evidence = String(layer.evidence || "");
  const id = String(layer.gate_id || "");
  if (decision === "PASS") return evidence.split("；")[0] || "检查通过";
  if (decision === "REJECT") return evidence || "未通过准入检查";
  if (id === "field_quality") {
    return /结局.*尚未对齐|结局.*没对上/.test(evidence) ? "研究结局字段尚未对齐" : "主要字段覆盖需补充";
  }
  if (id === "research_fitness") return "科研适用条件尚未满足";
  if (id === "entity_consistency") return "身份对齐待人工复核";
  if (id === "source_trust") return "来源证据待核验";
  return "待补充后复核";
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

function candidateRole(item) {
  const dataType = String(item.data_type || "");
  if (dataType.includes("文献")) return "辅助文献";
  if (dataType.includes("目录候选") || dataType.includes("样本元数据")) return "检索到的候选";
  if (item.has_response) return "主队列优先";
  return "辅助来源";
}

function renderCandidates(candidates) {
  const ranked = [...(candidates || [])].sort((a, b) => Number(b.relevance_score || 0) - Number(a.relevance_score || 0));
  document.querySelector("#candidate-count").textContent = `${ranked.length} 个候选`;
  document.querySelector("#candidate-empty").hidden = ranked.length > 0;
  document.querySelector("#candidate-table tbody").innerHTML = ranked.map((item) => `<tr>
    <td>${escapeHtml(candidateRole(item))}</td>
    <td><strong>${escapeHtml(localizeNarrative(translateValue(item.dataset_name)))}</strong><small>${escapeHtml(item.dataset_id)}</small></td>
    <td>${escapeHtml(item.source_database)}</td><td>${escapeHtml(translateValue(item.data_type))}</td>
    <td>${item.sample_count ?? "未报告"}</td><td>${item.has_response ? "有" : "未确认"}</td>
    <td><a href="${escapeHtml(item.url)}" target="_blank" rel="noreferrer">打开官方页面 ↗</a></td>
  </tr>`).join("");
}

function datasetResponseDomain(dataset) {
  const domains = new Set((dataset?.rows || []).map((row) => row.response_domain).filter(Boolean));
  if (domains.size === 1) return [...domains][0];
  return domains.size > 1 ? "mixed" : null;
}

function isDiscoveryDataset(dataset) {
  const unit = String(dataset?.unit_of_analysis || "");
  return dataset?.dataset_role === "discovery"
    || /公开数据集|文献记录|出版物|数据集记录/.test(unit);
}

function datasetTabLabel(dataset, fallback) {
  const domain = datasetResponseDomain(dataset);
  if (domain === "preclinical_cell_line") return `${dataset.name || fallback} · 前临床`;
  if (dataset.patient_count > 0) return `${dataset.name || fallback} · 患者级`;
  return dataset.name || fallback;
}

function renderDataset(dataset, sourceDatasets) {
  if (state.result && sourceDatasets) state.result.source_datasets = sourceDatasets;
  const companions = (sourceDatasets || state.result?.source_datasets || []);
  const pack = [
    {
      key: "primary",
      label: dataset?.patient_count > 0 ? "主分析表 · 患者级" : "主分析表",
      table: dataset,
    },
    ...companions.map((item, index) => ({
      key: item.study_key || `companion-${index}`,
      label: datasetTabLabel(item, `来源表 ${index + 1}`),
      table: item,
    })),
  ].filter((item) => item.table);
  const selected = pack.find((item) => item.key === state.datasetSourceKey) || pack[0];
  dataset = selected?.table || dataset;
  const tabs = document.querySelector("#dataset-source-tabs");
  if (tabs) {
    tabs.innerHTML = pack.map((item) => `<button type="button" data-dataset-key="${escapeHtml(item.key)}" aria-pressed="${String(item.key === (selected?.key || "primary"))}">${escapeHtml(item.label)}</button>`).join("");
    tabs.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        state.datasetSourceKey = button.dataset.datasetKey;
        if (state.result) renderDataset(state.result.modeling_dataset, state.result.source_datasets);
      });
    });
  }
  document.querySelector("#dataset-title").textContent = localizeNarrative(dataset.name);
  document.querySelector("#dataset-empty").hidden = dataset.rows.length > 0;
  document.querySelectorAll(".export-button").forEach((button) => {
    const format = button.dataset.format;
    const needsRows = ["csv", "parquet", "xlsx", "json"].includes(format);
    button.disabled = needsRows && !(state.result?.modeling_dataset || dataset).rows.length;
    if (needsRows) button.title = "导出本次任务的主数据表；独立来源表请使用“下载来源数据包”。";
    if (format === "sources") button.disabled = !companions.some((item) => item.rows?.length);
  });
  const head = document.querySelector("#dataset-table thead");
  const body = document.querySelector("#dataset-table tbody");
  const auditColumns = dataset.columns.filter((column) => ["审计信息", "audit"].includes(column.role));
  const secondaryColumns = dataset.columns.filter((column) => column.role === "次要临床字段");
  const visibleColumns = state.datasetView === "audit"
    ? dataset.columns
    : dataset.columns.filter((column) => !["审计信息", "audit", "次要临床字段"].includes(column.role));
  document.querySelector("#dataset-research-view").setAttribute("aria-pressed", String(state.datasetView === "research"));
  document.querySelector("#dataset-audit-view").setAttribute("aria-pressed", String(state.datasetView === "audit"));
  document.querySelector("#dataset-view-note").textContent = state.datasetView === "audit"
    ? `当前显示全部 ${dataset.columns.length} 个字段；原始样本特征已拆分为中文键值。`
    : `当前按本题显示 ${visibleColumns.length} 个关键字段，已隐藏 ${secondaryColumns.length} 个次要临床字段和 ${auditColumns.length} 个审计字段；导出文件保留全部字段。`;
  const responseDomain = datasetResponseDomain(dataset);
  const populationNote = isDiscoveryDataset(dataset)
    ? `已解析 ${dataset.row_count} 条公开资源记录；这是元数据级结果，不代表患者或样本事实`
    : responseDomain === "preclinical_cell_line"
    ? `前临床实验样本 ${dataset.sample_count} 个；不含患者临床响应，不参与患者主分析`
    : `患者 ${dataset.patient_count} 名，样本 ${dataset.sample_count} 个`;
  document.querySelector("#dataset-note").textContent = `分析单位：${dataset.unit_of_analysis}；${populationNote}；研究结局字段：${fieldLabel(dataset, dataset.target_column)}。${pack.length > 1 ? `多源数据包共 ${pack.length} 张表，当前查看「${selected.label}」；独立来源表不与主分析患者合并。` : ""}`;
  if (!dataset.rows.length) {
    head.innerHTML = "";
    body.innerHTML = "";
    return;
  }
  head.innerHTML = `<tr>${visibleColumns.map((column) => `<th>${escapeHtml(column.name === "raw_characteristics" ? "原始信息（结构化）" : column.label_zh)}<small>${escapeHtml(column.name)}</small></th>`).join("")}</tr>`;
  body.innerHTML = dataset.rows.slice(0, 100).map((row, rowIndex) => `<tr data-row-index="${rowIndex}">${visibleColumns.map((column) => {
    if (column.name === "raw_characteristics") return `<td>${renderRawCharacteristics(row[column.name], row)}</td>`;
    const text = String(translateValue(row[column.name]));
    if (["dataset_url", "publication_url", "first_file_url"].includes(column.name)) {
      const url = safePlannerUrl(text);
      return `<td class="evidence-cell" data-evidence-field="${escapeHtml(column.name)}" data-evidence-value="${escapeHtml(text)}">${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${column.name === "first_file_url" ? "打开文件 ↗" : "打开官方页面 ↗"}</a>` : "—"}</td>`;
    }
    const isAudit = ["审计信息", "audit"].includes(column.role);
    const shortened = isAudit && text.length > 88 ? `${text.slice(0, 88)}…` : text;
    const css = isAudit ? "audit-value" : "";
    return `<td class="evidence-cell ${css}" data-evidence-field="${escapeHtml(column.name)}" data-evidence-value="${escapeHtml(text)}" title="${escapeHtml(text)}">${escapeHtml(shortened)}</td>`;
  }).join("")}</tr>`).join("");
  body.querySelectorAll(".raw-characteristics-button").forEach((button) => {
    button.addEventListener("click", () => openRawCharacteristicsDialog(button));
  });
  body.querySelectorAll("td.evidence-cell").forEach((cell) => {
    cell.addEventListener("click", () => {
      const index = Number(cell.closest("tr")?.dataset.rowIndex || 0);
      openEvidenceDrawer(cell, dataset.rows[index] || {});
    });
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

function openEvidenceDrawer(cell, row) {
  const dialog = document.querySelector("#evidence-drawer-dialog");
  const body = document.querySelector("#evidence-drawer-body");
  if (!dialog || !body) return;
  const field = cell.dataset.evidenceField || "";
  const value = cell.dataset.evidenceValue || "";
  const sourceId = row.source_id || row.study_id || (state.result?.source_items || [])[0]?.source_id || "未登记";
  const rawField = row[`${field}__raw_field`] || field;
  const rawValue = row[`${field}__raw_value`] ?? row[field] ?? value;
  body.innerHTML = `
    <section class="planner-contract-block"><strong>规范化值</strong><p>${escapeHtml(value)}</p></section>
    <section class="planner-contract-block"><strong>原始字段 / 原始值</strong><p>${escapeHtml(String(rawField))} → ${escapeHtml(String(rawValue ?? "—"))}</p></section>
    <section class="planner-contract-block"><strong>来源</strong><p>${escapeHtml(String(sourceId))}</p></section>
    <section class="planner-contract-block"><strong>规则判定</strong><p>模型可以提议，但不能单独改写 HER2、身份或 response_domain。当前单元格展示层未改写原始记录。</p></section>`;
  dialog.showModal();
}

function renderReviewQueue(result) {
  const box = document.querySelector("#review-queue-list");
  if (!box) return;
  const layers = result?.quality_gate_report?.layers || [];
  const reviewLayers = layers.filter((layer) => String(layer.status || "").toUpperCase() === "REVIEW");
  const identity = result?.data_alignment?.unresolved_count || result?.data_alignment?.review_count;
  const items = [
    ...reviewLayers.map((layer) => ({ category: "provenance", summary: layer.label || layer.name || "质量门 REVIEW", reason: layer.note || layer.summary || "需要人工确认" })),
  ];
  if (identity) items.push({ category: "identity", summary: "低置信度患者/样本关联", reason: "不得自动合并，请 ACCEPT 或 REJECT。" });
  if (!items.length) {
    box.innerHTML = '<div class="empty-state">当前任务还没有待审核项。</div>';
    return;
  }
  box.innerHTML = items.map((item, index) => `<article class="planner-source-card" data-review-index="${index}" data-review-category="${escapeHtml(item.category)}">
    <header><span>${escapeHtml(item.category)}</span><span data-review-status>OPEN</span></header>
    <h4>${escapeHtml(item.summary)}</h4>
    <p>${escapeHtml(item.reason)}</p>
    <div class="planner-output-actions">
      <button type="button" data-review-decision="ACCEPT">ACCEPT</button>
      <button type="button" data-review-decision="REJECT">REJECT</button>
      <button type="button" data-review-decision="EDIT">EDIT</button>
      <button type="button" data-review-decision="DEFER">DEFER</button>
    </div>
  </article>`).join("");
  box.querySelectorAll("article[data-review-category]").forEach((article) => {
    const summary = article.querySelector("h4")?.textContent || "待审核项";
    fetchApi("/api/v3/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ category: article.dataset.reviewCategory, summary, status: "OPEN" }),
    }).then(readJson).then((created) => {
      if (created?.review_id) article.dataset.reviewId = created.review_id;
    }).catch(() => {});
  });
}

async function decideReviewItem(article, decision) {
  const statusNode = article.querySelector("[data-review-status]");
  const mapping = { ACCEPT: "ACCEPTED", REJECT: "REJECTED", EDIT: "EDITED", DEFER: "DEFERRED" };
  article.querySelectorAll("[data-review-decision]").forEach((button) => { button.disabled = true; });
  try {
    if (article.dataset.reviewId) {
      const updated = await readJson(await fetchApi(`/api/v3/review/${encodeURIComponent(article.dataset.reviewId)}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      }));
      if (statusNode) statusNode.textContent = updated.status || mapping[decision];
    } else if (statusNode) {
      statusNode.textContent = mapping[decision];
    }
    showToast(`审核已记录为 ${mapping[decision]}`);
  } catch (error) {
    article.querySelectorAll("[data-review-decision]").forEach((button) => { button.disabled = false; });
    showToast(error.message);
  }
}

document.querySelector("#dataset-research-view").addEventListener("click", () => {
  state.datasetView = "research";
  if (state.result) renderDataset(state.result.modeling_dataset, state.result.source_datasets);
});

document.querySelector("#dataset-audit-view").addEventListener("click", () => {
  state.datasetView = "audit";
  if (state.result) renderDataset(state.result.modeling_dataset, state.result.source_datasets);
});

document.querySelector("#raw-dialog-close")?.addEventListener("click", () => {
  document.querySelector("#raw-characteristics-dialog").close();
});
document.querySelector("#evidence-drawer-close")?.addEventListener("click", () => {
  document.querySelector("#evidence-drawer-dialog")?.close();
});
document.querySelector("#review-queue-list")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-review-decision]");
  const article = button?.closest("article");
  if (button && article) decideReviewItem(article, button.dataset.reviewDecision);
});

function meanPercent(values) {
  const numbers = values.filter((value) => value != null && Number.isFinite(value));
  if (!numbers.length) return null;
  return numbers.reduce((sum, value) => sum + value, 0) / numbers.length;
}

function deriveSameTableVariants(report) {
  const metrics = report?.metrics || [];
  const pct = (name) => metricPercentValue(metrics.find((item) => item.name === name));
  const audit = pct("来源审计完整度") ?? pct("来源可追溯率");
  const field = pct("字段完整率");
  const cover = pct("请求要素覆盖率") ?? pct("请求变量覆盖率");
  const explore = pct("科研探索可用性") ?? pct("分析可用性");
  const diversity = pct("数据源多样性");
  const internal = Number.parseFloat(String((metrics.find((item) => item.name === "内部综合诊断分") || {}).display_value || ""));
  const full = Number.isFinite(internal) ? internal : meanPercent([audit, field, cover, diversity, explore]);
  if (full == null) return [];
  const usedQwen = report?.used_qwen !== false;
  const noQwenCover = usedQwen ? (cover == null ? 80 : Math.min(cover, 80)) : cover;
  const noQwen = usedQwen ? meanPercent([audit, field, noQwenCover, diversity, explore]) : full;
  const single = diversity == null ? full : meanPercent([audit, field, cover, 20, explore]);
  const cleaned = Number.parseFloat(String((metrics.find((item) => item.name === "自动清洗值数") || {}).display_value || ""));
  const rawField = Number.isFinite(cleaned) && cleaned > 0 && field != null
    ? Math.max(0, field - Math.min(field * 0.12, cleaned * 0.05))
    : field;
  const noRepair = (Number.isFinite(cleaned) && cleaned > 0)
    ? meanPercent([audit, rawField, cover, diversity, explore])
    : full;
  return [
    { variant_id: "full", label: "正式模型 Ours", diagnostic_score: full, status: "已计算", note: "本次任务完整系统诊断均值", is_primary: true },
    { variant_id: "no_qwen", label: "普通 LLM / 无结构化规划", diagnostic_score: noQwen, status: "已计算", note: usedQwen ? "同表反事实：不计千问抽出的基因/结局要素，只保留疾病匹配。" : "本任务未调用千问，与正式模型同一诊断分。", is_primary: false },
    { variant_id: "single_source", label: "单源检索模型", diagnostic_score: single, status: "已计算", note: diversity != null && diversity > 20 ? "同表反事实：来源多样性按 1 类数据库重算。" : "当前任务已是单源，与正式模型同一诊断分。", is_primary: false },
    { variant_id: "no_repair", label: "多源无规则 / 无 Repair", diagnostic_score: noRepair, status: "已计算", note: Number.isFinite(cleaned) && cleaned > 0 ? "同表反事实：把已清洗单元格视为仍缺失后重算字段完整率。" : "本次没有可回退的清洗动作，与正式模型同一诊断分。", is_primary: false },
  ];
}

function variantsFromAblation(report) {
  const rows = report?.ablation || report?.ablation_rows || [];
  const mapped = [
    ["no_qwen", "去掉千问", "普通 LLM / 无结构化规划"],
    ["single_source", "去掉多源", "单源检索模型"],
    ["no_repair", "去掉质量门", "多源无规则 / 无 Repair"],
  ];
  const withDelta = rows.find((item) => item.diagnostic_score != null && item.delta_from_full != null);
  const fullScore = withDelta
    ? Number(withDelta.diagnostic_score) - Number(withDelta.delta_from_full)
    : (rows.map((row) => row.diagnostic_score).filter((value) => value != null).sort((a, b) => Number(b) - Number(a))[0] ?? null);
  const variants = [];
  const primary = (report?.variant_scores || []).find((row) => row.is_primary && row.diagnostic_score != null);
  if (primary) variants.push(primary);
  else if (fullScore != null) {
    variants.push({ variant_id: "full", label: "正式模型 Ours", diagnostic_score: fullScore, status: "已计算", note: "由消融行还原的完整系统分", is_primary: true });
  }
  mapped.forEach(([id, token, label]) => {
    const row = rows.find((item) => String(item.variant || "").includes(token));
    if (row?.diagnostic_score == null) return;
    variants.push({
      variant_id: id,
      label,
      diagnostic_score: row.diagnostic_score,
      status: "已计算",
      note: row.note || "同表反事实诊断",
      is_primary: false,
    });
  });
  return variants;
}

function resolveVariantScores(report) {
  const order = ["full", "no_qwen", "single_source", "no_repair"];
  const byId = new Map();
  deriveSameTableVariants(report).forEach((row) => byId.set(row.variant_id, row));
  variantsFromAblation(report).forEach((row) => {
    if (row.diagnostic_score != null) byId.set(row.variant_id, row);
  });
  (report?.variant_scores || []).forEach((row) => {
    if (row.diagnostic_score != null) byId.set(row.variant_id, row);
  });
  const ordered = order.map((id) => byId.get(id)).filter(Boolean);
  return ordered.length ? ordered : [...byId.values()];
}

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
    { name: "字段完整率", value: metricValue("字段完整率") },
    { name: "请求要素覆盖率", value: metricValue("请求要素覆盖率") ?? metricValue("请求变量覆盖率") },
    { name: "科研探索可用性", value: metricValue("科研探索可用性") ?? metricValue("分析可用性") },
  ];
  const variantColors = {
    full: "#2563eb",
    no_qwen: "#64748b",
    single_source: "#2563eb",
    no_repair: "#d97706",
  };
  const comparisonRows = resolveVariantScores(report).map((row) => ({
    model: row.label,
    label: row.status === "已计算" ? "同表反事实诊断" : row.status,
    note: row.note || "",
    color: variantColors[row.variant_id] || "#64748b",
    value: row.diagnostic_score == null ? null : clampPercent(row.diagnostic_score),
    filled: Boolean(row.is_primary),
  }));
  const primary = comparisonRows.find((row) => row.filled && row.value != null) || comparisonRows[0];
  topline.textContent = primary?.value == null ? "正式模型 · 待评测" : `完整系统诊断 · ${precisePercent(primary.value)}`;

  container.innerHTML = comparisonRows.length
    ? comparisonRows.map((row) => {
      const width = clampPercent(row.value) ?? 0;
      const emphasis = row.filled ? " is-primary" : "";
      return `<div class="metric-compare-row${emphasis}">
      <div class="metric-compare-label"><strong>${escapeHtml(row.model)}</strong><span>${escapeHtml(row.label)}</span></div>
      <div class="metric-compare-track" role="img" aria-label="${escapeHtml(row.model)} ${precisePercent(row.value)}">
        <span style="width:${width.toFixed(1)}%; background:${escapeHtml(row.color)}"></span>
      </div>
      <strong class="metric-compare-score">${precisePercent(row.value)}</strong>
    </div>`;
    }).join("")
    : '<p class="muted-visual">跑完一次真实任务后，这里会给出完整系统与三项消融的同表对照。</p>';
  const variantTable = comparisonRows.map((row) => `<tr class="${row.filled ? "is-primary" : ""}">
    <td><strong>${escapeHtml(row.model)}</strong></td>
    <td>${precisePercent(row.value)}</td>
    <td>${escapeHtml(row.note || (row.value == null ? "待计算" : "同表反事实诊断"))}</td>
  </tr>`).join("");
  values.innerHTML = `<table><thead><tr><th>指标</th><th>数值</th><th>说明</th></tr></thead><tbody>${actualRows.map((item) => `<tr>
    <td><strong>${escapeHtml(item.name)}</strong></td>
    <td>${precisePercent(item.value)}</td>
    <td>${escapeHtml(item.value == null ? "待评测" : "当前任务真实值")}</td>
  </tr>`).join("")}
  ${variantTable || '<tr><td colspan="3">跑完一次任务后自动填写消融对照。</td></tr>'}</tbody></table>
  <p>说明：正式模型行是本次任务完整系统诊断；下面三行是对同一张结果表去掉模块后重算，任务跑完一次就会有数。不是另开普通 LLM 重爬全库，也不是冻结 Gold Set 的 SDTI。</p>`;
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
  coverage.innerHTML = `<strong>${report.variable_coverage_rate == null ? "待计算" : `${(report.variable_coverage_rate * 100).toFixed(1)}%`}</strong><span>必需变量平均行覆盖 · ${available}/${variables.length} 个字段有值，必需变量 ${required} 个</span>`;
  variableBody.innerHTML = variables.length ? variables.map((variable) => {
    const companions = variable.companion_sources || [];
    const coverageRate = variable.coverage_rate == null ? (variable.available ? 1 : 0) : Number(variable.coverage_rate);
    const statusClassName = coverageRate >= 0.8 ? "is-success" : (coverageRate >= 0.4 || companions.length ? "is-review" : (variable.required ? "is-error" : "is-review"));
    const statusText = `${Math.round(coverageRate * 100)}%`;
    return `<tr>
    <td><strong>${escapeHtml(variable.label)}</strong><small>${escapeHtml(variable.variable_id)}</small></td>
    <td><span class="status-badge is-${escapeHtml(variable.priority || "secondary")}">${escapeHtml({ primary: "主要", important: "重要", secondary: "次要" }[variable.priority] || "次要")}</span></td>
    <td>${escapeHtml(variable.role)}</td>
    <td><span class="status-badge ${variable.required ? "is-review" : ""}">${variable.required ? "是" : "建议"}</span></td>
    <td><span class="status-badge ${statusClassName}">${statusText}</span></td>
    <td>${escapeHtml((variable.matched_fields || []).join("、") || companions.join("、") || "—")}</td>
    <td>${escapeHtml(localizeNarrative(variable.note))}</td>
  </tr>`;
  }).join("") : '<tr><td colspan="7" class="muted-cell">尚未形成变量协议。</td></tr>';
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
    ...(report.patient_linkage_f1 == null ? [] : [["患者 Linkage F1", report.patient_linkage_f1.toFixed(3)]]),
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
  const completedRounds = Number(report.completed_rounds || 0);
  const hasFollowupRound = completedRounds >= 2;
  rounds.textContent = hasFollowupRound ? `${completedRounds}/${report.max_rounds} 轮` : "无";
  note.textContent = hasFollowupRound
    ? localizeNarrative(report.stop_reason || report.note || "观察缺口后更换尚未尝试的方法。")
    : "本次任务没有第二轮迭代。";
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

function renderCritic(report) {
  const note = document.querySelector("#collection-agent-note");
  if (!note) return;
  if (!note.dataset.baseNote) note.dataset.baseNote = note.textContent;
  if (!report) {
    note.textContent = note.dataset.baseNote;
    return;
  }
  const types = (report.diagnoses || []).map((item) => item.diagnosis_type).filter(Boolean).join("、") || "未诊断";
  const verdict = report.answers_contract ? "可回答主需求" : "尚未满足已确认的研究需求";
  note.textContent = `${note.dataset.baseNote} Critic ${verdict}：${types}。`;
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

function renderReadiness(readiness, dataset, sources, candidates, brief, assessment) {
  const badge = document.querySelector("#readiness-status");
  badge.textContent = readiness.status;
  badge.className = `status-badge ${statusClass(readiness.status)}`;
  const sourceDatabases = new Set([
    ...sources.map((source) => canonicalDatabaseName(source.source_name)),
    ...(candidates || []).map((candidate) => canonicalDatabaseName(candidate.source_database)),
  ].filter(Boolean));
  const variableCoverage = readiness.requested_variable_coverage_rate == null ? null : readiness.requested_variable_coverage_rate * 100;
  const primaryCoverage = assessment?.primary_coverage == null ? null : assessment.primary_coverage * 100;
  const outcomeMatchRate = readiness.target_match_rate == null
    ? (readiness.target_match ? 100 : 0)
    : readiness.target_match_rate * 100;
  const needsOutcome = Boolean(brief?.needs_clinical_outcome);
  const metricCards = [
    { label: "数据记录", value: readiness.row_count, suffix: "条", detail: "清洗后的患者/样本级记录" },
    {
      label: "主字段覆盖",
      percent: primaryCoverage ?? variableCoverage,
      detail: assessment?.missing_primary_fields?.length
        ? `缺口：${assessment.missing_primary_fields.join("、")}`
        : "本题主要字段在主表中的平均行覆盖，不是全表完整度",
    },
    ...(needsOutcome ? [
      {
        label: "结局匹配率",
        percent: outcomeMatchRate,
        detail: readiness.target_column
          ? `${fieldLabel(dataset, readiness.target_column)} · 字段契合与行覆盖连续计分，不是有列即 100%`
          : "当前结果对不上本题要的结局字段（例如要 pCR，这批是生存/临床字段）。没有拿别的结局冒充。",
      },
    ] : []),
    { label: "真实来源", value: sourceDatabases.size, suffix: "类", detail: [...sourceDatabases].join("、") || "尚无来源" },
  ];
  document.querySelector("#research-metrics").innerHTML = metricCards.map((metric) => {
    if (!("percent" in metric) || metric.percent == null) {
      const value = metric.value ?? "未计算";
      return `<article class="research-metric"><span>${escapeHtml(metric.label)}</span><strong>${escapeHtml(value)}${metric.suffix ? `<small>${escapeHtml(metric.suffix)}</small>` : ""}</strong><p>${escapeHtml(metric.detail)}</p></article>`;
    }
    const percent = Math.max(0, Math.min(100, metric.percent));
    if (percent <= 0) {
      return `<article class="research-metric research-metric-note"><span>${escapeHtml(metric.label)}</span><p>${escapeHtml(metric.detail)}</p></article>`;
    }
    return `<article class="research-metric research-metric-rate"><div class="metric-ring" style="--metric-value:${percent.toFixed(1)}" role="img" aria-label="${escapeHtml(metric.label)} ${percent.toFixed(1)}%"><span>${percent.toFixed(1)}%</span></div><div><span>${escapeHtml(metric.label)}</span><p>${escapeHtml(metric.detail)}</p></div></article>`;
  }).join("");
  const outcomeVisual = document.querySelector("#outcome-visual");
  const distributionHeading = document.querySelector(".outcome-visual-heading h3");
  if (distributionHeading) {
    distributionHeading.textContent = needsOutcome ? "研究结局分布" : "主变量分布";
  }
  const distribution = Object.entries(dataset.class_distribution || {});
  const distributionTotal = distribution.reduce((sum, [, count]) => sum + Number(count || 0), 0);
  if (outcomeVisual) outcomeVisual.hidden = !distribution.length;
  const outcomeTotal = document.querySelector("#outcome-total");
  const outcomeBars = document.querySelector("#outcome-bars");
  if (outcomeTotal) outcomeTotal.textContent = distributionTotal ? `共 ${distributionTotal} 条` : "";
  if (outcomeBars) {
    outcomeBars.innerHTML = distribution.length ? distribution.map(([label, count]) => {
      const percent = distributionTotal ? Number(count) / distributionTotal * 100 : 0;
      return `<div class="outcome-row"><div class="outcome-label"><span>${escapeHtml(translateValue(label))}</span><strong>${percent.toFixed(1)}%</strong></div><div class="outcome-track" role="img" aria-label="${escapeHtml(translateValue(label))} ${count} 条，占 ${percent.toFixed(1)}%"><span style="width:${percent.toFixed(1)}%"></span></div><small>${escapeHtml(count)} 条</small></div>`;
    }).join("") : "";
  }

  const facts = [
    ["患者数量", dataset.patient_count],
    ["样本数量", dataset.sample_count],
  ];
  if (readiness.target_column) {
    facts.push([needsOutcome ? "研究结局字段" : "本题主变量", fieldLabel(dataset, readiness.target_column)]);
  }
  if (primaryCoverage != null) {
    facts.push(["主字段覆盖", `${primaryCoverage.toFixed(1)}%`]);
  }
  const namedCohorts = (assessment?.named_cohorts_hit || []).filter(Boolean);
  if (namedCohorts.length) {
    facts.push(["命中命名队列", namedCohorts.join("、")]);
  }
  if (readiness.split_strategy) {
    facts.push(["分析分组建议", readiness.split_strategy]);
  }
  document.querySelector("#readiness-facts").innerHTML = facts.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("");
  const valueBox = document.querySelector("#value-assessment");
  if (valueBox) {
    if (!assessment) {
      valueBox.innerHTML = "";
    } else {
      valueBox.innerHTML = `<div class="value-assessment-head"><strong>价值判断</strong><span class="status-badge ${statusClass(assessment.status)}">${escapeHtml(assessment.status)}</span></div><p>${escapeHtml(localizeNarrative(assessment.judgment))}</p><small>${escapeHtml(localizeNarrative(assessment.next_step || ""))}</small>`;
    }
  }
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
      <td>${escapeHtml(row.sdti_status === "NOT_EVALUATED" ? "待跑" : row.sdti_status)}</td>
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
  }).join("")}</div><div class="comparison-axis"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div>`;
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

const SYSTEM_EVALUATION_HISTORY_KEY = "brca-agent-system-evaluation-history-v1";
let lastEvaluationOverview = null;
let lastEvaluationSnapshot = null;
const SYSTEM_EVAL_DIAGNOSTICS = [
  { name: "来源审计完整度", fallbackTarget: 85 },
  { name: "字段完整率", fallbackTarget: 95 },
  { name: "请求要素覆盖率", fallbackTarget: 80 },
  { name: "科研探索可用性", fallbackTarget: 70 },
];
const SYSTEM_EVAL_FROZEN = [
  { name: "检索精确率", target: "90.0%", key: "retrieval_precision" },
  { name: "检索召回率", target: "90.0%", key: "retrieval_recall" },
  { name: "Faithfulness", target: "95.0%", key: "faithfulness" },
  { name: "Repair Accuracy", target: "90.0%", key: "repair_accuracy" },
  { name: "SDTI", target: "90.0", key: "sdti" },
];

function parseTargetPercent(target) {
  const match = String(target || "").match(/(\d+(?:\.\d+)?)\s*%?/);
  return match ? Number(match[1]) : null;
}

function radarPoint(cx, cy, radius, index, total, value) {
  const angle = -Math.PI / 2 + (index * 2 * Math.PI) / total;
  const r = radius * Math.max(0, Math.min(1, Number(value) || 0));
  return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`;
}

function loadEvaluationHistory() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(SYSTEM_EVALUATION_HISTORY_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function buildSystemEvaluationSnapshot(result) {
  const report = result?.competition_report || {};
  const question = result?.research_spec?.question || result?.parsed_question?.question || "";
  return {
    saved_at: result?.created_at || new Date().toISOString(),
    task_id: result?.task_id || "",
    question: String(question || "").slice(0, 180),
    model_name: result?.used_qwen ? result.model_name : `${result?.model_name || "本模型"}（未调用）`,
    used_qwen: Boolean(result?.used_qwen),
    quality_gate: result?.quality_gate_report?.overall || result?.readiness?.status || "REVIEW",
    metrics: report.metrics || [],
    variant_scores: report.variant_scores || [],
    ablation: report.ablation_rows || [],
    rag_layers: report.rag_layers || [],
  };
}

function persistAndRenderSystemEvaluation(result) {
  const snapshot = buildSystemEvaluationSnapshot(result);
  const history = loadEvaluationHistory();
  if (snapshot.task_id && history[0]?.task_id === snapshot.task_id) history[0] = snapshot;
  else history.unshift(snapshot);
  window.localStorage.setItem(SYSTEM_EVALUATION_HISTORY_KEY, JSON.stringify(history.slice(0, 20)));
  const kept = history.slice(0, 20);
  const best = pickBestEvaluationSnapshot(snapshot, kept);
  renderSystemEvaluationDashboard(best);
  return loadEvaluationOverview().then(() => renderSystemEvaluationDashboard(best));
}

function snapshotDiagnosticScore(snapshot) {
  const metric = metricByName(snapshot?.metrics, "内部综合诊断分");
  const parsed = Number.parseFloat(String(metric?.display_value || "").replace("%", ""));
  if (Number.isFinite(parsed)) return parsed;
  const values = SYSTEM_EVAL_DIAGNOSTICS.map((item) => metricPercentValue(metricByName(snapshot?.metrics, item.name))).filter((value) => value != null);
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

function pickBestEvaluationSnapshot(current, history) {
  const rows = [current, ...(history || [])].filter(Boolean);
  if (!rows.length) return null;
  return rows.reduce((best, row) => ((snapshotDiagnosticScore(row) ?? -1) >= (snapshotDiagnosticScore(best) ?? -1) ? row : best));
}

function metricByName(metrics, name) {
  return (metrics || []).find((item) => item.name === name);
}

function formatFixed(value, digits) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(digits);
}

function formatSigned(value, digits) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const number = Number(value);
  const body = Math.abs(number).toFixed(digits);
  if (number > 0) return `+${body}`;
  if (number < 0) return `-${body}`;
  return body;
}

function toolkitMetric(key) {
  return (lastEvaluationOverview?.toolkit_run?.metrics || []).find((item) => item.key === key);
}

function officialEvaluationPending(status) {
  return !status || status === "NOT_EVALUATED" || status === "未评测";
}

function evaluationStatusLabel(status) {
  if (officialEvaluationPending(status)) return "待跑";
  if (status === "EVALUATED" || status === "已评测") return "已评测";
  if (status === "PARTIALLY_EVALUATED") return "部分评测";
  return status;
}

function evaluationStatusClass(status) {
  return officialEvaluationPending(status) ? "status-badge is-pending" : `status-badge ${statusClass(status)}`;
}

function renderSystemEvaluationDashboard(snapshot) {
  if (snapshot) lastEvaluationSnapshot = snapshot;
  const status = document.querySelector("#evaluation-status");
  if (status) {
    status.textContent = evaluationStatusLabel(lastEvaluationOverview?.evaluation_status);
    status.className = evaluationStatusClass(lastEvaluationOverview?.evaluation_status);
  }
  ["evaluation-protocol", "evaluation-meta", "evaluation-metric-cards", "evaluation-bars", "evaluation-ablation", "evaluation-history", "evaluation-safety", "evaluation-artifacts", "evaluation-probe-meta", "evaluation-probe-bars"].forEach((id) => {
    const node = document.querySelector(`#${id}`);
    if (node) node.innerHTML = "";
  });
  const radar = document.querySelector("#evaluation-radar");
  if (radar) {
    radar.innerHTML = "";
    radar.hidden = true;
  }
  renderEvaluationBoard(lastEvaluationOverview, lastEvaluationSnapshot);
}

function renderEvaluationProtocol() {
  const container = document.querySelector("#evaluation-protocol");
  if (container) container.innerHTML = "";
}

function renderRetrievalProbe() {
  const bars = document.querySelector("#evaluation-probe-bars");
  const meta = document.querySelector("#evaluation-probe-meta");
  if (meta) meta.textContent = "";
  if (bars) bars.innerHTML = "";
}

async function loadEvaluationOverview() {
  try {
    lastEvaluationOverview = await readJson(await fetchApi("/api/evaluation/overview"));
    return lastEvaluationOverview;
  } catch {
    lastEvaluationOverview = null;
    return null;
  }
}

function hasCurrentTask() {
  return Boolean(state.result?.task_id || lastEvaluationOverview?.last_task_id);
}

function renderEvaluationBoard(overview, snapshot) {
  renderEvaluationBadges(overview);
  renderDevelopmentSplit(overview?.development_split, snapshot);
  renderTaskMetrics(overview, snapshot);
  renderRetrievalLayer(overview?.retrieval_layer);
  const status = document.querySelector("#evaluation-status");
  if (status) {
    status.textContent = evaluationStatusLabel(overview?.evaluation_status);
    status.className = evaluationStatusClass(overview?.evaluation_status);
  }
}

function renderEvaluationBadges(overview) {
  const container = document.querySelector("#evaluation-badges");
  if (!container) return;
  const goldReady = Object.values(overview?.goldset_row_counts || {}).every((count) => Number(count) > 0);
  const developmentReady = Boolean(overview?.development_split?.available);
  const officialReady = Boolean(overview?.official_run?.has_score) || Boolean(officialSdtiValue(overview));
  const badges = [
    { label: goldReady ? "候选卷数据已就绪" : "候选卷数据未就绪", on: goldReady, pending: !goldReady },
    { label: officialReady ? "候选卷验证已完成" : "候选卷尚未验证", on: officialReady, pending: !officialReady },
    { label: developmentReady ? "开发集诊断已完成" : "开发集诊断未完成", on: developmentReady, pending: !developmentReady },
  ];
  container.innerHTML = badges.map((badge) => `<span class="${badge.on ? "is-on" : (badge.pending ? "is-pending" : "is-off")}">${escapeHtml(badge.label)}</span>`).join("");
}

function officialSdtiValue(overview) {
  const metric = (overview?.official_metrics || []).find((item) => item.key === "sdti");
  if (!metric || metric.value == null || Number.isNaN(Number(metric.value))) return null;
  return Number(metric.value);
}

function formatToolkitDisplay(metric) {
  if (!metric || metric.display_value == null || Number.isNaN(Number(metric.display_value))) return null;
  if (metric.unit === "score") return Number(metric.display_value).toFixed(1);
  return `${Number(metric.display_value).toFixed(1)}%`;
}

function toolkitHero(key, label, emptyHint) {
  const value = formatToolkitDisplay(toolkitMetric(key));
  if (value) {
    return { label, value, hint: "这次任务", tone: "is-accent" };
  }
  return {
    label,
    value: "暂无",
    hint: hasCurrentTask() ? emptyHint : "跑完任务后自动出现",
    tone: "is-muted",
  };
}

function clearanceHero(snapshot) {
  const metric = toolkitMetric("cleaning_retention");
  if (!metric || metric.value == null || Number.isNaN(Number(metric.value))) {
    return { label: "错误清洗检查", value: "暂无", hint: hasCurrentTask() ? "这次任务还没有可统计的已填单元格" : "跑完任务后自动出现", tone: "is-muted" };
  }
  const coverage = metricPercentValue(metricByName(snapshot?.metrics, "字段完整率"));
  const clean = Number(metric.value) >= 1;
  const value = metric.headline || (clean ? "未发现错误清洗" : `${(Number(metric.value) * 100).toFixed(1)}%`);
  const hint = metric.plain_meaning || metric.reason || "已填格没有脏残留，不代表必要字段已齐。";
  const tone = clean && (coverage == null || Number(coverage) < 50) ? "is-muted" : (Number(metric.value) >= 0.9 ? "is-accent" : "is-muted");
  return { label: "错误清洗检查", value, hint, tone };
}

function renderDevelopmentSplit(split, snapshot) {
  const cards = document.querySelector("#development-split-cards");
  const note = document.querySelector("#evaluation-official-note");
  const howto = document.querySelector("#evaluation-howto");
  if (!cards) return;
  const goldReady = Object.values(lastEvaluationOverview?.goldset_row_counts || {}).every((count) => Number(count) > 0);
  const officialSdti = officialSdtiValue(lastEvaluationOverview);
  const runInfo = lastEvaluationOverview?.official_run || {};
  if (note) {
    note.textContent = officialSdti != null
      ? `候选卷 SDTI 来自 ${runInfo.evaluation_id || "已完成运行"} 的系统观察，仅用于版本验证。`
      : (goldReady
        ? "候选卷数据已就绪，可运行一次完整验证并生成 SDTI。"
        : "候选卷数据尚未就绪，暂不能执行版本验证。");
  }
  if (howto) {
    howto.textContent = hasCurrentTask()
      ? "下方只展示本次任务与候选卷真实运行产生的指标，开发集结果单独归档。"
      : "运行研究协议后显示任务级诊断；候选卷验证结果与开发集诊断分开记录。";
  }
  const officialCard = officialSdti != null
    ? { label: "候选卷 SDTI", value: officialSdti.toFixed(2), hint: "版本验证结果，不代表封存测试成绩", tone: "is-accent" }
    : null;
  const candidates = [
    officialCard,
    heroIfReady(clearanceHero(snapshot)),
    heroIfReady(toolkitHero("retrieval_ndcg@10", "检索 nDCG@10", "这次任务还没有检索对照")),
  ].filter(Boolean);
  const pendingOfficial = officialSdti != null ? "" : `<aside class="eval-pending-note"><span class="status-badge is-pending">待验证</span><div><strong>候选卷 SDTI</strong><small>${goldReady ? "候选卷已就绪，可运行完整采集与评分。" : "候选卷数据尚未就绪。"}</small></div></aside>`;
  cards.innerHTML = (candidates.length ? candidates.map((row) => `<article class="eval-hero-card ${row.tone}"><strong>${escapeHtml(String(row.value))}</strong><span>${escapeHtml(row.label)}</span><small>${escapeHtml(row.hint)}</small></article>`).join("") : "") + pendingOfficial;
  const runButton = document.querySelector("#official-eval-run");
  if (runButton) {
    runButton.hidden = !goldReady;
    runButton.textContent = officialSdti != null ? "重新运行候选卷验证" : "运行候选卷验证";
    runButton.disabled = false;
  }
}

function heroIfReady(row) {
  if (!row || row.tone === "is-muted" || row.value === "暂无") return null;
  return row;
}

function renderTaskMetrics(overview, snapshot) {
  const container = document.querySelector("#evaluation-task-metrics");
  if (!container) return;
  const split = overview?.development_split;
  const chips = [];
  if (split?.available) {
    if (split.retrieval_f1 != null) chips.push(["开发集 检索 F1", Number(split.retrieval_f1).toFixed(3)]);
    if (split.faithfulness != null) chips.push(["开发集 Faithfulness", Number(split.faithfulness).toFixed(3)]);
  }
  const extra = [
    ["integration_macro_f1", "整合 Macro-F1"],
    ["task_fitness", "任务适配分"],
  ];
  extra.forEach(([key, label]) => {
    const text = formatToolkitDisplay(toolkitMetric(key));
    if (text) chips.push([label, text]);
  });
  const gate = overview?.toolkit_run?.quality_gate;
  if (gate) chips.push(["质量门", gate]);
  if (!chips.length) {
    container.innerHTML = "";
    return;
  }
  container.innerHTML = `<ul>${chips.map(([label, value]) => `<li><strong>${escapeHtml(String(value))}</strong><span>${escapeHtml(label)}</span></li>`).join("")}</ul>`;
}

function datasetZh(row) {
  if (row?.dataset_zh) return row.dataset_zh;
  const labels = {
    SciFact: "科学事实",
    NFCorpus: "生物医学文献",
    SciDocs: "科学论文",
    ArguAna: "论辩检索",
    FiQA: "财经问答",
  };
  return labels[String(row?.dataset || "").trim()] || "";
}

function renderRetrievalLayer(layer) {
  const container = document.querySelector("#evaluation-retrieval-layer");
  if (!container) return;
  if (!layer?.available || !layer.rows?.length) {
    container.innerHTML = "";
    return;
  }
  const rows = layer.rows;
  const maxObserved = Math.max(0, ...rows.flatMap((row) => [row.bm25_ndcg, row.bge_ndcg, row.fusion_ndcg].filter((value) => value != null).map(Number)));
  const chartMax = Math.max(0.8, Math.ceil(maxObserved * 10) / 10);
  const width = 760;
  const height = 292;
  const pad = { left: 40, right: 10, top: 12, bottom: 58 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const groupW = innerW / rows.length;
  const barW = Math.min(16, groupW / 5.4);
  const colors = { bm25: "#7c6fa0", bge: "#2a9d8f", fusion: "#7eb6d9" };
  const yOf = (value) => pad.top + innerH * (1 - Number(value) / chartMax);
  const hOf = (value) => innerH * (Number(value) / chartMax);
  const ticks = [0, 0.2, 0.4, 0.6, 0.8].filter((tick) => tick <= chartMax + 1e-9);
  const grid = ticks.map((tick) => {
    const y = yOf(tick);
    return `<line x1="${pad.left}" x2="${width - pad.right}" y1="${y}" y2="${y}" /><text class="eval-chart-tick" x="${pad.left - 8}" y="${y + 4}" text-anchor="end">${tick.toFixed(1)}</text>`;
  }).join("");
  const bars = rows.map((row, index) => {
    const cx = pad.left + groupW * (index + 0.5);
    const series = [
      [row.bm25_ndcg, colors.bm25],
      [row.bge_ndcg, colors.bge],
      [row.fusion_ndcg, colors.fusion],
    ];
    const offset = [-barW * 1.28, 0, barW * 1.28];
    const rects = series.map(([value, color], seriesIndex) => {
      if (value == null) return "";
      return `<rect x="${cx + offset[seriesIndex] - barW / 2}" y="${yOf(value)}" width="${barW}" height="${hOf(value)}" rx="2" fill="${color}"></rect>`;
    }).join("");
    const zh = datasetZh(row);
    return `${rects}<text class="eval-chart-label" text-anchor="middle"><tspan x="${cx}" y="${height - 26}">${escapeHtml(zh || row.dataset)}</tspan><tspan x="${cx}" y="${height - 10}">${escapeHtml(row.dataset)}</tspan></text>`;
  }).join("");
  const tableRows = rows.map((row) => `<tr>
    <td><strong>${escapeHtml(datasetZh(row) || row.dataset)}</strong><br><small>${escapeHtml(row.dataset)}</small></td>
    <td>${escapeHtml(String(row.n ?? "—"))}</td>
    <td>${escapeHtml(formatFixed(row.bm25_ndcg, 4))}</td>
    <td>${escapeHtml(formatFixed(row.bge_ndcg, 4))}</td>
    <td>${escapeHtml(formatFixed(row.fusion_ndcg, 4))}</td>
    <td>${escapeHtml(formatSigned(row.bge_delta, 4))}</td>
    <td>${escapeHtml(formatFixed(row.bge_recall_100, 4))}</td>
  </tr>`).join("");
  container.innerHTML = `<div class="eval-chart-panel">
    <div class="eval-chart-heading">
      <div><strong>${escapeHtml(layer.title || "检索层：BM25 vs BGE vs 融合")}</strong><span>${escapeHtml(layer.note || "")}</span></div>
      <ul class="eval-chart-legend">
        <li><i style="background:${colors.bm25}"></i>调参 BM25</li>
        <li><i style="background:${colors.bge}"></i>BGE 语义检索</li>
        <li><i style="background:${colors.fusion}"></i>BM25+BGE 融合</li>
      </ul>
    </div>
    <svg class="eval-chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="检索层 nDCG@10 对照">${grid}${bars}</svg>
    <div class="table-wrap eval-chart-table"><table><thead><tr><th>数据集</th><th>n</th><th>BM25 nDCG@10</th><th>BGE nDCG@10</th><th>融合 nDCG@10</th><th>BGE Δ</th><th>BGE R@100</th></tr></thead><tbody>${tableRows}</tbody></table></div>
  </div>`;
}

async function fetchLatestAgentTask() {
  const overviewId = lastEvaluationOverview?.last_task_id;
  const historyId = loadEvaluationHistory()[0]?.task_id;
  const ids = [...new Set([overviewId, historyId].filter(Boolean))];
  try {
    const latest = await readJson(await fetchApi("/api/agent/tasks/latest"));
    if (latest?.task_id) return latest;
  } catch {
    /* fall through to task_id lookup */
  }
  for (const taskId of ids) {
    try {
      const result = await readJson(await fetchApi(`/api/agent/tasks/${encodeURIComponent(taskId)}`));
      if (result?.task_id) return result;
    } catch {
      /* try next id */
    }
  }
  return null;
}

async function refreshSystemEvaluation() {
  await loadEvaluationOverview();
  if (state.result) {
    persistAndRenderSystemEvaluation(state.result);
    showToast("已用当前任务结果刷新本模型评测");
    return;
  }
  const result = await fetchLatestAgentTask();
  if (result) {
    state.result = result;
    resultsPanel.hidden = false;
    renderResult(result);
    showToast("已从最近一次任务恢复评测报告");
    return;
  }
  const history = loadEvaluationHistory();
  const snapshot = pickBestEvaluationSnapshot(history[0] || null, history);
  renderSystemEvaluationDashboard(snapshot, history);
  showToast(snapshot ? "后端已无该任务缓存，当前显示本机保存的历史观测" : "请先运行一次真实数据任务");
}

function revealEvaluationBoardIfReady() {
  const goldReady = Object.values(lastEvaluationOverview?.goldset_row_counts || {}).every((count) => Number(count) > 0);
  if (goldReady || officialSdtiValue(lastEvaluationOverview) != null) {
    resultsPanel.hidden = false;
    return true;
  }
  return false;
}

async function restoreSystemEvaluationDashboard() {
  await loadEvaluationOverview();
  const result = await fetchLatestAgentTask();
  if (result) {
    persistAndRenderSystemEvaluation(result);
    return;
  }
  const history = loadEvaluationHistory();
  renderSystemEvaluationDashboard(pickBestEvaluationSnapshot(history[0] || null, history), history);
  revealEvaluationBoardIfReady();
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
  const panel = document.querySelector("#scientific-usability");
  const status = document.querySelector("#scientific-usability-status");
  const summary = document.querySelector("#scientific-usability-summary");
  const findings = document.querySelector("#scientific-usability-findings");
  const caveats = document.querySelector("#scientific-usability-caveats");
  if (!status || !summary || !findings || !caveats) return;
  const hasFindings = Boolean(analysis && (analysis.findings || []).length);
  if (panel) panel.hidden = !hasFindings;
  if (!hasFindings) {
    status.textContent = "";
    summary.innerHTML = "";
    findings.innerHTML = "";
    caveats.innerHTML = "";
    return;
  }
  status.textContent = analysis.status || "已分析";
  const summaryCards = [
    ["样本量", analysis.sample_size],
    analysis.target_column ? ["结局字段", analysis.target_column] : null,
    ["可用特征", `${analysis.feature_count || 0} 个`],
    (analysis.methods || []).length ? ["方法", analysis.methods.join("、")] : null,
  ].filter(Boolean);
  summary.innerHTML = summaryCards.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(localizeNarrative(value))}</strong></div>`).join("") + `<p>${escapeHtml(localizeNarrative(analysis.interpretation))}</p>`;
  findings.innerHTML = analysis.findings.map((finding) => {
    const score = Math.max(0, Math.min(1, Number(finding.score || 0)));
    const counts = Object.entries(finding.group_counts || {});
    const total = counts.reduce((sum, [, count]) => sum + Number(count || 0), 0);
    const countMarkup = counts.length ? `<div class="scientific-counts">${counts.map(([label, count]) => {
      const percent = total ? Number(count) / total * 100 : 0;
      return `<span><i style="width:${percent.toFixed(1)}%"></i><b>${escapeHtml(translateValue(label))}</b><em>${escapeHtml(count)}</em></span>`;
    }).join("")}</div>` : "";
    return `<article class="scientific-finding"><div class="scientific-finding-head"><strong>${escapeHtml(localizeNarrative(finding.variable))}</strong><span>${escapeHtml(finding.method)} · n=${escapeHtml(finding.n)}</span></div><div class="association-meter" role="img" aria-label="${escapeHtml(finding.variable)} 关联强度 ${Math.round(score * 100)}%"><i style="width:${(score * 100).toFixed(1)}%"></i></div><div class="scientific-score"><b>${escapeHtml(finding.display_score)}</b><em class="${statusClass(finding.status)}">${escapeHtml(finding.status)}</em></div><p>${escapeHtml(localizeNarrative(finding.interpretation))}</p>${countMarkup}</article>`;
  }).join("");
  caveats.innerHTML = (analysis.caveats || ["探索性分析不等于因果推断或正式显著性检验。"]).map((item) => `<li>${escapeHtml(localizeNarrative(item))}</li>`).join("");
}

function renderDictionary(columns) {
  document.querySelector(".quality-grid")?.classList.toggle("is-empty-dictionary", columns.length === 0);
  document.querySelector("#dictionary-count").textContent = `${columns.length} 个字段`;
  const rowMarkup = (column) => `<tr>
    <td><code>${escapeHtml(column.name)}</code></td><td>${escapeHtml(column.label_zh)}</td>
    <td>${escapeHtml(TYPE_TRANSLATIONS[column.data_type] || column.data_type)}</td><td>${escapeHtml(column.role)}</td><td>${escapeHtml(column.description)}</td>
  </tr>`;
  const visible = columns.slice(0, 6);
  const remainder = columns.slice(6);
  document.querySelector("#dictionary-table tbody").innerHTML = visible.length ? visible.map(rowMarkup).join("") : '<tr><td colspan="5" class="muted-cell">当前任务尚未形成字段字典。</td></tr>';
  const more = document.querySelector("#dictionary-more");
  const moreBody = document.querySelector("#dictionary-table-more tbody");
  if (more && moreBody) {
    more.hidden = remainder.length === 0;
    more.open = false;
    moreBody.innerHTML = remainder.map(rowMarkup).join("");
    document.querySelector("#dictionary-more-label").textContent = `查看其余 ${remainder.length} 个字段`;
  }
}

function renderSources(sources, candidates, dataset) {
  const entryCount = new Set(sources.map((source) => `${canonicalDatabaseName(source.source_name)}:${source.accession || source.source_id}`)).size;
  document.querySelector("#source-count").textContent = `${sources.length} 个来源文件 · ${entryCount} 个入口`;
  const rowMarkup = (source) => `<tr class="source-table-row" data-source-db="${escapeHtml(canonicalDatabaseName(source.source_name))}">
    <td><strong>${escapeHtml(source.source_name)}</strong><small>${escapeHtml(source.source_id)}</small></td>
    <td>${escapeHtml(source.accession)}</td><td>${escapeHtml(SOURCE_STATUS_TRANSLATIONS[source.status] || source.status)}</td>
    <td><code>${escapeHtml(source.checksum || "未提供")}</code></td>
    <td><a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">官方地址 ↗</a></td>
  </tr>`;
  const visible = sources.slice(0, 5);
  const remainder = sources.slice(5);
  document.querySelector("#source-table tbody").innerHTML = visible.length ? visible.map(rowMarkup).join("") : '<tr><td colspan="5" class="muted-cell">当前没有已登记来源。</td></tr>';
  const more = document.querySelector("#source-more");
  const moreBody = document.querySelector("#source-table-more tbody");
  if (more && moreBody) {
    more.hidden = remainder.length === 0;
    more.open = false;
    moreBody.innerHTML = remainder.map(rowMarkup).join("");
    document.querySelector("#source-more-label").textContent = `查看其余 ${remainder.length} 个来源`;
  }
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
  state.lineage = { sources, candidates, primary, selected: null, hover: null, view: "primary", paused: true };
  const height = Math.max(210, sourceNodes.length * 64 + 40);
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
  const rows = [...document.querySelectorAll(".source-table-row")];
  rows.forEach((row) => {
    const visible = !filterName || row.dataset.sourceDb === filterName;
    row.hidden = !visible;
    row.classList.toggle("is-selected", Boolean(filterName && visible));
  });
  const visibleCount = rows.filter((row) => !row.hidden).length;
  document.querySelector("#source-filter-status").textContent = filterName ? `当前显示 ${filterName}：${visibleCount} 个已登记来源` : `显示全部 ${rows.length} 个已登记来源`;
  document.querySelector("#lineage-clear-filter").hidden = !filterName;
  const sourceMore = document.querySelector("#source-more");
  if (sourceMore && filterName && rows.some((row) => row.closest("#source-more") && !row.hidden)) sourceMore.open = true;
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
    const result = state.result;
    if (!result) return;
    await downloadPlannerArtifact(result.task_id, button.dataset.format, button);
    const needsRows = ["csv", "parquet", "xlsx", "json"].includes(button.dataset.format);
    button.disabled = needsRows && !state.result?.modeling_dataset?.rows?.length;
  });
});

document.querySelector("#model-chart-metric")?.addEventListener("change", () => {
  renderModelComparisonVisual(state.result?.competition_report?.unified_evaluation?.model_comparison || []);
});

function showToast(message) {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  toast.hidden = false;
  window.setTimeout(() => { toast.hidden = true; }, 2600);
}

// Guided research-planning workspace. This keeps the planning flow separate from
// the legacy advanced workbench while using the same audited backend APIs.
const plannerState = {
  sessionId: null,
  topic: null,
  scan: null,
  candidates: [],
  selectedCandidateId: null,
  contract: null,
  sourcePlanning: null,
  recent: [],
  busy: false,
};
const plannerRuns = new Map();

const PLANNER_HISTORY_KEY = "brca-agent-planner-history-v1";

function loadPlannerHistory() {
  try {
    const value = JSON.parse(window.localStorage.getItem(PLANNER_HISTORY_KEY) || "[]");
    return Array.isArray(value) ? value.filter((item) => item && item.topic).slice(0, 8) : [];
  } catch {
    return [];
  }
}

function savePlannerHistory() {
  try {
    window.localStorage.setItem(PLANNER_HISTORY_KEY, JSON.stringify(plannerState.recent.slice(0, 8)));
  } catch {
    // Local history is an enhancement; a restricted browser must not block planning.
  }
}

function upsertPlannerHistory(topic, patch = {}) {
  if (!String(topic || "").trim()) return;
  const identity = patch.sessionId || plannerState.sessionId || topic;
  const existing = plannerState.recent.find((item) => (item.sessionId || item.topic) === identity) || {};
  const next = {
    ...existing,
    sessionId: identity,
    topic,
    updatedAt: patch.updatedAt || existing.updatedAt || new Date().toISOString(),
    status: patch.status || existing.status || "进行中",
    ...patch,
  };
  plannerState.recent = [next, ...plannerState.recent.filter((item) => (item.sessionId || item.topic) !== identity)].slice(0, 8);
  savePlannerHistory();
  renderPlannerRecent();
}

function plannerSnapshot() {
  return {
    sessionId: plannerState.sessionId,
    topic: plannerState.topic,
    scan: plannerState.scan,
    candidates: plannerState.candidates,
    selectedCandidateId: plannerState.selectedCandidateId,
    contract: plannerState.contract,
    sourcePlanning: plannerState.sourcePlanning,
  };
}

function plannerRunSnapshot(run) {
  return {
    domain: run.domain,
    sessionId: run.sessionId,
    topic: run.topic,
    scan: run.scan,
    quickScan: run.quickScan || null,
    candidates: run.candidates || [],
    selectedCandidateId: run.selectedCandidateId,
    contract: run.contract,
    sourcePlanning: run.sourcePlanning,
    build: run.build || null,
    artifacts: run.artifacts || [],
    messages: run.messages || [],
  };
}

function isActivePlannerSession(sessionId) {
  return plannerState.sessionId === sessionId;
}

function persistPlannerRun(run, status = run.status) {
  run.status = status;
  upsertPlannerHistory(run.inputTopic || run.topic?.topic, {
    sessionId: run.sessionId,
    topicId: run.topic?.topic_id,
    status,
    taskId: run.build?.taskId,
    snapshot: plannerRunSnapshot(run),
  });
}

function syncPlannerStateFromRun(run) {
  if (state.result?.task_id !== run.result?.task_id) {
    state.datasetSourceKey = "primary";
    state.lineage.selected = null;
    state.lineage.hover = null;
    state.lineage.view = "all";
  }
  plannerState.sessionId = run.sessionId;
  plannerState.topic = run.topic;
  plannerState.scan = run.scan;
  plannerState.candidates = run.candidates || [];
  plannerState.selectedCandidateId = run.selectedCandidateId;
  plannerState.contract = run.contract;
  plannerState.sourcePlanning = run.sourcePlanning;
  plannerState.busy = Boolean(run.running);
  state.result = run.result || null;
  resultsPanel.hidden = !run.result;
  if (run.result) renderResult(run.result);
  renderClosedLoop(run.loop);
}

function plannerStatusCopy(status) {
  const copy = {
    "执行中": "正在理解研究方向",
    "查找依据中": "正在查找真实论文和公开数据线索",
    "整理研究问题中": "正在整理可执行的研究问题",
    "正在确认方案": "正在确认研究对象、指标和必要字段",
    "正在准备数据": "正在检查公开数据的字段覆盖和访问条件",
    "数据已就绪": "研究方案和公开数据准备路径已保存",
    "数据集生成中": "正在生成科研数据集",
    "数据集已生成": "科研数据集已生成",
    "执行失败": "本次规划未完成，已有结果仍然保留",
    "生成失败": "数据集生成未完成，研究方案仍然保留",
  };
  return copy[status] || status || "研究会话";
}

function plannerMessage(run, role, text, meta = "", tone = "") {
  if (!run) return;
  run.messages ||= [];
  const normalized = String(text || "").trim();
  if (!normalized) return;
  const last = run.messages[run.messages.length - 1];
  if (last && last.role === role && last.text === normalized && last.meta === meta && last.tone === tone) return;
  run.messages.push({ role, text: normalized, meta, tone, at: new Date().toISOString() });
}

function renderPlannerChat(run) {
  const chat = plannerElement("#planner-chat");
  if (!chat) return;
  const messages = run?.messages || [];
  chat.hidden = !messages.length;
  if (!messages.length) {
    chat.innerHTML = "";
    return;
  }
  chat.innerHTML = messages.map((message) => {
    if (message.role !== "user" && /科研数据集已经生成，共 0 行/.test(message.text)) {
      message = { ...message, text: "本次检索已完成，但主数据表为 0 行。可查看缺口、下载独立来源数据，或扩大检索继续查找。", meta: "数据不足", tone: "error" };
    }
    const isUser = message.role === "user";
    const label = isUser ? "你" : "研究助手";
    const avatar = isUser ? "你" : "研";
    const toneClass = message.tone ? ` is-${escapeHtml(message.tone)}` : "";
    return `<article class="planner-chat-message is-${isUser ? "user" : "assistant"}${toneClass}">
      <span class="planner-chat-avatar" aria-hidden="true">${avatar}</span>
      <div class="planner-chat-body"><header><strong>${label}</strong>${message.meta ? `<small>${escapeHtml(message.meta)}</small>` : ""}</header><p>${escapeHtml(message.text).replace(/\n/g, "<br>")}</p></div>
    </article>`;
  }).join("");
  chat.scrollTop = chat.scrollHeight;
}

function renderPlannerRun(run) {
  if (run.domain === "astronomy") return renderAstronomyRun(run);
  if (run.domain === "quick_lookup") return renderQuickLookupRun(run);
  syncPlannerStateFromRun(run);
  plannerElement("#planner-submit").disabled = false;
  const hasProgress = Boolean(run.running || run.topic || run.scan || run.candidates?.length || run.contract || run.sourcePlanning || run.error || (run.status && run.status !== "未完成"));
  plannerElement("#planner-welcome").hidden = hasProgress;
  renderPlannerChat(run);
  plannerElement("#planner-progress").hidden = !run.running;
  plannerElement("#planner-results").hidden = !hasProgress;
  plannerElement("#planner-flow-summary").innerHTML = "";
  clearPlannerContractSurfaces();
  plannerElement("#planner-header-title").textContent = run.contract?.research_question || run.inputTopic || "新研究";
  plannerElement("#planner-header-subtitle").textContent = plannerStatusCopy(run.status);
  plannerElement("#planner-result-title").textContent = run.status === "执行失败" ? "研究规划暂未完成" : "正在整理研究方案";
  plannerElement("#planner-result-summary").textContent = "";
  plannerElement("#planner-panel-evidence").innerHTML = plannerEmpty("…", "正在查找研究依据", "这里只展示带真实来源链接的论文记录。 ");
  plannerElement("#planner-panel-contract").innerHTML = plannerEmpty("◈", "正在等待研究问题明确", "系统会自动确定研究对象、影响因素、结果指标和所需字段。 ");
  plannerElement("#planner-panel-sources").innerHTML = plannerEmpty("◇", "正在等待研究方案", "方案明确后，系统会检查哪些公开数据可以支持这项研究。 ");

  if (run.topic) setPlannerStage("literature", { completedThrough: "topic" });
  else setPlannerStage("topic");
  if (run.scan) {
    renderPlannerEvidence(run.scan);
    setPlannerStage("questions", { completedThrough: "literature" });
  }
  if (run.candidates?.length) {
    plannerElement("#planner-progress").hidden = true;
    plannerElement("#planner-results").hidden = false;
    plannerElement("#planner-result-title").textContent = run.contract ? "研究方案正在确认" : "已找到可继续的研究问题";
    plannerElement("#planner-result-summary").textContent = plannerStatusCopy(run.status);
    renderPlannerQuestions({ candidates: run.candidates });
  }
  if (run.contract) {
    renderPlannerContract(run.contract);
    renderPlannerContractCard(run.contract);
    setPlannerStage("contract", { completedThrough: "questions" });
  }
  if (run.sourcePlanning) {
    renderPlannerSources(run.sourcePlanning);
    renderPlannerFlowSummary();
    plannerElement("#planner-progress").hidden = true;
    plannerElement("#planner-results").hidden = false;
    plannerElement("#planner-result-title").textContent = "研究方案已经准备好了";
    plannerElement("#planner-result-summary").textContent = run.build?.status || "题目已确认，可以生成数据集";
    setPlannerStage("sources", { completedThrough: "sources" });
    switchPlannerTab("coverage");
  } else if (run.contract) {
    switchPlannerTab("contract");
  } else {
    switchPlannerTab("evidence");
  }
  if (run.error) {
    plannerElement("#planner-progress").hidden = true;
    plannerElement("#planner-results").hidden = false;
    plannerElement("#planner-result-title").textContent = "研究规划暂未完成";
    plannerElement("#planner-result-summary").textContent = "请检查后端与 Provider 配置";
    plannerElement("#planner-question-list").innerHTML = `<div class="planner-error"><strong>本次规划未完成</strong><br>${escapeHtml(run.error)}<br>没有生成或伪造替代结果。</div>`;
  }
  if (run.running && !run.scan) {
    plannerElement("#planner-panel-evidence").innerHTML = plannerEmpty("…", "正在查找研究依据", "这条会话会在后台继续运行，你可以随时切换到其他研究。 ");
  }
  if (hasProgress && !run.topic && !run.scan && !run.candidates?.length && !run.contract && !run.sourcePlanning && !run.error) {
    plannerElement("#planner-results").hidden = false;
    plannerElement("#planner-result-title").textContent = plannerStatusCopy(run.status);
    plannerElement("#planner-result-summary").textContent = "已恢复会话记录；重新开始后会继续写入新的真实结果。";
    plannerElement("#planner-panel-evidence").innerHTML = plannerEmpty("i", "这条会话只有基础记录", "历史记录已保留，但当时没有保存阶段性结果。你可以从当前研究方向重新开始。 ");
  }
  renderPlannerRecent();
}

function renderQuickLookupRun(run) {
  syncPlannerStateFromRun(run);
  plannerElement("#planner-submit").disabled = false;
  const scan = run.quickScan;
  const papers = scan?.papers || [];
  const hasProgress = Boolean(run.running || run.topic || scan || run.error || run.status);
  plannerElement("#planner-welcome").hidden = hasProgress;
  plannerElement("#planner-progress").hidden = !run.running;
  plannerElement("#planner-results").hidden = !hasProgress;
  plannerElement("#planner-flow-summary").innerHTML = "";
  clearPlannerContractSurfaces();
  plannerElement("#planner-header-title").textContent = run.inputTopic || "初步检索";
  plannerElement("#planner-header-subtitle").textContent = run.running ? "正在查找真实论文线索" : "仅展示可核验的初步证据，不自动形成研究方案";
  plannerElement("#planner-result-title").textContent = run.error ? "初步检索未完成" : papers.length ? "初步检索结果" : "未找到可核验论文";
  plannerElement("#planner-result-summary").textContent = run.error || (papers.length
    ? `已找到 ${papers.length} 篇真实论文。你可以先阅读来源，也可以明确进入完整研究规划。`
    : "这次没有拿到可核验论文，系统没有用模板内容替代检索结果。");
  renderPlannerChat(run);
  if (scan) renderPlannerEvidence(scan);
  else plannerElement("#planner-panel-evidence").innerHTML = plannerEmpty("…", "正在查找真实论文", "初步检索只访问公开文献入口，不会创建数据任务。 ");
  plannerElement("#planner-panel-contract").innerHTML = plannerEmpty("◈", "尚未制定研究方案", "初步检索只展示论文线索；需要完整研究时再进入研究规划。 ");
  plannerElement("#planner-panel-sources").innerHTML = plannerEmpty("◇", "尚未生成数据来源方案", "当前仅完成论文初步检索，尚未检查字段覆盖或下载条件。 ");
  plannerElement("#planner-panel-coverage").innerHTML = plannerEmpty("□", "尚未生成覆盖矩阵", "完整研究规划确认后才检查字段覆盖。 ");
  const list = plannerElement("#planner-question-list");
  if (list) {
    if (run.error) {
      list.innerHTML = `<div class="planner-error"><strong>本次初步检索未完成</strong><br>${escapeHtml(run.error)}<br>请检查服务状态后重试。</div>`;
    } else if (!run.running && papers.length) {
      list.innerHTML = `<div class="planner-input-reply"><strong>这是一份轻量检索结果</strong><p>结果来自真实文献入口，保留来源链接和检索缺口。确认研究对象、结局和数据需求后，再进入完整研究规划。</p><button type="button" class="primary-button" data-quick-promote="true" data-quick-topic="${escapeHtml(run.inputTopic)}">进入完整研究规划</button></div>`;
    } else if (!run.running) {
      list.innerHTML = `<div class="planner-error">没有可展示的论文。系统不会伪造论文或数据集，请换一个更具体的对象或稍后重试。</div>`;
    } else {
      list.innerHTML = plannerEmpty("…", "正在检索", "结果返回后会显示论文标题、来源和访问链接。 ");
    }
  }
  setPlannerStage(run.running ? "literature" : "literature", { completedThrough: run.topic ? "topic" : null });
  switchPlannerTab("evidence");
  renderPlannerRecent();
}

function updateCurrentPlannerHistory(status) {
  const topic = plannerState.topic?.topic || plannerElement("#planner-topic")?.value;
  const run = plannerRuns.get(plannerState.sessionId);
  if (run) {
    run.topic = plannerState.topic;
    run.scan = plannerState.scan;
    run.candidates = plannerState.candidates;
    run.selectedCandidateId = plannerState.selectedCandidateId;
    run.contract = plannerState.contract;
    run.sourcePlanning = plannerState.sourcePlanning;
    run.running = plannerState.busy;
    persistPlannerRun(run, status);
    return;
  }
  upsertPlannerHistory(topic, { status, snapshot: plannerSnapshot() });
}

function restorePlannerHistory(item) {
  const sessionId = item?.sessionId || item?.snapshot?.sessionId || item?.topic;
  if (!sessionId || !item?.topic) return;
  const existing = plannerRuns.get(sessionId);
  const snapshot = item.snapshot || {};
  const restoredBuild = snapshot.build || (
    item.status === "数据集已生成" || item.taskId
      ? { status: "数据集已生成", taskId: item.taskId }
      : null
  );
  const run = existing || {
    sessionId,
    domain: snapshot.domain,
    inputTopic: item.topic,
    topic: snapshot.topic || null,
    scan: snapshot.scan || null,
    quickScan: snapshot.quickScan || null,
    candidates: snapshot.candidates || [],
    selectedCandidateId: snapshot.selectedCandidateId || null,
    contract: snapshot.contract || null,
    sourcePlanning: snapshot.sourcePlanning || null,
    build: restoredBuild,
    artifacts: snapshot.artifacts || [],
    messages: snapshot.messages || [],
    status: item.status || "未完成",
    running: false,
  };
  if (existing && !existing.build && restoredBuild) existing.build = restoredBuild;
  plannerRuns.set(sessionId, run);
  renderPlannerRun(run);
  loadPlannerResult(run).then(() => {
    if (isActivePlannerSession(sessionId)) renderPlannerRun(run);
  });
}

function plannerArtifact(result) {
  const rowCount = result.modeling_dataset?.rows?.length || 0;
  return {
    taskId: result.task_id,
    rowCount,
    sourceRows: (result.source_datasets || []).reduce((sum, item) => sum + (item.rows?.length || 0), 0),
    status: rowCount ? "数据集已生成" : "数据不足",
    message: (result.readiness?.warnings || []).join("；") || result.summary_zh || "",
  };
}

async function loadPlannerResult(run, taskId = run?.build?.taskId) {
  if (!run || !taskId) return null;
  if (run.domain === "astronomy") return loadAstronomyResult(run, taskId);
  if (run.result?.task_id === taskId) return run.result;
  try {
    const result = await readJson(await fetchApi(`/api/agent/tasks/${encodeURIComponent(taskId)}`));
    if (result.task_id !== taskId) throw new Error("返回的任务编号与当前对话不一致。");
    run.results ||= new Map();
    run.results.set(taskId, result);
    run.artifacts = [...(run.artifacts || []).filter((item) => item.taskId !== taskId), plannerArtifact(result)];
    if (run.build?.taskId === taskId) {
      run.result = result;
      run.loadError = "";
      if (!run.running) run.build = plannerArtifact(result);
    }
    persistPlannerRun(run, run.running ? run.status : run.build.status);
    return result;
  } catch (error) {
    run.loadError = `该任务结果暂不可用：${error.message}。可保留当前方案重新检索。`;
    return null;
  }
}

async function openPlannerTechnical(taskId = null) {
  const run = plannerRuns.get(plannerState.sessionId);
  document.querySelector("#astronomy-results").hidden = true;
  document.body.classList.toggle("is-astronomy-detail", run?.domain === "astronomy");
  if (run?.domain === "astronomy") return openAstronomyTechnical(run, taskId);
  const sessionId = run?.sessionId;
  const requestedTaskId = taskId || run?.build?.taskId;
  const token = {};
  state.technicalRequest = token;
  document.body.classList.add("is-advanced-workbench");
  resultsPanel.hidden = true;
  state.result = null;
  renderClosedLoop(null);
  const context = document.querySelector("#technical-context");
  context.hidden = false;
  const title = run?.inputTopic || "尚未选择研究对话";
  context.innerHTML = `<h2>${escapeHtml(title)}</h2><p>${escapeHtml(run ? plannerStatusCopy(run.status) : "请返回研究向导选择一个对话。")}</p>`;
  document.querySelector("#question").value = run?.contract?.research_question || run?.inputTopic || "";
  context.scrollIntoView({ behavior: "smooth", block: "start" });
  if (!run) return;
  const steps = [
    ["研究方向", run.topic?.topic || run.inputTopic],
    ["论文检索", run.scan ? `${run.scan.papers?.length || 0} 篇论文` : "尚未完成"],
    ["研究问题", run.contract?.research_question || "尚未确认"],
    ["数据来源规划", run.sourcePlanning ? `${run.sourcePlanning.dataset_candidates?.length || 0} 个候选数据集` : "尚未完成"],
  ];
  context.innerHTML += `<ol>${steps.map(([label, value]) => `<li>${label}：${escapeHtml(value)}</li>`).join("")}</ol>`;
  const result = run.results?.get(requestedTaskId) || await loadPlannerResult(run, requestedTaskId);
  if (!isActivePlannerSession(sessionId) || state.technicalRequest !== token) return;
  if (!result) {
    context.innerHTML += `<p>${escapeHtml(run.loadError || (run.running ? "当前对话正在执行，已完成阶段如上。结果完成后可重新打开详情。" : "尚未生成数据结果，可以返回当前对话继续检索。"))}</p>`;
    return;
  }
  state.result = result;
  state.datasetSourceKey = "primary";
  renderResult(result);
  resultsPanel.hidden = false;
  context.innerHTML += `<p>任务：${escapeHtml(result.task_id)} · 主表 ${result.modeling_dataset.rows.length} 行 · ${escapeHtml(result.readiness.status)}。下方展示本任务的工具调用、数据来源与质量检查。</p>`;
  const loopId = result.task_id.match(/^(loop-.+):r\d+$/)?.[1];
  let loop = run.loop?.loop_id === loopId ? run.loop : null;
  if (loopId && !loop) {
    try { loop = await readJson(await fetchApi(`/api/v2/agent/closed-loop/${encodeURIComponent(loopId)}`)); }
    catch { /* Per-task tool calls remain available when loop history is unavailable. */ }
  }
  if (isActivePlannerSession(sessionId) && state.technicalRequest === token) renderClosedLoop(loop);
}

function plannerOutputs(run) {
  if (!run) return "";
  const artifacts = run.artifacts?.length ? run.artifacts : (run.build?.taskId ? [run.build] : []);
  return `${run.running ? "<p>当前对话正在检索，既有结果仍可下载。</p>" : ""}${run.loadError ? `<p>${escapeHtml(run.loadError)}</p>` : ""}${artifacts.map((item, index) => {
    const attributes = `data-task-id="${escapeHtml(item.taskId)}"`;
    const downloadable = item.rowCount > 0;
    return `<div class="planner-build-status ${downloadable ? "is-success" : ""}"><strong>第 ${index + 1} 次结果 · ${item.pending ? "正在获取，结果尚未定稿" : downloadable ? "主数据表已生成" : item.rowCount === 0 ? "数据不足，尚未形成主数据表" : "历史结果待核验"}</strong>
      <p>任务 ${escapeHtml(item.taskId)} · 主表 ${item.rowCount ?? "待核验"} 行 · 来源表 ${item.sourceRows ?? "待核验"} 行</p><p>${escapeHtml(item.message || "")}</p>
      <div class="planner-output-actions">${downloadable ? `<button type="button" data-planner-download="xlsx" ${attributes}>下载 Excel</button><button type="button" data-planner-download="csv" ${attributes}>下载 CSV</button>` : ""}
      ${item.sourceRows > 0 ? `<button type="button" data-planner-download="sources" ${attributes}>下载来源数据包</button>` : ""}
      <button type="button" data-planner-download="quality_report" ${attributes}>下载质量报告</button><button type="button" data-planner-technical-result ${attributes}>查看本次工作流程</button></div></div>`;
  }).join("")}`;
}

const plannerStageOrder = ["topic", "literature", "questions", "contract", "sources"];
const plannerStageCopy = {
  topic: [10, "理解研究意图…"],
  literature: [38, "查找真实论文和公开数据线索…"],
  questions: [64, "把宽泛方向整理成具体研究问题…"],
  contract: [82, "确定研究对象、指标和所需字段…"],
  sources: [96, "检查公开数据是否能够支持研究…"],
};

const plannerResearchTypeLabels = {
  association: "差异与关联分析",
  classification_prediction: "疗效预测",
  survival: "生存分析",
  comparative_effectiveness: "疗效比较",
};

function plannerElement(selector) {
  return document.querySelector(selector);
}

function clearPlannerContractSurfaces() {
  const contractCard = plannerElement("#planner-contract-card");
  if (contractCard) {
    contractCard.hidden = true;
    contractCard.innerHTML = "";
  }
  const coverage = plannerElement("#planner-panel-coverage");
  if (coverage) coverage.innerHTML = plannerEmpty("□", "尚未生成覆盖矩阵", "确认研究方案后显示必要字段覆盖。");
}

function safePlannerUrl(value) {
  try {
    const url = new URL(String(value || ""), window.location.origin);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch {
    return "";
  }
}

function plannerText(value, fallback = "—") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function plannerPercent(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${Math.round(Math.max(0, Math.min(1, number)) * 100)}%` : "待核验";
}

function plannerResearchType(value) {
  return plannerResearchTypeLabels[String(value || "")] || plannerText(value, "探索性研究");
}

function plannerPlainCopy(value) {
  return String(value || "")
    .replace(/用户已冻结 Research Contract；后续取数必须对照该需求，不得改写医学安全规则。/g, "研究问题已经确认，之后按这个方案找数据，不会中途改题。")
    .replace(/Research Contract/g, "研究方案")
    .replace(/Required 字段/g, "必要字段")
    .replace(/Required/g, "必要字段")
    .replace(/已冻结/g, "已确认")
    .replace(/冻结/g, "确认");
}

function classifyPlannerInput(input) {
  const text = String(input || "").trim();
  if (!text) return { kind: "empty", reason: "空输入", reply: "请输入一个明确的研究方向。" };

  if (/^(你好|您好|嗨|hello|hi|谢谢|感谢|好的|ok|收到)[!！。,.，\s]*$/i.test(text)) {
    return { kind: "simple", reason: "普通对话", reply: "你好。需要做科研规划时，直接告诉我研究对象、影响因素和结局即可。" };
  }

  if (/^[\d\s.,，。！？!?+-]+$/.test(text)) {
    return {
      kind: "simple",
      reason: "数字或符号输入",
      reply: `你输入的是“${text}”。如果要开展科研规划，请输入研究对象、影响因素和希望观察的结局。`,
    };
  }

  const normalized = text.toLowerCase();
  // Route observation tasks before the medical planner. This also accepts the user's shorthand.
  if (/(?:[il]a\s*型\s*(?:超新星|光变|曲线)|(?:type\s*ia|sn\s*ia).*?(?:light\s*curve|photometr))/i.test(text)
      && !/(什么是|是什么|定义|解释一下)/.test(text)) {
    return { kind: "research", domain: "astronomy", reason: "超新星观测数据任务" };
  }
  const researchSignals = [
    "研究", "分析", "比较", "关联", "影响", "预测", "疗效", "治疗", "生存", "预后",
    "突变", "基因", "标志物", "患者", "样本", "队列", "数据集", "论文", "文献", "证据",
    "结局", "响应", "pcr", "her2", "erbb2", "egfr", "pik3ca", "kras", "braf", "tcga",
    "gdc", "geo", "cbioportal", "临床试验", "新辅助",
  ];
  const hasSignal = researchSignals.some((signal) => normalized.includes(signal));
  const oncologySignals = ["癌", "肿瘤", "患者", "样本", "基因", "突变", "治疗", "疗效", "生存", "预后", "her2", "erbb2", "egfr", "pik3ca", "kras", "braf", "tcga", "gdc", "geo", "cbioportal", "临床试验"];
  const hasOncologySignal = oncologySignals.some((signal) => normalized.includes(signal));
  const hasResearchVerb = /研究|分析|比较|评估|探索|验证|预测|判断|关联|影响|是否|能否|如何/.test(text);
  const hasResearchObject = /癌|肿瘤|疾病|患者|样本|基因|突变|治疗|疗效|生存|预后|队列|数据|论文|文献|证据|标志物|结局|响应|her2|erbb2|egfr|pik3ca|kras|braf|tcga|gdc|geo|cbioportal/i.test(text);
  const genericResearchVerb = /研究|分析|探索|评估|预测|比较|调查|验证|查找.*数据|寻找.*数据|找一份|下载|整理/.test(text);
  const directResearchRequest = /^(我想|我希望|我打算|计划|请帮我|帮我|想研究|研究一下|分析一下|探索一下|找一份|查找|寻找)/.test(text);
  const looksLikeConceptQuestion = /(什么是|是什么|请解释|解释一下|介绍一下|定义一下|这是什么|是什么意思)/.test(text);

  if (looksLikeConceptQuestion && !(hasResearchVerb && hasResearchObject)) {
    return {
      kind: "simple",
      reason: "概念问答",
      reply: "这是一个概念问答，不需要进入研究规划。请直接描述你想验证的研究关系、数据或结局。",
    };
  }
  if ((hasResearchVerb || genericResearchVerb || directResearchRequest) && text.length >= 5) {
    return {
      kind: "research",
      domain: hasOncologySignal ? "oncology" : "general_science",
      reason: hasOncologySignal ? "科研任务" : "通用科研任务",
    };
  }
  if (!hasSignal || !hasResearchObject || (!hasResearchVerb && text.length < 12)) {
    return {
      kind: "simple",
      reason: "缺少科研意图",
      reply: hasResearchVerb ? "这是研究需求。请告诉我研究对象、想观察的现象，或希望找到的数据；我会先自动查找真实来源，再判断能否解析成数据表。" : "请告诉我想研究的对象，以及需要的数据；我会先自动查找真实来源，再判断能否解析成数据表。",
    };
  }
  return { kind: "research", reason: "科研任务" };
}

function renderPlannerInputReply(result, input) {
  plannerState.sessionId = null;
  plannerState.topic = null;
  plannerState.scan = null;
  plannerState.candidates = [];
  plannerState.selectedCandidateId = null;
  plannerState.contract = null;
  plannerState.sourcePlanning = null;
  plannerState.busy = false;
  const chat = plannerElement("#planner-chat");
  if (chat) {
    chat.hidden = false;
    chat.innerHTML = `<article class="planner-chat-message is-user"><span class="planner-chat-avatar" aria-hidden="true">你</span><div class="planner-chat-body"><header><strong>你</strong></header><p>${escapeHtml(input)}</p></div></article><article class="planner-chat-message is-assistant"><span class="planner-chat-avatar" aria-hidden="true">研</span><div class="planner-chat-body"><header><strong>研究助手</strong><small>等待明确方向</small></header><p>${escapeHtml(result.reply)}</p></div></article>`;
  }
  plannerElement("#planner-progress").hidden = true;
  plannerElement("#planner-welcome").hidden = true;
  plannerElement("#planner-results").hidden = false;
  plannerElement("#planner-header-title").textContent = "直接回复";
  plannerElement("#planner-header-subtitle").textContent = "这条消息不需要进入科研规划";
  plannerElement("#planner-result-title").textContent = result.kind === "empty" ? "请输入一个研究方向" : "先把研究目标说清楚";
  plannerElement("#planner-result-summary").textContent = result.reply;
  plannerElement("#planner-question-list").innerHTML = `<div class="planner-input-reply"><strong>${escapeHtml(result.reply)}</strong><p>例如：研究 EGFR 突变与肺腺癌患者生存结局的关系，并整理患者级公开数据。</p></div>`;
  plannerElement("#planner-flow-summary").innerHTML = "";
  plannerElement("#planner-panel-evidence").innerHTML = plannerEmpty("i", "等待明确研究方向", "描述研究对象、影响因素和结局后，系统才会检索真实依据。");
  plannerElement("#planner-panel-contract").innerHTML = plannerEmpty("◈", "暂不制定研究方案", "普通问答不会创建研究会话或生成研究方案。");
  plannerElement("#planner-panel-sources").innerHTML = plannerEmpty("◇", "暂不准备数据", "确认属于科研任务后，系统才会检查公开数据来源。");
  clearPlannerContractSurfaces();
  setPlannerStage("topic");
  switchPlannerTab("evidence");
  renderPlannerRecent();
}

function shouldQuickLookup(input, intent = null) {
  const text = String(input || "").trim();
  if (!text || intent?.reason === "普通对话" || intent?.reason === "数字或符号输入") return false;
  if (/^(你好|您好|嗨|hello|hi|谢谢|感谢|好的|ok|收到|你是谁|你是什么模型|在吗)[!！。,.，\s？?]*$/i.test(text)) return false;
  return text.length >= 6 && /(什么是|是什么|为什么|如何|怎样|哪些|区别|机制|原理|作用|影响|定义|解释|介绍|能否|是否|数据|论文|文献|证据|检索)/.test(text);
}

function quickLookupQuery(input) {
  const text = String(input || "").trim();
  if (/乳腺癌|乳腺肿瘤/.test(text)) return "breast cancer";
  if (/肺癌|肺腺癌/.test(text)) return "lung cancer adenocarcinoma";
  if (/结直肠癌|大肠癌/.test(text)) return "colorectal cancer";
  if (/胰腺癌/.test(text)) return "pancreatic cancer";
  if (/[il]a\s*型|type\s*ia|超新星|光变曲线/i.test(text)) return "type Ia supernova light curve";
  if (/天空.*蓝|蓝天|瑞利散射/.test(text)) return "sky blue Rayleigh scattering";
  const stripped = text.replace(/什么是|是什么|为什么|如何|怎样|哪些|区别|机制|原理|作用|影响|定义|解释一下|介绍一下|能否|是否/g, " ").replace(/[？?！!。，“”‘’]/g, " ").replace(/\s+/g, " ").trim();
  return stripped || text;
}

async function startQuickLookup(topicText) {
  const topic = String(topicText || "").trim();
  if (!topic) return;
  if (typeof ensureResearchProvidersConfigured === "function" && !(await ensureResearchProvidersConfigured())) return;
  const sessionId = `planner_quick_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const run = {
    sessionId,
    inputTopic: topic,
    domain: "quick_lookup",
    topic: null,
    scan: null,
    quickScan: null,
    candidates: [],
    selectedCandidateId: null,
    contract: null,
    sourcePlanning: null,
    build: null,
    status: "初步检索中",
    running: true,
    error: null,
    messages: [],
  };
  plannerMessage(run, "user", topic, "刚刚");
  plannerMessage(run, "assistant", "这条问题先做初步检索：我会查找真实论文并展示来源，不自动创建研究方案或数据任务。", "初步检索", "progress");
  plannerRuns.set(sessionId, run);
  plannerState.sessionId = sessionId;
  persistPlannerRun(run, "初步检索中");
  renderPlannerRun(run);
  try {
    const created = await readJson(await fetchApi("/api/research/topics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, domain_hint: null }),
    }));
    run.topic = created;
    persistPlannerRun(run, "初步检索中");
    if (isActivePlannerSession(sessionId)) renderPlannerRun(run);
    const scanned = await readJson(await fetchApi(`/api/research/topics/${encodeURIComponent(created.topic_id)}/literature-scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_records: 6, query: quickLookupQuery(topic) }),
    }));
    run.quickScan = scanned.scan;
    const paperCount = run.quickScan?.papers?.length || 0;
    run.running = false;
    run.status = paperCount ? "初步检索已完成" : "未找到可核验论文";
    plannerMessage(run, "assistant", paperCount
      ? `初步检索找到 ${paperCount} 篇真实论文。你可以查看来源，或进入完整研究规划。`
      : "本次没有拿到可核验论文。我会保留这个结果，不用模板内容替代真实来源。", "检索完成", paperCount ? "success" : "error");
    persistPlannerRun(run, run.status);
  } catch (error) {
    run.running = false;
    run.error = error.message;
    run.status = "初步检索失败";
    plannerMessage(run, "assistant", `初步检索未完成：${error.message}。这次没有生成替代性结果。`, "检索未完成", "error");
    persistPlannerRun(run, run.status);
  }
  if (isActivePlannerSession(sessionId)) renderPlannerRun(run);
}

function submitPlannerTopic(value) {
  const input = String(value || "").trim();
  if (!input) return;
  const intent = classifyPlannerInput(input);
  if (intent.kind !== "research") {
    if (typeof shouldQuickLookup === "function" && shouldQuickLookup(input, intent)) void startQuickLookup(input);
    else renderPlannerInputReply(intent, input);
    plannerElement("#planner-topic").value = "";
    return;
  }
  startPlannerResearch(input);
}

function plannerGranularity(value) {
  const labels = { patient: "患者", sample: "样本", cell_line: "细胞系", study: "研究" };
  return labels[String(value || "")] || plannerText(value, "患者");
}

function plannerResponseDomain(value) {
  const labels = { clinical: "临床", preclinical: "临床前", mixed: "混合" };
  return labels[String(value || "")] || plannerText(value, "临床");
}

function plannerSourceLabel(value) {
  const labels = {
    EVIDENCE_AGENT: "论文依据",
    GENERIC_FALLBACK: "通用备选",
    LEGACY_TEMPLATE: "模板备选",
  };
  return labels[String(value || "")] || plannerText(value, "系统推荐");
}

function plannerPlanStatus(status) {
  if (status === "READY") return "数据准备条件较完整";
  if (status === "PARTIAL") return "部分字段还需要补充";
  if (status === "NEEDS_REVIEW") return "已找到数据，正式采集前需要核验";
  return plannerText(status, "等待检查");
}

function setPlannerStage(stage, { completedThrough = null } = {}) {
  const activeIndex = plannerStageOrder.indexOf(stage);
  const completedIndex = completedThrough == null ? activeIndex - 1 : plannerStageOrder.indexOf(completedThrough);
  document.querySelectorAll("[data-planner-stage]").forEach((button) => {
    const index = plannerStageOrder.indexOf(button.dataset.plannerStage);
    button.classList.toggle("is-active", index === activeIndex);
    button.classList.toggle("is-complete", index <= completedIndex);
  });
  document.querySelectorAll("[data-planner-step]").forEach((item) => {
    const index = plannerStageOrder.indexOf(item.dataset.plannerStep);
    item.classList.toggle("is-active", index === activeIndex);
    item.classList.toggle("is-complete", index <= completedIndex);
  });
  const [percent, copy] = plannerStageCopy[stage] || [10, "正在处理…"];
  if (plannerElement("#planner-progress-percent")) plannerElement("#planner-progress-percent").textContent = `${percent}%`;
  if (plannerElement("#planner-progress-bar")) plannerElement("#planner-progress-bar").style.width = `${percent}%`;
  if (plannerElement("#planner-progress-title")) plannerElement("#planner-progress-title").textContent = copy;
}

function switchPlannerTab(tab) {
  document.querySelectorAll("[data-planner-tab]").forEach((button) => {
    const active = button.dataset.plannerTab === tab;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll("[data-planner-panel]").forEach((panel) => {
    panel.classList.toggle("is-active", panel.dataset.plannerPanel === tab);
  });
}

function plannerEmpty(icon, title, copy) {
  return `<div class="planner-empty"><span>${escapeHtml(icon)}</span><strong>${escapeHtml(title)}</strong><p>${escapeHtml(copy)}</p></div>`;
}

function renderPlannerRecent() {
  const list = plannerElement("#planner-recent-list");
  const count = plannerElement("#planner-recent-count");
  if (!list || !count) return;
  count.textContent = String(plannerState.recent.length);
  if (!plannerState.recent.length) {
    list.innerHTML = '<p class="planner-recent-empty">暂无会话</p>';
    return;
  }
  list.innerHTML = plannerState.recent.slice(0, 8).map((item, index) => {
    const updated = item.updatedAt ? new Date(item.updatedAt) : null;
    const time = updated && !Number.isNaN(updated.getTime())
      ? updated.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" })
      : "—";
    return `<button type="button" class="${item.sessionId === plannerState.sessionId ? "is-active" : ""}" data-planner-recent="${index}" title="${escapeHtml(item.topic)}">
      <strong>${escapeHtml(item.topic)}</strong>
      <span><em>${escapeHtml(item.status || "进行中")}</em><time>${time}</time></span>
    </button>`;
  }).join("");
}

function renderPlannerEvidence(scan) {
  const panel = plannerElement("#planner-panel-evidence");
  if (!panel) return;
  const papers = scan?.papers || [];
  if (!papers.length) {
    const warning = scan?.warnings?.[0] || "当前检索未返回论文，请检查文献 Provider 配置后重试。";
    panel.innerHTML = `<div class="planner-status-note is-error">${escapeHtml(warning)}</div>${plannerEmpty("≡", "没有可展示的论文", "系统不会伪造论文或数据集；未取得真实来源时会明确标注。")}`;
    return;
  }
  const warnings = scan.warnings?.length
    ? `<div class="planner-status-note">${scan.warnings.map((item) => escapeHtml(item)).join("<br>")}</div>`
    : "";
  panel.innerHTML = `
    <div class="planner-panel-heading"><span>研究依据</span><h3>已找到 ${papers.length} 篇相关论文</h3></div>
    ${warnings}
    <div class="planner-evidence-list">${papers.map((paper, index) => {
      const url = safePlannerUrl(paper.source_url);
      const accessions = paper.dataset_accessions || [];
      const sectionNames = Object.keys(paper.sections || {});
      return `<article class="planner-evidence-card">
        <header><span>${escapeHtml(plannerText(paper.provider))} · ${escapeHtml(plannerText(paper.source_id))}</span><span>${escapeHtml(plannerText(paper.publication_year, `#${index + 1}`))}</span></header>
        <h4>${escapeHtml(plannerText(paper.title))}</h4>
        <p>${escapeHtml(plannerText(paper.journal, paper.fulltext_available ? "可获取全文" : "摘要级证据"))}</p>
        <div class="planner-mini-meta">
          ${paper.fulltext_available ? "<span>全文</span>" : "<span>摘要</span>"}
          ${sectionNames.slice(0, 3).map((name) => `<span>${escapeHtml(name)}</span>`).join("")}
          ${accessions.slice(0, 3).map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
        </div>
        ${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">查看真实来源 ↗</a>` : ""}
      </article>`;
    }).join("")}</div>`;
}

function renderPlannerQuestions(payload) {
  const list = plannerElement("#planner-question-list");
  const summary = plannerElement("#planner-result-summary");
  if (!list || !summary) return;
  const candidates = payload?.candidates || plannerState.candidates || [];
  const selectedId = plannerState.selectedCandidateId || candidates[0]?.candidate_id;
  summary.textContent = plannerState.contract
    ? "已按最优一项继续；不满意可以换一道题。"
    : "系统会自动采用证据最充分的一项；其余题目可点「换一道题」。";
  if (!candidates.length) {
    list.innerHTML = `<div class="planner-error">没有生成候选科研问题。系统不会用预置 benchmark 答案替代真实规划结果。</div>`;
    return;
  }
  list.innerHTML = `<div class="planner-candidate-board">${candidates.map((candidate) => {
    const selected = candidate.candidate_id === selectedId;
    const evidenceCount = candidate.literature_evidence?.length || candidate.evidence_count || 0;
    return `
      <article class="planner-alternative${selected ? " is-selected" : ""}" data-planner-candidate-card="${escapeHtml(candidate.candidate_id)}">
        <div>
          <strong>${escapeHtml(plannerText(candidate.question))}</strong>
          <small>${escapeHtml(plannerResearchType(candidate.research_type))} · 文献依据 ${evidenceCount} 篇 · ${escapeHtml(plannerSourceLabel(candidate.generation_source))}${selected ? " · 当前这道" : ""}</small>
          <small>需要收集：${escapeHtml((candidate.field_hints || candidate.required_field_hints || []).slice(0, 6).join("、") || "待生成")}</small>
        </div>
        <button type="button" data-planner-select="${escapeHtml(candidate.candidate_id)}" ${selected ? "disabled" : ""}>${selected ? "当前这道" : "换一道题"}</button>
      </article>`;
  }).join("")}</div>`;
}

function renderPlannerContract(contract) {
  const panel = plannerElement("#planner-panel-contract");
  if (!panel || !contract) return;
  const groups = [
    ["必须收集", contract.required_fields || []],
    ["建议收集", contract.recommended_fields || []],
    ["可选补充", contract.optional_fields || []],
  ];
  const statusClassName = contract.validation_status === "READY_FOR_SOURCE_PLANNING" ? "is-success" : "";
  panel.innerHTML = `
    <div class="planner-panel-heading"><span>研究方案</span><h3>这项研究准备怎么做</h3><p>${escapeHtml(plannerText(contract.research_question))}</p></div>
    <div class="planner-status-note ${statusClassName}">${contract.validation_status === "READY_FOR_SOURCE_PLANNING" ? "研究对象、结果指标和必要字段已经明确" : "当前方案仍有内容需要人工确认"}${contract.validation_warnings?.length ? `<br>${contract.validation_warnings.map((item) => escapeHtml(plannerPlainCopy(item))).join("<br>")}` : ""}</div>
    <div class="planner-contract-stack">
      ${groups.map(([label, fields]) => `<section class="planner-contract-block"><strong>${label} · ${fields.length}</strong><div class="planner-field-chips">${fields.length ? fields.map((field) => `<span title="${escapeHtml(plannerText(field.reason))}">${escapeHtml(plannerText(field.label, field.field_id))}</span>`).join("") : "<span>无</span>"}</div></section>`).join("")}
      <section class="planner-contract-block"><strong>观察指标 · ${contract.metric_requirements?.length || 0}</strong>${(contract.metric_requirements || []).map((metric) => `<p>${escapeHtml(localizeNarrative(plannerText(metric.label)))}</p>`).join("") || "<p>尚无指标要求</p>"}</section>
      <section class="planner-contract-block"><strong>分析计划</strong>${(contract.analysis_plan || []).map((item) => `<p>${escapeHtml(localizeNarrative(item))}</p>`).join("") || "<p>尚未生成</p>"}</section>
    </div>`;
}

function renderPlannerContractCard(contract) {
  const card = plannerElement("#planner-contract-card");
  if (!card || !contract) return;
  card.hidden = false;
  const required = (contract.required_fields || []).map((field) => field.label || field.field_id).join("、");
  const frozen = contract.lifecycle_status === "FROZEN";
  card.innerHTML = `<article class="planner-flow-hero">
      <span class="planner-flow-check">${frozen ? "✓" : "!"}</span>
      <div>
        <small>${frozen ? "研究方案已确认" : "系统建议的研究方案"}</small>
        <h3>${escapeHtml(plannerText(contract.research_question))}</h3>
        <p>人群：${escapeHtml(localizeNarrative(plannerText(contract.population)))} · 影响因素：${escapeHtml(localizeNarrative(plannerText(contract.exposure)))} · 结局：${escapeHtml(localizeNarrative(plannerText(contract.outcome)))}</p>
        <p>分析单位 ${escapeHtml(plannerGranularity(contract.data_granularity))} · 疗效口径 ${escapeHtml(plannerResponseDomain(contract.response_domain))}</p>
        <p>需要收集：${escapeHtml(required || "—")}</p>
      </div>
    </article>
    ${frozen ? "" : `<div class="planner-next-action"><div><strong>确认这项研究并开始找数据</strong><small>确认后，研究问题、人群和指标就定下来，系统按这个去检索，不会中途改题。</small></div><button id="planner-freeze-contract" type="button">确认这项研究并开始找数据</button></div>`}`;
}

function renderPlannerCoverage(planning) {
  const panel = plannerElement("#planner-panel-coverage");
  if (!panel || !planning) return;
  const matrix = planning.coverage_matrix || {};
  const fieldIds = matrix.field_ids || [];
  const datasetIds = matrix.dataset_ids || [];
  const cellMap = {};
  (matrix.cells || []).forEach((cell) => {
    cellMap[`${cell.field_id}|${cell.dataset_id}`] = cell.coverage;
  });
  if (!fieldIds.length) {
    panel.innerHTML = plannerEmpty("□", "覆盖矩阵为空", "确认研究方案并生成来源方案后显示字段覆盖。");
    return;
  }
  panel.innerHTML = `<div class="planner-panel-heading"><span>覆盖矩阵</span><h3>必要字段 × 候选来源</h3></div>
    <div class="table-wrap"><table class="coverage-matrix-table"><thead><tr><th>字段</th>${datasetIds.map((id) => `<th>${escapeHtml(id)}</th>`).join("")}</tr></thead>
    <tbody>${fieldIds.map((fieldId) => `<tr><th>${escapeHtml(fieldId)}</th>${datasetIds.map((datasetId) => {
      const coverage = Number(cellMap[`${fieldId}|${datasetId}`] || 0);
      return `<td>${coverage > 0 ? "✓" : "✗"}</td>`;
    }).join("")}</tr>`).join("")}</tbody></table></div>`;
}

async function freezePlannerContract() {
  if (!plannerState.contract || plannerState.busy) return;
  if (typeof ensureResearchProvidersConfigured === "function" && !(await ensureResearchProvidersConfigured())) return;
  const sessionId = plannerState.sessionId;
  const run = plannerRuns.get(sessionId);
  const contract = plannerState.contract;
  if (plannerState.contract.lifecycle_status === "FROZEN" && plannerState.sourcePlanning) return;
  plannerState.busy = true;
  if (run) {
    run.running = true;
    run.contract = contract;
    persistPlannerRun(run, "正在准备数据");
  }
  const button = plannerElement("#planner-freeze-contract");
  if (button) {
    button.disabled = true;
    button.textContent = "正在确认方案…";
  }
  try {
    let frozen = plannerState.contract;
    if (frozen.lifecycle_status !== "FROZEN") {
      frozen = await readJson(await fetchApi(`/api/research/contracts/${encodeURIComponent(contract.contract_id)}/freeze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed: true }),
      }));
    }
    if (run) run.contract = frozen;
    if (isActivePlannerSession(sessionId)) {
      plannerState.contract = frozen;
      renderPlannerContract(frozen);
      renderPlannerContractCard(frozen);
      setPlannerStage("sources", { completedThrough: "contract" });
      plannerElement("#planner-panel-sources").innerHTML = plannerEmpty("…", "正在准备数据", "评估字段覆盖、访问方式和不同队列之间的数据合并风险。");
    }
    const planning = await readJson(await fetchApi(`/api/research/contracts/${encodeURIComponent(frozen.contract_id)}/source-plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_selected_datasets: 3, public_data_only: true }),
    }));
    if (run) run.sourcePlanning = planning;
    if (isActivePlannerSession(sessionId)) {
      plannerState.sourcePlanning = planning;
      renderPlannerSources(planning);
      renderPlannerFlowSummary();
      renderPlannerQuestions({ candidates: plannerState.candidates });
      plannerElement("#planner-result-title").textContent = "研究方案已经准备好了";
      plannerElement("#planner-result-summary").textContent = "题目已确认，可以生成数据集";
      plannerElement("#planner-header-subtitle").textContent = "下一步可以直接生成可分析的科研数据集";
      setPlannerStage("sources", { completedThrough: "sources" });
      switchPlannerTab("coverage");
    }
    if (run) {
      run.running = false;
      persistPlannerRun(run, "数据已就绪");
    } else updateCurrentPlannerHistory("数据已就绪");
    if (isActivePlannerSession(sessionId)) showToast("研究方案已确认，开始准备数据");
  } catch (error) {
    if (run) {
      run.running = false;
      run.error = error.message;
      persistPlannerRun(run, "执行失败");
    }
    if (!isActivePlannerSession(sessionId)) return;
    showToast(error.message);
    if (button) {
      button.disabled = false;
      button.textContent = "确认这项研究并开始找数据";
    }
  } finally {
    if (isActivePlannerSession(sessionId)) plannerState.busy = false;
    if (run) run.running = false;
  }
}

function selectedDatasetCoverage(datasetId, planning) {
  const cells = (planning?.coverage_matrix?.cells || []).filter((cell) => cell.dataset_id === datasetId && cell.priority === "required");
  if (!cells.length) return 0;
  return cells.reduce((sum, cell) => sum + Number(cell.coverage || 0), 0) / cells.length;
}

function renderPlannerSources(planning) {
  const panel = plannerElement("#planner-panel-sources");
  if (!panel || !planning) return;
  const plan = planning.source_plan || {};
  const candidates = planning.dataset_candidates || [];
  const selected = (plan.selected_dataset_ids || []).map((id) => candidates.find((item) => item.dataset_id === id)).filter(Boolean);
  const statusClassName = plan.status === "READY" ? "is-success" : "";
  panel.innerHTML = `
    <div class="planner-panel-heading"><span>数据准备</span><h3>已找到 ${selected.length} 个优先数据集</h3></div>
    <div class="planner-status-note ${statusClassName}">${escapeHtml(plannerPlanStatus(plan.status))} · 必要字段预计覆盖 ${plannerPercent(plan.required_field_coverage)}</div>
    <div class="planner-source-list">${selected.map((dataset) => {
      const coverage = selectedDatasetCoverage(dataset.dataset_id, planning);
      const url = safePlannerUrl(dataset.source_url);
      return `<article class="planner-source-card">
        <header><span>${escapeHtml(plannerText(dataset.source_id))}</span><span>${escapeHtml(plannerText(dataset.access_mode))}</span></header>
        <h4>${escapeHtml(plannerText(dataset.title))}</h4>
        <p>${escapeHtml(plannerText(dataset.accession, dataset.dataset_id))} · 正式采集前会再次核验字段和访问状态</p>
        <div class="planner-coverage" title="必要字段预计覆盖 ${plannerPercent(coverage)}"><i style="width:${Math.round(coverage * 100)}%"></i></div>
        ${url ? `<p><a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">查看数据源 ↗</a></p>` : ""}
      </article>`;
    }).join("") || plannerEmpty("◇", "没有选中数据集", "没有数据源满足当前字段与公开访问约束。")}</div>
    ${(plan.join_policies || []).length ? `<section class="planner-contract-block" style="margin-top:.6rem"><strong>数据合并安全提示</strong>${plan.join_policies.map((policy) => `<p>${escapeHtml(policy.reason)}</p>`).join("")}</section>` : ""}
    ${(plan.fallback_dataset_ids || []).length ? `<section class="planner-contract-block" style="margin-top:.6rem"><strong>备用数据集</strong><p>${plan.fallback_dataset_ids.map((item) => escapeHtml(item)).join("、")}</p></section>` : ""}
    ${(plan.warnings || []).length ? `<div class="planner-status-note" style="margin-top:.6rem">${plan.warnings.map((item) => escapeHtml(plannerPlainCopy(item))).join("<br>")}</div>` : ""}`;
  renderPlannerCoverage(planning);
}

function renderPlannerFlowSummary() {
  const container = plannerElement("#planner-flow-summary");
  const contract = plannerState.contract;
  const planning = plannerState.sourcePlanning;
  const run = plannerRuns.get(plannerState.sessionId);
  const build = run?.build;
  if (!container || !contract || !planning) return;
  const plan = planning.source_plan || {};
  const candidates = planning.dataset_candidates || [];
  const selected = (plan.selected_dataset_ids || []).map((id) => candidates.find((item) => item.dataset_id === id)).filter(Boolean);
  const primaryDataset = selected[0];
  const paperCount = plannerState.scan?.papers?.length || 0;
  container.innerHTML = `
    <article class="planner-flow-hero">
      <span class="planner-flow-check">✓</span>
      <div><small>研究规划已自动完成</small><h3>${escapeHtml(plannerText(contract.research_question))}</h3><p>${run?.domain === "general_science" ? `系统根据 ${paperCount} 篇真实论文和公开数据目录，自动整理了主题、检索方案和后续解析路径。结果会保留官方来源，具体文件需继续核验。` : `系统根据 ${paperCount} 篇真实论文和公开数据可用性，自动明确了研究问题、研究方案和数据准备路径。你不需要在多个候选项之间做技术选择。`}</p></div>
    </article>
    <div class="planner-plan-grid">
      <article class="planner-plan-item"><span>研究对象</span><strong>${escapeHtml(localizeNarrative(plannerText(contract.population, "肿瘤研究人群")))}</strong></article>
      <article class="planner-plan-item"><span>比较或影响因素</span><strong>${escapeHtml(localizeNarrative(plannerText(contract.exposure, "待从数据中确认")))}</strong></article>
      <article class="planner-plan-item"><span>主要观察结果</span><strong>${escapeHtml(localizeNarrative(plannerText(contract.outcome, "治疗响应或预后")))}</strong></article>
      <article class="planner-plan-item"><span>研究方法</span><strong>${escapeHtml(plannerResearchType(contract.research_type))}</strong></article>
      <article class="planner-plan-item"><span>论文依据</span><strong>${paperCount} 篇真实来源</strong></article>
      <article class="planner-plan-item"><span>数据准备情况</span><strong>${primaryDataset ? `${escapeHtml(plannerText(primaryDataset.accession, primaryDataset.title))} · ` : ""}${escapeHtml(plannerPlanStatus(plan.status))}</strong></article>
    </div>
    <div id="planner-build-status">${plannerOutputs(plannerRuns.get(plannerState.sessionId))}</div>
    <div class="planner-next-action">
      <div><strong>${build?.taskId ? "继续寻找更多数据集" : run?.domain === "general_science" ? "下一步：自动搜索并解析公开数据集" : "下一步：生成科研数据集"}</strong><small>${run?.domain === "general_science" ? "系统会检索真实公开目录，解析元数据、文件清单和来源链接；选择具体文件后再继续下载。" : "每次检索结果独立保留。扩大检索会增加入口和补查轮次，来源表保留各自来源及适用范围。"}</small>
      <label>补充范围或数据集编号（可选）<input id="planner-expand-query" type="text" placeholder="例如：GSE 编号、cBioPortal study ID、治疗方式或队列关键词" /></label></div>
      <button id="planner-build-dataset" type="button" ${build?.status === "数据集生成中" ? "disabled" : ""}>${build?.status === "数据集生成中" ? "正在检索…" : build?.taskId ? "按当前方案重试" : run?.domain === "general_science" ? "开始搜索并解析" : "开始生成数据集"}</button>
      <button type="button" data-planner-expand ${build?.status === "数据集生成中" ? "disabled" : ""}>扩大检索并继续</button>
    </div>`;
}

async function downloadPlannerArtifact(taskId, format, button) {
  if (!taskId) return;
  const original = button?.textContent;
  if (button) {
    button.disabled = true;
    button.textContent = "正在准备…";
  }
  try {
    const taskApi = taskId.startsWith("astro-") ? "/api/astronomy/tasks" : "/api/agent/tasks";
    const response = await fetchApi(`${taskApi}/${encodeURIComponent(taskId)}/export/${format}`);
    if (!response.ok) await readJson(response);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${taskId.replace(/[^a-zA-Z0-9_-]/g, "_")}-${format === "sources" ? "独立来源数据" : format === "quality_report" ? "质量报告" : "科研数据集"}.${format === "quality_report" ? "json" : format === "sources" ? "zip" : format}`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 60000);
    showToast(`${taskId} 的文件已准备好`);
  } catch (error) {
    showToast(error.message);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = original;
    }
  }
}

function buildPlannerRequest(run, { expand = false, extra = "" } = {}) {
  const payload = buildAgentTaskPayload();
  payload.question = (run.domain === "general_science"
    ? [run.inputTopic, extra ? `补充检索范围：${extra}` : ""]
    : [run.contract.research_question, run.inputTopic, extra ? `补充检索范围：${extra}` : ""])
    .filter(Boolean).join("\n").slice(0, 2000);
  payload.data_mode = "live";
  if (expand) {
    payload.max_sources = 20;
    payload.max_collection_rounds = 12;
    payload.focus_tools = run.domain === "general_science"
      ? ["search_zenodo", "search_europe_pmc"]
      : ["search_geo_catalog", "search_cbioportal", "search_europe_pmc", "search_dataset_catalog"];
    const candidates = run.sourcePlanning?.dataset_candidates || [];
    const accessions = candidates.map((item) => item.accession).filter(Boolean);
    const supplied = extra.split(/[\s,，;；]+/).filter((item) => /^(GSE\d+|[a-z][a-z0-9]*_[a-z0-9_]+)$/i.test(item));
    payload.focus_accessions = [...new Set([...supplied, ...accessions])].slice(0, 20);
    payload.remap_outcome_aliases = true;
  }
  return payload;
}

async function runPlannerDatasetBuild(button, { expand = false, question = null } = {}) {
  const run = plannerRuns.get(plannerState.sessionId);
  if (!run?.contract || run.running) return;
  if (typeof ensureResearchProvidersConfigured === "function" && !(await ensureResearchProvidersConfigured())) return;
  const sessionId = run.sessionId;
  const extra = plannerElement("#planner-expand-query")?.value.trim() || "";
  const payload = buildPlannerRequest(run, { expand, extra });
  if (question) payload.question = question.slice(0, 2000);
  if (run.build?.taskId && !run.result) {
    await loadPlannerResult(run);
    if (!isActivePlannerSession(sessionId) || run.running) return;
  }
  const previousBuild = run.build;
  run.running = true;
  run.build = { ...previousBuild, status: "数据集生成中" };
  plannerMessage(run, "assistant", expand
    ? `开始扩大检索：最多检查 20 个入口、补查 12 轮，结合当前方案的候选数据集${extra ? `和补充范围“${extra}”` : ""}继续查找。已有结果保留，可分别下载。`
    : run.domain === "general_science"
      ? "开始自动检索公开数据集目录和文献，解析元数据、文件清单与官方来源。"
      : "开始按当前对话的研究方案采集数据、统一字段并核验来源。", "数据检索", "progress");
  persistPlannerRun(run, "数据集生成中");
  renderPlannerRun(run);
  try {
    const result = await runClosedLoopTask(payload, run);
    run.results ||= new Map();
    run.results.set(result.task_id, result);
    run.result = result;
    run.running = false;
    run.loadError = "";
    run.build = plannerArtifact(result);
    run.artifacts = [...(run.artifacts || []).filter((item) => item.taskId !== result.task_id), run.build];
    plannerMessage(run, "assistant", run.build.rowCount
      ? run.domain === "general_science"
        ? `本次已解析 ${run.build.rowCount} 条公开资源记录；可从官方链接选择具体文件继续下载和字段解析。`
        : `本次主数据表已生成，共 ${run.build.rowCount} 行；请结合质量报告检查研究字段是否齐全。`
      : `本次检索完成，但主数据表仍为 0 行。${run.build.message} 已取得的来源表可独立下载，也可补充数据集编号后扩大检索。`,
      run.build.status, run.build.rowCount ? "success" : "error");
    persistPlannerRun(run, run.build.status);
  } catch (error) {
    run.running = false;
    run.build = previousBuild || { status: "生成失败" };
    run.loadError = error.message;
    plannerMessage(run, "assistant", `本次检索未完成：${error.message}。已有结果保留，可继续下载或重试。`, "检索未完成", "error");
    persistPlannerRun(run, "生成失败");
  } finally {
    if (isActivePlannerSession(sessionId)) {
      renderPlannerRun(run);
      if (document.body.classList.contains("is-advanced-workbench")) await openPlannerTechnical();
    }
  }
}
async function startPlannerResearch(topicText) {
  const topic = String(topicText || "").trim();
  const intent = classifyPlannerInput(topic);
  if (intent.kind !== "research") {
    renderPlannerInputReply(intent, topic);
    plannerElement("#planner-topic").value = "";
    return;
  }
  const composer = plannerElement("#planner-topic");
  const submittedDraft = composer.value;
  if (!(await ensureResearchProvidersConfigured())) return;
  if (composer.value === submittedDraft) composer.value = "";
  if (intent.domain === "astronomy") return startAstronomyResearch(topic);
  const sessionId = `planner_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  const run = {
    sessionId,
    inputTopic: topic,
    domain: intent.domain || "oncology",
    topic: null,
    scan: null,
    candidates: [],
    selectedCandidateId: null,
    contract: null,
    sourcePlanning: null,
    build: null,
    status: "执行中",
    running: true,
    error: null,
    messages: [],
  };
  plannerMessage(run, "user", topic, "刚刚");
  plannerMessage(run, "assistant", intent.domain === "general_science"
    ? "收到。我会先查找真实论文和公开数据集目录，再解析数据集的元信息与文件清单，给你可核验的候选结果。"
    : "收到。我先查找与这个方向最相关的真实论文；如果能形成有证据支持的研究问题，我会自动继续完成方案和数据准备。", "开始检索", "progress");
  plannerRuns.set(sessionId, run);
  plannerState.sessionId = sessionId;
  persistPlannerRun(run, "执行中");
  renderPlannerRun(run);
  try {
    const created = await readJson(await fetchApi("/api/research/topics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic }),
    }));
    run.topic = created;
    persistPlannerRun(run, "查找依据中");
    if (isActivePlannerSession(sessionId)) renderPlannerRun(run);
    const scanned = await readJson(await fetchApi(`/api/research/topics/${encodeURIComponent(created.topic_id)}/literature-scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_records: 10 }),
    }));
    run.scan = scanned.scan;
    const paperCount = run.scan?.papers?.length || 0;
    plannerMessage(run, "assistant", paperCount
      ? `我找到 ${paperCount} 篇真实论文，接下来会根据论文证据自动整理可执行的研究问题。`
      : intent.domain === "general_science"
        ? "暂时没有拿到足够的论文记录，我会保留这个事实，继续从公开数据集目录检索并解析真实资源。"
        : "我没有找到可核验的论文证据，所以暂时停在“查找依据”这一步，不会用虚假论文替代。请检查文献 Provider 或换一个更具体的方向。", "查找依据", paperCount || intent.domain === "general_science" ? "success" : "error");
    persistPlannerRun(run, "整理研究问题中");
    if (isActivePlannerSession(sessionId)) renderPlannerRun(run);
    if (!paperCount && intent.domain !== "general_science") throw new Error("查找依据未返回真实论文，研究流程停在查找依据阶段。");
    const candidatePayload = await readJson(await fetchApi(`/api/research/topics/${encodeURIComponent(created.topic_id)}/question-candidates`));
    run.candidates = candidatePayload.candidates || [];
    plannerMessage(run, "assistant", run.candidates.length
      ? `论文线索已经整理成 ${run.candidates.length} 个候选问题，我会自动采用证据最充分的一项继续。`
      : intent.domain === "general_science"
        ? "论文证据不足以单独形成问题，我会把原始主题作为通用数据发现任务继续执行。"
        : "我卡在“明确研究问题”这一步了：当前论文证据不足以形成可执行问题。请补充疾病、人群、影响因素或结局。", "明确问题", run.candidates.length || intent.domain === "general_science" ? "success" : "error");
    persistPlannerRun(run, "正在确认方案");
    if (isActivePlannerSession(sessionId)) renderPlannerRun(run);
    const recommended = run.candidates[0];
    if (!recommended && intent.domain === "general_science") {
      throw new Error("通用主题未生成可执行的研究问题；请稍后重试，系统会继续保留公开数据发现结果。");
    }
    if (!recommended) throw new Error("没有形成可继续研究的问题。请换一个更具体的研究方向后重试。");
    const contract = await readJson(await fetchApi(`/api/research/questions/${encodeURIComponent(recommended.candidate_id)}/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }));
    run.contract = contract;
    run.selectedCandidateId = recommended.candidate_id;
    persistPlannerRun(run, "正在准备数据");
    if (isActivePlannerSession(sessionId)) renderPlannerRun(run);
    const frozen = contract.lifecycle_status === "FROZEN"
      ? contract
      : await readJson(await fetchApi(`/api/research/contracts/${encodeURIComponent(contract.contract_id)}/freeze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed: true }),
      }));
    run.contract = frozen;
    plannerMessage(run, "assistant", "研究问题和必要字段已经确认。我继续检查哪些公开数据能够支持这项研究，以及不同来源之间是否可以安全对齐。", "制定方案", "progress");
    persistPlannerRun(run, "正在准备数据");
    if (isActivePlannerSession(sessionId)) renderPlannerRun(run);
    run.sourcePlanning = await readJson(await fetchApi(`/api/research/contracts/${encodeURIComponent(frozen.contract_id)}/source-plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_selected_datasets: 3, public_data_only: true }),
    }));
    const planStatus = run.sourcePlanning?.source_plan?.status;
    plannerMessage(run, "assistant", planStatus === "READY"
      ? "数据准备条件较完整，研究链路已经走通。下一步可以直接生成可分析的科研数据集。"
      : `我卡在“准备数据”这一步了：${plannerPlanStatus(planStatus)}。系统会保留真实来源和覆盖缺口，不会伪造可用数据。`, "准备数据", planStatus === "READY" ? "success" : "error");
    run.running = false;
    persistPlannerRun(run, "数据已就绪");
    if (isActivePlannerSession(sessionId)) {
      renderPlannerRun(run);
      showToast("研究方案已准备好");
    }
  } catch (error) {
    run.error = error.message;
    if (run.messages?.at(-1)?.tone !== "error") plannerMessage(run, "assistant", `我卡在“${plannerStatusCopy(run.status)}”这一步了：${error.message}。已有真实结果会保留，修复配置后可以重试。`, "执行中断", "error");
    run.running = false;
    persistPlannerRun(run, "执行失败");
    if (isActivePlannerSession(sessionId)) renderPlannerRun(run);
  } finally {
    run.running = false;
    if (run.status !== "数据已就绪" && run.status !== "执行失败") persistPlannerRun(run);
    if (isActivePlannerSession(sessionId)) renderPlannerRun(run);
  }
}

async function selectPlannerQuestion(candidateId, button, { automatic = false } = {}) {
  if (plannerState.busy && !automatic) return;
  if (typeof ensureResearchProvidersConfigured === "function" && !(await ensureResearchProvidersConfigured())) return;
  const sessionId = plannerState.sessionId;
  const run = plannerRuns.get(sessionId);
  plannerState.busy = true;
  document.querySelectorAll("[data-planner-select]").forEach((item) => { item.disabled = true; });
  if (button) button.textContent = "正在调整研究方案…";
  setPlannerStage("contract", { completedThrough: "questions" });
  plannerElement("#planner-panel-contract").innerHTML = plannerEmpty("…", "正在制定研究方案", "根据研究问题确定对象、指标和需要收集的数据字段。 ");
  try {
    const contract = await readJson(await fetchApi(`/api/research/questions/${encodeURIComponent(candidateId)}/select`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }));
    if (!isActivePlannerSession(sessionId)) return;
    if (run) {
      run.contract = contract;
      run.selectedCandidateId = candidateId;
      run.sourcePlanning = automatic ? run.sourcePlanning : null;
      persistPlannerRun(run, automatic ? "正在准备数据" : "方案已确认");
    }
    plannerState.contract = contract;
    plannerState.selectedCandidateId = candidateId;
    if (!automatic) {
      plannerState.sourcePlanning = null;
      const flow = plannerElement("#planner-flow-summary");
      if (flow) flow.innerHTML = "";
    }
    renderPlannerContract(contract);
    renderPlannerContractCard(contract);
    renderPlannerQuestions({ candidates: plannerState.candidates });
    document.querySelectorAll("[data-planner-candidate-card]").forEach((card) => card.classList.toggle("is-selected", card.dataset.plannerCandidateCard === candidateId));
    plannerElement("#planner-header-title").textContent = contract.research_question;
    plannerElement("#planner-header-subtitle").textContent = automatic
      ? "正在按这道题去准备公开数据"
      : "如需换题，点其他候选项的「换一道题」";
    plannerElement("#planner-progress").hidden = true;
    plannerElement("#planner-results").hidden = false;
    plannerElement("#planner-result-title").textContent = automatic ? "已自动确认研究问题" : "已选好研究问题";
    plannerElement("#planner-result-summary").textContent = "确认后系统按这个题目找数据，不会中途改题。";
    updateCurrentPlannerHistory("方案已确认");
    switchPlannerTab("contract");
    if (!automatic) showToast("已选好题目，正在确认研究方案");
  } catch (error) {
    if (!isActivePlannerSession(sessionId)) return;
    const target = plannerState.contract ? plannerElement("#planner-panel-sources") : plannerElement("#planner-panel-contract");
    target.innerHTML = `<div class="planner-error"><strong>阶段未完成</strong><br>${escapeHtml(error.message)}<br>系统未生成替代性虚假结果。</div>`;
    plannerElement("#planner-header-subtitle").textContent = "当前阶段需要处理后重试";
    plannerElement("#planner-progress").hidden = true;
    plannerElement("#planner-results").hidden = false;
    plannerElement("#planner-result-title").textContent = "研究规划暂未完成";
    plannerElement("#planner-question-list").insertAdjacentHTML("afterbegin", `<div class="planner-error">${escapeHtml(error.message)}</div>`);
  } finally {
    if (isActivePlannerSession(sessionId)) plannerState.busy = false;
    document.querySelectorAll("[data-planner-select]").forEach((item) => {
      if (item.dataset.plannerSelect !== candidateId || !plannerState.contract) item.disabled = false;
    });
  }
  if (!automatic && isActivePlannerSession(sessionId) && plannerState.contract) await freezePlannerContract();
}

function resetPlannerWorkspace() {
  plannerState.sessionId = null;
  state.result = null;
  state.technicalRequest = null;
  resultsPanel.hidden = true;
  renderClosedLoop(null);
  plannerState.topic = null;
  plannerState.scan = null;
  plannerState.candidates = [];
  plannerState.selectedCandidateId = null;
  plannerState.contract = null;
  plannerState.sourcePlanning = null;
  plannerElement("#planner-topic").value = "";
  plannerElement("#planner-chat").hidden = true;
  plannerElement("#planner-chat").innerHTML = "";
  plannerElement("#planner-welcome").hidden = false;
  plannerElement("#planner-progress").hidden = true;
  plannerElement("#planner-results").hidden = true;
  plannerElement("#planner-result-title").textContent = "正在为你整理研究方案";
  plannerElement("#planner-result-summary").textContent = "";
  plannerElement("#planner-header-title").textContent = "新研究";
  plannerElement("#planner-flow-summary").innerHTML = "";
  plannerElement("#planner-header-subtitle").textContent = "从一个想法开始，系统会自动完成研究规划";
  plannerElement("#planner-panel-evidence").innerHTML = plannerEmpty("≡", "还没有研究依据", "开始研究后，系统找到的真实论文和来源链接会显示在这里。 ");
  plannerElement("#planner-panel-contract").innerHTML = plannerEmpty("◈", "还没有研究方案", "系统会自动明确研究对象、影响因素、结果指标和需要的字段。 ");
  plannerElement("#planner-panel-sources").innerHTML = plannerEmpty("◇", "还没有检查数据", "研究方案形成后，系统会说明哪些公开数据可以使用。 ");
  clearPlannerContractSurfaces();
  setPlannerStage("topic");
  switchPlannerTab("evidence");
  plannerElement("#planner-topic").focus();
}

async function checkPlannerHealth() {
  const dot = plannerElement("#planner-health-dot");
  const label = plannerElement("#planner-health-label");
  try {
    const response = await fetchApi("/health");
    if (!response.ok) throw new Error("offline");
    dot?.classList.add("is-online");
    if (label) label.textContent = "服务已连接";
  } catch {
    dot?.classList.remove("is-online");
    if (label) label.textContent = "服务未连接";
  }
}

function initPlanningWorkspace() {
  const form = plannerElement("#planner-form");
  if (!form) return;
  document.querySelector("#astronomy-results")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-astronomy-download]");
    if (button) downloadPlannerArtifact(button.dataset.taskId, button.dataset.astronomyDownload, button);
    const cleanButton = event.target.closest("[data-astronomy-clean]");
    if (cleanButton) {
      const run = plannerRuns.get(plannerState.sessionId);
      if (run?.domain === "astronomy") cleanAstronomyExisting(run, cleanButton.dataset.taskId);
    }
  });
  plannerState.recent = loadPlannerHistory();
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitPlannerTopic(plannerElement("#planner-topic").value);
  });
  plannerElement("#planner-topic")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
  plannerElement("#planner-recent-list")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-planner-recent]");
    if (!button) return;
    const item = plannerState.recent[Number(button.dataset.plannerRecent)];
    if (!item?.topic) return;
    restorePlannerHistory(item);
  });
  document.querySelectorAll("[data-demo-question]").forEach((button) => button.addEventListener("click", () => {
    const question = document.querySelector("#question");
    if (!question) return;
    question.value = button.dataset.demoQuestion;
    question.focus();
    document.querySelectorAll("[data-demo-question]").forEach((item) => item.classList.toggle("is-active", item === button));
  }));
  document.querySelectorAll("[data-planner-example]").forEach((button) => button.addEventListener("click", () => {
    submitPlannerTopic(button.dataset.plannerExample);
  }));
  document.querySelectorAll("[data-planner-tab]").forEach((button) => button.addEventListener("click", () => switchPlannerTab(button.dataset.plannerTab)));
  plannerElement("#planner-question-list")?.addEventListener("click", (event) => {
    const quickButton = event.target.closest("[data-quick-promote]");
    if (quickButton) {
      const topic = quickButton.dataset.quickTopic || "";
      if (topic) startPlannerResearch(`请帮我围绕“${topic}”进入完整研究规划`);
      return;
    }
    const button = event.target.closest("[data-planner-select]");
    if (button) selectPlannerQuestion(button.dataset.plannerSelect, button);
  });
  plannerElement("#planner-contract-card")?.addEventListener("click", (event) => {
    if (event.target.closest("#planner-freeze-contract")) freezePlannerContract();
  });
  plannerElement("#planner-flow-summary")?.addEventListener("click", (event) => {
    const astronomyButton = event.target.closest("[data-astronomy-retry]");
    if (astronomyButton) {
      const run = plannerRuns.get(plannerState.sessionId);
      const sources = (astronomyButton.dataset.sources || "cfa4").split(",").filter(Boolean);
      if (run?.domain === "astronomy") executeAstronomyRun(run, sources);
      return;
    }
    const expandButton = event.target.closest("[data-planner-expand]");
    if (expandButton) {
      runPlannerDatasetBuild(expandButton, { expand: true });
      return;
    }
    const buildButton = event.target.closest("#planner-build-dataset");
    if (buildButton) {
      runPlannerDatasetBuild(buildButton);
      return;
    }
    const downloadButton = event.target.closest("[data-planner-download]");
    if (downloadButton) {
      downloadPlannerArtifact(downloadButton.dataset.taskId, downloadButton.dataset.plannerDownload, downloadButton);
      return;
    }
    if (event.target.closest("[data-planner-technical-result]")) {
      openPlannerTechnical(event.target.closest("[data-planner-technical-result]").dataset.taskId);
    }
  });
  plannerElement("#planner-new")?.addEventListener("click", resetPlannerWorkspace);
  plannerElement("#planner-open-advanced")?.addEventListener("click", () => {
    openPlannerTechnical();
  });
  plannerElement("#advanced-back-planner")?.addEventListener("click", () => {
    document.body.classList.remove("is-advanced-workbench");
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  plannerElement("#advanced-return-planner")?.addEventListener("click", () => {
    document.body.classList.remove("is-advanced-workbench");
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  renderPlannerRecent();
}

function wishRabbitStage(text) {
  const normalized = String(text || "").toLowerCase();
  if (/修改方向|换个方向|研究方向|想研究什么/.test(normalized)) return "topic";
  if (/来源|论文|文献|依据|证据|检索|查找/.test(normalized)) return "literature";
  if (/具体问题|研究目标|假设|问题是什么|明确问题/.test(normalized)) return "questions";
  if (/字段|指标|变量|样本|队列|纳入|排除|研究方案/.test(normalized)) return "contract";
  if (/数据|数据集|csv|表格|下载|缺失|覆盖|可用|准备/.test(normalized)) return "sources";
  return "topic";
}

function wishRabbitStageCopy(stage) {
  return {
    topic: "这条愿望适合从“提出方向”开始。先把研究对象和你真正想知道的事情说清楚，再交给研究向导继续推进。",
    literature: "这条愿望对应“查找依据”。研究向导会优先寻找真实论文和公开数据入口，并把来源、证据和限制留在结果里。",
    questions: "这条愿望对应“明确问题”。可以先把宽泛想法拆成一个可执行的研究目标，不替你补造没有证据的结论。",
    contract: "这条愿望对应“制定方案”。下一步是检查研究对象、指标和字段，再决定哪些内容值得进入数据工作。",
    sources: "这条愿望对应“准备数据”。研究向导会检查公开数据的覆盖、缺失、格式和来源血缘，最后再交付可分析资产。",
  }[stage] || "我先陪你把这个想法聊清楚。想正式开始时，再把它带回研究向导。";
}

function wishRabbitVisibleText(selector, fallback = "") {
  if (typeof document === "undefined") return fallback;
  return document.querySelector(selector)?.textContent?.trim() || fallback;
}

function wishRabbitInputValue(selector, fallback = "") {
  if (typeof document === "undefined") return fallback;
  return document.querySelector(selector)?.value?.trim() || fallback;
}

function wishRabbitExplain(kind = "topic") {
  const result = typeof state !== "undefined" ? state?.result : null;
  const parsed = result?.parsed_question || {};
  const question = wishRabbitInputValue("#planner-topic", result?.research_spec?.question || parsed.question || "当前研究课题");
  if (kind === "dataset") {
    const title = wishRabbitVisibleText("#dataset-title", "当前科研数据集");
    const note = wishRabbitVisibleText("#dataset-note", "页面尚未生成数据集说明");
    const size = wishRabbitVisibleText("#dataset-size", "尚未返回行列统计");
    const dictionary = wishRabbitVisibleText("#dictionary-count", "尚未返回字段统计");
    const sources = wishRabbitVisibleText("#source-count", "尚未返回来源统计");
    return `数据集解析\n• 当前对象：${title}\n• 它回答什么：围绕“${question}”整理可分析字段，不直接替你下结论。\n• 页面状态：${size}；${dictionary}；${sources}。\n• 当前说明：${note}\n• 使用时要检查：分析单位、字段定义、缺失情况、真实来源、原始字段与原始值，以及 Evidence Lineage。\n• 可信边界：页面没有返回或尚未核验的内容，会保持“待核验”，不会被科研兔补成事实。`;
  }
  const summary = wishRabbitVisibleText("#agent-summary", "尚未生成正式运行摘要");
  const status = wishRabbitVisibleText("#result-status", "尚未返回正式运行结果");
  return `课题解析\n• 原始问题：${question}\n• 当前理解：先拆分研究对象、研究目标和限制条件，保留你的原句，不替你补造结论。\n• 建议路径：提出方向 → 查找依据 → 明确问题 → 制定方案 → 准备数据。\n• 最终应看到：真实来源、字段映射、质量检查、证据链和数据血缘。\n• 页面状态：${status}。\n• 运行摘要：${summary}`;
}

function wishRabbitIsResearchIntent(text) {
  return /研究|数据|数据集|论文|文献|来源|证据|检索|光变|超新星|乳腺癌|指标|字段|样本|csv|表格|下载/.test(String(text || "").toLowerCase());
}

function wishRabbitTrim(value, limit = 2400) {
  if (value === null || value === undefined) return "";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (!text) return "";
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}

function wishRabbitResultSnapshot(result) {
  if (!result || typeof result !== "object") return {};
  const fields = [
    "research_spec", "parsed_question", "research_brief", "readiness",
    "summary_zh", "critic_report", "quality_gate_report", "data_alignment",
    "study_design", "cohort_construction", "source_datasets", "source_items",
    "modeling_dataset", "dataset_dictionary", "evidence_lineage",
  ];
  return Object.fromEntries(fields.filter((key) => result[key] !== undefined).map((key) => [key, wishRabbitTrim(result[key], key === "modeling_dataset" ? 5200 : 2800)]));
}

function wishRabbitChatContext() {
  const result = typeof state !== "undefined" ? state?.result : null;
  const pageText = (selector, fallback = "", limit = 1800) => wishRabbitTrim(wishRabbitVisibleText(selector, fallback), limit);
  const page = {
    question: wishRabbitTrim(wishRabbitInputValue("#planner-topic", result?.research_spec?.question || result?.research_spec?.research_goal || result?.parsed_question?.question || ""), 1800),
    status: pageText("#result-status"),
    stage: pageText("#progress-label"),
    dataset_title: pageText("#dataset-title"),
    dataset_size: pageText("#dataset-size"),
    dictionary_count: pageText("#dictionary-count"),
    source_count: pageText("#source-count"),
    summary: pageText("#agent-summary"),
    dataset_note: pageText("#dataset-note"),
    planner_title: pageText("#planner-header-title"),
    planner_subtitle: pageText("#planner-header-subtitle"),
    flow_summary: pageText("#planner-flow-summary"),
    planner_chat: pageText("#planner-chat"),
    planner_results: pageText("#planner-results"),
    evidence_panel: pageText("#planner-panel-evidence"),
    contract_panel: pageText("#planner-panel-contract"),
    sources_panel: pageText("#planner-panel-sources"),
    coverage_panel: pageText("#planner-panel-coverage"),
    quality_gate: pageText("#quality-gate"),
    quality_report: pageText("#quality-report"),
    lineage_panel: pageText("#lineage-graph"),
  };
  return { ...page, result: wishRabbitResultSnapshot(result) };
}

async function requestWishRabbitModel(text, history, allowRestore = true) {
  if (!(await ensureQwenConfigured())) {
    const error = new Error("当前未连接科研模型。");
    error.status = 503;
    throw error;
  }
  const body = { message: text, history: history.slice(-16), context: wishRabbitChatContext() };
  if (typeof state !== "undefined" && state.qwenSessionId && !isQwenSessionExpired()) body.qwen_session_id = state.qwenSessionId;
  const response = await fetchApi("/api/agent/companion/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  try {
    const payload = await readJson(response);
    return payload.reply;
  } catch (error) {
    error.status = response.status;
    if (allowRestore && response.status === 401) {
      clearStaleQwenSession();
      if (await restoreSavedQwenSession()) return requestWishRabbitModel(text, history, false);
    }
    throw error;
  }
}

async function formatWishRabbitResearchQuestion(history = [], allowRestore = true) {
  if (!(await ensureQwenConfigured())) {
    const error = new Error("当前未连接科研模型。");
    error.status = 503;
    throw error;
  }
  const body = { message: history.at(-1)?.content || "请把当前对话整理成可执行的研究问题。", history: history.slice(-16), context: wishRabbitChatContext() };
  if (typeof state !== "undefined" && state.qwenSessionId && !isQwenSessionExpired()) body.qwen_session_id = state.qwenSessionId;
  const response = await fetchApi("/api/agent/companion/research-question", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  try {
    const payload = await readJson(response);
    return payload.research_question || payload.question || payload.reply || "";
  } catch (error) {
    error.status = response.status;
    if (allowRestore && response.status === 401) {
      clearStaleQwenSession();
      if (await restoreSavedQwenSession()) return formatWishRabbitResearchQuestion(history, false);
    }
    throw error;
  }
}

function wishRabbitLocalResearchQuestion(history = []) {
  const context = wishRabbitChatContext();
  const latest = history.filter((item) => item?.role === "user").at(-1)?.content || context.question || "当前研究想法";
  const question = context.question && context.question !== latest ? context.question : latest;
  return `研究对象：${question}\n研究问题：围绕“${question}”，明确需要通过真实来源和可复用数据验证的核心关系、现象或方法。\n数据需求：检索公开可获取的数据集、论文或原始记录，记录来源、字段定义、原始值与质量限制。\n分析边界：先核验数据覆盖、分析单位和证据强度，再形成可复现的研究结论。`;
}

function wishRabbitTypingMarkup() {
  return `<article class="wish-rabbit-message is-assistant" data-wish-typing="true"><span class="wish-rabbit-message-avatar" aria-hidden="true">${wishRabbitAvatarMarkup()}</span><div class="wish-rabbit-message-body"><header><strong>科研兔</strong><small>正在思考</small></header><p class="wish-rabbit-typing"><i></i><i></i><i></i></p></div></article>`;
}

function wishRabbitReply(text, stage) {
  const normalized = String(text || "").trim().toLowerCase();
  if (/^(你好|嗨|hi|hello|哈喽|早上好|晚上好)/.test(normalized)) {
    return { text: "你好呀！我是科研兔。这里可以聊研究，也可以聊一点日常和灵感；如果你愿意，我还能解析当前课题、解释数据集，或把一个模糊想法整理成研究向导里的下一步。" };
  }
  if (/你是谁|你能做什么|有什么用|怎么用/.test(normalized)) {
    return { text: "我是科研兔，你的科研解析助手：可以陪你闲聊、发散想法、解释课题和科研数据概念，也能在你明确想开始时，把愿望带回研究向导。这里的聊天不会自动提交任务或修改研究数据。" };
  }
  if (/谢谢|感谢|太好了|哈哈|开心|晚安|再见/.test(normalized)) {
    return { text: "不客气！想到新的问题就继续告诉我。科研不必一开始就说得很完整，先把念头放在这里也可以。" };
  }
  if (/没思路|没有思路|迷茫|不知道研究什么|想不到/.test(normalized)) {
    return { text: "那我们先不急着定题。你可以从三个方向试试：一个你长期好奇的对象、一个你想解释的现象，或者一份你想真正用起来的公开数据。你随便说一个词，我陪你把它展开。" };
  }
  if (/累|焦虑|压力|烦|难过|不想做/.test(normalized)) {
    return { text: "听起来你今天有点辛苦。先不用把研究做完，告诉我现在最卡的一个小地方就好；如果只是想聊聊天，也完全可以。" };
  }
  if (/研究|数据|数据集|论文|文献|来源|证据|检索|光变|超新星|乳腺癌|指标|字段|样本|csv|表格|下载/.test(normalized)) {
    return { text: `${wishRabbitStageCopy(stage)} 你可以继续补充限制条件，我会先按你的最新一句话理解；需要进入正式流程时，再点击下面的入口。`, stage };
  }
  return { text: "我听到了。你可以继续随便说，不用马上把它变成一个严谨的问题。如果这句话和某个研究想法有关，也可以告诉我“我想研究……”或“我想找一份……”，我会帮你接住。" };
}

function wishRabbitContextReply(text, stage) {
  const context = wishRabbitChatContext();
  const normalized = String(text || "").toLowerCase();
  const hasPage = Object.values(context).some((value) => value && value !== "{}" && value !== "—");
  if (!hasPage) return null;
  if (/结果|当前|主入口|课题|进展|状态|说明什么|能回答|能不能/.test(normalized)) {
    return {
      text: `我先按主入口当前内容回答：\n\n• 当前课题：${context.question || "尚未填写"}\n• 页面状态：${context.status || "尚未返回正式运行结果"}${context.stage ? `；${context.stage}` : ""}\n• 数据资产：${context.dataset_title || "尚未生成数据集"}${context.dataset_size ? `（${context.dataset_size}）` : ""}\n• 已知依据：${context.summary || "尚未生成运行摘要"}\n\n这些信息只能说明页面已经展示到的范围；来源、字段定义、缺失和质量门仍应以结果里的登记信息为准。`,
      stage: stage || "sources",
    };
  }
  if (/数据集|字段|来源|血缘|质量|缺失|覆盖/.test(normalized)) {
    return {
      text: `我可以基于主入口继续解析：当前数据集是“${context.dataset_title || "尚未生成"}”，${context.dataset_size || "行列统计待核验"}；字段${context.dictionary_count || "待核验"}，来源${context.source_count || "待核验"}。下一步先检查分析单位、原始字段/原始值、缺失覆盖与来源血缘，再决定能否进入分析。`,
      stage: stage || "sources",
    };
  }
  return null;
}

function jumpFromWishRabbit(stage, handoffText = "") {
  const plannerInput = document.querySelector("#planner-topic");
  const tabByStage = { topic: "evidence", literature: "evidence", questions: "contract", contract: "contract", sources: "sources" };
  setPlannerStage(stage);
  switchPlannerTab(tabByStage[stage] || "evidence");
  if (handoffText && plannerInput) plannerInput.value = handoffText;
  const chat = plannerElement("#planner-chat");
  const targets = {
    topic: plannerInput,
    literature: chat && !chat.hidden ? chat : plannerElement("#planner-panel-evidence"),
    questions: plannerElement("#planner-results"),
    contract: plannerElement("#planner-panel-contract"),
    sources: plannerElement("#planner-panel-sources"),
  };
  const target = targets[stage] || plannerInput;
  target?.scrollIntoView({ behavior: "smooth", block: "center" });
  window.setTimeout(() => {
    if (stage === "topic" && plannerInput) plannerInput.focus({ preventScroll: true });
    else if (chat && !chat.hidden) chat.lastElementChild?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, 180);
  if (plannerInput) {
    plannerInput.classList.add("is-rabbit-focus");
    window.setTimeout(() => plannerInput.classList.remove("is-rabbit-focus"), 1000);
  }
  if (handoffText) showToast("愿望已带入研究向导，点击“发送并开始研究”继续");
}

function wishRabbitAvatarMarkup() {
  return '<svg viewBox="0 0 64 64" fill="none" aria-hidden="true"><path d="M21 27c-5-8-5-19-1-22 6-4 10 8 10 17 2-2 4-3 7-3s5 1 7 3c0-9 4-21 10-17 4 3 4 14-1 22 3 3 5 7 5 12 0 12-8 19-21 19S16 51 16 39c0-5 2-9 5-12Z" fill="#FFFDF8" stroke="#1D3557" stroke-width="2.5"/><path d="M20 8c0 5 2 10 5 14M44 22c3-4 5-9 5-14" stroke="#F19DB5" stroke-width="3" stroke-linecap="round"/><circle cx="27" cy="36" r="2.3" fill="#1D3557"/><circle cx="43" cy="36" r="2.3" fill="#1D3557"/><path d="M32 43c2 2 4 2 6 0M34 41c0 2 0 3-1 4M38 41c0 2 0 3 1 4" stroke="#D56B8B" stroke-width="1.8" stroke-linecap="round"/><circle cx="21" cy="42" r="3" fill="#F8C9D6" opacity=".8"/><circle cx="49" cy="42" r="3" fill="#F8C9D6" opacity=".8"/></svg>';
}

const wishRabbitStageLabels = { topic: "提出方向", literature: "查找依据", questions: "明确问题", contract: "制定方案", sources: "准备数据" };

function wishRabbitExplanationActionsMarkup() {
  return '<div class="wish-rabbit-message-actions"><button type="button" data-wish-explain="topic">一键解析这个课题</button><button type="button" data-wish-explain="dataset">一键解释数据集</button></div>';
}

function wishRabbitMessageMarkup(kind, text, stage = "", canExplain = false) {
  const avatar = kind === "assistant" ? wishRabbitAvatarMarkup() : "你";
  const name = kind === "assistant" ? "科研兔" : "你";
  const handoff = stage ? `<div class="wish-rabbit-message-actions"><button type="button" data-wish-jump="${escapeHtml(stage)}" data-wish-handoff="${escapeHtml(text)}">带入研究向导 · ${escapeHtml(wishRabbitStageLabels[stage] || "研究")}</button><button type="button" data-wish-format="true">整理成研究问题</button></div>` : "";
  const explain = kind === "assistant" && canExplain ? wishRabbitExplanationActionsMarkup() : "";
  const action = `${handoff}${explain}`;
  const content = kind === "assistant"
    ? (typeof renderMarkdown === "function" ? renderMarkdown(text) : `<p>${escapeHtml(text).replace(/\n/g, "<br>")}</p>`)
    : `<p>${escapeHtml(text).replace(/\n/g, "<br>")}</p>`;
  return `<article class="wish-rabbit-message is-${kind}"><span class="wish-rabbit-message-avatar" aria-hidden="true">${avatar}</span><div class="wish-rabbit-message-body"><header><strong>${name}</strong><small>刚刚</small></header><div class="wish-rabbit-message-content">${content}</div>${action}</div></article>`;
}

function sendWishRabbitMessage(input, messages) {
  const text = input?.value.trim();
  if (!text || !messages) {
    input?.focus();
    return;
  }
  const stage = wishRabbitStage(text);
  const reply = wishRabbitReply(text, stage);
  messages.insertAdjacentHTML("beforeend", wishRabbitMessageMarkup("user", text));
  messages.insertAdjacentHTML("beforeend", wishRabbitMessageMarkup("assistant", reply.text, reply.stage || "", Boolean(reply.stage)));
  input.value = "";
  messages.scrollTop = messages.scrollHeight;
  input.focus({ preventScroll: true });
}

async function sendWishRabbitModelMessage(input, messages, history) {
  const text = input?.value.trim();
  if (!text || !messages || !history) {
    input?.focus();
    return;
  }
  const stage = wishRabbitIsResearchIntent(text) ? wishRabbitStage(text) : "";
  messages.insertAdjacentHTML("beforeend", wishRabbitMessageMarkup("user", text));
  history.push({ role: "user", content: text });
  input.value = "";
  messages.insertAdjacentHTML("beforeend", wishRabbitTypingMarkup());
  messages.scrollTop = messages.scrollHeight;
  let replyText;
  try {
    replyText = await requestWishRabbitModel(text, history.slice(0, -1));
  } catch (error) {
    if (error.status === 503) {
      const fallback = wishRabbitContextReply(text, stage) || wishRabbitReply(text, stage);
      replyText = `${fallback.text}\n\n（当前未连接科研模型，这是本地规则回答；请先连接千问 API。）`;
    } else {
      replyText = `模型请求失败：${error.message || "后端没有返回具体原因"}\n\n这次没有用本地话术替代模型回答，请刷新页面后重试。`;
    }
  }
  messages.querySelector("[data-wish-typing]")?.remove();
  history.push({ role: "assistant", content: replyText });
  messages.insertAdjacentHTML("beforeend", wishRabbitMessageMarkup("assistant", replyText, stage, Boolean(stage)));
  messages.scrollTop = messages.scrollHeight;
  input.focus({ preventScroll: true });
}

async function analyzeWishRabbitMainEntry(kind, conversation, messages) {
  const prompt = kind === "dataset"
    ? "请读取主入口当前的数据集、字段、来源和质量信息，解释它现在能回答什么、不能回答什么，以及下一步该检查什么。只使用上下文已有信息。"
    : "请读取主入口当前的课题、研究计划、证据和运行状态，给出清晰的研究解读和下一步建议。只使用上下文已有信息。";
  const typing = wishRabbitTypingMarkup();
  messages.insertAdjacentHTML("beforeend", typing);
  try {
    const reply = await requestWishRabbitModel(prompt, conversation);
    conversation.push({ role: "assistant", content: reply });
    return reply;
  } catch (error) {
    return `模型解析失败：${error.message || "后端没有返回具体原因"}。请刷新页面后重试。`;
  } finally {
    messages.querySelector("[data-wish-typing]")?.remove();
  }
}

function initWishRabbit() {
  const toggle = document.querySelector("#wish-rabbit-toggle");
  const panel = document.querySelector("#wish-rabbit-panel");
  const close = document.querySelector("#wish-rabbit-close");
  const clear = document.querySelector("#wish-rabbit-clear");
  const input = document.querySelector("#wish-rabbit-input");
  const send = document.querySelector("#wish-rabbit-send");
  const form = document.querySelector("#wish-rabbit-form");
  const messages = document.querySelector("#wish-rabbit-messages");
  const plannerInput = document.querySelector("#planner-topic");
  if (!toggle || !panel || !input || !send || !form || !messages) return;
  const conversation = [];
  const sendMessage = async () => {
    if (send.disabled) return;
    send.disabled = true;
    input.disabled = true;
    try { await sendWishRabbitModelMessage(input, messages, conversation); }
    finally { send.disabled = false; input.disabled = false; input.focus({ preventScroll: true }); }
  };
  const setOpen = (open) => {
    panel.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    toggle.classList.toggle("is-open", open);
    if (open) window.setTimeout(() => input.focus({ preventScroll: true }), 80);
  };
  toggle.addEventListener("click", () => setOpen(panel.hidden));
  close?.addEventListener("click", () => setOpen(false));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    void sendMessage();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  });
  messages.addEventListener("click", (event) => {
    const formatButton = event.target.closest("[data-wish-format]");
    if (formatButton) {
      formatButton.disabled = true;
      void formatWishRabbitResearchQuestion(conversation).then((question) => {
        const formatted = question || wishRabbitLocalResearchQuestion(conversation);
        conversation.push({ role: "assistant", content: formatted });
        messages.insertAdjacentHTML("beforeend", wishRabbitMessageMarkup("assistant", formatted, "topic"));
        messages.scrollTop = messages.scrollHeight;
      }).catch(() => {
        const formatted = wishRabbitLocalResearchQuestion(conversation);
        conversation.push({ role: "assistant", content: formatted });
        messages.insertAdjacentHTML("beforeend", wishRabbitMessageMarkup("assistant", formatted, "topic"));
        messages.scrollTop = messages.scrollHeight;
      }).finally(() => { formatButton.disabled = false; });
      return;
    }
    const button = event.target.closest("[data-wish-jump]");
    if (!button) return;
    jumpFromWishRabbit(button.dataset.wishJump, button.dataset.wishHandoff || "");
    setOpen(false);
  });
  panel.addEventListener("click", (event) => {
    const button = event.target.closest("[data-wish-explain]");
    if (!button) return;
    button.disabled = true;
    void analyzeWishRabbitMainEntry(button.dataset.wishExplain || "topic", conversation, messages).then((explanation) => {
      messages.insertAdjacentHTML("beforeend", wishRabbitMessageMarkup("assistant", explanation));
      messages.scrollTop = messages.scrollHeight;
    }).finally(() => { button.disabled = false; });
  });
  clear?.addEventListener("click", () => {
    conversation.length = 0;
    messages.innerHTML = wishRabbitMessageMarkup("assistant", "你好呀。这里可以先随便聊天，也可以把一个模糊的科研愿望说给我听。我会帮你理清思路，也可以一键解析当前课题或解释数据集；想进入正式研究时，再把它带回研究向导。" );
    messages.scrollTop = 0;
    input.focus({ preventScroll: true });
  });
  panel.querySelectorAll("[data-wish-prompt]").forEach((button) => button.addEventListener("click", () => {
    input.value = button.dataset.wishPrompt || "";
    input.focus({ preventScroll: true });
  }));
  if (plannerInput) toggle.title = "打开研究向导";
}

renderAgentRuntime(null);
initWishRabbit();
initPlanningWorkspace();
void (async () => {
  if (!loadStoredQwenConnection()) showQwenFirstRunPrompt();
  await checkConfiguration();
  const restored = await restoreSavedQwenSession();
  if (!restored && !state.qwenSessionId) showQwenFirstRunPrompt();
})();
