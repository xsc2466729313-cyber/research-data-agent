const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const index = readFileSync(path.join(__dirname, '../index.html'), 'utf8');
const app = readFileSync(path.join(__dirname, '../app.js'), 'utf8');
const styles = readFileSync(path.join(__dirname, '../styles.css'), 'utf8');

test('the research guide is the default shell and does not expose the legacy blue backend entry', () => {
  assert.match(index, /id="planning-workspace"/);
  assert.match(index, /id="planner-form"/);
  assert.match(index, /id="planner-new"/);
  assert.doesNotMatch(index, /自主研究工作区/);
  assert.doesNotMatch(index, /href="\/v31\//);
  assert.doesNotMatch(index, /蓝色后台/);
  assert.doesNotMatch(index, /返回蓝色工作台/);
  assert.doesNotMatch(index, /window\.location\.replace\("\/v31\/#\/workspace"\)/);
  assert.doesNotMatch(app, /renderPlannerRecent\(\);\s*checkPlannerHealth\(\);/);
  assert.doesNotMatch(app, /\ncheckConfiguration\(\);\n/);
  assert.match(index, /<title>科研数据智能体<\/title>/);
  assert.doesNotMatch(index, /肿瘤与天文观测/);
  assert.doesNotMatch(index, /千问科研数据智能体/);
});

test('every autonomous run requires a verified Qwen connection before fallback can apply', () => {
  assert.match(index, /id="allow-fallback"/);
  assert.match(index, /开始自主研究/);
  assert.match(app, /async function ensureExecutionReady\(\)/);
  assert.match(app, /async function ensureQwenConfigured\(\)/);
  assert.match(app, /return ensureQwenConfigured\(\);/);
  assert.doesNotMatch(app, /if \(allowFallback\)\s*\{[\s\S]*?return true;/);
  assert.match(index, /id="qwen-first-run-dialog"/);
  assert.match(index, /配置完成前，示例和研究问题都不会运行/);
  assert.match(app, /form\.addEventListener\("submit"/);
  assert.match(app, /runClosedLoopTask\(payload\)/);
});

test('qwen credentials are saved locally and restored into a new backend session', () => {
  assert.match(app, /const QWEN_CONNECTION_STORAGE_KEY = "oncology_qwen_connection_v1"/);
  assert.match(app, /function saveStoredQwenConnection\(connection\)/);
  assert.match(app, /function clearStoredQwenConnection\(\)/);
  assert.match(app, /async function restoreSavedQwenSession\(\)/);
  assert.match(app, /saveStoredQwenConnection\(connection\)/);
  assert.match(app, /await restoreSavedQwenSession\(\)/);
  assert.match(index, /清除本机连接/);
  assert.match(app, /这次没有用本地话术替代模型回答/);
});

test('autonomous progress and agent runtime are grounded in returned result fields', () => {
  for (const label of ['正在理解研究对象与目标', '正在规划检索路径与证据需求', '正在发现公开来源与可机器读取数据', '正在建立证据链与来源血缘', '正在执行质量门与独立 Critic 检查', '正在整理矩阵、字段字典与可复用资产']) {
    assert.match(app, new RegExp(label));
  }
  assert.match(index, /id="progress-phase-list"/);
  assert.match(index, /id="agent-runtime-grid"/);
  assert.match(app, /result\.critic_report/);
  assert.match(app, /result\.quality_gate_report/);
  assert.match(app, /result\.source_items/);
});

test('wish rabbit is an interactive research companion that routes back to the existing planner', () => {
  assert.match(index, /id="wish-rabbit"/);
  assert.match(index, /id="wish-rabbit-toggle"/);
  assert.match(index, /id="wish-rabbit-panel"/);
  assert.match(index, /id="wish-rabbit-input"/);
  assert.match(index, /id="wish-rabbit-send"/);
  assert.match(index, /id="wish-rabbit-form"/);
  assert.match(index, /id="wish-rabbit-clear"/);
  assert.match(index, /RESEARCH COMPANION/);
  assert.match(index, /title="和科研兔聊聊研究想法"/);
  assert.match(index, /<strong>科研兔<\/strong>/);
  assert.match(index, /科研解析助手/);
  assert.match(index, /data-wish-explain="topic"/);
  assert.match(index, /data-wish-explain="dataset"/);
  assert.match(index, /data-wish-prompt="请把我们接下来的聊天整理成研究问题">整理问题<\/button>/);
  assert.doesNotMatch(index, />随时整理研究问题<\/button>/);
  assert.match(index, /data-wish-explain="topic"/);
  assert.doesNotMatch(index, /帮我整理一个愿望/);
  const wishRabbitSource = app.slice(app.indexOf('function initWishRabbit'), app.indexOf('renderAgentRuntime(null);'));
  assert.match(app, /function wishRabbitStage\(text\)/);
  assert.match(app, /function wishRabbitReply\(text, stage\)/);
  assert.match(app, /function wishRabbitExplain\(kind = "topic"\)/);
  assert.match(app, /function jumpFromWishRabbit\(stage, handoffText = ""\)/);
  assert.match(app, /function sendWishRabbitMessage\(input, messages\)/);
  assert.match(app, /data-wish-jump/);
  assert.match(app, /data-wish-explain/);
  assert.match(app, /async function requestWishRabbitModel/);
  assert.match(app, /async function sendWishRabbitModelMessage/);
  assert.match(app, /async function formatWishRabbitResearchQuestion/);
  assert.match(app, /api\/agent\/companion\/research-question/);
  assert.match(app, /function wishRabbitChatContext\(\)/);
  assert.match(app, /data-wish-format/);
  assert.match(app, /sendWishRabbitModelMessage/);
  assert.match(app, /input\.addEventListener\("keydown"/);
  assert.match(app, /plannerInput\.value = handoffText/);
  assert.match(app, /setPlannerStage\(stage\)/);
  assert.doesNotMatch(wishRabbitSource, /form\.requestSubmit\(\)/);
  assert.match(styles, /\.wish-rabbit-avatar \{[^}]*overflow: hidden/);
  assert.match(styles, /\.wish-rabbit-avatar svg \{[^}]*transform: translateX\(-3px\)/);
  assert.match(styles, /\.wish-rabbit-messages \{[^}]*max-height: 500px/);
  assert.match(styles, /\.wish-rabbit-composer textarea \{[^}]*min-height: 80px/);
  assert.match(index, /wish-rabbit-message-avatar[^>]*aria-hidden="true"><svg/);
});

test('ordinary questions use a transparent quick literature lookup before full planning', () => {
  assert.match(app, /async function startQuickLookup\(topicText\)/);
  assert.match(app, /domain: "quick_lookup"/);
  assert.match(app, /literature-scan/);
  assert.match(app, /data-quick-promote="true"/);
  assert.match(app, /进入完整研究规划/);
  assert.match(app, /quickScan: run\.quickScan \|\| null/);
  const start = app.indexOf('function shouldQuickLookup');
  const end = app.indexOf('async function startQuickLookup');
  const context = {};
  vm.runInNewContext(`${app.slice(start, end)}; this.shouldQuickLookup = shouldQuickLookup; this.quickLookupQuery = quickLookupQuery;`, context);
  assert.equal(context.shouldQuickLookup('什么是乳腺癌'), true);
  assert.equal(context.shouldQuickLookup('为什么天空是蓝色的'), true);
  assert.equal(context.shouldQuickLookup('你好'), false);
  assert.equal(context.shouldQuickLookup('你是谁'), false);
  assert.equal(context.quickLookupQuery('什么是乳腺癌'), 'breast cancer');
  assert.equal(context.quickLookupQuery('为什么天空是蓝色的'), 'sky blue Rayleigh scattering');
});

test('astronomy uses the shared planner panel vocabulary while keeping observation semantics', () => {
  const astronomy = readFileSync(path.join(__dirname, '../astronomy.js'), 'utf8');
  assert.match(astronomy, /class="planner-panel-heading"/);
  assert.match(astronomy, /class="planner-evidence-card"/);
  assert.match(astronomy, /class="planner-status-note"/);
  assert.match(astronomy, /不使用患者表/);
});

test('single-round acquisition does not present a negative iteration effect', () => {
  assert.match(app, /const hasFollowupRound = completedRounds >= 2/);
  assert.match(app, /rounds\.textContent = hasFollowupRound \? `\$\{completedRounds\}\/\$\{report\.max_rounds\} 轮` : "无"/);
  assert.match(app, /本次任务没有第二轮迭代。/);
});

test('wish rabbit sends the main entry body and result evidence as chat context', () => {
  const source = app.slice(app.indexOf('function wishRabbitStage'), app.indexOf('renderAgentRuntime(null);'));
  const elements = {
    '#planner-topic': { value: '比较两个公开数据集的缺失模式' },
    '#result-status': { textContent: '已完成' },
    '#progress-label': { textContent: '准备数据' },
    '#dataset-title': { textContent: '公开数据集对照表' },
    '#agent-summary': { textContent: '已发现两个来源' },
  };
  const context = {
    document: { querySelector(selector) { return elements[selector] || null; } },
    state: { result: { research_spec: { question: '比较两个公开数据集的缺失模式' }, quality_gate_report: { status: 'review' }, source_items: [{ source_id: 'zenodo:1' }] } },
  };
  vm.runInNewContext(`${source}; this.wishRabbitChatContext = wishRabbitChatContext;`, context);
  const snapshot = context.wishRabbitChatContext();
  assert.equal(snapshot.question, '比较两个公开数据集的缺失模式');
  assert.equal(snapshot.dataset_title, '公开数据集对照表');
  assert.match(snapshot.result.quality_gate_report, /review/);
  assert.match(snapshot.result.source_items, /zenodo:1/);
});

test('wish rabbit can locally format a conversation into a research handoff', () => {
  const source = app.slice(app.indexOf('function wishRabbitStage'), app.indexOf('renderAgentRuntime(null);'));
  const context = {
    document: { querySelector() { return null; } },
    state: { result: null },
  };
  vm.runInNewContext(`${source}; this.wishRabbitLocalResearchQuestion = wishRabbitLocalResearchQuestion;`, context);
  const formatted = context.wishRabbitLocalResearchQuestion([{ role: 'user', content: '我想找一份可以下载的鸟类迁徙数据' }]);
  assert.match(formatted, /研究对象/);
  assert.match(formatted, /鸟类迁徙数据/);
  assert.match(formatted, /数据需求/);
});

test('wish rabbit send appends a user message, clears the composer, and offers a planner handoff', () => {
  const source = app.slice(app.indexOf('function wishRabbitStage'), app.indexOf('renderAgentRuntime(null);'));
  const context = { escapeHtml: (value) => String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;') };
  vm.runInNewContext(`${source}; this.sendWishRabbitMessage = sendWishRabbitMessage;`, context);
  const input = { value: '我想查找一套可下载的数据', focus() {} };
  const messages = { scrollHeight: 320, scrollTop: 0, html: '', insertAdjacentHTML(_position, html) { this.html += html; } };
  context.sendWishRabbitMessage(input, messages);
  assert.equal(input.value, '');
  assert.equal(messages.scrollTop, 320);
  assert.match(messages.html, /wish-rabbit-message is-user/);
  assert.match(messages.html, /data-wish-jump="literature"/);
  assert.match(messages.html, /带入研究向导.*查找依据/);
});

test('wish rabbit formats assistant markdown as readable HTML', () => {
  const source = app.slice(app.indexOf('const escapeHtml'), app.indexOf('const TERM_TRANSLATIONS'));
  const context = {};
  vm.runInNewContext(`${source}; this.renderMarkdown = renderMarkdown;`, context);
  const html = context.renderMarkdown('### 1. 概念解释\n\n* **原理解析**：说明\n* **文献方法**：总结');
  assert.match(html, /<h3>1\. 概念解释<\/h3>/);
  assert.match(html, /<ul><li><strong>原理解析<\/strong>：说明<\/li>/);
  assert.match(html, /<strong>文献方法<\/strong>/);
  assert.doesNotMatch(html, /<script/i);
});

test('wish rabbit keeps casual chat conversational without forcing a research handoff', () => {
  const source = app.slice(app.indexOf('function wishRabbitStage'), app.indexOf('renderAgentRuntime(null);'));
  const context = {};
  vm.runInNewContext(`${source}; this.wishRabbitReply = wishRabbitReply;`, context);
  const reply = context.wishRabbitReply('今天有点累，陪我聊聊天', 'topic');
  assert.match(reply.text, /可以/);
  assert.equal(reply.stage, undefined);
});

test('wish rabbit explanation stays grounded when the page has no result yet', () => {
  const source = app.slice(app.indexOf('function wishRabbitStage'), app.indexOf('renderAgentRuntime(null);'));
  const context = {};
  vm.runInNewContext(`${source}; this.wishRabbitExplain = wishRabbitExplain;`, context);
  const explanation = context.wishRabbitExplain('topic');
  assert.match(explanation, /课题解析/);
  assert.match(explanation, /尚未返回正式运行结果/);
});

test('evidence lineage remains an auditable interactive surface', () => {
  assert.match(index, /EVIDENCE LINEAGE/);
  assert.match(index, /id="lineage-graph"/);
  assert.match(index, /查看完整来源关系图/);
  assert.match(app, /function renderLineage\(sources, candidates, dataset\)/);
  assert.match(app, /state\.lineage\.selected/);
  assert.match(styles, /\.lineage-node:hover \.lineage-hit-area/);
});
