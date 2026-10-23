const { chromium } = require("playwright-core");
const { spawn } = require("node:child_process");
const { mkdtempSync, mkdirSync } = require("node:fs");
const { tmpdir } = require("node:os");
const path = require("node:path");
const assert = require("node:assert/strict");

(async () => {
  const root = path.resolve(__dirname, "../..");
  const data = mkdtempSync(path.join(tmpdir(), "personaweaver-conversation-"));
  const output = path.join(root, ".docs/plan/assets/2026-10-23-harness");
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
    const card = await api("/api/v1/cards", { book_id: book.book_id, name: "林默", intro: "谨慎寡言", content: "不轻信他人。" });
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
    await page.getByRole("status").filter({ hasText: "生成草稿" }).waitFor();
    await page.waitForTimeout(200);
    assert.equal(await page.getByText("林默正在城东等候，", { exact: true }).count(), 0);
    await page.getByRole("button", { name: "停止生成", exact: true }).click();
    await page.getByRole("button", { name: "恢复本次运行", exact: true }).waitFor();
    let saved = await api(`/api/v1/conversations/${conversation.id}`, null, "GET");
    assert.equal(saved.messages.length, 2, "unreviewed partial draft must not enter history");
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
    // Review failures retain their draft; page reload must expose explicit recovery.
    await api("/test/control", { fail_review: true });
    await input.fill("审核失败恢复测试");
    await page.getByRole("button", { name: "发送消息", exact: true }).click();
    await page.getByRole("button", { name: "恢复本次运行", exact: true }).waitFor();
    const beforeResume = await api("/test/stats", {});
    await page.reload();
    await page.getByRole("button", { name: "恢复本次运行", exact: true }).click();
    await page.waitForFunction(() => !document.querySelector("textarea[aria-label='消息']").disabled);
    const afterResume = await api("/test/stats", {});
    assert.equal(afterResume.conversation, beforeResume.conversation);
    assert.equal(afterResume.review, beforeResume.review + 1);
    saved = await api(`/api/v1/conversations/${conversation.id}`, null, "GET");
    assert.equal(saved.messages.length, 6);
    await page.getByRole("button", { name: "执行记录", exact: true }).click();
    await page.getByRole("dialog", { name: "本轮执行记录", exact: true }).waitFor();
    await page.getByText("一致性校验通过", { exact: true }).first().waitFor();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(output, "trace-1440.png"), fullPage: true });
    await closeDrawer("本轮执行记录");
    // Settings preserve the selected cast on reopening, including narrow screens.
    await page.getByRole("button", { name: "会话设置", exact: true }).click();
    await page.locator(".el-radio-button").filter({ hasText: "内容写作" }).click();
    await page.locator(".el-radio-button").filter({ hasText: "剧本场景" }).click();
    const settings = page.getByRole("dialog", { name: "会话设置", exact: true });
    await settings.locator(".el-select").last().click();
    await page.getByRole("option", { name: "林默", exact: true }).click();
    await settings.getByRole("button", { name: "保存设置", exact: true }).click();
    await settings.waitFor({ state: "hidden" });
    await page.getByRole("button", { name: "会话设置", exact: true }).click();
    await settings.getByText("林默", { exact: true }).waitFor();
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.waitForTimeout(500);
      const bounds = await settings.boundingBox();
      assert.ok(bounds.x >= -1 && bounds.x + bounds.width <= width + 1, `settings drawer clipped at ${width}`);
      assert.equal(await settings.evaluate(el => el.scrollWidth > el.clientWidth), false, `settings overflow at ${width}`);
      await page.screenshot({ path: path.join(output, `writing-settings-${width}.png`), fullPage: true });
    }
    await closeDrawer("会话设置");
    const changed = await api(`/api/v1/conversations/${conversation.id}`, null, "GET");
    assert.equal(changed.mode, "writing");
    assert.equal(changed.writing_format, "screenplay");
    assert.deepEqual(changed.character_ids, [card.id]);
    await api("/test/control", { blocked: true });
    await input.fill("再次冲突不得发布");
    await page.getByRole("button", { name: "发送消息", exact: true }).click();
    await page.getByRole("alert").filter({ hasText: "一致性校验未通过" }).waitFor();
    const blocked = await api(`/api/v1/conversations/${conversation.id}`, null, "GET");
    assert.equal(blocked.messages.length, 6);
    assert.equal(await page.getByRole("button", { name: "恢复本次运行", exact: true }).count(), 0);
    await api("/test/control", { blocked: false });
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
    assert.equal(stats.conversation, 6);
    assert.equal(stats.memory, 3);
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole("button", { name: "新对话", exact: true }).click();
    const createDialog = page.getByRole("dialog", { name: "新建创作会话", exact: true });
    await createDialog.getByRole("textbox").fill("新建小说试写");
    await createDialog.locator(".el-radio-button").filter({ hasText: "内容写作" }).click();
    await createDialog.locator(".el-select").nth(0).click();
    await page.getByRole("option", { name: "浏览器测试作品", exact: true }).click();
    await createDialog.locator(".el-select").nth(1).click();
    await page.getByRole("option", { name: "林默", exact: true }).click();
    await createDialog.getByRole("button", { name: "创建会话", exact: true }).click();
    await createDialog.waitFor({ state: "hidden" });
    await page.getByRole("heading", { name: "新建小说试写", exact: true }).waitFor();
    await input.fill("写一段城东重逢");
    await page.getByRole("button", { name: "发送消息", exact: true }).click();
    await page.waitForFunction(() => !document.querySelector("textarea[aria-label='消息']").disabled);
    const created = (await api("/api/v1/conversations", null, "GET")).conversations.find(c => c.title === "新建小说试写");
    const novel = await api(`/api/v1/conversations/${created.id}`, null, "GET");
    assert.equal(novel.mode, "writing"); assert.equal(novel.writing_format, "novel");
    assert.deepEqual(novel.character_ids, [card.id]); assert.equal(novel.messages.length, 2);
    await page.goto(base + "/settings");
    await page.getByRole("button", { name: "测试工具能力", exact: true }).click();
    await page.locator(".el-message-box").getByRole("button", { name: "确认测试", exact: true }).click();
    await page.getByText("原生工具已验证", { exact: true }).waitFor();
    const verified = (await api("/api/v1/settings/models", null, "GET")).models.find(m => m.id === profile.id);
    assert.equal(verified.tool_support, "native");
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(output, "tools-verified-1440.png"), fullPage: true });
    assert.deepEqual(errors, []);
    console.log("PASS: stage SSE, cancel/no partial publication, reload/explicit resume without duplicate drafting, review gate, writing/cast settings, traces, Unicode citations, memory versions, safe Markdown, widths 320-1440. Screenshots: " + output);
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
