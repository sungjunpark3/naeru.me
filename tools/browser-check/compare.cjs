/* 원격 커밋의 HTML/산책 코드와 현재 배포본을 같은 시각·브라우저에서 비교한다. */
const { launchBrowser } = require('./browser.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const http = require('node:http');
const { execFileSync } = require('node:child_process');
const repo = path.resolve(__dirname, '../..');
const ref = process.argv[2];
assert(ref, '사용법: node tools/browser-check/compare.cjs <기준 커밋>');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'naeru-compare-'));
const baseline = path.join(temporary, 'baseline');
const candidate = path.join(repo, '.publish');
fs.mkdirSync(path.join(baseline, 'game'), { recursive: true });
for (const name of ['index.html', 'game/game.js']) {
  fs.writeFileSync(path.join(baseline, name), execFileSync('git', ['show', `${ref}:${name}`], { cwd: repo }));
}
// check-repo.py --baseline으로 바이트 일치를 먼저 확인한 img를 공유한다.
fs.symlinkSync(path.join(repo, 'img'), path.join(baseline, 'img'), 'dir');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.jpg': 'image/jpeg',
  '.png': 'image/png', '.webp': 'image/webp', '.mp4': 'video/mp4', '.webm': 'video/webm' };
const server = http.createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost');
  const match = /^\/(baseline|candidate)\/(.*)$/.exec(url.pathname);
  if (!match) { res.writeHead(404); return res.end(); }
  const root = match[1] === 'baseline' ? baseline : candidate;
  const file = path.resolve(root, match[2] || 'index.html');
  if (!file.startsWith(root + path.sep)) { res.writeHead(403); return res.end(); }
  fs.readFile(file, (err, bytes) => {
    if (err) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': mime[path.extname(file)] || 'text/plain' });
    res.end(bytes);
  });
});
(async () => {
  let browser;
  let passed = false;
  try {
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    browser = await launchBrowser({ deterministic: true });
    let count = 0;
    for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
      const pages = [];
      for (let i = 0; i < 2; i++) {
        const page = await browser.newPage({ viewport, reducedMotion: 'reduce' });
        await page.clock.setFixedTime(new Date('2026-09-11T03:00:00Z'));
        await page.addInitScript(() => localStorage.setItem('naeru-hint-seen', '1'));
        await page.route('https://**', route => route.abort());
        const errors = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('response', response => { if (response.status() >= 400) errors.push(response.url()); });
        pages.push({ page, errors });
      }
      const scenes = [];
      for (const season of ['spring', 'summer', 'autumn', 'winter'])
        for (const band of ['dawn', 'day', 'dusk', 'night'])
          for (const weather of ['clear', 'rain'])
            scenes.push(`s=${season}&v=${band}&w=${weather}&xmas=0`);
      for (const band of ['dawn', 'day', 'dusk', 'night'])
        for (const weather of ['clear', 'rain'])
          scenes.push(`s=winter&v=${band}&w=${weather}&xmas=1`);
      for (const query of scenes) {
        if (process.env.NAERU_COMPARE_FILTER && !query.includes(process.env.NAERU_COMPARE_FILTER)) continue;
        const states = [];
        for (const [i, { page, errors }] of pages.entries()) {
          const kind = i ? 'candidate' : 'baseline';
          await page.goto(`http://127.0.0.1:${server.address().port}/${kind}/?${query}`);
          await page.waitForFunction(() => document.documentElement.dataset.sceneReady === 'true' &&
            document.querySelector('#naeruHd').dataset.status === 'ready' &&
            document.querySelector('#naeruStill').naturalWidth === 4608 &&
            [...document.images].filter(e => e.getAttribute('src')).every(e => e.complete && e.naturalWidth),
            null, { timeout: 15000 });
          await page.evaluate(() => document.fonts.ready);
          await page.evaluate(() => new Promise(resolve =>
            requestAnimationFrame(() => requestAnimationFrame(resolve))));
          states.push(await page.evaluate(() => {
            function clean(value) { return value.replace(/\/(baseline|candidate)\//g, '/').replace(/\?v=[a-z0-9]+/g, ''); }
            const root = { ...document.documentElement.dataset }; delete root.av;
            return { root, body: { ...document.body.dataset },
              layers: ['#stage', '#naeru-move', '#naeruStill', '#landscape', '#foreground',
                '.foreground-layer.on', '#skyMotion', '#approach-setting'].map(selector => {
                  const e = document.querySelector(selector); if (!e) return null;
                  const box = e.getBoundingClientRect(), style = getComputedStyle(e);
                  return { selector, x: box.x, y: box.y, width: box.width, height: box.height,
                    src: clean(e.getAttribute('src') || ''), opacity: style.opacity,
                    transform: style.transform, display: style.display };
                }),
              requests: [...new Set(performance.getEntriesByType('resource')
                .filter(e => e.name.includes('/img/')).map(e => clean(new URL(e.name).pathname)))].sort()
            };
          }));
          await page.screenshot({ path: path.join(temporary, `${count}-${i}.png`), animations: 'disabled' });
          assert.deepEqual(errors, [], `${kind} ${query}`);
        }
        assert.deepEqual(states[1], states[0], `장면 상태·좌표·자산 경로 불일치: ${query}`);
        count++;
      }
      await Promise.all(pages.map(({ page }) => page.close()));
      console.log(`상태·좌표·URL 일치: ${viewport.width}×${viewport.height}`);
    }
    assert(count > 0, '비교할 장면이 없습니다.');
    const python = process.env.NAERU_PYTHON || path.join(repo, 'tools/naeru-split/.venv/bin/python');
    execFileSync(python, ['-c', `
from pathlib import Path
from PIL import Image, ImageChops
import sys
root=Path(sys.argv[1]); count=int(sys.argv[2])
failed=[]
for i in range(count):
    a=Image.open(root/f'{i}-0.png').convert('RGB')
    b=Image.open(root/f'{i}-1.png').convert('RGB')
    diff=ImageChops.difference(a,b)
    if diff.getbbox():
        failed.append(i)
        print(f'화면 픽셀 불일치: {i}, 영역 {diff.getbbox()}', flush=True)
assert not failed, f'화면 픽셀 불일치: {failed}'
print(f'기준본 대비 {count}개 데스크톱·모바일 화면 픽셀 완전 일치')
`, temporary, String(count)], { stdio: 'inherit' });
    passed = true;
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
    if (passed) fs.rmSync(temporary, { recursive: true, force: true });
    else console.error(`차이 확인용 임시 이미지: ${temporary}`);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
