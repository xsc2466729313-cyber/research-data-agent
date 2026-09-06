const assert = require('node:assert/strict');
const { test } = require('node:test');
const { readFileSync } = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const astronomySource = readFileSync(path.join(__dirname, '../astronomy.js'), 'utf8');
const stylesSource = readFileSync(path.join(__dirname, '../styles.css'), 'utf8');

function harness(overrides = {}) {
  const elements = new Map(), rendered = [];
  const c = vm.createContext({
    plannerRuns: new Map(), plannerState: {}, state: {}, resultsPanel: {},
    plannerElement: (id) => { if (!elements.has(id)) elements.set(id, { value: '', innerHTML: '', scrollIntoView() {} }); return elements.get(id); },
    escapeHtml: String, safePlannerUrl: String, persistPlannerRun() {}, plannerMessage() {},
    isActivePlannerSession: (id) => c.plannerState.sessionId === id,
    readJson: async (r) => r.json(),
    ...overrides,
  });
  vm.runInContext(readFileSync(path.join(__dirname, '../astronomy.js'), 'utf8'), c);
  c.renderAstronomyRun = (run) => rendered.push(run.sessionId);
  return { c, elements, rendered };
}
const result = (id, count = 2) => ({ task_id: id, status: 'completed', row_count: count, sources: [], errors: [] });

test('send clears composer, preserves original input, and never requests Qwen', async () => {
  const { c } = harness();
  c.executeAstronomyRun = async (run) => { assert.equal(run.inputTopic, '我想研究Ia型曲线'); };
  c.plannerElement('#planner-topic').value = '我想研究Ia型曲线';
  await c.startAstronomyResearch('我想研究Ia型曲线');
  assert.equal(c.plannerElement('#planner-topic').value, '');
  assert.equal(c.plannerRuns.size, 1);
});

test('new result keeps previous downloadable artifacts and background task cannot render another conversation', async () => {
  const { c, rendered } = harness({ fetchApi: async () => ({ json: async () => result('astro-A-new', 3) }) });
  const a = { sessionId: 'A', build: { taskId: 'astro-A-new' }, artifacts: [{ taskId: 'astro-A-old', rowCount: 2 }] };
  c.plannerState.sessionId = 'B';
  await c.watchAstronomyRun(a, 'astro-A-new');
  assert.deepEqual(Array.from(a.artifacts, (item) => item.taskId), ['astro-A-old', 'astro-A-new']);
  assert.equal(a.astronomy.task_id, 'astro-A-new');
  assert.equal(rendered.length, 0);
});

test('history loads its own task and transport failure allows retry', async () => {
  const urls = [];
  const { c } = harness({ fetchApi: async (url) => { urls.push(url); return { json: async () => result('astro-own') }; } });
  const run = { sessionId: 'A', build: { taskId: 'astro-own' } };
  await c.loadAstronomyResult(run, 'astro-own');
  assert.deepEqual(urls, ['/api/astronomy/tasks/astro-own']);
  assert.equal(run.astronomy.task_id, 'astro-own');
  c.fetchApi = async () => { throw new Error('offline'); };
  run.running = true;
  assert.equal(await c.loadAstronomyResult(run, 'astro-own'), null);
  assert.equal(run.running, false);
  assert.equal(run.astronomy.task_id, 'astro-own');
});

