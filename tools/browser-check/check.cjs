/* 앱에는 의존성을 추가하지 않고 실제 브라우저의 표시·입력·상태 전환을 검사한다. */
const { chromium } = require(process.env.NAERU_PLAYWRIGHT || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const repo = path.resolve(__dirname, '../..');
const out = process.env.NAERU_CHECK_OUTPUT;
if (out) fs.mkdirSync(out, { recursive: true });
const mime = { '.html': 'text/html', '.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp',
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
    args: process.platform === 'darwin' ?
      ['--enable-gpu', '--ignore-gpu-blocklist', '--use-angle=metal'] :
      ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'],
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
    await page.waitForFunction(() => [...document.querySelectorAll('video.naeru')]
      .some(v => v.classList.contains('on') && !v.paused && v.currentTime > .3),
    null, { timeout: 30000 }); // 첫 인사 동안은 뉴트럴 프레임을 의도적으로 멈춘다.
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
              const layered = ['autumn', 'winter'].includes(season) && w === 'clear';
              assert.equal(await p.evaluate(() => document.documentElement.dataset.landscape),
                layered ? 'ready' : 'none');
              assert.equal(await p.locator('.landscape-layer.on').count(), layered ? 1 : 0);
              if (layered) {
                assert.match(await p.locator('.landscape-layer.on').getAttribute('src'),
                  new RegExp(`landscape-${band}-${season}\\.webp`));
                assert.deepEqual(await p.locator('#landscape').boundingBox(),
                  await p.locator('#stage').boundingBox());
              }
              const foreground = ['autumn', 'winter'].includes(season);
              assert.equal(await p.evaluate(() => document.documentElement.dataset.foreground),
                foreground ? 'ready' : 'none');
              assert.equal(await p.locator('.foreground-layer.on').count(), foreground ? 1 : 0);
              if (foreground) {
                assert.match(await p.locator('.foreground-layer.on').getAttribute('src'),
                  new RegExp(`foreground-${state.variant}-${season}\\.webp`));
              }
              await p.waitForFunction(() => document.querySelector('#naeruHd').dataset.status === 'ready' &&
                document.querySelector('#naeruStill').naturalWidth === 4608);
              const character = season === 'winter' && w === 'clear'
                ? `winter-${band}` : state.variant;
              assert.match(await p.locator('#naeruStill').getAttribute('src'),
                new RegExp(`naeru-${character}-hd\\.webp`));
              assert.deepEqual(p.errors, []); assert.deepEqual(p.missing, []);
              await shot(p, `${season}-${band}-${w}`);
            }
          } finally { await p.close(); }
        }));
      }
    });
    await check('겨울 맑은 네 시간대: 모자·목도리 몸짓과 장면 한정', async () => {
      const p = await makePage({ viewport: { width: 1440, height: 900 } });
      try {
        for (const band of ['dawn', 'day', 'dusk', 'night']) {
          await open(p, `s=winter&v=${band}&w=clear&act=0&ball=0&flit=0&ff=0`);
          await playing(p);
          assert.match(await p.locator('video.naeru.on').getAttribute('src'),
            new RegExp(`naeru-winter-${band}\\.(webm|mp4)`));
          await p.waitForFunction(() =>
            document.querySelector('#naeruHd').dataset.status === 'ready');
          assert.match(await p.locator('#naeruHd').getAttribute('src'),
            new RegExp(`naeru-winter-${band}-hd\\.webp`));
          await p.waitForTimeout(400);
          await shot(p, `winter-${band}-outfit-motion`);
        }

        await open(p, 's=winter&v=day&w=rain&act=0&ball=0&flit=0&ff=0');
        await playing(p);
        await p.waitForFunction(() =>
          document.querySelector('#naeruHd').dataset.status === 'ready');
        assert.match(await p.locator('video.naeru.on').getAttribute('src'),
          /naeru-day-rain\.(webm|mp4)/);
        assert.doesNotMatch(await p.locator('#naeruHd').getAttribute('src'),
          /naeru-winter-/);

        await open(p, 's=autumn&v=day&w=clear&act=0&ball=0&flit=0&ff=0');
        await playing(p);
        await p.waitForFunction(() =>
          document.querySelector('#naeruHd').dataset.status === 'ready');
        assert.match(await p.locator('video.naeru.on').getAttribute('src'),
          /naeru-day\.(webm|mp4)/);
        assert.doesNotMatch(await p.locator('#naeruHd').getAttribute('src'),
          /naeru-winter-/);
        assert.deepEqual(p.errors, []); assert.deepEqual(p.missing, []);
      } finally { await p.close(); }
    });
    await check('가을 낮 풍경 레이어: 실패·시간 초과·장면 전환에도 원본 배경 유지', async () => {
      await Promise.all(['failed', 'slow', 'scene'].map(async kind => {
        const p = await makePage({ reducedMotion: 'reduce' });
        let release;
        const held = new Promise(resolve => { release = resolve; });
        await p.route('**/landscape-day-autumn.webp?*', async route => {
          if (kind === 'failed') return route.abort();
          await held;
          await route.fulfill({ path: path.join(repo, 'img/landscape-day-autumn.webp') });
        });
        try {
          await p.goto(base + '/?s=autumn&v=day&w=clear', { waitUntil: 'domcontentloaded' });
          if (kind === 'scene') {
            await p.click('#settings-open'); await p.selectOption('#setting-band', 'night');
            await p.waitForFunction(() => document.body.dataset.variant === 'night' &&
              document.documentElement.dataset.sceneReady === 'true');
            release(); await p.waitForTimeout(300);
            assert.equal(await p.evaluate(() => document.documentElement.dataset.landscape), 'ready');
            assert.match(await p.locator('.landscape-layer.on').getAttribute('src'),
              /landscape-night-autumn\.webp/);
          } else {
            await p.waitForFunction(() => document.documentElement.dataset.sceneReady === 'true');
            assert.equal(await p.evaluate(() => document.documentElement.dataset.landscape), 'failed');
            assert.equal(await p.locator('.landscape-layer.on').count(), 0);
            assert.match(await p.locator('.bg-layer.on').evaluate(e => e.style.backgroundImage),
              /sky-day-autumn\.webp/);
            if (kind === 'slow') {
              release(); await p.waitForTimeout(300);
              assert.equal(await p.locator('.landscape-layer.on').count(), 0);
            }
          }
          assert.deepEqual(p.errors, []);
        } finally { release(); await p.close(); }
      }));
    });
    await check('가을·겨울 맑음 네 시간대: 정지본에서 영상으로 즉시 교체', async () => {
      for (const season of ['autumn', 'winter']) {
        for (const band of ['dawn', 'day', 'dusk', 'night']) {
        const p = await makePage();
        const requested = [];
        p.on('request', request => requested.push(request.url()));
        try {
          await open(p, `s=${season}&v=${band}&w=clear&act=0&ball=0&flit=0&ff=0`);
          assert.match(await p.locator('.bg-layer.on').evaluate(e => e.style.backgroundImage),
            new RegExp(`sky-${band}-${season}\\.webp`));
          assert.equal(requested.some(url =>
            url.includes(`bg-${band}-${season}.jpg`)), false);
          await p.waitForFunction(() =>
            document.documentElement.dataset.skyMotion === 'playing');
          const state = await p.locator('#skyMotion').evaluate(
            async (video, { band, season }) => {
            video.pause(); video.currentTime = 0;
            await new Promise(resolve => {
              if (video.currentTime === 0 && video.readyState >= 2) return resolve();
              video.addEventListener('seeked', resolve, { once: true });
            });
            const image = new Image();
            image.src = `img/sky-${band}-${season}.webp?v=${
              document.documentElement.dataset.av}`;
            await image.decode();
            const canvas = document.createElement('canvas');
            canvas.width = 1920; canvas.height = 1080;
            const context = canvas.getContext('2d');
            context.drawImage(image, 0, 0);
            const still = context.getImageData(0, 0, 1920, 1080).data;
            context.clearRect(0, 0, 1920, 1080);
            context.drawImage(video, 0, 0);
            const motion = context.getImageData(0, 0, 1920, 1080).data;
            let difference = 0;
            for (let i = 0; i < still.length; i++) {
              difference += Math.abs(still[i] - motion[i]);
            }
            return { difference: difference / still.length,
              transition: getComputedStyle(video).transitionDuration,
              opacity: getComputedStyle(video).opacity };
          }, { band, season });
          // H.264의 YUV420 색을 브라우저가 RGB로 되돌릴 때 ffmpeg로 만든
          // 무손실 poster와 최대 약 3/255의 디코더별 반올림 차이가 난다.
          assert(state.difference < 3,
            `${season}/${band} 첫 프레임 차이: ${state.difference}`);
          assert.equal(state.transition, '0s');
          assert.equal(state.opacity, '1');
          await shot(p, `${season}-${band}-cloud-first`);
          assert.deepEqual(p.errors, []); assert.deepEqual(p.missing, []);
        } finally { await p.close(); }
      }
      }
    });
    await check('가을·겨울 맑음 구름: 60초 영상 재생·장면 이탈 정리', async () => {
      for (const season of ['autumn', 'winter']) {
      const p = await makePage({ viewport: { width: 1920, height: 1080 } });
      try {
        await open(p, `s=${season}&v=day&w=clear&act=0&ball=0&flit=0&ff=0`);
        await p.waitForFunction(() =>
          document.documentElement.dataset.skyMotion === 'playing');
        await p.waitForFunction(() => {
          const video = document.querySelector('#skyMotion');
          return !video.paused && video.currentTime > 0;
        });
        const before = await p.locator('#skyMotion').evaluate(v => ({
          src: v.currentSrc, duration: v.duration, time: v.currentTime,
          width: v.videoWidth, height: v.videoHeight, paused: v.paused,
          muted: v.muted, loop: v.loop, inline: v.playsInline,
          fit: getComputedStyle(v).objectFit
        }));
        await p.waitForTimeout(600);
        const after = await p.locator('#skyMotion').evaluate(v => v.currentTime);
        assert.match(before.src, new RegExp(`sky-day-${season}\\.mp4`));
        assert(Math.abs(before.duration - 60) < .05);
        assert.deepEqual([before.width, before.height], [1920, 1080]);
        assert.equal(before.paused, false);
        assert.equal(before.muted && before.loop && before.inline, true);
        assert.equal(before.fit, 'cover');
        assert(after > before.time + .2);
        assert.equal(await p.locator('.landscape-layer.on').count(), 1);
        await shot(p, `${season}-day-cloud-motion`);

        await p.click('#settings-open');
        await p.selectOption('#setting-season', 'summer');
        await p.waitForFunction(() => document.documentElement.dataset.season === 'summer' &&
          document.documentElement.dataset.sceneReady === 'true');
        assert.equal(await p.evaluate(() =>
          document.documentElement.dataset.skyMotion), 'none');
        assert.equal(await p.locator('#skyMotion').getAttribute('src'), null);
        assert.equal(await p.locator('#skyMotion').evaluate(v => v.paused), true);
        assert.deepEqual(p.errors, []); assert.deepEqual(p.missing, []);
      } finally { await p.close(); }
      }
    });
    await check('가을·겨울 구름: 실패·동작 줄이기·강수 장면은 정적 폴백', async () => {
      for (const kind of ['failed', 'reduced', 'rain', 'winter-rain', 'summer']) {
        const reducedMotion = kind === 'reduced' ? 'reduce' : 'no-preference';
        const p = await makePage({ reducedMotion });
        let requested = 0;
        p.on('request', request => {
          if (/sky-day-(autumn|winter)\.mp4/.test(request.url())) requested++;
        });
        if (kind === 'failed') {
          await p.route('**/sky-day-autumn.mp4?*', route => route.abort());
        }
        try {
          const query = kind === 'rain'
            ? 's=autumn&v=day&w=rain'
            : kind === 'winter-rain'
              ? 's=winter&v=day&w=rain'
            : kind === 'summer'
              ? 's=summer&v=day&w=clear'
              : 's=autumn&v=day&w=clear';
          await open(p, `${query}&act=0&ball=0&flit=0&ff=0`);
          if (kind === 'failed') {
            await p.waitForFunction(() =>
              document.documentElement.dataset.skyMotion === 'failed');
            assert(requested >= 1 && requested <= 2);
          } else {
            await p.waitForTimeout(300);
            assert.equal(requested, 0);
            assert.equal(await p.evaluate(() =>
              document.documentElement.dataset.skyMotion), 'none');
          }
          assert.equal(await p.locator('#skyMotion').evaluate(v =>
            v.classList.contains('on')), false);
          assert.equal(await p.locator('.bg-layer.on').count(), 1);
          assert.deepEqual(p.errors, []); assert.deepEqual(p.missing, []);
        } finally { await p.close(); }
      }
    });
    await check('가을 전경: 실패·시간 초과·오래된 응답에도 장면과 입력 유지', async () => {
      await Promise.all(['failed', 'slow', 'scene'].map(async kind => {
        const p = await makePage({ reducedMotion: 'reduce' });
        let release;
        const held = new Promise(resolve => { release = resolve; });
        await p.route('**/foreground-day-autumn.webp?*', async route => {
          if (kind === 'failed') return route.abort();
          await held;
          await route.fulfill({ path: path.join(repo, 'img/foreground-day-autumn.webp') });
        });
        try {
          await p.goto(base + '/?s=autumn&v=day&w=clear', { waitUntil: 'domcontentloaded' });
          if (kind === 'scene') {
            await p.click('#settings-open'); await p.selectOption('#setting-band', 'night');
            await p.waitForFunction(() => document.body.dataset.variant === 'night' &&
              document.documentElement.dataset.sceneReady === 'true');
            release(); await p.waitForTimeout(300);
            assert.match(await p.locator('.foreground-layer.on').getAttribute('src'),
              /foreground-night-autumn\.webp/);
          } else {
            await p.waitForFunction(() => document.documentElement.dataset.sceneReady === 'true');
            assert.equal(await p.evaluate(() => document.documentElement.dataset.foreground), 'failed');
            assert.equal(await p.locator('.foreground-layer.on').count(), 0);
            assert.equal(await p.locator('#naeruStill').isVisible(), true);
            if (kind === 'slow') {
              release(); await p.waitForTimeout(300);
              assert.equal(await p.locator('.foreground-layer.on').count(), 0);
            }
            await p.click('#settings-open'); await p.selectOption('#setting-band', 'night');
            await p.waitForFunction(() => document.documentElement.dataset.foreground === 'ready');
          }
          await p.selectOption('#setting-season', 'summer');
          await p.waitForFunction(() => document.documentElement.dataset.season === 'summer' &&
            document.documentElement.dataset.sceneReady === 'true');
          assert.equal(await p.locator('.foreground-layer.on').count(), 0);
          assert.deepEqual(p.errors, []);
        } finally { release(); await p.close(); }
      }));
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
        assert([576, 4608].includes(await p.locator('#naeruStill').evaluate(e => e.naturalWidth)));
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
        // 첫 접근 중에는 같은 정지본을 HD 레이어로 교차 전환한다.
        // 복귀 후 기본 정지본이 다시 보이는지까지 확인한다.
        await p.waitForFunction(() => !document.documentElement.dataset.approach &&
          getComputedStyle(document.querySelector('#naeruStill')).opacity === '1',
        null, { timeout: 20000 });
        assert.equal(await p.locator('#naeruStill').evaluate(e => getComputedStyle(e).opacity), '1');
        assert.equal(await p.locator('#naeruStill').evaluate(e => e.naturalWidth), 4608);
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
          await p.waitForFunction(() => document.querySelector('#ball').style.opacity === '1',
            null, { timeout: 30000 }); // 첫 인사가 끝난 뒤 공이 들어온다.
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
          null, { timeout: 35000 });
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
          p.waitForEvent('requestfinished', r => r.url().includes('sky-night-autumn.webp')),
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
    await check('그림자: 사계절·정지 모드와 점프 중 지면 고정', async () => {
      for (const season of ['spring', 'summer', 'autumn', 'winter']) {
        const p = await makePage({ reducedMotion: 'reduce' });
        try {
          await open(p, `s=${season}&v=day&w=clear&act=0`);
          assert.equal(await p.locator('#naeru-shadow').isVisible(), true);
          assert.equal(await p.locator('#naeru-shadow').evaluate(e => e.parentElement.id), 'stage');
          assert.equal(await p.locator('#approach-ground').count(), 0);
          assert.equal(await p.locator('#approach-shadow').count(), 0);
          const [shadow, body] = await Promise.all([
            p.locator('#naeru-shadow').boundingBox(), p.locator('#naeru-move').boundingBox()
          ]);
          assert.deepEqual(shadow, body);
          assert(await p.locator('#shadow-contact').evaluate(e => +getComputedStyle(e).opacity) > 0);
          assert.deepEqual(p.errors, []);
        } finally { await p.close(); }
      }
      await Promise.all([[1280, 720], [390, 844]].map(async ([width, height]) => {
        const p = await makePage({ viewport: { width, height } });
        try {
          await open(p, 's=summer&v=day&w=clear&act=approach&ball=0&flit=0&ff=0');
          await playing(p);
          const samples = await p.evaluate(() => new Promise(resolve => {
            const shadow = document.querySelector('#naeru-shadow');
            const body = document.querySelector('#naeru-move');
            const contact = document.querySelector('#shadow-contact');
            const frames = [];
            function sample() {
              const s = shadow.getBoundingClientRect(), b = body.getBoundingClientRect();
              frames.push({ groundY: s.y + s.height * .790323, bodyY: b.y,
                opacity: +getComputedStyle(contact).opacity });
              if (naeru.busy) requestAnimationFrame(sample);
              else resolve(frames);
            }
            frames.push({ groundY: shadow.getBoundingClientRect().y +
              shadow.getBoundingClientRect().height * .790323,
              bodyY: body.getBoundingClientRect().y, opacity: +getComputedStyle(contact).opacity });
            document.dispatchEvent(new Event('naeru:greet'));
            requestAnimationFrame(sample);
          }));
          assert(samples.length > 5);
          assert(samples[0].bodyY - Math.min(...samples.map(s => s.bodyY)) > 5);
          assert(Math.max(...samples.map(s => s.groundY)) -
            Math.min(...samples.map(s => s.groundY)) < .1);
          assert(Math.min(...samples.map(s => s.opacity)) < samples[0].opacity * .6);
          assert.equal(samples.at(-1).opacity, samples[0].opacity);
          await shot(p, `shadow-returned-${width}`);
          assert.deepEqual(p.errors, []);
        } finally { await p.close(); }
      }));
    });
    await check('근접 모션: 기존 원화의 얼굴 보존·팔·혀·몸의 독립 움직임', async () => {
      const p = await makePage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });
      p.setDefaultTimeout(30000);
      try {
        await p.clock.install({ time: now });
        await open(p, 's=autumn&v=day&w=clear&act=approach&ball=0&flit=0&ff=0');
        await p.waitForFunction(() => document.documentElement.dataset.closeMotion === 'playing');
        await p.clock.pauseAt(new Date(await p.evaluate(() => Date.now() + 50)));
        const samples = await p.evaluate(() => {
          const canvas = document.querySelector('#naeruCloseRig');
          const source = document.querySelector('#naeruClose');
          const gl = canvas.getContext('webgl'), scale = canvas.width / 576;
          const reference = document.createElement('canvas');
          reference.width = canvas.width; reference.height = canvas.height;
          const context = reference.getContext('2d');
          context.drawImage(source, 0, 0, reference.width, reference.height);
          function read(x, y, w, h) {
            [x, y, w, h] = [x, y, w, h].map(v => Math.round(v * scale));
            const pixels = new Uint8Array(w * h * 4);
            gl.readPixels(x, canvas.height - y - h, w, h, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
            const flipped = new Uint8Array(pixels.length);
            for (let row = 0; row < h; row++) {
              flipped.set(pixels.subarray(row * w * 4, (row + 1) * w * 4), (h - row - 1) * w * 4);
            }
            return flipped;
          }
          function difference(a, b) {
            let total = 0;
            for (let i = 0; i < a.length; i++) total += Math.abs(a[i] - b[i]);
            return total / a.length;
          }
          const faceBox = [195, 85, 105, 65];
          naeruCloseMotion.show(0, 0, 0, '1');
          const face = read(...faceBox);
          const original = context.getImageData(...faceBox.map(v => Math.round(v * scale))).data;
          // WebGL readPixels는 premultiplied alpha, ImageData는 straight alpha다.
          for (let i = 0; i < original.length; i += 4) {
            for (let c = 0; c < 3; c++) original[i + c] = Math.round(original[i + c] * original[i + 3] / 255);
          }
          const body = read(235, 220, 65, 105);
          naeruCloseMotion.show(1, 0, 0, '1');
          const bodyOnly = read(235, 220, 65, 105);
          const right = read(320, 210, 65, 85), left = read(120, 210, 70, 70);
          naeruCloseMotion.show(1, 1, 0, '1');
          const armRight = read(320, 210, 65, 85), armLeft = read(120, 210, 70, 70);
          const tongue = read(158, 215, 75, 110);
          naeruCloseMotion.show(1, 1, 1, '1');
          const faceMoved = read(195, 92, 105, 65);
          return { source: canvas.dataset.source, image: source.currentSrc,
            width: canvas.width, height: canvas.height,
            originalFaceError: difference(face, original), faceShapeError: difference(face, faceMoved),
            bodyChange: difference(body, bodyOnly), rightChange: difference(right, armRight),
            leftChange: difference(left, armLeft), tongueChange: difference(tongue, read(158, 215, 75, 110)),
            error: gl.getError(), identity: new DOMMatrix(getComputedStyle(
              document.querySelector('#naeru-stride')).transform).isIdentity };
        });
        assert.equal(samples.source, samples.image);
        assert.deepEqual([samples.width, samples.height], [4608, 3968]);
        assert(samples.originalFaceError < 1, `원화의 얼굴 픽셀 유지: ${samples.originalFaceError}`);
        assert(samples.faceShapeError < 1, `움직일 때도 얼굴 비율·선 유지: ${samples.faceShapeError}`);
        for (const key of ['bodyChange', 'rightChange', 'leftChange', 'tongueChange']) {
          assert(samples[key] > 2, `${key}: 전체 DOM 확대 없이 해당 부위가 실제로 움직인다`);
        }
        assert.equal(samples.error, 0);
        assert(samples.identity, '전체 DOM을 늘리는 숨쉬기를 사용하지 않는다');
        await p.clock.runFor(11000);
        assert.equal(await p.evaluate(() => document.documentElement.dataset.approach), undefined);
        assert(await p.locator('#naeruCloseRig').evaluate(c => c.width === 1 && c.style.opacity === '0'));
        assert.equal(await p.evaluate(() => naeru.busy || naeru.hold), false);
        assert.deepEqual(p.errors, []); assert.deepEqual(p.missing, []);
      } finally { await p.close(); }
    });
    await check('근접 모션: WebGL 실패·컨텍스트 손실에도 원화와 입력 복구', async () => {
      for (const kind of ['unavailable', 'lost']) {
        const p = await makePage(); p.setDefaultTimeout(30000);
        try {
          if (kind === 'unavailable') await p.addInitScript(() => {
            const getContext = HTMLCanvasElement.prototype.getContext;
            HTMLCanvasElement.prototype.getContext = function (type, ...args) {
              return type === 'webgl' ? null : getContext.call(this, type, ...args);
            };
          });
          await open(p, 's=autumn&v=day&w=clear&act=approach&ball=0&flit=0&ff=0');
          await p.waitForFunction(() => document.documentElement.dataset.approach === 'close');
          if (kind === 'lost') {
            await p.waitForFunction(() => document.documentElement.dataset.closeMotion === 'playing');
            await p.locator('#naeruCloseRig').evaluate(c => c.getContext('webgl')
              .getExtension('WEBGL_lose_context').loseContext());
            await p.waitForFunction(() => !document.documentElement.dataset.closeMotion);
          }
          assert(await p.locator('#naeruClose').evaluate(e =>
            e.naturalWidth === 4608 && getComputedStyle(e).visibility === 'visible'));
          assert.equal(await p.evaluate(() => document.documentElement.dataset.approachArt), 'closeup');
          await p.waitForFunction(() => !document.documentElement.dataset.approach);
          assert.equal(await p.evaluate(() => naeru.busy || naeru.hold), false);
          await playing(p);
          assert.deepEqual(p.errors, []);
        } finally { await p.close(); }
      }
    });
    await check('다가오기: 네 화면비에서 접근·눈 맞춤·자동 복귀', async () => {
      await Promise.all([[1920, 1080], [390, 844], [844, 390], [2560, 1080]].map(async ([width, height]) => {
        const p = await makePage({ viewport: { width, height } });
        try {
          await open(p, 's=autumn&v=day&w=clear&act=approach&ball=0&flit=0&ff=0');
          await p.waitForFunction(() => document.documentElement.dataset.approach === 'walking');
          assert.equal(await p.evaluate(() => naeru.busy && naeru.hold), true);
          const foregroundBox = await p.locator('#foreground').boundingBox();
          await shot(p, `approach-${width}-start`);
          await p.waitForTimeout(1800); await shot(p, `approach-${width}-walking`);
          await p.waitForFunction(() => document.documentElement.dataset.approach === 'close');
          const close = await p.evaluate(() => ({
            eye: document.querySelector('#naeru-brow').getBoundingClientRect().toJSON(),
            flowers: getComputedStyle(document.querySelector('.foreground-layer.on')).opacity,
            shadow: document.querySelector('#naeru-shadow').style.transform,
            approach: document.querySelector('#naeru-approach').style.transform,
            width: document.body.scrollWidth
          }));
          assert(close.eye.x > width * .3 && close.eye.x < width * .7);
          assert(close.eye.y > height * .25 && close.eye.y < height * .5);
          assert.equal(close.flowers, '1'); assert.equal(close.shadow, close.approach);
          assert.deepEqual(await p.locator('#foreground').boundingBox(), foregroundBox);
          assert.equal(close.width, width); await shot(p, `approach-${width}-close`);
          await p.waitForFunction(() => !document.documentElement.dataset.approach, null, { timeout: 15000 });
          assert.equal(await p.evaluate(() => naeru.busy || naeru.hold), false);
          assert.equal(await p.locator('#naeru-approach').evaluate(e => e.style.transform), '');
          assert.equal(await p.locator('#approach-return').isVisible(), false);
          assert.equal(await p.locator('.foreground-layer.on').evaluate(e => getComputedStyle(e).opacity), '1');
          assert.deepEqual(await p.locator('#foreground').boundingBox(), foregroundBox);
          await shot(p, `approach-${width}-returned`);
          await p.locator('#naeru-touch').press('Enter');
          assert.equal(await p.evaluate(() => naeru.busy), true);
          assert.deepEqual(p.errors, []); assert.deepEqual(p.missing, []);
        } finally { await p.close(); }
      }));
    });
    await check('다가오기: 가을 네 시간대의 첫 방문·꽃·지면 그림자', async () => {
      for (const [width, height] of [[1920, 1080], [390, 844]]) {
        await Promise.all(['dawn', 'day', 'dusk', 'night'].map(async band => {
          const p = await makePage({ viewport: { width, height } });
          p.setDefaultTimeout(30000);
          try {
            await p.addInitScript(() => { Math.random = () => .99; });
            await open(p, `s=autumn&v=${band}&w=clear&ball=0&flit=0&ff=0`);
            await p.waitForFunction(() => document.documentElement.dataset.approach === 'walking');
            const video = p.locator('video.naeru.on');
            const frozen = await video.evaluate(v => ({ time: v.currentTime,
              owner: v.dataset.pauseOwner, paused: v.paused }));
            assert.equal(frozen.owner, 'approach'); assert(frozen.paused);
            assert(frozen.time <= 8 / 24 || frozen.time >= 308 / 24);
            await p.waitForTimeout(1800);
            const incoming = await p.locator('#naeruCloseRig').evaluate(canvas => {
              const box = canvas.getBoundingClientRect();
              return { opacity: +canvas.style.opacity, width: canvas.width,
                height: canvas.height, displayWidth: box.width,
                displayHeight: box.height };
            });
            assert(incoming.opacity > .95);
            assert(incoming.width >= incoming.displayWidth);
            assert(incoming.height >= incoming.displayHeight);
            assert.equal(await video.evaluate(v => v.style.opacity), '0');
            await shot(p, `autumn-${band}-${width}-walking`);
            await p.waitForFunction(() => document.documentElement.dataset.approach === 'close');
            assert.equal(await p.evaluate(() => document.documentElement.dataset.approachQuality), 'hd');
            assert.equal(await p.evaluate(() => document.documentElement.dataset.approachArt), 'closeup');
            assert.equal(await p.locator('#naeruClose').evaluate(e => e.naturalWidth), 4608);
            assert.equal(await p.locator('#naeruClose').evaluate(e => e.style.opacity), '0');
            assert.equal(await p.locator('#naeruCloseRig').evaluate(e => e.style.opacity), '1');
            assert.notEqual(await p.locator('#naeruHd').evaluate(e => e.style.opacity), '1');
            assert.equal(await video.evaluate(v => v.style.opacity), '0');
            assert.match(await p.locator('.foreground-layer.on').getAttribute('src'),
              new RegExp(`foreground-${band}-autumn\\.webp`));
            assert.equal(await p.locator('#approach-flowers').count(), 0);
            assert.equal(await video.evaluate(v => v.currentTime), frozen.time);
            await shot(p, `autumn-${band}-${width}-close`);
            await p.waitForFunction(() => !document.documentElement.dataset.approach);
            await playing(p);
            assert.equal(await p.locator('#naeruClose').evaluate(e => e.style.opacity), '0');
            assert.equal(await p.locator('#naeruCloseRig').evaluate(e => e.style.opacity), '0');
            assert.match(await p.locator('#naeruStill').getAttribute('src'), /-hd\.webp/);
            assert.equal(await video.evaluate(v => v.dataset.pauseOwner), undefined);
            await shot(p, `autumn-${band}-${width}-returned`);
            assert.deepEqual(p.errors, []); assert.deepEqual(p.missing, []);
          } finally { await p.close(); }
        }));
      }
    });
    await check('다가오기: 겨울 네 시간대의 첫 방문·앞풀·근접 원화', async () => {
      await Promise.all(['dawn', 'day', 'dusk', 'night'].map(async band => {
        const p = await makePage({ viewport: { width: 1280, height: 720 } });
        p.setDefaultTimeout(30000);
        try {
          await p.addInitScript(() => { Math.random = () => .99; });
          await open(p, `s=winter&v=${band}&w=clear&ball=0&flit=0&ff=0`);
          await p.waitForFunction(() =>
            document.documentElement.dataset.approach === 'walking');
          assert.equal(await p.locator('#approach-setting').evaluate(e => e.hidden), false);
          assert.match(await p.locator('.foreground-layer.on').getAttribute('src'),
            new RegExp(`foreground-${band}-winter\\.webp`));
          await p.waitForTimeout(1800);
          assert(await p.locator('#naeruCloseRig').evaluate(canvas =>
            +canvas.style.opacity > .95 && canvas.width >= canvas.getBoundingClientRect().width));
          assert.equal(await p.locator('video.naeru.on').evaluate(v => v.style.opacity), '0');
          await p.waitForFunction(() =>
            document.documentElement.dataset.approach === 'close');
          assert.equal(await p.evaluate(() =>
            document.documentElement.dataset.approachQuality), 'hd');
          assert.equal(await p.evaluate(() =>
            document.documentElement.dataset.approachArt), 'closeup');
          assert.equal(await p.locator('#naeruClose').evaluate(e => e.naturalWidth), 4608);
          const character = `winter-${band}`;
          assert.match(await p.locator('#naeruClose').getAttribute('src'),
            new RegExp(`naeru-${character}-close\\.webp`));
          assert.match(await p.locator('#naeruCloseRig').getAttribute('data-source'),
            new RegExp(`naeru-${character}-close\\.webp`));
          await p.waitForTimeout(2500);
          await shot(p, `winter-${band}-approach-close`);
          await p.click('#approach-return');
          await p.waitForFunction(() => !document.documentElement.dataset.approach);
          assert.deepEqual(p.errors, []); assert.deepEqual(p.missing, []);
        } finally { await p.close(); }
      }));
    });
    await check('고해상도: 실패·늦은 로드·풍경 전환 중 오래된 응답', async () => {
      await Promise.all(['failed', 'slow', 'scene'].map(async kind => {
        const p = await makePage(); p.setDefaultTimeout(30000);
        let release;
        const held = new Promise(resolve => { release = resolve; });
        await p.route('**/naeru-day-hd.webp?*', async route => {
          if (kind === 'failed') return route.abort();
          await held;
          await route.fulfill({ path: path.join(repo, 'img/naeru-day-hd.webp') });
        });
        // 기존 HD 실패 검사는 근접 원화도 없을 때의 최후 정지본을 확인한다.
        await p.route('**/naeru-day-close.webp?*', route => route.abort());
        try {
          await open(p, 's=autumn&v=day&w=clear&act=approach&ball=0&flit=0&ff=0');
          if (kind === 'scene') {
            await p.click('#settings-open'); await p.selectOption('#setting-band', 'night');
            await p.waitForFunction(() => document.body.dataset.variant === 'night' &&
              document.querySelector('#naeruHd').dataset.status === 'ready');
            release(); await p.waitForTimeout(500);
            assert.match(await p.locator('#naeruHd').getAttribute('src'), /naeru-night-hd.webp/);
            await p.keyboard.press('Escape');
            await p.waitForFunction(() => document.documentElement.dataset.approach === 'walking');
            assert.equal(await p.evaluate(() => document.documentElement.dataset.approachQuality), 'hd');
          } else {
            await p.waitForFunction(() => document.documentElement.dataset.approach === 'walking');
            assert.equal(await p.evaluate(() => document.documentElement.dataset.approachQuality), 'original');
            if (kind === 'slow') {
              release();
              await p.waitForFunction(() => document.querySelector('#naeruHd').dataset.status === 'ready');
              await p.waitForFunction(() => document.documentElement.dataset.approach === 'close');
              assert.equal(await p.locator('#naeruHd').evaluate(e => e.style.opacity), '0');
              assert.equal(await p.evaluate(() => document.documentElement.dataset.approachQuality), 'original');
            }
            await p.click('#approach-return');
            await p.waitForFunction(() => !document.documentElement.dataset.approach);
            await playing(p);
            if (kind === 'slow') {
              await p.evaluate(() => document.dispatchEvent(new Event('naeru:approach')));
              await p.waitForFunction(() => document.documentElement.dataset.approach === 'close');
              assert.equal(await p.evaluate(() => document.documentElement.dataset.approachQuality), 'hd');
              assert.equal(await p.locator('#naeruHd').evaluate(e => e.style.opacity), '1');
            }
          }
          assert.deepEqual(p.errors, []);
        } finally { release(); await p.close(); }
      }));
    });
    await check('근접 원화: 실패·지연·이전 장면 응답과 원래 HD 복귀', async () => {
      await Promise.all(['failed', 'slow', 'scene'].map(async kind => {
        const p = await makePage(); p.setDefaultTimeout(30000);
        let release;
        const held = new Promise(resolve => { release = resolve; });
        await p.route('**/naeru-day-close.webp?*', async route => {
          if (kind === 'failed') return route.abort();
          await held;
          await route.fulfill({ path: path.join(repo, 'img/naeru-day-close.webp') });
        });
        try {
          await open(p, 's=autumn&v=day&w=clear&act=approach&ball=0&flit=0&ff=0');
          if (kind === 'scene') {
            await p.click('#settings-open'); await p.selectOption('#setting-band', 'night');
            await p.waitForFunction(() => document.body.dataset.variant === 'night' &&
              document.querySelector('#naeruClose').dataset.status === 'ready');
            release(); await p.waitForTimeout(300);
            assert.match(await p.locator('#naeruClose').getAttribute('src'), /naeru-night-close\.webp/);
            await p.keyboard.press('Escape');
            await p.waitForFunction(() => document.documentElement.dataset.approach === 'close');
            assert.equal(await p.evaluate(() => document.documentElement.dataset.approachArt), 'closeup');
          } else {
            await p.waitForFunction(() => document.documentElement.dataset.approach === 'walking');
            assert.equal(await p.evaluate(() => document.documentElement.dataset.approachArt), 'restored');
            if (kind === 'slow') {
              release();
              await p.waitForFunction(() => document.querySelector('#naeruClose').dataset.status === 'ready');
            }
            await p.waitForFunction(() => document.documentElement.dataset.approach === 'close');
            assert.equal(await p.locator('#naeruHd').evaluate(e => e.style.opacity), '1');
            assert.notEqual(await p.locator('#naeruClose').evaluate(e => e.style.opacity), '1');
          }
          await p.click('#approach-return');
          await p.waitForFunction(() => !document.documentElement.dataset.approach);
          assert.equal(await p.locator('#naeruClose').evaluate(e => e.style.opacity), '0');
          assert.match(await p.locator('#naeruStill').getAttribute('src'), /-hd\.webp/);
          if (kind === 'slow') {
            await playing(p);
            await p.evaluate(() => document.dispatchEvent(new Event('naeru:approach')));
            await p.waitForFunction(() => document.documentElement.dataset.approach === 'close');
            assert.equal(await p.evaluate(() => document.documentElement.dataset.approachArt), 'closeup');
            assert.equal(await p.locator('#naeruClose').evaluate(e => e.style.opacity), '0');
            assert.equal(await p.locator('#naeruCloseRig').evaluate(e => e.style.opacity), '1');
          }
          assert.deepEqual(p.errors, []);
        } finally { release(); await p.close(); }
      }));
    });
    await check('호출 버튼: 실제 몸짓·영상 포즈 대기·안내·탐색 없이 고정·재생 복원', async () => {
      const p = await makePage();
      p.setDefaultTimeout(30000);
      try {
        await open(p, 's=autumn&v=day&w=clear&act=approach&ball=0&flit=0&ff=0');
        await p.waitForFunction(() => document.documentElement.dataset.approach === 'walking');
        await p.click('#approach-return');
        await p.waitForFunction(() => !document.documentElement.dataset.approach);
        await playing(p);
        await p.click('#settings-open');
        // 로컬 서버의 탐색 지원 여부에 기대지 않고 실제 팔 동작까지 재생한다.
        await p.waitForFunction(() => {
          const v = document.querySelector('video.naeru.on');
          return v && !v.paused && !v.seeking && v.currentTime >= 5 && v.currentTime < 7;
        });
        await p.evaluate(() => {
          const v = document.querySelector('video.naeru.on');
          window.approachSeeks = 0;
          v.addEventListener('seeking', () => window.approachSeeks++);
          document.dispatchEvent(new Event('naeru:greet'));
        });
        await p.click('#approach-preview');
        await p.evaluate(() => document.dispatchEvent(new Event('naeru:focus-complete')));
        assert.equal(await p.locator('#settings-panel').evaluate(e => e.open), false);
        assert.equal(await p.locator('#approach-wait').isVisible(), true);
        await p.waitForTimeout(200);
        assert.equal(await p.evaluate(() => naeru.busy), true);
        assert.equal(await p.evaluate(() => document.documentElement.dataset.approach), undefined);
        await p.waitForFunction(() => !naeru.busy && naeru.hold);
        assert.equal(await p.evaluate(() => document.documentElement.dataset.approach), undefined);
        assert.equal(await p.locator('video.naeru.on').evaluate(v => v.paused), false);
        await p.evaluate(() => document.dispatchEvent(new Event('naeru:greet')));
        assert.equal(await p.evaluate(() => naeru.busy), false);
        await shot(p, 'call-waiting-for-pose');
        await p.waitForFunction(() => document.documentElement.dataset.approach === 'walking');
        assert.equal(await p.locator('#approach-wait').isVisible(), false);
        assert.equal(await p.locator('#approach-preview').isEnabled(), false);
        assert.equal(await p.locator('#approach-preview').textContent(), '다가오는 중');
        const frozen = await p.locator('video.naeru.on').evaluate(v => v.currentTime);
        assert(frozen <= 8 / 24 || frozen >= 308 / 24);
        assert.equal(await p.evaluate(() => window.approachSeeks), 0);
        assert.equal(await p.locator('#naeru-act').evaluate(e => e.style.transform), '');
        await p.waitForTimeout(1200);
        assert.equal(await p.locator('video.naeru.on').evaluate(v => v.currentTime), frozen);
        await p.click('#approach-return');
        assert.equal(await p.locator('#approach-preview').textContent(), '돌아가는 중');
        await p.waitForFunction(() => !document.documentElement.dataset.approach);
        await playing(p);
        assert.equal(await p.locator('video.naeru.on').evaluate(v => v.dataset.pauseOwner), undefined);
        assert.equal(await p.evaluate(() => naeru.busy || naeru.hold), false);
        assert.equal(await p.locator('#approach-preview').isEnabled(), true);
        assert.equal(await p.locator('#approach-preview').textContent(), '가까이 와줘');
        assert.deepEqual(p.errors, []);
      } finally { await p.close(); }
    });
    await check('다가오기: 팔·혀 동작 중 숨김·풍경 변경·동작 줄이기·화면 회전·Escape', async () => {
      await Promise.all(['hidden', 'scene', 'reduced', 'resize', 'escape'].map(async kind => {
        const p = await makePage();
        p.setDefaultTimeout(30000);
        try {
          await open(p, 's=autumn&v=day&w=clear&act=approach&ball=0&flit=0&ff=0');
          await p.waitForFunction(() => document.documentElement.dataset.closeMotion === 'playing');
          await p.waitForTimeout(1800);
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
          else {
            await p.keyboard.press('Escape');
            assert.equal(await p.evaluate(() => document.documentElement.dataset.closeMotion), 'playing');
          }
          await p.waitForFunction(() => !document.documentElement.dataset.approach);
          assert.equal(await p.evaluate(() => naeru.busy || naeru.hold), false);
          assert.equal(await p.locator('#naeru-stride').evaluate(e => e.style.transform), '');
          assert(await p.locator('#naeruCloseRig').evaluate(c => c.width === 1 && c.style.opacity === '0'));
          assert.equal(await p.evaluate(() => document.documentElement.dataset.closeMotion), undefined);
          assert.equal(await p.locator('#naeruHd').evaluate(e => e.style.opacity), '0');
          assert.equal(await p.evaluate(() => [...document.querySelectorAll('video.naeru')]
            .every(v => !v.style.opacity)), true);
          assert.equal(await p.locator('#naeru-shadow').evaluate(e => e.style.transform), '');
          assert.equal(await p.locator('#naeru-shadow').evaluate(e =>
            e.style.getPropertyValue('--contact-density')), '1.000');
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
    await check('다가오기: 출발 전 포즈 예약 중 숨김·정지 모드 복구', async () => {
      await Promise.all(['hidden', 'reduced'].map(async kind => {
        const p = await makePage();
        try {
          await open(p, 's=autumn&v=night&w=clear&act=approach&ball=0&flit=0&ff=0');
          await p.waitForFunction(() => document.querySelector('video[data-pause-owner="approach"]') &&
            !document.documentElement.dataset.approach);
          if (kind === 'hidden') {
            await p.evaluate(() => {
              Object.defineProperty(document, 'hidden', { configurable: true, value: true });
              document.dispatchEvent(new Event('visibilitychange'));
            });
          } else await p.emulateMedia({ reducedMotion: 'reduce' });
          await p.waitForFunction(() => !naeru.busy && !naeru.hold &&
            !document.querySelector('video[data-pause-owner="approach"]'));
          assert.equal(await p.evaluate(() => document.documentElement.dataset.approach), undefined);
          if (kind === 'hidden') {
            await p.evaluate(() => {
              Object.defineProperty(document, 'hidden', { configurable: true, value: false });
              document.dispatchEvent(new Event('visibilitychange'));
            });
            await p.waitForFunction(() => document.documentElement.dataset.approach === 'walking');
          } else {
            assert.equal(await p.locator('#naeruStill').evaluate(e => e.classList.contains('on')), true);
          }
          assert.deepEqual(p.errors, []);
        } finally { await p.close(); }
      }));
    });
    await check('호출 버튼: 첫 인사 대기 중 설정을 열어도 클릭 가능', async () => {
      await Promise.all([[1280, 720], [390, 844]].map(async ([width, height]) => {
        const p = await makePage({ viewport: { width, height } });
        p.setDefaultTimeout(30000);
        try {
          await open(p, 's=autumn&v=day&w=clear&act=approach&ball=0&flit=0&ff=0');
          await p.click('#settings-open');
          await p.waitForTimeout(3200);
          assert.equal(await p.evaluate(() => document.documentElement.dataset.approach), undefined);
          await shot(p, `call-startup-${width}`);
          assert.equal(await p.locator('#approach-preview').isEnabled(), true);
          await p.click('#approach-preview');
          assert.equal(await p.locator('#settings-panel').evaluate(e => e.open), false);
          await p.waitForFunction(() => document.documentElement.dataset.approach === 'walking');
          await p.click('#approach-return');
          await p.waitForFunction(() => !document.documentElement.dataset.approach);
          await playing(p);
          assert.equal(await p.evaluate(() => naeru.busy || naeru.hold), false);
          assert.deepEqual(p.errors, []);
        } finally { await p.close(); }
      }));
    });
    await check('호출 버튼: 영상 포즈 대기 중 숨김·정지·풍경 변경 정리', async () => {
      await Promise.all(['hidden', 'reduced', 'scene'].map(async kind => {
        const p = await makePage(); p.setDefaultTimeout(30000);
        try {
          await open(p, 's=autumn&v=day&w=clear&act=approach&ball=0&flit=0&ff=0');
          await p.waitForFunction(() => document.documentElement.dataset.approach === 'walking');
          await p.click('#approach-return');
          await p.waitForFunction(() => !document.documentElement.dataset.approach);
          await playing(p);
          await p.click('#settings-open');
          await p.waitForFunction(() => {
            const v = document.querySelector('video.naeru.on');
            return v && !v.paused && !v.seeking && v.currentTime >= 5 && v.currentTime < 7;
          });
          await p.click('#approach-preview');
          await p.waitForFunction(() => naeru.hold && !naeru.busy &&
            !document.querySelector('video[data-pause-owner="approach"]'));
          assert.equal(await p.locator('#approach-wait').isVisible(), true);
          if (kind === 'hidden') {
            await p.evaluate(() => {
              Object.defineProperty(document, 'hidden', { configurable: true, value: true });
              document.dispatchEvent(new Event('visibilitychange'));
            });
          } else if (kind === 'reduced') await p.emulateMedia({ reducedMotion: 'reduce' });
          else {
            await p.click('#settings-open'); await p.selectOption('#setting-season', 'winter');
            await p.waitForFunction(() => document.documentElement.dataset.season === 'winter');
          }
          await p.waitForFunction(() => !naeru.busy && !naeru.hold);
          assert.equal(await p.locator('#approach-wait').isVisible(), false);
          assert.equal(await p.evaluate(() => document.documentElement.dataset.approach), undefined);
          if (kind === 'hidden') {
            await p.evaluate(() => {
              Object.defineProperty(document, 'hidden', { configurable: true, value: false });
              document.dispatchEvent(new Event('visibilitychange'));
            });
            await playing(p);
            assert.equal(await p.locator('#approach-wait').isVisible(), false);
          }
          assert.deepEqual(p.errors, []);
        } finally { await p.close(); }
      }));
    });
    await check('다가오기: 설정 버튼·중복 요청·집중 완료 예약·장면 제한', async () => {
      const p = await makePage();
      p.setDefaultTimeout(30000); // 요청 시점에 따라 영상 한 루프를 기다린다.
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
      await Promise.all(['s=spring&v=dusk&w=clear',
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
    await check('다가오기: 첫 방문·약 5분·포즈 대기·숨은 탭 방문 누적 방지', async () => {
      const p = await makePage();
      try {
        await p.clock.install({ time: now });
        await p.addInitScript(() => {
          Math.random = () => .5;
          // 가상 시계는 네이티브 영상 시간을 진행시키지 않는다. 이 검사만
          // 포즈 시간을 제어하고 실제 재생·탐색 여부는 별도 검사에서 확인한다.
          window.testPoseTime = .1;
          const time = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'currentTime');
          Object.defineProperty(HTMLMediaElement.prototype, 'currentTime', {
            configurable: true, get() { return window.testPoseTime; }, set: time.set
          });
          // 재생 감시에도 가상 재생을 알린다. 실제 벽시계의 timeupdate를
          // 기다리면 수 분을 건너뛴 검사에서 영상 실패 폴백으로 바뀐다.
          setInterval(() => {
            document.querySelectorAll('video.naeru.on').forEach(v => {
              if (!v.paused) v.dispatchEvent(new Event('timeupdate'));
            });
          }, 200);
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
        await open(p, 's=autumn&v=day&w=clear&ball=0&flit=0&ff=0');
        await p.waitForFunction(() => window.visits.length === 1);
        await p.clock.pauseAt(new Date(await p.evaluate(() => Date.now() + 1000)));
        await p.clock.runFor(15000);
        assert.equal(await p.evaluate(() => document.documentElement.dataset.approach), undefined);
        assert.deepEqual(p.errors, []);
        async function advanceBeforeVisit(startedAt) {
          const elapsed = await p.evaluate(() => performance.now());
          await p.clock.fastForward(Math.max(0, Math.floor(startedAt + 299000 - elapsed)));
        }
        await advanceBeforeVisit(await p.evaluate(() => window.visits[0]));
        assert.equal(await p.evaluate(() => window.visits.length), 1);
        await p.evaluate(() => { window.testPoseTime = 5; naeru.hold = true; });
        await p.clock.runFor(3000);
        assert.equal(await p.evaluate(() => window.visits.length), 1);
        await p.evaluate(() => { naeru.hold = false; });
        await p.clock.runFor(3000);
        assert.equal(await p.evaluate(() => window.visits.length), 1);
        await p.evaluate(() => { window.testPoseTime = .1; });
        await p.clock.runFor(12000);
        assert.equal(await p.evaluate(() => window.visits.length), 2);
        const visits = await p.evaluate(() => window.visits);
        assert(visits[1] - visits[0] >= 305000);
        await p.clock.runFor(3000);
        assert.equal(await p.evaluate(() => document.documentElement.dataset.approach), undefined);
        await advanceBeforeVisit(visits[1]);
        assert.equal(await p.evaluate(() => window.visits.length), 2);
        await p.clock.runFor(12000);
        assert.equal(await p.evaluate(() => window.visits.length), 3);
        await p.evaluate(() => {
          Object.defineProperty(document, 'hidden', { configurable: true, value: true });
          document.dispatchEvent(new Event('visibilitychange'));
        });
        await p.clock.fastForward(600000);
        assert.equal(await p.evaluate(() => window.visits.length), 3);
        const resumedAt = await p.evaluate(() => {
          Object.defineProperty(document, 'hidden', { configurable: true, value: false });
          document.dispatchEvent(new Event('visibilitychange'));
          return performance.now();
        });
        await advanceBeforeVisit(resumedAt);
        assert.equal(await p.evaluate(() => window.visits.length), 3);
        await p.clock.runFor(12000);
        assert.equal(await p.evaluate(() => window.visits.length), 4);
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
