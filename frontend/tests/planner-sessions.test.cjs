const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = readFileSync(path.join(__dirname, '../app.js'), 'utf8');
function harness(names, overrides = {}) {
  const elements = new Map();
  const rendered = [];
  const context = vm.createContext({
    state: {}, plannerState: { sessionId: 'A' }, plannerRuns: new Map(),
    resultsPanel: { hidden: true },
    document: {
      body: { classList: { add() {}, toggle() {}, contains() { return false; } } },
      querySelector(id) {
        if (!elements.has(id)) elements.set(id, { innerHTML: '', value: '', scrollIntoView() {} });
        return elements.get(id);
      },
    },
    readJson: async (response) => {
      if (!response.ok) throw new Error(response.message);
      return response.json();
    },
    escapeHtml: (v) => String(v ?? ''),
    renderResult: (v) => rendered.push(v.task_id), renderClosedLoop() {},
    plannerStatusCopy: (v) => v, persistPlannerRun() {},
    ...overrides,
  });
  for (const name of names) {
    const start = source.search(new RegExp(`(?:async )?function ${name}\\(`));
    assert.notEqual(start, -1, name);
    const remainder = source.slice(start + 1);
    const next = remainder.search(/\n(?:async )?function /);
    vm.runInContext(source.slice(start, next < 0 ? source.length : start + 1 + next), context);
  }
  return { context, rendered, elements };
}
const deferred = () => {
  let resolve;
  const promise = new Promise((r) => { resolve = r; });
  return { promise, resolve };
};
const result = (id, count = 1) => ({
  task_id: id, modeling_dataset: { rows: Array.from({ length: count }, () => ({})) },
  source_datasets: [{ rows: [{ source_id: id }] }],
  readiness: { status: count ? '待复核' : '数据不足', warnings: count ? [] : ['患者资料缺失'] },
});
const response = (value) => ({ ok: true, json: async () => value });
const run = (id) => ({ sessionId: id, inputTopic: `对话${id}`, contract: { research_question: `问题${id}` }, build: { taskId: `task-${id}` } });

test('sending a simple message clears the composer and preserves the sent bubble', () => {
  const elements = new Map();
  const { context: c } = harness(['classifyPlannerInput', 'renderPlannerInputReply', 'submitPlannerTopic'], {
    plannerElement: (id) => {
      if (!elements.has(id)) elements.set(id, { value: '', innerHTML: '' });
      return elements.get(id);
    },
    plannerEmpty: () => '', clearPlannerContractSurfaces() {}, setPlannerStage() {},
    switchPlannerTab() {}, renderPlannerRecent() {},
  });
  c.plannerElement('#planner-topic').value = '你好呀';
  c.submitPlannerTopic('你好呀');
  assert.equal(c.plannerElement('#planner-topic').value, '');
  assert.match(c.plannerElement('#planner-chat').innerHTML, /你好呀/);
});

test('contest example and shorthand route to astronomy before medical API credentials', () => {
  const started = [];
  const { context: c } = harness(['classifyPlannerInput', 'startPlannerResearch'], {
    startAstronomyResearch: (topic) => started.push(topic),
    ensureResearchProvidersConfigured: () => { throw new Error('must not require medical credentials'); },
  });
  for (const text of ['我希望研究 Ia 型超新星光变曲线', '我想研究Ia型曲线', 'Type Ia supernova light curves']) {
    assert.equal(c.classifyPlannerInput(text).domain, 'astronomy');
    c.startPlannerResearch(text);
  }
  assert.equal(started.length, 3);
  assert.equal(c.classifyPlannerInput('EGFR 突变与肺腺癌患者生存有何关联？').kind, 'research');
  assert.notEqual(c.classifyPlannerInput('什么是 Ia 型超新星').kind, 'research');
});

test('unknown research topics enter the general autonomous discovery path', () => {
  const { context: c } = harness(['classifyPlannerInput', 'buildPlannerRequest'], {
    buildAgentTaskPayload: () => ({ use_qwen: false }),
  });
  const intent = c.classifyPlannerInput('我想研究火星尘埃中的甲烷变化，并找可下载的数据集');
  assert.equal(intent.kind, 'research');
  assert.equal(intent.domain, 'general_science');
  const payload = c.buildPlannerRequest({
    domain: 'general_science',
    inputTopic: '我想研究火星尘埃中的甲烷变化，并找可下载的数据集',
    contract: { research_question: '通用研究问题' },
  }, { expand: true });
  assert.match(payload.question, /火星尘埃/);
  assert.equal(Array.from(payload.focus_tools).join(','), 'search_zenodo,search_europe_pmc');
});

test('progress renders neither refill the sent text nor erase the next draft', () => {
  const elements = new Map();
  const { context: c } = harness(['renderPlannerRun'], {
    plannerElement: (id) => {
      if (!elements.has(id)) elements.set(id, { value: '', innerHTML: '' });
      return elements.get(id);
    },
    syncPlannerStateFromRun() {}, renderPlannerChat() {}, plannerEmpty: () => '',
    clearPlannerContractSurfaces() {}, setPlannerStage() {}, switchPlannerTab() {}, renderPlannerRecent() {},
  });
  c.renderPlannerRun({ inputTopic: '已经发送的问题' });
  assert.equal(c.plannerElement('#planner-topic').value, '');
  c.plannerElement('#planner-topic').value = '下一条尚未发送';
  c.renderPlannerRun({ inputTopic: '已经发送的问题' });
  assert.equal(c.plannerElement('#planner-topic').value, '下一条尚未发送');
});

