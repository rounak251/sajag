// Screenshots for the README, taken at the moment that tells the story.
const pw = require('/Users/rounakchoudhary/Desktop/datascience/snack-skyline/node_modules/playwright-core');
const exe = `${process.env.HOME}/Library/Caches/ms-playwright/chromium-1248/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;
const [base, out] = process.argv.slice(2);
(async () => {
  const browser = await pw.chromium.launch({ executablePath: exe, args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const open = async (viewport, hash, mobile = false) => {
    const page = await browser.newPage({ viewport, deviceScaleFactor: mobile ? 2 : 1.5, reducedMotion: 'reduce' });
    await page.goto(`${base}${hash}`);
    await page.waitForTimeout(2500);
    return page;
  };
  const scene = 'year=2024&date=2024-09-25&lead=7&district=darbhanga';
  let page = await open({ width: 1440, height: 900 }, `#/?${scene}`);
  await page.getByRole('button', { name: 'All Bihar' }).click();
  await page.waitForTimeout(800);
  await page.screenshot({ path: `${out}/map.png` });
  console.log('note:', await page.locator('#raised-note').innerText().catch(() => 'none'));
  console.log('level:', await page.locator('#p-level').innerText().catch(() => 'none'));
  await page.getByRole('tab', { name: /Alert/i }).click().catch(async () => page.getByText('Alert preview').first().click());
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${out}/alert.png` });
  await page.close();
  page = await open({ width: 1440, height: 1000 }, '#/evidence');
  await page.screenshot({ path: `${out}/evidence.png` });
  await page.close();
  page = await open({ width: 390, height: 844 }, `#/?${scene}`, true);
  await page.screenshot({ path: `${out}/phone.png` });
  await page.close();
  await browser.close();
})();
