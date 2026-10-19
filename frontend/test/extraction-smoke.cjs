const { chromium } = require("playwright");
const { spawn } = require("node:child_process");
const { mkdirSync, mkdtempSync } = require("node:fs");
const { tmpdir } = require("node:os");
const path = require("node:path");
const assert = require("node:assert/strict");

(async () => {
  const root = path.resolve(__dirname, "../..");
  const data = mkdtempSync(path.join(tmpdir(), "personaweaver-extraction-"));
  const output = path.join(root, ".docs/plan/assets/2026-10-17-extraction");
  mkdirSync(output, { recursive: true });
  const base = "http://127.0.0.1:18763";
  const server = spawn(process.env.PW_TEST_PYTHON || "python",
    ["-m", "uvicorn", "backend.tests.extraction_preview:app", "--host", "127.0.0.1", "--port", "18763"], {
      cwd: root, windowsHide: true, stdio: ["ignore", "ignore", "pipe"],
      env: { ...process.env, PERSONAWEAVER_DATA_DIR: data, PERSONAWEAVER_AGENT_DIR: path.join(data, "agent") },
    });
  let logs = "", browser, page;
  server.stderr.on("data", chunk => { logs += chunk; });
  async function screenshot(name) {
    await page.waitForFunction(() => !document.querySelector(".el-message"));
    await page.evaluate(async () => {
      await Promise.all(document.getAnimations().filter(animation =>
        animation.effect?.getComputedTiming().iterations !== Infinity
      ).map(animation => animation.finished.catch(() => {})));
    });
    await page.screenshot({ path: path.join(output, name), fullPage: true, animations: "disabled" });
  }
  async function api(route, method = "GET", body) {
    const response = await fetch(base + "/api/v1" + route, {
      method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined,
    });
    assert.ok(response.ok, `${route}: ${response.status} ${await response.clone().text()}`);
    return response.json();
  }
  try {
    for (let i = 0; i < 80; i++) {
      if (server.exitCode !== null) throw new Error(logs);
      try { if ((await fetch(base + "/health")).ok) break; } catch {}
      if (i === 79) throw new Error("Startup timeout\n" + logs);
      await new Promise(resolve => setTimeout(resolve, 250));
    }
    await api("/auth/me");
    const profile = await api("/settings/models", "POST", {
      name: "验收提取模型", model: "browser-fixture", provider: "remote_api",
      base_url: "http://127.0.0.1:9999/v1", activate: false,
    });
    await api(`/settings/models/${profile.id}/test`, "POST");
    await api("/settings/selection", "PUT", { extraction_model_id: profile.id });
    const text = "第一章 初遇\n😀林川是医师，背着药箱与阿遥走进青石镇。\n\n第二章 行医\n林川在青石镇为阿遥换药，将药箱放在身旁。\n\n第三章 远行\n林川收起药箱，与阿遥离开青石镇。失败一次";
    const upload = await fetch(base + "/api/v1/books?filename=story.txt&title=" + encodeURIComponent("青石行医录"), {
      method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: text,
    });
    const book = await upload.json();
    await api(`/books/${book.book_id}/parse`, "POST");
    browser = await chromium.launch({
      headless: true, ...(process.env.PW_TEST_EXECUTABLE ? { executablePath: process.env.PW_TEST_EXECUTABLE } : {}),
    });
    page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => { if (message.type() === "warning" && message.text().includes("[Vue warn]")) errors.push(message.text()); });
    await page.goto(base + "/upload");
    await page.getByRole("button", { name: "提取作品资料", exact: true }).click();
    await page.getByText("提取模型：验收提取模型").waitFor();
    await page.getByText("连续区间", { exact: true }).click();
    await page.locator(".extraction-range input").first().fill("2");
    await page.locator(".extraction-range input").last().fill("3");
    await screenshot("extract-desktop.png");
    await page.getByText("全部章节", { exact: true }).click();
    await page.getByRole("button", { name: "开始提取", exact: true }).click();
    await page.getByText("浏览器验收：模拟临时失败，检查点已保留", { exact: true }).first().waitFor();
    await page.getByRole("button", { name: "续跑", exact: true }).click();
    await page.getByText("提取完成，累计覆盖 3/3 章", { exact: true }).waitFor();
    await screenshot("task-desktop.png");
    await page.locator(".el-drawer__close-btn:visible").last().click();
    await page.getByRole("button", { name: "查看资料", exact: true }).click();
    await page.getByRole("button", { name: "查看", exact: true }).first().click();
    await page.getByText("综合档案", { exact: false }).first().waitFor();
    await page.locator(".source-quote button").first().click();
    await page.locator("mark").waitFor();
    assert.equal(await page.locator("mark").innerText(), "😀林川是医师，背着药箱与阿遥走进青石镇。");
    await screenshot("citation-desktop.png");
    await page.locator(".el-drawer__close-btn:visible").last().click();
    await page.locator(".evidence .el-checkbox").first().click();
    await page.getByRole("button", { name: "拆分选中来源", exact: true }).click();
    await page.getByRole("button", { name: "确定", exact: true }).click();
    await page.getByText("资料归并已更新", { exact: true }).waitFor();
    assert.equal(await page.locator(".asset-item").count(), 2);
    await page.locator(".asset-item").first().getByRole("button", { name: "创建角色卡", exact: true }).click();
    await page.locator(".el-dialog input").fill("林川 · 初遇");
    await page.locator(".el-dialog").getByRole("button", { name: "创建角色卡", exact: true }).click();
    await page.getByText("角色卡已创建", { exact: true }).waitFor();
    await page.locator(".el-dialog:visible").waitFor({ state: "hidden" });
    await screenshot("summary-desktop.png");
    for (const width of [1024, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, "summary overflow " + width);
      await page.getByRole("button", { name: "查看", exact: true }).first().click();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, "detail overflow " + width);
      if (width === 390) await screenshot("summary-mobile.png");
      await page.locator(".el-drawer__close-btn:visible").last().click();
    }
    await page.goto(base + "/upload");
    await page.getByRole("button", { name: "提取作品资料", exact: true }).click();
    await page.getByText("提取模型：验收提取模型").waitFor();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, "extract dialog overflow");
    await screenshot("extract-mobile.png");
    assert.deepEqual(errors, []);
    console.log("PASS: range/model dialog, failure/retry, checkpoints, Unicode citation highlight, split, entity-backed card, responsive widths; " + output);
  } catch (error) {
    if (page) {
      await page.screenshot({ path: path.join(output, "failure.png"), fullPage: true });
      console.error(await page.locator(".el-message").allTextContents());
    }
    throw error;
  } finally {
    if (browser) await browser.close();
    server.kill();
    await new Promise(resolve => { if (server.exitCode !== null) resolve(); else server.once("exit", resolve); });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
