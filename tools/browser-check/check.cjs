/* 앱에는 의존성을 추가하지 않고 실제 브라우저의 표시·입력·상태 전환을 검사한다. */
const { chromium } = require(process.env.NAERU_PLAYWRIGHT || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const repo = path.resolve(__dirname, '../..');
const out = process.env.NAERU_CHECK_OUTPUT;
if (out) fs.mkdirSync(out, { recursive: true });
const mime = { '.html': 'text/html', '.jpg': 'image/jpeg', '.png': 'image/png',
  '.webm': 'video/webm', '.mp4': 'video/mp4' };
const results = [];
const server = http.createServer((req, res) => {
  const pathname = new URL(req.url, 'http://localhost').pathname;
  const file = path.resolve(repo, '.' + (pathname === '/' ? '/index.html' : pathname));
  if (!file.startsWith(repo + path.sep)) { res.writeHead(403); return res.end(); }
  fs.readFile(file, (error, data) => {
    if (error) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': mime[path.extname(file)] || 'text/plain' });
    res.end(data);
  });
});
const now = new Date('2026-09-11T03:00:00Z');
function meteo(code = 3) {
  return { current: { weather_code: code, temperature_2m: 22.4 },
    daily: { sunrise: ['2026-09-11T06:09', '2026-09-12T06:10'],
      sunset: ['2026-09-11T18:46', '2026-09-12T18:45'] } };
}
async function check(name, fn) {
  if (process.env.NAERU_CHECK_FILTER && !name.includes(process.env.NAERU_CHECK_FILTER)) return;
  try { await fn(); results.push({ name, pass: true }); console.log('PASS', name); }
  catch (error) {
    results.push({ name, pass: false, error: error.stack });
    console.error('FAIL', name, error.stack.slice(0, 2000));
  }
}
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = 'http://127.0.0.1:' + server.address().port;
  const browser = await chromium.launch({ headless: true,
    ...(process.env.NAERU_BROWSER ? { executablePath: process.env.NAERU_BROWSER } : {}) });
  async function makePage(options = {}) {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, ...options });
    page.setDefaultTimeout(8000);
    page.errors = []; page.missing = [];
    page.on('pageerror', e => page.errors.push(e.message));
    page.on('response', r => { if (r.url().startsWith(base) && r.status() >= 400) page.missing.push(r.url()); });
    await page.clock.setFixedTime(now);
    await page.addInitScript(() => localStorage.setItem('naeru-hint-seen', '1'));
    await page.route('https://api.open-meteo.com/**', r => r.fulfill({ json: meteo() }));
    return page;
  }
  async function open(page, query = '') {
    await page.goto(base + '/?' + query, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => document.documentElement.dataset.sceneReady === 'true');
  }
  async function playing(page) {
    await page.waitForFunction(() => [...document.querySelectorAll('video')]
      .some(v => v.classList.contains('on') && !v.paused && v.currentTime > .3));
  }
  async function shot(page, name) {
    if (out) await page.screenshot({ path: path.join(out, name + '.png'), animations: 'disabled' });
  }
  try {
    await check('32개 배경·계절 필터·자산 요청', async () => {
      for (const season of ['spring', 'summer', 'autumn', 'winter']) {
        await Promise.all(['dawn', 'day', 'dusk', 'night'].map(async band => {
          const p = await makePage({ reducedMotion: 'reduce' });
          try {
            for (const w of ['clear', 'rain']) {
              await open(p, `s=${season}&v=${band}&w=${w}`);
              await p.waitForTimeout(2700);
              const state = await p.evaluate(() => ({
                season: document.documentElement.dataset.season,
                variant: document.body.dataset.variant,
                filter: getComputedStyle(document.querySelector('#frame')).filter,
                still: getComputedStyle(document.querySelector('#naeruStill')).opacity,
                video: [...document.querySelectorAll('video')].some(v => v.getAttribute('src'))
              }));
              assert.equal(state.season, season);
              assert.equal(state.variant, band + (w === 'rain' ? '-rain' : ''));
              assert.notEqual(state.filter, 'none');
              assert.equal(state.still, '1'); assert.equal(state.video, false);
              assert.deepEqual(p.errors, []); assert.deepEqual(p.missing, []);
              await shot(p, `${season}-${band}-${w}`);
            }
          } finally { await p.close(); }
        }));
      }
    });
    await check('다섯 화면비와 설정 패널 접근', async () => {
      for (const [width, height] of [[390, 844], [320, 568], [768, 1024], [2560, 1080], [844, 390]]) {
        const p = await makePage({ viewport: { width, height }, reducedMotion: 'reduce' });
        try {
          await open(p, 's=autumn&v=day');
          assert.equal(await p.evaluate(() => document.body.scrollWidth), width);
          const hit = await p.locator('#naeru-touch').boundingBox();
          assert(hit.x >= 0 && hit.x + hit.width <= width);
          assert(hit.y >= 0 && hit.y + hit.height <= height);
          await shot(p, `layout-${width}x${height}`);
          await p.click('#settings-open');
          const box = await p.locator('#settings-panel').boundingBox();
          assert(box.x >= 0 && box.y >= 0 && box.x + box.width <= width);
          assert(box.y + box.height <= height);
          await shot(p, `settings-${width}x${height}`);
          await p.keyboard.press('Escape');
          await p.waitForFunction(() => !document.querySelector('#settings-panel').open);
          assert.equal(await p.evaluate(() => document.activeElement.id), 'settings-open');
          assert.deepEqual(p.errors, []);
        } finally { await p.close(); }
      }
    });
    await check('설정 변경·저장·빠른 장면 전환·키보드 인사', async () => {
      const p = await makePage();
      try {
        await open(p, 's=autumn&v=day&w=clear&ball=0&flit=0&ff=0'); await playing(p);
        await p.click('#settings-open');
        await p.selectOption('#setting-season', 'spring');
        await p.selectOption('#setting-season', 'summer');
        await p.selectOption('#setting-season', 'winter');
        await p.selectOption('#setting-band', 'night');
        await p.selectOption('#setting-date', 'ko');
        await p.uncheck('#setting-clock');
        await p.waitForFunction(() => document.body.dataset.variant === 'night' &&
          document.documentElement.dataset.season === 'winter');
        assert.equal(await p.locator('.clock-wrap').isVisible(), false);
        assert.match(await p.locator('#date').textContent(), /금요일/);
        await p.reload(); await p.waitForFunction(() => document.documentElement.dataset.sceneReady === 'true');
        assert.equal(await p.locator('.clock-wrap').isVisible(), false);
        assert.equal(await p.evaluate(() => document.documentElement.dataset.season), 'winter');
        await playing(p);
        await p.locator('#naeru-touch').press('Enter');
        assert.equal(await p.evaluate(() => window.naeru.busy), true);
        await p.waitForFunction(() => !window.naeru.busy);
        assert.deepEqual(p.errors, []);
      } finally { await p.close(); }
    });
    await check('실행 중 OS 동작 줄이기 왕복·초기 정지 모드 복구', async () => {
      for (const initial of ['no-preference', 'reduce']) {
        const p = await makePage({ reducedMotion: initial });
        try {
          await open(p, 'v=day&w=clear&ball=0&flit=0&ff=0');
          if (initial === 'no-preference') await playing(p);
          await p.emulateMedia({ reducedMotion: 'reduce' });
          await p.waitForFunction(() => [...document.querySelectorAll('video')].every(v => v.paused) &&
            document.querySelector('#naeruStill').classList.contains('on'));
          assert.equal(await p.locator('#naeruStill').evaluate(e => getComputedStyle(e).opacity), '1');
          await p.emulateMedia({ reducedMotion: 'no-preference' }); await playing(p);
          await p.click('#settings-open'); await p.selectOption('#setting-motion', 'still');
          await p.waitForFunction(() => document.documentElement.dataset.motion === 'still');
          assert.equal(await p.locator('#naeruStill').evaluate(e => getComputedStyle(e).opacity), '1');
          await p.selectOption('#setting-motion', 'auto'); await playing(p);
          assert.deepEqual(p.errors, []);
        } finally { await p.close(); }
      }
    });
    for (const [name, status, body] of [['429', 429, { error: true }], ['잘못된 JSON 구조', 200, {}]]) {
      await check(`날씨 ${name}: 이전 성공 데이터 유지`, async () => {
        const p = await makePage({ reducedMotion: 'reduce' });
        const cached = { w: 'rain', t: now.getTime(), sr: 369, ss: 1126,
          sr2: 370, day: '2026-09-11', tp: 22.4, cd: 61 };
        try {
          await p.addInitScript(c => localStorage.setItem('naeru-weather', JSON.stringify(c)), cached);
          await p.route('https://api.open-meteo.com/**', r => r.fulfill({ status, json: body }));
          await open(p, 'v=day');
          await p.waitForFunction(() => document.querySelector('#info').textContent.includes('갱신 지연'));
          assert.equal(await p.evaluate(() => document.body.dataset.weather), 'rain');
          assert.deepEqual(await p.evaluate(() => JSON.parse(localStorage.getItem('naeru-weather'))), cached);
          assert.deepEqual(p.errors, []);
        } finally { await p.close(); }
      });
    }
    await check('날씨 기다리는 동안 시계·그림 즉시 표시, 소낙눈 문구', async () => {
      const p = await makePage({ reducedMotion: 'reduce' }); let pending;
      try {
        await p.route('https://api.open-meteo.com/**', r => { pending = r; });
        await open(p, 'v=day');
        assert.equal(await p.locator('#time').textContent(), '12:00');
        assert.equal(await p.locator('#naeruStill').evaluate(e => e.naturalWidth), 576);
        assert(pending);
        await pending.fulfill({ json: meteo(85) });
        await p.waitForFunction(() => document.querySelector('#info').textContent.includes('소낙눈'));
        assert.deepEqual(p.errors, []);
      } finally { await p.close(); }
    });
    await check('영상 파일 실패 시 정지본 유지', async () => {
      const p = await makePage();
      try {
        await p.route('**/img/naeru-*.webm*', r => r.abort());
        await p.route('**/img/naeru-*.mp4*', r => r.abort());
        await open(p, 'v=day&w=clear&ball=0&flit=0&ff=0');
        await p.waitForTimeout(4500);
        assert.equal(await p.locator('#naeruStill').evaluate(e => getComputedStyle(e).opacity), '1');
        assert.deepEqual(p.errors, []);
      } finally { await p.close(); }
    });
    await check('20·30·60fps에서 공 종료와 입력 복구', async () => {
      await Promise.all([20, 30, 60].map(async fps => {
        const p = await makePage();
        try {
          await p.addInitScript(fps => {
            window.requestAnimationFrame = fn => setTimeout(() => fn(performance.now()), 1000 / fps);
            window.cancelAnimationFrame = clearTimeout;
          }, fps);
          await open(p, 'v=day&w=clear&ball=1&flit=0&ff=0');
          await p.waitForFunction(() => document.querySelector('#ball').style.opacity === '1');
          await p.waitForFunction(() => document.querySelector('#ball').style.opacity === '0' &&
            !window.naeru.busy, null, { timeout: 12000 });
          await p.locator('#naeru-touch').press('Space');
          assert.equal(await p.evaluate(() => window.naeru.busy), true);
          await p.waitForFunction(() => !window.naeru.busy);
          assert.deepEqual(p.errors, []);
        } finally { await p.close(); }
      }));
    });
    await check('나비가 영상을 세운 동안 탭 숨김·복귀', async () => {
      const p = await makePage();
      try {
        await open(p, 's=autumn&v=day&w=clear&ball=0&flit=1&ff=0');
        await p.waitForFunction(() => !!document.querySelector('video[data-pause-owner="butterfly"]'),
          null, { timeout: 22000 });
        await p.evaluate(() => {
          Object.defineProperty(document, 'hidden', { configurable: true, value: true });
          document.dispatchEvent(new Event('visibilitychange'));
        });
        assert.equal(await p.evaluate(() => window.naeru.hold), false);
        assert.equal(await p.locator('#flit').evaluate(e => e.style.opacity), '0');
        assert.equal(await p.evaluate(() => [...document.querySelectorAll('video')].every(v => v.paused)), true);
        await p.evaluate(() => {
          Object.defineProperty(document, 'hidden', { configurable: true, value: false });
          document.dispatchEvent(new Event('visibilitychange'));
        });
        await playing(p); assert.deepEqual(p.errors, []);
      } finally { await p.close(); }
    });
    await check('코덱 판정 중 풍경 변경·탭 숨김·복귀', async () => {
      const p = await makePage();
      let releaseProbe;
      const held = new Promise(resolve => { releaseProbe = resolve; });
      let sawProbe;
      const requestedProbe = new Promise(resolve => { sawProbe = resolve; });
      await p.route('**/alpha-probe.webm?*', async route => {
        sawProbe(); await held;
        await route.fulfill({ path: path.join(repo, 'img/alpha-probe.webm') });
      });
      try {
        await open(p, 's=autumn&v=day&w=clear&ball=0&flit=0&ff=0');
        await requestedProbe;
        const nightImages = Promise.all([
          p.waitForEvent('requestfinished', r => r.url().includes('bg-night-autumn.jpg')),
          p.waitForEvent('requestfinished', r => r.url().includes('naeru-night.png'))
        ]);
        await p.click('#settings-open'); await p.selectOption('#setting-band', 'night');
        await nightImages;
        await p.waitForTimeout(100);
        assert.equal(await p.evaluate(() => document.documentElement.dataset.sceneReady), 'false');
        await p.evaluate(() => {
          Object.defineProperty(document, 'hidden', { configurable: true, value: true });
          document.dispatchEvent(new Event('visibilitychange'));
        });
        releaseProbe();
        await p.waitForFunction(() => document.body.dataset.variant === 'night' &&
          document.documentElement.dataset.sceneReady === 'true');
        assert.equal(await p.locator('#naeruStill').evaluate(e => e.classList.contains('on')), true);
        await p.evaluate(() => {
          Object.defineProperty(document, 'hidden', { configurable: true, value: false });
          document.dispatchEvent(new Event('visibilitychange'));
        });
        await playing(p); assert.deepEqual(p.errors, []);
      } finally { releaseProbe(); await p.close(); }
    });
    await check('다가오기: 네 화면비에서 접근·눈 맞춤·자동 복귀', async () => {
      await Promise.all([[1920, 1080], [390, 844], [844, 390], [2560, 1080]].map(async ([width, height]) => {
        const p = await makePage({ viewport: { width, height } });
        try {
          await open(p, 's=autumn&v=day&w=clear&act=approach&ball=0&flit=0&ff=0');
          await p.waitForFunction(() => document.documentElement.dataset.approach === 'walking');
          assert.equal(await p.evaluate(() => naeru.busy && naeru.hold), true);
          await shot(p, `approach-${width}-start`);
          await p.waitForTimeout(1800); await shot(p, `approach-${width}-walking`);
          await p.waitForFunction(() => document.documentElement.dataset.approach === 'close');
          const close = await p.evaluate(() => ({
            eye: document.querySelector('#naeru-brow').getBoundingClientRect().toJSON(),
            flowers: getComputedStyle(document.querySelector('#approach-flowers')).opacity,
            ground: document.querySelector('#approach-ground').style.opacity,
            width: document.body.scrollWidth
          }));
          assert(close.eye.x > width * .3 && close.eye.x < width * .7);
          assert(close.eye.y > height * .25 && close.eye.y < height * .5);
          assert.equal(close.flowers, '1'); assert.equal(close.ground, '1');
          assert.equal(close.width, width); await shot(p, `approach-${width}-close`);
          await p.waitForFunction(() => !document.documentElement.dataset.approach);
          assert.equal(await p.evaluate(() => naeru.busy || naeru.hold), false);
          assert.equal(await p.locator('#naeru-approach').evaluate(e => e.style.transform), '');
          assert.equal(await p.locator('#approach-return').isVisible(), false);
          await shot(p, `approach-${width}-returned`);
          await p.locator('#naeru-touch').press('Enter');
          assert.equal(await p.evaluate(() => naeru.busy), true);
          assert.deepEqual(p.errors, []); assert.deepEqual(p.missing, []);
        } finally { await p.close(); }
      }));
    });
    await check('다가오기: 숨김·풍경 변경·동작 줄이기·화면 회전·Escape', async () => {
      await Promise.all(['hidden', 'scene', 'reduced', 'resize', 'escape'].map(async kind => {
        const p = await makePage();
        try {
          await open(p, 's=autumn&v=day&w=clear&act=approach&ball=0&flit=0&ff=0');
          await p.waitForFunction(() => document.documentElement.dataset.approach === 'walking');
          await p.waitForTimeout(700);
          if (kind === 'hidden') {
            await p.evaluate(() => {
              Object.defineProperty(document, 'hidden', { configurable: true, value: true });
              document.dispatchEvent(new Event('visibilitychange'));
            });
          } else if (kind === 'scene') {
            await p.click('#settings-open'); await p.selectOption('#setting-season', 'winter');
            await p.waitForFunction(() => document.documentElement.dataset.season === 'winter');
          } else if (kind === 'reduced') await p.emulateMedia({ reducedMotion: 'reduce' });
          else if (kind === 'resize') await p.setViewportSize({ width: 390, height: 844 });
          else await p.keyboard.press('Escape');
          await p.waitForFunction(() => !document.documentElement.dataset.approach);
          assert.equal(await p.evaluate(() => naeru.busy || naeru.hold), false);
          assert.equal(await p.locator('#naeru-stride').evaluate(e => e.style.transform), '');
          assert.equal(await p.locator('#approach-ground').evaluate(e => e.style.opacity), '0');
          if (kind === 'hidden') {
            await p.evaluate(() => {
              Object.defineProperty(document, 'hidden', { configurable: true, value: false });
              document.dispatchEvent(new Event('visibilitychange'));
            });
            await playing(p); await p.waitForTimeout(3000);
            assert.equal(await p.evaluate(() => document.documentElement.dataset.approach), undefined);
          }
          assert.deepEqual(p.errors, []);
        } finally { await p.close(); }
      }));
    });
    await check('다가오기: 설정 버튼·중복 요청·집중 완료 예약·장면 제한', async () => {
      const p = await makePage();
      try {
        await open(p, 's=autumn&v=day&w=clear&ball=0&flit=0&ff=0'); await playing(p);
        await p.click('#settings-open'); await p.click('#approach-preview');
        await p.waitForFunction(() => document.documentElement.dataset.approach === 'walking');
        await p.evaluate(() => {
          document.dispatchEvent(new Event('naeru:approach'));
          document.dispatchEvent(new Event('naeru:approach'));
        });
        await p.click('#approach-return');
        await p.waitForFunction(() => !document.documentElement.dataset.approach);
        await p.locator('#naeru-touch').press('Enter');
        await p.evaluate(() => document.dispatchEvent(new Event('naeru:focus-complete')));
        await p.waitForFunction(() => document.documentElement.dataset.approach === 'walking');
        await p.emulateMedia({ reducedMotion: 'reduce' });
        await p.waitForFunction(() => !document.documentElement.dataset.approach);
        assert.deepEqual(p.errors, []);
      } finally { await p.close(); }
      await Promise.all(['s=winter&v=day&w=clear', 's=autumn&v=dusk&w=clear',
        's=autumn&v=day&w=rain', 's=autumn&v=day&w=clear&still=1'].map(async query => {
        const p = await makePage();
        try {
          await open(p, query + '&ball=0&flit=0&ff=0');
          await p.click('#settings-open');
          assert.equal(await p.locator('#approach-setting').isVisible(), false);
          await p.keyboard.press('Escape');
          await p.evaluate(() => document.dispatchEvent(new Event('naeru:focus-complete')));
          await p.waitForTimeout(3200);
          assert.equal(await p.evaluate(() => document.documentElement.dataset.approach), undefined);
          assert.deepEqual(p.errors, []);
        } finally { await p.close(); }
      }));
    });
    await check('다가오기: 지난 집중 시간으로 재접속해도 한 번 알림', async () => {
      const p = await makePage();
      try {
        await p.addInitScript(() => sessionStorage.setItem('naeru-focus',
          JSON.stringify({ end: Date.now() - 1000 })));
        await open(p, 's=autumn&v=day&w=clear&ball=0&flit=0&ff=0');
        await p.waitForFunction(() => document.documentElement.dataset.approach === 'walking');
        assert.match(await p.locator('#focus-label').textContent(), /수고했어요/);
        assert.equal(await p.evaluate(() => sessionStorage.getItem('naeru-focus')), null);
        await p.click('#approach-return');
        await p.waitForFunction(() => !document.documentElement.dataset.approach);
        await p.waitForTimeout(1500);
        assert.equal(await p.evaluate(() => document.documentElement.dataset.approach), undefined);
        assert.deepEqual(p.errors, []);
      } finally { await p.close(); }
    });
    await check('다가오기: 5분 자동 방문 반복·숨은 탭 방문 누적 방지', async () => {
      const p = await makePage();
      try {
        await p.clock.install({ time: now });
        await p.addInitScript(() => {
          Math.random = () => .5;
          window.visits = [];
          document.addEventListener('naeru:scene', () => {
            if (document.documentElement.dataset.sceneReady === 'true') {
              window.readyAt = performance.now();
            }
          });
          document.addEventListener('DOMContentLoaded', () => {
            new MutationObserver(() => {
              if (document.documentElement.dataset.approach === 'walking') {
                window.visits.push(performance.now());
              }
            }).observe(document.documentElement, { attributes: true,
              attributeFilter: ['data-approach'] });
          });
        });
        await open(p, 's=autumn&v=day&w=clear&ball=0&flit=0&ff=0'); await playing(p);
        await p.clock.pauseAt(new Date(await p.evaluate(() => Date.now() + 1000)));
        assert.deepEqual(p.errors, []);
        async function advanceBeforeVisit(startedAt) {
          const elapsed = await p.evaluate(() => performance.now());
          await p.clock.fastForward(Math.max(0, Math.floor(startedAt + 299000 - elapsed)));
        }
        await advanceBeforeVisit(await p.evaluate(() => window.readyAt));
        assert.equal(await p.evaluate(() => window.visits.length), 0);
        await p.clock.runFor(12000);
        assert.equal(await p.evaluate(() => window.visits.length), 1);
        await advanceBeforeVisit(await p.evaluate(() => window.visits[0]));
        assert.equal(await p.evaluate(() => window.visits.length), 1);
        await p.clock.runFor(12000);
        assert.equal(await p.evaluate(() => window.visits.length), 2);
        await p.evaluate(() => {
          Object.defineProperty(document, 'hidden', { configurable: true, value: true });
          document.dispatchEvent(new Event('visibilitychange'));
        });
        await p.clock.fastForward(600000);
        assert.equal(await p.evaluate(() => window.visits.length), 2);
        const resumedAt = await p.evaluate(() => {
          Object.defineProperty(document, 'hidden', { configurable: true, value: false });
          document.dispatchEvent(new Event('visibilitychange'));
          return performance.now();
        });
        await advanceBeforeVisit(resumedAt);
        assert.equal(await p.evaluate(() => window.visits.length), 2);
        await p.clock.runFor(12000);
        assert.equal(await p.evaluate(() => window.visits.length), 3);
        assert.deepEqual(p.errors, []); assert.deepEqual(p.missing, []);
      } finally { await p.close(); }
    });
    await check('집중 시간 저장·완료·종료', async () => {
      const p = await makePage({ reducedMotion: 'reduce' });
      try {
        await open(p, 'w=clear'); await p.click('#settings-open');
        await p.click('#focus-start');
        assert.match(await p.locator('#focus-label').textContent(), /25:00/);
        await shot(p, 'focus-running');
        await p.reload(); await p.waitForFunction(() => !document.querySelector('#focus-strip').hidden);
        const saved = await p.evaluate(() => JSON.parse(sessionStorage.getItem('naeru-focus')));
        await p.clock.setFixedTime(new Date(saved.end + 1000));
        await p.waitForFunction(() => document.querySelector('#focus-label').textContent.includes('수고했어요'));
        assert.equal(await p.title(), '내루미');
        assert.equal(await p.evaluate(() => sessionStorage.getItem('naeru-focus')), null);
        await shot(p, 'focus-complete');
        await p.click('#focus-stop');
        assert.equal(await p.locator('#focus-strip').isVisible(), false);
        assert.deepEqual(p.errors, []);
      } finally { await p.close(); }
    });
  } finally {
    await browser.close(); await new Promise(resolve => server.close(resolve));
    if (out) fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(results, null, 2));
  }
  console.log(`${results.filter(r => r.pass).length}/${results.length} checks passed`);
  if (results.some(r => !r.pass)) process.exitCode = 1;
})().catch(e => { console.error(e); server.close(); process.exitCode = 1; });
