/*
 * Capture the review-facing frontend surfaces without credentials.
 *
 * If a completed local task exists, the script also renders its real returned
 * result. Set RESEARCH_AGENT_TASK_ID to pin an exact task; otherwise the latest
 * task is used. Set RESEARCH_AGENT_RESULT_PREFIX to avoid mixing screenshots
 * from different tasks. The result screenshots preserve the returned PASS/REVIEW
 * state and must not be described as benchmark scores.
 * The reference-style pair uses RESEARCH_AGENT_REFERENCE_TASK_ID (defaulting
 * to the documented loop-91ef39cffd32:r3 task) and writes clean source frames
 * to .tmp for scripts/annotate_reference_style_screenshots.py.
 *
 * This script intentionally uses a locally supplied Playwright runtime rather
 * than adding a production dependency. Example:
 *   $env:NODE_PATH = "tmp/pwcap/node_modules"
 *   node scripts/capture_frontend_screenshots.js
 */

const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const baseUrl = process.env.RESEARCH_AGENT_URL || "http://127.0.0.1:8000";
const outputDir = path.resolve(__dirname, "../docs/images");
const tempDir = path.resolve(__dirname, "../.tmp");
const resultPrefix = process.env.RESEARCH_AGENT_RESULT_PREFIX || "kernel-lab-real-run";
const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH ||
  "C:/Users/xsc/AppData/Local/ms-playwright/chromium-1228/chrome-win64/chrome.exe";

fs.mkdirSync(outputDir, { recursive: true });
fs.mkdirSync(tempDir, { recursive: true });

async function dismissConfiguration(page) {
  const firstRun = page.locator("#qwen-first-run-dialog");
  if (await firstRun.isVisible().catch(() => false)) {
    const configure = page.locator("#qwen-first-run-configure");
    if (await configure.isVisible().catch(() => false)) await configure.click();
  }
  const connection = page.locator("#qwen-connection-dialog");
  if (await connection.isVisible().catch(() => false)) {
    const cancel = page.locator("#qwen-cancel-config");
    const close = page.locator("#qwen-dialog-close");
    if (await cancel.isVisible().catch(() => false)) await cancel.click();
    else if (await close.isVisible().catch(() => false)) await close.click();
  }
  await page.waitForTimeout(250);
}

async function hideFloatingAssistant(page) {
  await page.addStyleTag({
    // Keep the raw-characteristics dialog visible for the audit screenshot;
    // only the first-run/API configuration dialogs and floating helper are UI noise.
    content: "html{scroll-behavior:auto!important}.wish-rabbit{display:none!important} #qwen-first-run-dialog[open],#qwen-connection-dialog[open]{display:none!important}",
  });
}

async function renderPinnedResult(page, requestedTaskId) {
  return page.evaluate(async ({ requestedTaskId: taskId }) => {
    const endpoint = taskId
      ? `/api/agent/tasks/${encodeURIComponent(taskId)}`
      : "/api/agent/tasks/latest";
    const response = await fetch(endpoint);
    if (!response.ok) throw new Error(`Cannot load task result (${response.status})`);
    const result = await response.json();
    globalThis.__screenshotResult = result;
    // app.js keeps state in a top-level lexical binding rather than window.
    eval("state.result = globalThis.__screenshotResult");
    renderResult(result);
    document.querySelector("#results").hidden = false;
    delete globalThis.__screenshotResult;
    return {
      taskId: result.task_id,
      status: result.status,
      agentMode: result.agent_mode,
      rows: result.modeling_dataset?.row_count ?? 0,
      columns: result.modeling_dataset?.columns?.length ?? 0,
      patients: result.modeling_dataset?.patient_count ?? 0,
      samples: result.modeling_dataset?.sample_count ?? 0,
      sourceItems: result.source_items?.length ?? 0,
      qualityGate: result.quality_gate_report?.overall || result.quality_gate_report?.overall_status || "UNKNOWN",
    };
  }, { requestedTaskId });
}

async function screenshotLocator(page, selector, filename) {
  const locator = page.locator(selector);
  if (!(await locator.isVisible().catch(() => false))) return false;
  await page.addStyleTag({ content: ".topbar{position:static!important}" });
  await page.evaluate(() => window.scrollTo(0, 0));
  await locator.screenshot({ path: path.join(outputDir, filename) });
  return true;
}

async function capturePlanner(browser) {
  const desktop = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  await desktop.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await dismissConfiguration(desktop);
  await desktop.screenshot({ path: path.join(outputDir, "frontend-home-clean-20260906.png"), fullPage: true });

  const assistantToggle = desktop.locator("#wish-rabbit-toggle");
  if (await assistantToggle.isVisible().catch(() => false)) {
    await assistantToggle.click();
    await desktop.waitForTimeout(250);
    await desktop.screenshot({ path: path.join(outputDir, "research-companion-open-20260906.png"), fullPage: true });
    await screenshotLocator(desktop, "#wish-rabbit-panel", "research-companion-panel-20260906.png");
  }
  await desktop.close();

  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  await mobile.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await dismissConfiguration(mobile);
  await mobile.screenshot({ path: path.join(outputDir, "frontend-home-mobile-clean-20260906.png"), fullPage: true });
  await mobile.close();
}

