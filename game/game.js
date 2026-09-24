/* ── 들판 산책 ────────────────────────────────────────────────────
   index.html이 첫 방향키나 첫 들판 탭에서 불러온다. 페이지를 옮기지 않고
   지금 화면의 배경·영상·그림자를 그대로 쓴다. 방향키로 들판을 걷고(위·아래는
   들판의 안쪽·앞쪽), 스페이스로 점프한다. 터치에서는 누른 곳으로 걸어가고
   끌면 손가락을 따라오며, 내루미를 누르면 점프한다. 30초 동안 입력이 없으면
   처음 자리로 걸어 돌아가며 카메라도 원래 화면으로 물러나고, 그대로
   시작페이지가 된다.

   겹의 소유: #naeru-approach=들판 위치·원근 크기 / #naeru-stride=걸음 /
   #naeru-move=점프 높이 / #naeru-act=도약·착지의 눌림 / #naeru-face=방향.
   진행 중에는 index의 몸짓·공·나비·다가오기를 naeru:game으로 멈춘다.
   그 동작들의 정리 코드가 탭 전환 등에서 다시 돌 수 있으므로 매 프레임
   자기 겹을 다시 쓴다. */
(function () {
  "use strict";
  if (window.naeruGame) return;

  var root = document.documentElement;
  function byId(id) { return document.getElementById(id); }
  var move = byId("naeru-move"), approach = byId("naeru-approach");
  var stride = byId("naeru-stride"), act = byId("naeru-act"), face = byId("naeru-face");
  var panel = byId("settings-panel"), greeting = byId("greeting");
  var message = byId("scene-message");
  if (!move || !approach || !stride || !act || !face) return;

  // 좌표 계약(tools/naeru-split/coords.py): 원본 3840×2160, 크롭 576×496,
  // 발끝 (2020,1720). 위치는 발끝의 프레임 비율로 다룬다.
  var CROP_W = 576 / 3840, CROP_H = 496 / 2160;
  var HOME_X = 2020 / 3840, HOME_Y = 1720 / 2160;
  var FOOT_V = (1720 - 1328) / 496;          // 크롭 안 발끝 높이
  var BODY_V = 0.5;                           // 카메라가 따라가는 몸 중심
  // 지평선에 가까울수록 작게. 저해상도 영상을 과하게 키우지 않도록 앞쪽을 제한한다.
  // 봄·여름은 좌우 앞꽃이 배경에 그려져 있어 그 위로 올라서지 않게 가장자리를 비운다.
  var HORIZON = 0.63, FAR = 0.755, NEAR = 0.835, LEFT = 0.2, RIGHT = 0.86;
  // 산책 중 카메라 확대 — 좌우로 스크롤할 여백. 세로 화면은 이미 좌우가 잘려 있어
  // 확대하지 않아도 여백이 충분하므로 1로 둔다.
  var ZOOM = 1.3;
  var IDLE_MS = 30000;
  var SPEED_X = 0.15, SPEED_Y = 0.05;         // 프레임 비율/초(원래 크기 기준)
  var STEP_HZ = 3.2;
  // 점프 높이는 크롭 높이의 %. 봉우리 = v²/2g
  var GRAVITY = 560, JUMP_V = 165, TURN_V = 72, FLIP_AT = 2.5;

  var style = document.createElement("style");
  style.textContent =
    // 배경·풍경·내루미·앞풀·반딧불이를 같은 값으로 옮겨야 서로 어긋나지 않는다.
    // 모두 화면 중앙이 중심인 상자라 같은 transform이 같은 점을 가리킨다.
    "html[data-game] :is(.bg-still, .bg-layer, #skyMotion, #landscape, #stage," +
    " #foreground, #glow) { transform: var(--game-camera, none); }" +
    // 화면 크기 배경은 cover로 잘린 부분을 그리지 않아, 옮기면 빈 띠가 드러난다.
    // 산책 중에는 같은 16:9 프레임 상자로 바꾼다. 비율이 같아 정지 화면은 그대로다.
    "html[data-game] :is(.bg-still, .bg-layer, #skyMotion) { inset: auto;" +
    " left: var(--game-frame-left); top: var(--game-frame-top);" +
    " width: var(--game-frame-width); height: var(--game-frame-height); }" +
    ".clock-wrap, #settings-open { transition: opacity 1.2s ease; }" +
    "html[data-game=play] .clock-wrap { opacity: .18; }" +
    "html[data-game=play] #settings-open { opacity: .2; }" +
    // 산책 중 탭·끌기가 확대·당겨서 새로고침·길게 누르기 메뉴로 새지 않게 한다.
    // 설정 창은 main 밖이라 스크롤을 그대로 쓴다.
    "html[data-game] :is(main, .bg-still, #naeru-touch) { touch-action: none; }" +
    "html[data-game] body { -webkit-user-select: none; user-select: none;" +
    " -webkit-touch-callout: none; }";
  document.head.appendChild(style);

  var keys = new Set(), active = false, phase = "", frame = 0, last = 0;
  var x = HOME_X, y = HOME_Y, up = 0, vu = 0, facing = 1, wantFace = 0;
  var beat = 0, walk = 0, lean = 0, lead = 0, lastInput = 0;
  var camX = 0, camY = 0, zoom = 1;
  var takeoffAt = -1e9, takeoffForce = 0, landAt = -1e9, landForce = 0;
  var blendUntil = 0, leaping = false;
  var goal = null, dragId = null;             // 터치로 정한 발끝 목표, 끌고 있는 손가락
  var frameGeo = "";

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function depth(fy) { return (fy - HORIZON) / (HOME_Y - HORIZON); }
  function isArrow(key) { return /^Arrow(Up|Down|Left|Right)$/.test(key); }
  function isSpace(e) { return e.key === " " || e.code === "Space"; }
  function formField(el) {
    return el && /^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName);
  }
  function frameBox() {
    var vw = innerWidth, vh = innerHeight, W, H;
    if (vw / vh >= 16 / 9) { W = vw; H = vw * 9 / 16; } else { H = vh; W = vh * 16 / 9; }
    return { vw: vw, vh: vh, W: W, H: H, L: (vw - W) / 2, T: (vh - H) / 2 };
  }
  function setFrame(b) {
    var geo = [b.L, b.T, b.W, b.H].join();
    if (geo === frameGeo) return;
    frameGeo = geo;
    root.style.setProperty("--game-frame-left", b.L + "px");
    root.style.setProperty("--game-frame-top", b.T + "px");
    root.style.setProperty("--game-frame-width", b.W + "px");
    root.style.setProperty("--game-frame-height", b.H + "px");
  }
  // 누른 화면 위치를 카메라 역변환으로 들판의 발끝 좌표로 바꾼다.
  // 하늘이나 가장자리를 누르면 가장 가까운 들판 지점으로 간다.
  function toField(cx, cy) {
    var b = frameBox(), mx = b.vw / 2, my = b.vh / 2;
    var px = mx + (cx - mx - camX) / zoom, py = my + (cy - my - camY) / zoom;
    return { x: clamp((px - b.L) / b.W, LEFT, RIGHT), y: clamp((py - b.T) / b.H, FAR, NEAR) };
  }
  // 목표 발끝까지 같은 속도로 곧장 걷는다. 이번 프레임에 닿으면 그 자리에 두고 null.
  function seek(gx, gy, sc, dt) {
    var ax = (gx - x) / SPEED_X, ay = (gy - y) / SPEED_Y, left = Math.hypot(ax, ay);
    if (left <= sc * dt) { x = gx; y = gy; return null; }
    return [ax / left, ay / left];
  }
  function canStart() {
    return !active && !window.naeruReduced() && !document.hidden &&
           root.dataset.sceneReady === "true" && !root.dataset.approach && !panel.open;
  }
  function claim() {
    // 멈춰 둔 동작들이 정리하며 풀어 둔 값을 다시 잡는다. 인사 클릭도 막는다.
    if (window.naeru) { window.naeru.busy = true; window.naeru.hold = true; }
  }

  function start(touch) {
    // 정리 코드가 지우기 전의 자세를 기억해 두었다가 이어받는다.
    var moveT = move.style.transform, actT = act.style.transform;
    var flipped = /scaleX\(-1\)/.test(face.style.transform);
    setFrame(frameBox());                       // 배경 상자를 바꾸기 전에 치수부터
    active = true; phase = "play"; root.dataset.game = "play";
    document.dispatchEvent(new Event("naeru:game"));
    claim();
    var lifted = /translateY\((-?[\d.]+)%\)/.exec(moveT || "");
    up = lifted ? Math.max(0, -Number(lifted[1])) : 0; vu = 0;  // 공중이면 그대로 떨어진다
    facing = flipped ? -1 : 1; wantFace = 0;
    face.style.transform = flipped ? "scaleX(-1)" : "";
    if (actT) {
      // 하던 몸짓은 뚝 끊지 않고 짧게 풀어 준다.
      act.style.transform = actT; act.style.transition = "transform .25s ease-out";
      blendUntil = performance.now() + 300;
      requestAnimationFrame(function () { act.style.transform = ""; });
    }
    x = HOME_X; y = HOME_Y; leaping = false; beat = 0; walk = 0; lean = 0; lead = 0;
    camX = camY = 0; zoom = 1; lastInput = performance.now();
    if (greeting) greeting.hidden = true;
    goal = null; dragId = null;
    if (message) message.textContent = touch
      ? "들판을 산책해요. 가고 싶은 곳을 누르고, 내루미를 누르면 뛰어요."
      : "들판을 산책해요. 방향키로 걷고 스페이스로 뛰어요.";
    last = performance.now();
    frame = requestAnimationFrame(step);
  }

  function finish() {
    cancelAnimationFrame(frame);
    active = false; phase = ""; keys.clear(); goal = null; dragId = null;
    approach.style.transform = ""; stride.style.transform = "";
    move.style.transform = ""; act.style.transform = ""; act.style.transition = "";
    face.style.transform = "";
    if (window.naeruShadow) { window.naeruShadow.travel(""); window.naeruShadow.lift(0); }
    root.style.removeProperty("--game-camera");
    if (window.naeru) { window.naeru.busy = false; window.naeru.hold = false; }
    delete root.dataset.game;
    ["left", "top", "width", "height"].forEach(function (k) {
      root.style.removeProperty("--game-frame-" + k);
    });
    frameGeo = "";
    // 멈춰 둔 몸짓·공·나비·다가오기를 새로 시작한다. 다음 방문도 여기서 새로 센다.
    document.dispatchEvent(new Event("naeru:game"));
  }

  // 돌기 위한 작은 폴짝 중에도 점프는 받는다. 큰 점프 중의 연타만 무시한다.
  function jump() {
    if (leaping) return;
    leaping = true; vu = JUMP_V; takeoff(performance.now(), 1);
  }
  function takeoff(now, force) { takeoffAt = now; takeoffForce = force; }
  function goBack() {
    phase = "returning"; root.dataset.game = "returning"; goal = null;
  }
  function resume() {
    phase = "play"; root.dataset.game = "play";
  }

  function step(now) {
    var dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    if (!active) return;
    // 산책 도중 움직임 줄이기가 켜지면 애니메이션 없이 바로 제자리로 둔다.
    if (window.naeruReduced()) { finish(); return; }
    claim();

    var ix = 0, iy = 0, sc = depth(y), dir;
    if (phase === "play") {
      ix = (keys.has("ArrowRight") ? 1 : 0) - (keys.has("ArrowLeft") ? 1 : 0);
      iy = (keys.has("ArrowDown") ? 1 : 0) - (keys.has("ArrowUp") ? 1 : 0);
      if (ix || iy) {
        // 방향키가 들어오면 터치 목표보다 우선한다.
        lastInput = now; goal = null;
        if (ix && iy) { ix *= Math.SQRT1_2; iy *= Math.SQRT1_2; }
      } else if (goal) {
        dir = seek(goal.x, goal.y, sc, dt);
        if (dir) { ix = dir[0]; iy = dir[1]; } else goal = null;
      }
      if (now - lastInput >= IDLE_MS && up === 0 && vu === 0) goBack();
    }
    if (phase === "returning") {
      // 처음 자리로 곧장 걷는다. 도착하면 원래 방향을 보도록 공중에서 돈다.
      dir = seek(HOME_X, HOME_Y, sc, dt);
      if (dir) { ix = dir[0]; iy = dir[1]; } else if (facing !== 1) wantFace = 1;
    }

    var ox = x, oy = y;
    x = clamp(x + SPEED_X * sc * ix * dt, LEFT, RIGHT);
    y = clamp(y + SPEED_Y * sc * iy * dt, FAR, NEAR);
    sc = depth(y);
    var moving = Math.abs(x - ox) + Math.abs(y - oy) > 1e-6;

    // 방향 전환은 공중에서만 한다. 땅에 있으면 작게 폴짝 뛰어 돈다.
    // 거의 세로로만 걸을 때 좌우 성분이 조금 섞여도 돌지 않게 한다.
    if (Math.abs(ix) > 0.2) wantFace = ix < 0 ? 1 : -1;
    if (wantFace === facing) wantFace = 0;
    var grounded = up === 0 && vu === 0;
    if (wantFace && grounded) { vu = TURN_V; takeoff(now, 0.4); }
    if (up > 0 || vu > 0) {
      vu -= GRAVITY * dt; up += vu * dt;
      if (wantFace && up >= FLIP_AT) { facing = wantFace; wantFace = 0; }
      if (up <= 0) {
        landForce = clamp(-vu / JUMP_V, 0, 1); up = 0; vu = 0; leaping = false;
        if (landForce > 0.2) landAt = now;
      }
    }

    // 걸음: 발을 딛는 박자마다 좌우로 기울고 살짝 뜬다. 멈추면 부드럽게 줄인다.
    var target = moving && up === 0 ? 1 : 0;
    walk += (target - walk) * (1 - Math.exp(-dt * 10));
    if (walk < 0.01 && !target) { walk = 0; beat = 0; }
    else beat += dt * STEP_HZ;
    lean += ((moving ? ix : 0) - lean) * (1 - Math.exp(-dt * 6));
    var sway = Math.sin(beat * Math.PI) * walk;
    var lift = Math.pow(Math.sin(beat * Math.PI), 2) * walk;

    var place = "translate(" + ((x - HOME_X) / CROP_W * 100).toFixed(3) + "%," +
      ((y - HOME_Y) / CROP_H * 100).toFixed(3) + "%) scale(" + sc.toFixed(4) + ")";
    approach.style.transform = place;
    stride.style.transform = "translate(" + (sway * 0.9).toFixed(3) + "%," +
      (-lift * 2.4).toFixed(3) + "%) rotate(" + (sway * 2 + lean * 1.6).toFixed(3) +
      "deg) scaleY(" + (1 - lift * 0.015).toFixed(4) + ")";
    // 점프 높이는 원근 크기를 따라간다. #naeru-move는 크기 겹 바깥이다.
    move.style.transform = up > 0 ? "translateY(" + (-up * sc).toFixed(3) + "%)" : "";
    face.style.transform = facing < 0 ? "scaleX(-1)" : "";
    if (window.naeruShadow) {
      window.naeruShadow.travel(place);
      window.naeruShadow.lift(Math.max(up / 26, lift * 0.4));
    }
    if (now > blendUntil) {
      act.style.transition = "";
      act.style.transform = squash(now);
    }

    camera(dt, sc);

    if (phase === "returning" && x === HOME_X && y === HOME_Y && facing === 1 &&
        !wantFace && up === 0 && walk === 0 &&
        Math.abs(zoom - 1) < 0.001 && Math.abs(camX) < 0.3 && Math.abs(camY) < 0.3) {
      finish(); return;
    }
    frame = requestAnimationFrame(step);
  }

  // 도약할 때 늘고, 착지할 때 눌린다. 기준점이 발끝이라 발은 땅에 붙어 있다.
  function squash(now) {
    var t = (now - takeoffAt) / 180;
    if (t >= 0 && t < 1 && (up > 0 || vu > 0)) {
      var k = (1 - t) * takeoffForce;
      return "scale(" + (1 - 0.05 * k).toFixed(4) + "," + (1 + 0.07 * k).toFixed(4) + ")";
    }
    t = (now - landAt) / 200;
    if (t >= 0 && t < 1) {
      var s = Math.sin(t * Math.PI) * landForce;
      return "scale(" + (1 + 0.07 * s).toFixed(4) + "," + (1 - 0.08 * s).toFixed(4) + ")";
    }
    return "";
  }

  /* 카메라: 확대한 채 몸을 따라가되 배경 끝이 보이지 않게 가둔다. 점프는
     따라 올라가지 않는다. 돌아갈 때는 원래 화면(확대 1, 이동 0)으로 물러난다. */
  function camera(dt, sc) {
    var b = frameBox(), vw = b.vw, vh = b.vh, W = b.W, H = b.H;
    setFrame(b);
    var returning = phase === "returning";
    var zoomTo = returning || vw < vh ? 1 : ZOOM;
    zoom += (zoomTo - zoom) * (1 - Math.exp(-dt * (returning ? 1.6 : 2.2)));
    if (Math.abs(zoom - 1) < 0.0005 && returning) zoom = 1;
    lead += (-facing * 0.05 * W - lead) * (1 - Math.exp(-dt * 1.5));
    var tx = 0, ty = 0;
    if (!returning) {
      var fx = (vw - W) / 2 + x * W + lead;
      var fy = (vh - H) / 2 + (y - (FOOT_V - BODY_V) * CROP_H * sc) * H;
      tx = -(fx - vw / 2) * zoom; ty = -(fy - vh / 2) * zoom;
    }
    var k = 1 - Math.exp(-dt * (returning ? 2 : 3.5));
    camX += (tx - camX) * k; camY += (ty - camY) * k;
    var mx = Math.max(0, (W * zoom - vw) / 2), my = Math.max(0, (H * zoom - vh) / 2);
    camX = clamp(camX, -mx, mx); camY = clamp(camY, -my, my);
    if (returning && Math.abs(camX) < 0.3 && Math.abs(camY) < 0.3 && zoom === 1) camX = camY = 0;
    if (zoom === 1 && !camX && !camY) root.style.removeProperty("--game-camera");
    else root.style.setProperty("--game-camera", "translate(" + camX.toFixed(2) + "px," +
      camY.toFixed(2) + "px) scale(" + zoom.toFixed(5) + ")");
  }

  document.addEventListener("keydown", function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    var arrow = isArrow(e.key), space = isSpace(e);
    if (!arrow && !space) return;
    if (panel.open || formField(e.target)) return;
    if (!active) {
      if (arrow && canStart()) { e.preventDefault(); keys.add(e.key); start(); }
      return;
    }
    // 포커스된 버튼이 스페이스로 눌리거나 화면이 스크롤되지 않게 한다.
    e.preventDefault();
    lastInput = performance.now();
    if (phase === "returning") resume();
    if (arrow) keys.add(e.key);
    else if (!e.repeat) jump();
  });
  document.addEventListener("keyup", function (e) { keys.delete(e.key); });

  // 터치·펜만 받는다. 데스크톱 마우스 클릭은 기존 시작페이지 동작을 유지한다.
  // 멈춰 있을 때의 내루미 탭은 기존 인사로 두고, 산책 중에는 점프가 된다.
  document.addEventListener("pointerdown", function (e) {
    if (e.pointerType === "mouse" || !e.isPrimary || panel.open) return;
    var naeru = e.target.closest("#naeru-touch");
    if (!naeru && e.target.closest("button, a, input, select, dialog, .scene-ui")) return;
    if (!active) {
      if (naeru || !canStart()) return;
      start(true);
    }
    lastInput = performance.now();
    if (phase === "returning") resume();
    if (naeru) { jump(); return; }
    goal = toField(e.clientX, e.clientY); dragId = e.pointerId;
  });
  document.addEventListener("pointermove", function (e) {
    if (!active || e.pointerId !== dragId || phase !== "play") return;
    lastInput = performance.now(); goal = toField(e.clientX, e.clientY);
  });
  function release(e) { if (e.pointerId === dragId) dragId = null; }
  document.addEventListener("pointerup", release);
  document.addEventListener("pointercancel", release);
  // 첫 탭은 산책 전에 시작돼 touch-action이 아직 기본값이다. 끄는 동안 화면이
  // 당겨지지 않게 막는다. 설정 창이 열려 있으면 그 스크롤을 그대로 둔다.
  document.addEventListener("touchmove", function (e) {
    if (active && !panel.open && e.cancelable) e.preventDefault();
  }, { passive: false });
  addEventListener("blur", function () { keys.clear(); });
  document.addEventListener("visibilitychange", function () { if (document.hidden) keys.clear(); });

  window.naeruGame = {
    // 로더가 불러오는 동안 누르고 있던 방향키와 첫 탭 위치를 넘겨받는다.
    boot: function (held, tap) {
      if (!canStart()) return;
      held.forEach(function (key) { if (isArrow(key)) keys.add(key); });
      start(Boolean(tap));
      if (tap) { goal = toField(tap.x, tap.y); dragId = tap.id; }
    },
    get active() { return active; }
  };
})();
