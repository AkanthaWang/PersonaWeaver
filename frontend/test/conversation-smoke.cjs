const { chromium } = require("playwright-core");
const { spawn } = require("node:child_process");
const { mkdtempSync, mkdirSync } = require("node:fs");
const { tmpdir } = require("node:os");
const path = require("node:path");
const assert = require("node:assert/strict");

(async () => {
  const root = path.resolve(__dirname, "../..");
  const data = mkdtempSync(path.join(tmpdir(), "personaweaver-conversation-"));
  const output = path.join(root, ".docs/plan/assets/2026-10-22-conversation");
  mkdirSync(output, { recursive: true });
  const base = "http://127.0.0.1:18765";
  let logs = "", browser, page;
  const server = spawn(process.env.PW_TEST_PYTHON || "python", [
    "-B", "-m", "uvicorn", "backend.tests.conversation_preview:app", "--host", "127.0.0.1", "--port", "18765",
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
  async function closeDrawer(title) {
    const drawer = page.getByRole("dialog", { name: title, exact: true });
    await drawer.getByRole("button", { name: "Close this dialog", exact: true }).click();
    await drawer.waitFor({ state: "hidden" });
  }
  try {
    for (let i = 0; i < 100; i++) {
      if (server.exitCode !== null) throw new Error(logs);
      try { if ((await fetch(base + "/health")).ok) break; } catch {}
      if (i === 99) throw new Error("server startup timeout\n" + logs);
      await new Promise(r => setTimeout(r, 300));
    }
    await api("/api/v1/auth/me", null, "GET");
    const profile = await api("/api/v1/settings/models", {
      name: "Mock conversation", provider: "ollama", model: "mock", base_url: "http://never-called.invalid",
      context_window: 8192, max_tokens: 512, activate: true,
    });
    const book = await api("/test/setup", {});
    const conversation = await api("/api/v1/conversations", { title: "城东场景", book_id: book.book_id, profile_id: profile.id });
    browser = await chromium.launch(process.env.PW_TEST_EXECUTABLE
      ? { executablePath: process.env.PW_TEST_EXECUTABLE, headless: true } : { headless: true });
    page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on("pageerror", err => errors.push(err.message));
    await page.goto(`${base}/chat?conversation=${conversation.id}`);
    const input = page.getByRole("textbox", { name: "消息", exact: true });
    await input.waitFor();
    await input.fill("林默现在在哪里？");
    const preview = await page.waitForResponse(r => r.url().endsWith("/context-preview") && r.status() === 200);
    const previewData = await preview.json();
    assert.equal(previewData.context_usage.context_window, 8192);
    assert.ok(previewData.context_usage.components.input > 0);
    await page.getByRole("button", { name: "发送消息", exact: true }).click();
    await page.getByText("城东之约", { exact: true }).first().waitFor();
    await page.waitForFunction(() => !document.querySelector("textarea[aria-label='消息']").disabled);
    assert.equal(await page.evaluate(() => window.unsafe), undefined);
    await page.getByRole("button", { name: "参考来源", exact: true }).first().click();
    await page.getByRole("button", { name: "查看原文", exact: true }).first().click();
    await page.locator(".reader mark").waitFor();
    assert.ok((await page.locator(".reader mark").textContent()).includes("林默"));
    await closeDrawer("章节原文");
    await closeDrawer("本轮参考来源");
    await page.getByRole("button", { name: /^记忆/ }).click();
    await page.getByText("约定在城东重逢", { exact: true }).waitFor();
    await page.getByRole("button", { name: "编辑", exact: true }).click();
    assert.equal(await page.getByRole("checkbox", { name: "人工锁定，不允许自动覆盖" }).isChecked(), true);
    await page.locator(".el-dialog textarea").fill("人工更正：在城西重逢");
    await page.getByRole("button", { name: "保存记忆", exact: true }).click();
    await page.getByText("人工更正：在城西重逢", { exact: true }).waitFor();
    await closeDrawer("当前分支记忆");
    await input.fill("暂停，等待剧情");
    await page.getByRole("button", { name: "发送消息", exact: true }).click();
    await page.getByText("林默正在城东等候，", { exact: true }).waitFor();
    await page.getByRole("button", { name: "停止生成", exact: true }).click();
    await page.getByText("已中断 · 已保存文本，可继续对话", { exact: true }).waitFor();
    await input.fill("继续");
    await page.getByRole("button", { name: "发送消息", exact: true }).click();
    await page.waitForFunction(() => !document.querySelector("textarea[aria-label='消息']").disabled);
    await page.getByRole("button", { name: /^记忆/ }).click();
    await page.getByText("人工更正：在城西重逢", { exact: true }).waitFor();
    await page.getByRole("button", { name: "删除", exact: true }).click();
    await page.locator(".el-message-box").getByRole("button", { name: "删除", exact: true }).click();
    await page.getByText("已删除", { exact: true }).waitFor();
    await page.getByRole("button", { name: "撤销此版本", exact: true }).click();
    await page.getByText("人工更正：在城西重逢", { exact: true }).waitFor();
    await closeDrawer("当前分支记忆");
    for (const width of [1440, 1024, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.waitForTimeout(150);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `overflow at ${width}`);
      assert.equal(await page.evaluate(() => {
        const heading = document.querySelector(".pi-chat-heading").getBoundingClientRect();
        const actions = document.querySelector(".chat-heading-actions").getBoundingClientRect();
        return actions.bottom <= heading.bottom + 1;
      }), true, `heading controls overlap timeline at ${width}`);
      await page.screenshot({ path: path.join(output, `chat-${width}.png`), fullPage: true });
    }
    const stats = await api("/test/stats", {});
    assert.equal(stats.conversation, 3);
    assert.equal(stats.memory, 2);
    assert.deepEqual(errors, []);
    console.log("PASS: native stream, budget, stop/continue, sources/Unicode highlight, memory edit/delete/undo, manual-lock protection, safe Markdown, widths 320-1440. Screenshots: " + output);
  } catch (error) {
    if (page) {
      await page.screenshot({ path: path.join(output, "failure.png"), fullPage: true }).catch(() => {});
      console.error((await page.locator("body").innerText()).slice(-6000));
    }
    console.error(logs.slice(-6000));
    throw error;
  } finally {
    if (browser) await browser.close();
    server.kill();
    await new Promise(resolve => { if (server.exitCode !== null) resolve(); else server.once("exit", resolve); });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
