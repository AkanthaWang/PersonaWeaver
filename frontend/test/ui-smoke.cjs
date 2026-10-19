// Run with Playwright available via NODE_PATH and Python backend dependencies installed.
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const { mkdtempSync, mkdirSync } = require('node:fs');
const { tmpdir } = require('node:os');
const path = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const root = path.resolve(__dirname, '../..');
  const data = mkdtempSync(path.join(tmpdir(), 'personaweaver-ui-'));
  const output = path.join(root, '.docs/plan/assets/2026-10-14-workspace');
  mkdirSync(output, { recursive: true });
  const base = 'http://127.0.0.1:18761';
  const server = spawn(process.env.PW_TEST_PYTHON || 'python', ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '18761'], {
    cwd: root, windowsHide: true,
    env: { ...process.env, PERSONAWEAVER_DATA_DIR: data, PERSONAWEAVER_DB_PATH: path.join(data, 'ui.sqlite3'), ECNU_API_BASE_URL: '', ECNU_API_KEY: '', ECNU_MODEL_NAME: '' },
    stdio: ['ignore', 'ignore', 'pipe'],
  });
  let serverLog = '';
  server.stderr.on('data', (chunk) => { serverLog += chunk.toString(); });
  let browser, page;
  try {
    for (let attempt = 0; attempt < 60; attempt++) {
      if (server.exitCode !== null) throw new Error('Test server exited: ' + serverLog);
      try { if ((await fetch(base + '/health')).ok) break; } catch {}
      if (attempt === 59) throw new Error('Test server startup timed out');
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    browser = await chromium.launch({ channel: process.env.PW_TEST_BROWSER || 'chrome', headless: true });
    page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('console', (message) => { if (message.type() === 'warning' && message.text().includes('[Vue warn]')) errors.push(message.text()); });
    await page.addInitScript(() => localStorage.setItem('personaweaver.local.token', 'expired-old-session'));
    await page.goto(base + '/');
    await page.getByRole('heading', { name: '继续编织你的故事' }).waitFor();
    assert.match(page.url(), /dashboard/);
    assert.equal(await page.locator('input[type=password]').count(), 0);
    await page.screenshot({ path: path.join(output, 'dashboard-desktop.png'), fullPage: true });
    await page.getByRole('link', { name: '编辑个人资料' }).click();
    await page.getByRole('heading', { name: '个人资料', exact: true }).waitFor();
    await page.getByPlaceholder('怎么称呼你？').fill('故事编织者');
    await page.getByPlaceholder('仅用于个人资料').fill('writer@example.com');
    const saved = page.waitForResponse((response) => response.url().endsWith('/auth/profile') && response.request().method() === 'PATCH');
    await page.getByRole('button', { name: '保存个人资料' }).click();
    assert.equal((await saved).status(), 200);
    const uploaded = page.waitForResponse((response) => response.url().includes('/auth/avatar') && response.request().method() === 'POST');
    await page.locator('input[type=file]').setInputFiles(path.join(root, 'frontend/src/assets/avatar.png'));
    assert.equal((await uploaded).status(), 200);
    await page.reload();
    await page.waitForFunction(() => document.querySelector('.account strong')?.textContent === '故事编织者');
    await page.waitForFunction(() => document.querySelector('.settings-avatar')?.getAttribute('src')?.includes('/api/v1/avatars/'));
    assert.equal(await page.locator('input[type=password]').count(), 0);
    await page.screenshot({ path: path.join(output, 'profile-desktop.png'), fullPage: true });
    await page.getByRole('tab', { name: '模型设置' }).click();
    await page.locator('.model-row').first().waitFor();
    assert.equal(await page.locator('.model-form .el-form-item__label').first().evaluate((node) => getComputedStyle(node).fontSize), '14px');
    await page.locator('.spec-section .el-input-number input').first().fill('65536');
    await page.locator('.spec-section .el-input-number input').first().blur();
    const modelSaved = page.waitForResponse((response) => response.url().includes('/settings/models') && ['POST', 'PUT'].includes(response.request().method()));
    await page.getByRole('button', { name: '保存', exact: true }).click();
    const modelResponse = await modelSaved;
    assert.ok([200, 201].includes(modelResponse.status()), await modelResponse.text());
    await page.waitForFunction(() => Object.keys(localStorage).some((key) => key.startsWith('personaweaver.model-notes.') && JSON.parse(localStorage.getItem(key)).context_window === 65536));
    await page.reload();
    await page.waitForFunction(() => document.querySelector('.spec-section .el-input-number input')?.value === '65536');
    await page.screenshot({ path: path.join(output, 'models-desktop.png'), fullPage: true });
    for (const width of [1024, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'model page overflow at ' + width);
      if (width === 390) await page.screenshot({ path: path.join(output, 'models-mobile.png'), fullPage: true });
    }
    await page.getByRole('tab', { name: '个人资料' }).click();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'profile page overflow at 320');
    await page.getByRole('tab', { name: '服务状态' }).click();
    await page.getByRole('button', { name: '检测连接' }).click();
    await page.getByText('已连接', { exact: true }).waitFor();
    for (const route of ['/upload', '/summary', '/characters', '/chat']) {
      await page.goto(base + route);
      await page.locator('.page-body').waitFor();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'route overflow: ' + route);
    }
    for (const removed of ['/login', '/welcome', '/unknown-route']) {
      await page.goto(base + removed);
      await page.locator('.page-body').waitFor();
      assert.match(page.url(), /dashboard/, 'removed route should fall back to dashboard: ' + removed);
    }
    assert.deepEqual(errors, []);
    console.log('PASS: reachable routes, removed-route fallback, stale-token compatibility, persisted profile/avatar/model notes, service health, responsive widths 1440/1024/768/390/320; screenshots: ' + output);
  } catch (error) {
    if (page) {
      await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true });
      console.error(await page.locator('.model-form input').evaluateAll((nodes) => nodes.map((node) => ({ type: node.type, value: node.value, validity: node.validationMessage }))));
      console.error(await page.locator('.el-message').allTextContents());
    }
    throw error;
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
