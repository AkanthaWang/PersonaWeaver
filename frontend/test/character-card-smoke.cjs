const { chromium } = require("playwright-core");
const { spawn } = require("node:child_process");
const { mkdtempSync, mkdirSync } = require("node:fs");
const { tmpdir } = require("node:os");
const path = require("node:path");
const assert = require("node:assert/strict");

(async () => {
  const root = path.resolve(__dirname, "../..");
  const data = mkdtempSync(path.join(tmpdir(), "personaweaver-character-"));
  const output = path.join(root, ".docs/plan/assets/2026-10-22-character");
  mkdirSync(output, { recursive: true });
  const base = "http://127.0.0.1:18766";
  let logs = "", browser;
  const server = spawn(process.env.PW_TEST_PYTHON || "python", [
    "-B", "-m", "uvicorn", "backend.tests.conversation_preview:app", "--host", "127.0.0.1", "--port", "18766",
  ], { cwd: root, windowsHide: true, stdio: ["ignore", "ignore", "pipe"],
    env: { ...process.env, PERSONAWEAVER_DATA_DIR: data, PERSONAWEAVER_DB_PATH: path.join(data, "test.sqlite3"),
      PERSONAWEAVER_AGENT_DIR: path.join(data, "agent"), PERSONAWEAVER_SESSION_DIR: path.join(data, "sessions"),
      ECNU_API_BASE_URL: "", ECNU_API_KEY: "", ECNU_MODEL_NAME: "" } });
  server.stderr.on("data", chunk => { logs += chunk.toString(); });
  async function api(url, body, method = "POST") {
    const response = await fetch(base + url, { method, headers: { "Content-Type": "application/json" },
      ...(body ? { body: JSON.stringify(body) } : {}) });
    assert.ok(response.ok, `${response.status}: ${await response.clone().text()}\n${logs}`);
    return response.json();
  }
  try {
    for (let i = 0; i < 100; i++) {
      if (server.exitCode !== null) throw new Error(logs);
      try { if ((await fetch(base + "/health")).ok) break; } catch {}
      if (i === 99) throw new Error("server startup timeout\n" + logs);
      await new Promise(resolve => setTimeout(resolve, 300));
    }
    await api("/api/v1/auth/me", null, "GET");
    await api("/api/v1/settings/models", {
      name: "Mock character", provider: "ollama", model: "mock", base_url: "http://never-called.invalid",
      context_window: 8192, max_tokens: 512, activate: true,
    });
    const book = await api("/test/setup", {});
    const original = "手工设定与历史资料。".repeat(200);
    const card = await api("/api/v1/cards", {
      book_id: book.book_id, name: "林默", intro: "寡言而重情的猎户少年。", content: original,
    });
    const prior = await api("/api/v1/conversations", { card_id: card.id });
    browser = await chromium.launch(process.env.PW_TEST_EXECUTABLE
      ? { executablePath: process.env.PW_TEST_EXECUTABLE, headless: true } : { headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on("pageerror", err => errors.push(err.message));
    await page.goto(base + "/characters");
    await page.getByRole("heading", { name: "林默", exact: true }).waitFor();
    await page.getByRole("button", { name: "精简角色卡", exact: true }).click();
    await page.locator(".el-message-box").getByRole("button", { name: "取消", exact: true }).click();
    const cards = await api("/api/v1/cards", null, "GET");
    assert.equal(cards.cards[0].content, original);
    await page.getByRole("button", { name: "精简角色卡", exact: true }).click();
    const response = page.waitForResponse(r => r.url().endsWith(`/cards/${card.id}/compact`) && r.status() === 200);
    await page.locator(".el-message-box").getByRole("button", { name: "精简", exact: true }).click();
    const compacted = await (await response).json();
    assert.equal(compacted.id, card.id);
    assert.ok(compacted.content.length <= 1000);
    assert.ok(compacted.content.includes(compacted.intro));
    assert.ok(!compacted.content.includes(original));
    const unchanged = await api(`/api/v1/conversations/${prior.id}`, null, "GET");
    assert.equal(unchanged.card_id, card.id);
    for (const width of [1440, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.waitForTimeout(150);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `overflow at ${width}`);
      await page.screenshot({ path: path.join(output, `cards-${width}.png`), fullPage: true });
    }
    await page.getByRole("button", { name: "编辑角色卡", exact: true }).click();
    await page.getByText("核心人设", { exact: true }).waitFor();
    await page.getByRole("dialog").getByRole("button", { name: "Close this dialog", exact: true }).click();
    await page.getByRole("button", { name: "开始角色对话", exact: true }).click();
    await page.getByPlaceholder("对「林默」说些什么…").waitFor();
    const cid = new URL(page.url()).searchParams.get("conversation");
    const conversation = await api(`/api/v1/conversations/${cid}`, null, "GET");
    assert.equal(conversation.mode, "roleplay");
    assert.equal(conversation.card_id, card.id);
    assert.equal(conversation.book_id, book.book_id);
    await page.screenshot({ path: path.join(output, "roleplay-320.png"), fullPage: true });
    assert.deepEqual(errors, []);
    console.log("PASS: cancel preserves custom card, compact keeps links, core persona editor, roleplay identity, widths 320-1440. Screenshots: " + output);
  } catch (error) {
    console.error(logs.slice(-6000));
    throw error;
  } finally {
    if (browser) await browser.close();
    server.kill();
    await new Promise(resolve => { if (server.exitCode !== null) resolve(); else server.once("exit", resolve); });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
