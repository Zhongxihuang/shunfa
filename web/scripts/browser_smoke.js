/* eslint-disable @typescript-eslint/no-require-imports */
const { chromium } = require('playwright');

const TARGET_URL = process.env.TARGET_URL || 'http://127.0.0.1:3000';
const username = `smoke_${Date.now()}`;
const password = 'smoke-password-123';
const screenshotPath =
  process.env.SCREENSHOT_PATH || '/private/tmp/shunfa-browser-smoke-profile.png';

async function clickByText(page, text) {
  await page.getByText(text, { exact: true }).click();
}

(async () => {
  const browser = await chromium.launch({
    headless: process.env.HEADLESS === 'true',
    slowMo: Number(process.env.SLOW_MO_MS || 80),
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const consoleErrors = [];
  const pageErrors = [];

  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await page.goto(`${TARGET_URL}/login`, { waitUntil: 'networkidle' });
  await clickByText(page, '注册');
  await page.locator('input[type="text"]').fill(username);
  await page.locator('input[type="password"]').nth(0).fill(password);
  await page.locator('input[type="password"]').nth(1).fill(password);
  await page.locator('form button[type="submit"]').click();
  await page.waitForURL(`${TARGET_URL}/`, { timeout: 15000 });

  await page.goto(`${TARGET_URL}/settings`, { waitUntil: 'networkidle' });
  await page.locator('input[placeholder="sk-..."]').fill('sk-browser-smoke-test-key');
  await clickByText(page, '保存 Key');
  await page.waitForSelector('text=...-key', { timeout: 10000 });

  await page.goto(`${TARGET_URL}/topics`, { waitUntil: 'networkidle' });
  // Stable hero copy that renders regardless of fallback/real topic supply.
  await page.waitForSelector('text=今天选一条就够了', { timeout: 15000 });
  await page.locator('button.min-h-40').first().click();
  await clickByText(page, '就选这一条');
  await page.waitForURL(/\/compose\?topic_id=/, { timeout: 15000 });

  await page.waitForSelector('text=生成草稿', { timeout: 15000 });
  await clickByText(page, '生成草稿');
  await page.waitForURL(/\/preview\?checkin_id=/, { timeout: 30000 });

  await page.waitForSelector('text=查看发布提示', { timeout: 15000 });
  await clickByText(page, '查看发布提示');
  await page.waitForSelector('text=生成图文素材', { timeout: 30000 });
  await clickByText(page, '生成图文素材');
  await page.waitForSelector('text=我已发到目标平台，确认打卡', { timeout: 30000 });
  await clickByText(page, '我已发到目标平台，确认打卡');
  await page.waitForSelector('text=发布完成', { timeout: 15000 });

  await page.goto(`${TARGET_URL}/profile`, { waitUntil: 'networkidle' });
  await page.screenshot({ path: screenshotPath, fullPage: true });

  if (pageErrors.length > 0) {
    throw new Error(`Page errors: ${pageErrors.join('\n')}`);
  }
  const sensitiveConsoleErrors = consoleErrors.filter((line) =>
    /authorization|x-user-api-key|sk-browser-smoke-test-key/i.test(line),
  );
  if (sensitiveConsoleErrors.length > 0) {
    throw new Error(`Sensitive console output: ${sensitiveConsoleErrors.join('\n')}`);
  }

  console.log(
    JSON.stringify(
      {
        status: 'passed',
        username,
        consoleErrorCount: consoleErrors.length,
        screenshot: screenshotPath,
      },
      null,
      2,
    ),
  );

  await browser.close();
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