async function captureKernel(browser) {
  const desktop = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  await desktop.goto(`${baseUrl}/?surface=kernel`, { waitUntil: "networkidle" });
  await dismissConfiguration(desktop);
  await hideFloatingAssistant(desktop);
  await desktop.screenshot({ path: path.join(outputDir, "kernel-lab-desktop-clean-20260906.png"), fullPage: true });
  await screenshotLocator(desktop, "#agent-runtime", "kernel-lab-agent-runtime-20260906.png");
  await screenshotLocator(desktop, "#task-entry", "kernel-lab-task-entry-20260906.png");
  await screenshotLocator(desktop, "#agent-architecture", "kernel-lab-agent-architecture-20260906.png");
  await desktop.close();

  const mobile = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1 });
  await mobile.goto(`${baseUrl}/?surface=kernel`, { waitUntil: "networkidle" });
  await dismissConfiguration(mobile);
  await hideFloatingAssistant(mobile);
  await mobile.screenshot({ path: path.join(outputDir, "kernel-lab-mobile-clean-20260906.png"), fullPage: true });
  await mobile.close();
}

async function captureKernelResult(browser) {
  const desktop = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  await desktop.goto(`${baseUrl}/?surface=kernel`, { waitUntil: "networkidle" });
  await dismissConfiguration(desktop);
  await hideFloatingAssistant(desktop);
  const taskId = process.env.RESEARCH_AGENT_TASK_ID || "";
  const resultInfo = await renderPinnedResult(desktop, taskId);
  await screenshotLocator(desktop, "#agent-runtime", `${resultPrefix}-runtime-20260906.png`);
  await screenshotLocator(desktop, "#results", `${resultPrefix}-20260906.png`);
  await screenshotLocator(desktop, "#quality-gates", `${resultPrefix}-quality-gates-20260906.png`);
  await screenshotLocator(desktop, "#research-data", `${resultPrefix}-research-data-20260906.png`);
  await screenshotLocator(desktop, "#provenance", `${resultPrefix}-provenance-20260906.png`);
  await desktop.close();
  return resultInfo;
}

async function captureReferenceStyleCurrentRun(browser) {
  const taskId = process.env.RESEARCH_AGENT_REFERENCE_TASK_ID ||
    process.env.RESEARCH_AGENT_TASK_ID ||
    "loop-91ef39cffd32:r3";
  const cleanQualityData = path.join(tempDir, "current-reference-quality-data-clean.png");
  const cleanRawModal = path.join(tempDir, "current-reference-raw-modal-clean.png");

  const qualityPage = await browser.newPage({ viewport: { width: 1440, height: 1100 }, deviceScaleFactor: 1 });
  await qualityPage.goto(`${baseUrl}/?surface=kernel`, { waitUntil: "networkidle" });
  await dismissConfiguration(qualityPage);
  await hideFloatingAssistant(qualityPage);
  const resultInfo = await renderPinnedResult(qualityPage, taskId);
  // Keep the protocol context, all four gates, and the beginning of the
  // structured-data table in one review-facing frame. Calculate the absolute
  // position instead of relying on a document-height magic number so small
  // copy/font changes do not move the red callouts to the wrong section.
  const qualityScroll = await qualityPage.evaluate(() => {
    const section = document.querySelector("#quality-gates");
    if (!section) return 0;
    return Math.max(0, Math.round(section.getBoundingClientRect().top + window.scrollY - 340));
  });
  await qualityPage.evaluate((y) => window.scrollTo(0, y), qualityScroll);
  await qualityPage.waitForTimeout(500);
  await qualityPage.screenshot({ path: cleanQualityData });
  await qualityPage.close();

  const modalPage = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  await modalPage.goto(`${baseUrl}/?surface=kernel`, { waitUntil: "networkidle" });
  await dismissConfiguration(modalPage);
  await hideFloatingAssistant(modalPage);
  await renderPinnedResult(modalPage, taskId);
  await modalPage.evaluate(() => document.querySelector("#research-data")?.scrollIntoView({ block: "center" }));
  await modalPage.waitForTimeout(400);
  // The audit view exposes raw_characteristics without changing the stored
  // result. Use DOM click so the lexical app state receives the event.
  await modalPage.evaluate(() => document.querySelector("#dataset-audit-view")?.click());
  await modalPage.waitForTimeout(120);
  await modalPage.waitForSelector("#dataset-table thead th", { state: "attached" });
  const rawButton = modalPage.locator('#dataset-table tbody tr[data-row-index="0"] .raw-characteristics-button');
  if (!(await rawButton.count())) {
    throw new Error("Current result has no raw-characteristics audit control");
  }
  await rawButton.evaluate((button) => button.click());
  await modalPage.waitForTimeout(180);
  // Keep the full raw record scrollable while fitting the same compact modal
  // composition as the reference image; the scrollbar signals that more rows
  // remain available for audit.
  await modalPage.addStyleTag({
    content: `
      #raw-characteristics-dialog { max-height: 68vh !important; overflow: hidden !important; }
      #raw-characteristics-dialog .table-wrap { max-height: 360px !important; overflow-y: auto !important; overflow-x: hidden !important; }
      #raw-characteristics-dialog .raw-dialog-note { background: #fff !important; margin-top: 10px !important; padding-top: 4px !important; }
    `,
  });
  await modalPage.waitForTimeout(180);
  await modalPage.screenshot({ path: cleanRawModal });
  await modalPage.close();
  return resultInfo;
}

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath });
  try {
    await capturePlanner(browser);
    await captureKernel(browser);
    const resultInfo = await captureKernelResult(browser).catch((error) => ({ skipped: error.message }));
    console.log(`Kernel result capture: ${JSON.stringify(resultInfo)}`);
    const referenceInfo = await captureReferenceStyleCurrentRun(browser).catch((error) => ({ skipped: error.message }));
    console.log(`Reference-style current run capture: ${JSON.stringify(referenceInfo)}`);
  } finally {
    await browser.close();
  }
  console.log(`Screenshots written to ${outputDir}`);
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
