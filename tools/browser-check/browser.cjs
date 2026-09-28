/* Playwright는 lockfile로 고정한다. H.264 없는 브라우저의 폴백을 성공으로 보지 않는다. */
const fs = require('node:fs');
const { chromium } = require(process.env.NAERU_PLAYWRIGHT || 'playwright');

async function launchBrowser({ deterministic = false } = {}) {
  const candidates = process.platform === 'darwin' ? [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'
  ] : [];
  const executablePath = process.env.NAERU_BROWSER || candidates.find(p => fs.existsSync(p));
  const browser = await chromium.launch({ headless: true,
    // 픽셀 대조만 소프트웨어 합성을 쓴다. 실제 동작 검사는 기존 GPU 경로를 쓴다.
    args: deterministic ? ['--disable-gpu'] : process.platform === 'darwin'
      ? ['--enable-gpu', '--ignore-gpu-blocklist', '--use-angle=metal']
      : ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'],
    ...(executablePath ? { executablePath } : {}) });
  const page = await browser.newPage();
  const h264 = await page.evaluate(() =>
    document.createElement('video').canPlayType('video/mp4; codecs="avc1.42E01E"'));
  await page.close();
  if (!h264) {
    await browser.close();
    throw new Error('H.264 재생이 필요합니다. NAERU_BROWSER에 Chrome/Edge 실행 파일을 지정하세요.');
  }
  console.log(`Browser ${browser.version()} / H.264 ${h264} / ${executablePath || 'Playwright Chromium'}`);
  return browser;
}
module.exports = { launchBrowser };