test('late A detail response cannot replace B; existing global result cannot suppress loading', async () => {
  const requests = { 'task-A': deferred(), 'task-B': deferred() };
  const { context: c, rendered } = harness(['isActivePlannerSession', 'plannerArtifact', 'loadPlannerResult', 'openPlannerTechnical'], {
    fetchApi: (url) => requests[url.split('/').at(-1)].promise,
  });
  c.plannerRuns.set('A', run('A')); c.plannerRuns.set('B', run('B'));
  c.state.result = result('unrelated');
  const a = c.openPlannerTechnical();
  c.plannerState.sessionId = 'B';
  const b = c.openPlannerTechnical();
  requests['task-B'].resolve(response(result('task-B'))); await b;
  requests['task-A'].resolve(response(result('task-A'))); await a;
  assert.deepEqual(rendered, ['task-B']);
  assert.equal(c.state.result.task_id, 'task-B');
  assert.equal(c.resultsPanel.hidden, false);
  assert.equal(c.plannerRuns.get('A').result.task_id, 'task-A');
  await c.openPlannerTechnical();
  assert.equal(c.state.result.task_id, 'task-B');
});

test('empty table has no Excel/CSV success buttons; sources and quality report remain available', () => {
  const { context: c } = harness(['plannerArtifact', 'plannerOutputs']);
  const artifact = c.plannerArtifact(result('task-empty', 0));
  const html = c.plannerOutputs({ artifacts: [artifact] });
  assert.match(html, /数据不足/);
  assert.doesNotMatch(html, /data-planner-download="(?:xlsx|csv)"/);
  assert.match(html, /data-planner-download="sources"/);
  assert.match(html, /data-planner-download="quality_report"/);
});

test('parallel downloads keep the task and content captured by each button', async () => {
  const pending = [], downloaded = [], urls = new Map();
  const { context: c } = harness(['downloadPlannerArtifact'], {
    fetchApi: (url) => { const wait = deferred(); pending.push({ url, ...wait }); return wait.promise; },
    window: { setTimeout() {} }, showToast() {},
    URL: { createObjectURL: (blob) => { const url = `blob:${blob}`; urls.set(url, blob); return url; }, revokeObjectURL() {} },
  });
  c.document.body.appendChild = () => {};
  c.document.createElement = () => ({ click() { downloaded.push({ name: this.download, blob: urls.get(this.href) }); }, remove() {} });
  const a = c.downloadPlannerArtifact('loop-A:r1', 'csv', { textContent: 'A' });
  const b = c.downloadPlannerArtifact('loop-B:r2', 'xlsx', { textContent: 'B' });
  pending[1].resolve({ ok: true, blob: async () => 'B-content' }); await b;
  c.state.result = result('unrelated');
  pending[0].resolve({ ok: true, blob: async () => 'A-content' }); await a;
  assert.match(pending[0].url, /loop-A%3Ar1\/export\/csv$/);
  assert.deepEqual(downloaded, [
    { name: 'loop-B_r2-科研数据集.xlsx', blob: 'B-content' },
    { name: 'loop-A_r1-科研数据集.csv', blob: 'A-content' },
  ]);
});

test('expanded retrieval carries conversation context, explicit datasets and a larger budget', () => {
  const { context: c } = harness(['buildPlannerRequest'], {
    buildAgentTaskPayload: () => ({ question: '其他对话', max_sources: 8, max_collection_rounds: 8 }),
  });
  const a = run('A');
  a.sourcePlanning = { dataset_candidates: [{ accession: 'GSE1234' }] };
  const payload = c.buildPlannerRequest(a, { expand: true, extra: 'GSE5678 luad_test 肺癌治疗' });
  assert.match(payload.question, /问题A\n对话A/);
  assert.doesNotMatch(payload.question, /其他对话/);
  assert.equal(payload.max_sources, 20);
  assert.equal(payload.max_collection_rounds, 12);
  assert.deepEqual(Array.from(payload.focus_accessions), ['GSE5678', 'luad_test', 'GSE1234']);
});

test('interleaved builds retain both histories without rendering the inactive conversation', async () => {
  const pending = { A: deferred(), B: deferred() }, views = [];
  const { context: c } = harness(['isActivePlannerSession', 'plannerArtifact', 'runPlannerDatasetBuild'], {
    plannerElement: () => ({ value: '' }), buildPlannerRequest: (r) => ({ question: r.inputTopic }),
    runClosedLoopTask: (_payload, r) => pending[r.sessionId].promise,
    renderPlannerRun: (r) => views.push(r.sessionId), plannerMessage() {},
  });
  const aRun = { ...run('A'), result: result('old-A'), artifacts: [{ taskId: 'old-A', rowCount: 1 }] };
  const bRun = { ...run('B'), result: result('old-B') };
  c.plannerRuns.set('A', aRun); c.plannerRuns.set('B', bRun);
  const a = c.runPlannerDatasetBuild({});
  c.plannerState.sessionId = 'B';
  const b = c.runPlannerDatasetBuild({});
  pending.B.resolve(result('new-B')); await b;
  pending.A.resolve(result('new-A', 0)); await a;
  assert.deepEqual(views, ['A', 'B', 'B']);
  assert.equal(aRun.build.status, '数据不足');
  assert.equal(bRun.build.taskId, 'new-B');
  assert.deepEqual(Array.from(aRun.artifacts, (item) => item.taskId), ['old-A', 'new-A']);
});
