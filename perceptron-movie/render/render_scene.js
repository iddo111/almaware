// Render an ALMA HTML animation to real video (Playwright records the page).
const { chromium } = require('playwright-core');
const url = process.argv[2];
const outdir = process.argv[3] || '.';
const secs = parseInt(process.argv[4] || '20', 10);
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: outdir, size: { width: 1280, height: 720 } },
  });
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForTimeout(secs * 1000);
  const video = page.video();
  await ctx.close();          // finalizes the webm
  const path = await video.path();
  await browser.close();
  console.log('VIDEO:' + path);
})().catch(e => { console.error('ERR:' + e.message); process.exit(1); });
