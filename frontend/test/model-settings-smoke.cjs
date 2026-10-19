const { chromium } = require("playwright");
const { spawn } = require("node:child_process");
const { mkdtempSync, mkdirSync } = require("node:fs");
const { tmpdir } = require("node:os");
const path = require("node:path");
const assert = require("node:assert/strict");

(async () => {
  const root = path.resolve(__dirname, "../..");
  const data = mkdtempSync(path.join(tmpdir(), "personaweaver-model-settings-"));
  const output = path.join(root, ".docs/plan/assets/2026-10-17-model-settings");
  mkdirSync(output, { recursive: true });
  const backend = "http://127.0.0.1:18761", base = "http://127.0.0.1:18762";
  let logs = "", browser, page;
  const server = spawn(process.env.PW_TEST_PYTHON || "python", [
    "-m", "uvicorn", "backend.tests.model_settings_preview:app", "--host", "127.0.0.1", "--port", "18761",
  ], {
    cwd: root, windowsHide: true, stdio: ["ignore", "ignore", "pipe"],
    env: { ...process.env, PERSONAWEAVER_DATA_DIR: data,
      PERSONAWEAVER_DB_PATH: path.join(data, "test.sqlite3"), PERSONAWEAVER_AGENT_DIR: path.join(data, "agent"),
      ECNU_API_BASE_URL: "", ECNU_API_KEY: "", ECNU_MODEL_NAME: "" },
  });
  const frontend = spawn(process.execPath, [
    path.join(root, "frontend/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", "18762", "--strictPort",
  ], {
    cwd: path.join(root, "frontend"), windowsHide: true, stdio: ["ignore", "ignore", "pipe"],
    env: { ...process.env, PERSONAWEAVER_API_TARGET: backend },
  });
  server.stderr.on("data", (chunk) => { logs += chunk; });
  frontend.stderr.on("data", (chunk) => { logs += chunk; });
  async function api(endpoint, method = "GET", body) {
    const result = await fetch(backend + "/api/v1" + endpoint, {
      method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined,
    });
    assert.ok(result.ok, `${endpoint}: ${result.status} ${await result.clone().text()}`);
    return result.json();
  }
  async function add(modelType, name, provider = "OpenAI") {
    const item = await api("/settings/models", "POST", {
      name, model: name, model_type: modelType, provider_name: provider,
      provider: "remote_api", base_url: backend + "/mock/v1", activate: false,
    });
    await api(`/settings/models/${item.id}/test`, "POST");
    return item;
  }
  async function choose(label, option) {
    await page.locator(".el-form-item").filter({ hasText: label }).locator(".el-select").click();
    await page.getByRole("option", { name: option }).click();
  }
  try {
    for (let attempt = 0; attempt < 80; attempt++) {
      if (server.exitCode !== null || frontend.exitCode !== null) throw new Error("Test server exited: " + logs);
      try { if ((await fetch(backend + "/health")).ok && (await fetch(base)).ok) break; } catch {}
      if (attempt === 79) throw new Error("Test servers timed out: " + logs);
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    browser = await chromium.launch({ channel: process.env.PW_TEST_BROWSER || "chrome", headless: true });
    page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "warning" && message.text().includes("[Vue warn]")) errors.push(message.text());
    });
    await page.goto(base + "/settings?tab=selection");
    await page.getByRole("heading", { name: "模型选用", exact: true }).waitFor();
    await page.waitForFunction(() => !document.querySelector(".el-loading-mask"));
    assert.equal(await page.locator(".selection-guide").count(), 3);
    assert.equal(await page.getByRole("combobox", { name: "选择提取模型", exact: true }).isDisabled(), true);
    await page.locator(".selection-guide").nth(1).click();
    await page.getByRole("tab", { name: "Embedding" }).waitFor();
    assert.equal(await page.getByRole("tab", { name: "Embedding" }).getAttribute("aria-selected"), "true");
    await page.getByRole("tab", { name: "Reranker" }).click();
    await page.getByPlaceholder("服务商提供的模型 ID").fill("browser-reranker");
    await page.getByRole("button", { name: "保存", exact: true }).click();
    await page.getByText("尚未测试连接", { exact: true }).waitFor();
    // Configure this model's provider to point at the isolated mock endpoint.
    await page.locator(".provider-row").click();
    await page.getByPlaceholder("https://example.com/v1/").fill(backend + "/mock/v1");
    await page.getByRole("button", { name: "保存服务商", exact: true }).click();
    await page.locator(".model-row").click();
    await page.getByRole("button", { name: "测试连接", exact: true }).click();
    await page.getByText("连接测试通过", { exact: true }).waitFor();
    const profiles = await api("/settings/models");
    const reranker = profiles.models.find((model) => model.model === "browser-reranker");
    assert.equal(reranker.test_status, "passed");
    const extraction = await add("llm", "gpt-test-extraction");
    const embedding = await add("embedding", "bge-test", "本地部署");
    const otherEmbedding = await add("embedding", "bge-alternate", "本地部署");
    await api("/settings/models", "POST", {
      name: "untested-hidden", model: "untested-hidden", model_type: "llm",
      provider_name: "OpenAI", provider: "remote_api", base_url: backend + "/mock/v1", activate: false,
    });
    await page.getByRole("tab", { name: "模型选用", exact: true }).click();
    await page.waitForFunction(() => !document.querySelector(".el-loading-mask"));
    await choose("选择提取模型", "gpt-test-extraction");
    assert.equal(await page.getByRole("option", { name: "untested-hidden" }).count(), 0);
    await choose("选择 Embedding 模型", "bge-test");
    await choose("选择 Reranker 模型", "browser-reranker");
    await page.getByRole("spinbutton", { name: "精排后保留结果数（Top-K）" }).fill("7");
    await page.getByRole("spinbutton", { name: "精排后保留结果数（Top-K）" }).blur();
    await page.getByRole("button", { name: "保存选用配置", exact: true }).click();
    await page.getByText("选用配置已保存", { exact: true }).waitFor();
    let saved = await api("/settings/selection");
    assert.equal(saved.extraction_model_id, extraction.id);
    assert.equal(saved.embedding_model_id, embedding.id);
    assert.equal(saved.reranker_model_id, reranker.id);
    assert.equal(saved.reranker_top_k, 7);
    await page.screenshot({ path: path.join(output, "selection-desktop.png"), fullPage: true });
    await page.reload();
    await page.waitForFunction(() => !document.querySelector(".el-loading-mask") && document.querySelector(".reranker-top-k input")?.value === "7");
    await choose("选择 Embedding 模型", "bge-alternate");
    await page.getByText("Embedding 模型已更改", { exact: true }).waitFor();
    await choose("选择 Embedding 模型", "bge-test");
    await choose("选择 Reranker 模型", "不使用（仅使用向量检索）");
    assert.equal(await page.locator(".reranker-top-k").count(), 0);
    await page.getByRole("button", { name: "保存选用配置", exact: true }).click();
    await page.getByText("选用配置已保存", { exact: true }).waitFor();
    saved = await api("/settings/selection");
    assert.equal(saved.reranker_model_id, null);
    assert.equal(saved.reranker_top_k, 7);
    await page.getByRole("tab", { name: "服务状态", exact: true }).click();
    await page.getByRole("button", { name: "检测连接", exact: true }).click();
    await page.getByText("已连接", { exact: true }).waitFor();
    assert.equal(await page.getByText("正常", { exact: true }).count(), 2);
    await page.screenshot({ path: path.join(output, "status-desktop.png"), fullPage: true });
    await api(`/settings/models/${extraction.id}`, "DELETE");
    await page.getByRole("tab", { name: "模型选用", exact: true }).click();
    await page.getByText("该模型已被删除，请重新选择", { exact: true }).waitFor();
    assert.equal(await page.locator(".selection-invalid").count(), 1);
    assert.equal(await page.getByRole("button", { name: "保存选用配置", exact: true }).isDisabled(), true);
    await page.screenshot({ path: path.join(output, "selection-deleted.png"), fullPage: true });
    for (const width of [1440, 1024, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, "selection overflow: " + width);
      if (width === 390) await page.screenshot({ path: path.join(output, "selection-mobile.png"), fullPage: true });
    }
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.getByRole("tab", { name: "模型设置", exact: true }).click();
    await page.getByRole("tab", { name: "Embedding" }).click();
    await page.getByRole("heading", { name: /bge-/ }).waitFor();
    await page.screenshot({ path: path.join(output, "embedding-desktop.png"), fullPage: true });
    for (const width of [1024, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, "model editor overflow: " + width);
    }
    assert.deepEqual(errors, []);
    console.log("PASS: empty states, category navigation, real API model save/test, provider grouping, tested-only choices, selection persistence, embedding warning, optional reranker, Top-K, health refresh, deleted references, responsive widths 320-1440. Screenshots: " + output);
  } catch (error) {
    if (page) {
      await page.screenshot({ path: path.join(output, "failure.png"), fullPage: true });
      console.error(await page.locator(".el-message").allTextContents());
    }
    throw error;
  } finally {
    if (browser) await browser.close();
    server.kill();
    frontend.kill();
    await Promise.all([server, frontend].filter((process) => process.exitCode === null).map((process) => new Promise((resolve) => process.once("exit", resolve))));
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