test('technical view reuses workbench panels and scoped download actions, with raw evidence collapsed', () => {
  const { c } = harness();
  const data = { ...result('astro-test', 17), requested_sources: ['cfa4'], rejected_count: 2,
    workflow: [{ operation: 'parse_and_align', source: 'cfa4', output_rows: 17, identity_rule: 'catalog-local exact SN' }],
    sources: [{ source_id: 'J/ApJS/200/12/table6', row_count: 19, url: 'https://example.org/table', sha256: 'unique-hash', retrieved_at: '2026-09-05T00:00:00Z' }],
    preview: [{ object_id: 'cfa4:sample', mjd: 55000, magnitude: 0, band: 'B', magnitude_error: 0.1, source_id: 'J/ApJS/200/12/table6' }], limitations: ['No inferred flux'] };
  const html = c.astronomyDetails(data, { prefix: 'astro-detail', downloads: true });
  assert.match(html, /class="results-toc"/);
  assert.match(html, /class="result-overview"/);
  assert.match(html, /class="section-heading"/);
  assert.match(html, /观测数据矩阵/);
  assert.match(html, /星等误差/);
  assert.match(html, /<td>0<\/td>/);
  assert.match(html, /data-astronomy-download="csv" data-task-id="astro-test"/);
  assert.match(html, /data-astronomy-download="xlsx" data-task-id="astro-test"/);
  assert.match(html, /<details class="report-drawer">[\s\S]*unique-hash[\s\S]*<\/details>/);
  assert.doesNotMatch(html, /<details[^>]+open/);
  assert.doesNotMatch(c.astronomyDetails(data), /data-astronomy-download=/);
  assert.doesNotMatch(c.astronomyDetails({ ...data, row_count: 0, preview: [], status: 'failed' }, { downloads: true }), /data-astronomy-download="(?:csv|xlsx)"/);
});

test('astronomy results keep the shared next-step card and render a readable source lineage graph', () => {
  const { c } = harness();
  const data = { ...result('astro-lineage', 8), requested_sources: ['cfa4'],
    workflow: [{ source: 'cfa4', operation: 'parse_and_align', input_rows: 10, output_rows: 8 }],
    sources: [{ source_id: 'J/ApJS/200/12/table6', row_count: 10, url: 'https://example.org/table' }] };
  const html = c.astronomyDetails(data, { prefix: 'astro-view', downloads: true });
  assert.match(html, /id="astro-view-lineage" class="astro-lineage"/);
  assert.match(html, /研究问题/);
  assert.match(html, /观测矩阵/);
  assert.match(html, /J\/ApJS\/200\/12\/table6/);
  const longSourceHtml = c.astronomyDetails({ ...data, sources: [{ source_id: 'very-long-source-identifier-which-needs-wrapping', row_count: 10 }] }, { prefix: 'astro-long', downloads: true });
  assert.match(longSourceHtml, /class="astro-lineage-source-label"[^>]*><tspan[^>]*>very-long-source-/);
  assert.match(stylesSource, /\.astro-lineage-source-card strong, \.astro-lineage-source-card code, \.astro-lineage-source-card span \{[^}]*overflow-wrap: anywhere/);
  assert.match(astronomySource, /class="planner-next-action astronomy-next-action"/);
  assert.match(astronomySource, /data-sources="\$\{escapeHtml\(sourceList\)\}"/);
  assert.doesNotMatch(astronomySource, /扩展操作会新增 KSP 目录/);
});

test('late astronomy detail response cannot replace a different conversation or its selected version', async () => {
  const elements = new Map();
  const element = (id) => { if (!elements.has(id)) elements.set(id, { hidden: true, innerHTML: '', scrollIntoView() {} }); return elements.get(id); };
  const { c } = harness({ document: { querySelector: element, body: { classList: { add() {} } } } });
  let resolveA;
  const pendingA = new Promise((resolve) => { resolveA = resolve; });
  c.loadAstronomyResult = async (run, id) => id === 'astro-A' ? pendingA : result('astro-B');
  c.astronomyDetails = (data) => `DATA:${data.task_id}`;
  const a = { sessionId: 'A', inputTopic: 'Topic A', build: { taskId: 'astro-A' } };
  const b = { sessionId: 'B', inputTopic: 'Topic B', build: { taskId: 'astro-B' } };
  c.plannerState.sessionId = 'A';
  const first = c.openAstronomyTechnical(a);
  c.plannerState.sessionId = 'B';
  await c.openAstronomyTechnical(b);
  resolveA(result('astro-A')); await first;
  assert.match(element('#technical-context').innerHTML, /Topic B/);
  assert.equal(element('#astronomy-results').innerHTML, 'DATA:astro-B');
  assert.equal(element('#astronomy-results').hidden, false);
  assert.equal(c.resultsPanel.hidden, true);
});
