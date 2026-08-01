# 여름수련회 오버레이 아트 생성 (3840x2160 SVG -> Edge headless PNG)
# base : 무보정(dusk) 톤 기준으로 그린 본체 — 이후 밴드별 그레이딩 적용
# glow : 밤/노을용 따뜻한 광원(모닥불·랜턴·텐트 불빛) — 알파 합성
import math, sys

W, H = 3840, 2160

# ROPE ----------------------------------------------------------------
# 좌우 나무 줄기에 묶인 밧줄(2차 베지어). x가 t에 선형이라 역산이 쉬움
R0 = (230, 600); R1 = (1920, 1080); R2 = (3610, 660)

def rope_t(x):  return (x - R0[0]) / (R2[0] - R0[0])
def rope_y(x):
    t = rope_t(x); u = 1 - t
    return u * u * R0[1] + 2 * t * u * R1[1] + t * t * R2[1]

# BANNER --------------------------------------------------------------
BX0, BX1 = 1000, 2840          # 현수막 좌우 (u .26 ~ .74)
BH       = 300                 # 천 높이
SAG      = 26                  # 아랫단 추가 처짐

def top_y(x):  return rope_y(x) + 14
def bot_y(x):
    s = math.sin(math.pi * (x - BX0) / (BX1 - BX0))
    return top_y(x) + BH + SAG * s

def edge_path(y_fn, x0, x1, n=26):
    """y_fn을 따라가는 폴리라인(부드러운 곡선용 좌표열)"""
    return [(x0 + (x1 - x0) * i / n, y_fn(x0 + (x1 - x0) * i / n))
            for i in range(n + 1)]

def poly(points):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in points)

def path_of(points, close=True):
    """폴리라인 좌표열 -> path d 문자열"""
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return d + " Z" if close else d


# TENT ----------------------------------------------------------------
def tent(cx, gy, w, h, front, side, ridge, door, shade, guy):
    """A형 텐트 3/4 뷰. cx=바닥 중심, gy=접지선, w=폭, h=높이"""
    ap_f = (cx - .10 * w, gy - h)              # 앞쪽 마룻대 꼭짓점
    ap_b = (cx + .24 * w, gy - .90 * h)        # 뒤쪽 꼭짓점
    fl   = (cx - .46 * w, gy + .01 * h)        # 앞면 좌하단
    fr   = (cx + .14 * w, gy + .02 * h)        # 앞면 우하단
    br   = (cx + .50 * w, gy - .07 * h)        # 측면 우하단
    s = []
    # 접지 그림자
    s.append(f'<ellipse cx="{cx + .02*w:.0f}" cy="{gy + .015*h:.0f}" '
             f'rx="{.52*w:.0f}" ry="{.075*h + 6:.0f}" fill="#2f3826" '
             f'opacity=".26" filter="url(#soft)"/>')
    # 측면(그늘)
    s.append(f'<path d="M{fr[0]:.0f},{fr[1]:.0f} L{ap_f[0]:.0f},{ap_f[1]:.0f} '
             f'L{ap_b[0]:.0f},{ap_b[1]:.0f} L{br[0]:.0f},{br[1]:.0f} Z" '
             f'fill="{side}"/>')
    # 앞면(빛 받는 면) — 천이 살짝 배부르게
    s.append(f'<path d="M{fl[0]:.0f},{fl[1]:.0f} '
             f'Q{cx - .30*w:.0f},{gy - .52*h:.0f} {ap_f[0]:.0f},{ap_f[1]:.0f} '
             f'Q{cx + .05*w:.0f},{gy - .48*h:.0f} {fr[0]:.0f},{fr[1]:.0f} Z" '
             f'fill="{front}"/>')
    # 마룻대
    s.append(f'<path d="M{ap_f[0]:.0f},{ap_f[1]:.0f} L{ap_b[0]:.0f},{ap_b[1]:.0f}" '
             f'stroke="{ridge}" stroke-width="{max(3, w*.016):.0f}" '
             f'stroke-linecap="round" fill="none"/>')
    # 입구(살짝 열린 삼각 + 걷어올린 자락)
    dx, dy = cx - .12 * w, gy
    s.append(f'<path d="M{dx - .13*w:.0f},{dy:.0f} '
             f'Q{dx - .02*w:.0f},{gy - .55*h:.0f} {ap_f[0] + .01*w:.0f},{ap_f[1] + .10*h:.0f} '
             f'Q{dx + .10*w:.0f},{gy - .50*h:.0f} {dx + .12*w:.0f},{dy:.0f} Z" '
             f'fill="{door}"/>')
    s.append(f'<path d="M{dx + .02*w:.0f},{dy:.0f} '
             f'Q{dx + .13*w:.0f},{gy - .40*h:.0f} {dx + .05*w:.0f},{gy - .62*h:.0f} '
             f'Q{dx + .17*w:.0f},{gy - .34*h:.0f} {dx + .15*w:.0f},{dy:.0f} Z" '
             f'fill="{shade}" opacity=".9"/>')
    # 앞면 세로 음영 (마룻대 쪽 밝고 자락 쪽 어둡게)
    s.append(f'<path d="M{fl[0]:.0f},{fl[1]:.0f} '
             f'Q{cx - .30*w:.0f},{gy - .52*h:.0f} {ap_f[0]:.0f},{ap_f[1]:.0f} '
             f'Q{cx + .05*w:.0f},{gy - .48*h:.0f} {fr[0]:.0f},{fr[1]:.0f} Z" '
             f'fill="url(#tentShade)"/>')
    # 자락 접지 그늘
    s.append(f'<path d="M{fl[0]:.0f},{fl[1]:.0f} L{br[0]:.0f},{br[1]:.0f}" '
             f'stroke="#3d3a26" stroke-width="{max(3, h*.035):.0f}" '
             f'opacity=".26" filter="url(#turfBlur)"/>')
    # 석양(우측 광원) 림라이트 — 마룻대와 측면 모서리에만
    s.append(f'<path d="M{ap_f[0]:.0f},{ap_f[1]:.0f} L{ap_b[0]:.0f},{ap_b[1]:.0f} '
             f'L{br[0]:.0f},{br[1]:.0f}" stroke="#f3ddb4" fill="none" '
             f'stroke-width="{max(2, w*.011):.0f}" opacity=".38"/>')
    # 팩줄 2가닥
    s.append(f'<path d="M{ap_f[0]:.0f},{ap_f[1] + .03*h:.0f} '
             f'L{cx - .62*w:.0f},{gy + .03*h:.0f}" stroke="{guy}" '
             f'stroke-width="{max(2, w*.006):.0f}" opacity=".55"/>')
    s.append(f'<path d="M{ap_b[0]:.0f},{ap_b[1] + .03*h:.0f} '
             f'L{cx + .66*w:.0f},{gy - .02*h:.0f}" stroke="{guy}" '
             f'stroke-width="{max(2, w*.006):.0f}" opacity=".5"/>')
    return "\n".join(s)


# GRASS ---------------------------------------------------------------
def rnd(i, seed):
    j = math.sin((i + seed) * 12.9898) * 43758.5453
    return j - math.floor(j)                     # 0~1 의사난수

def grass(cx, base_y, span, hi=52, seed=1.0, blades=True):
    """접지선을 풀 덩어리로 덮어 오브젝트가 잔디에 앉게 만든다.
       낱개 풀잎을 세우면 핀처럼 보여서, 톱니 실루엣 덩어리 + 뾰족한
       잎 몇 개만 얹는다"""
    x0, x1 = cx - span / 2, cx + span / 2
    pts, i, x = [], 0, x0
    while x < x1:                                # 위쪽 톱니 실루엣
        j = rnd(i, seed)
        step = 26 + 34 * j
        pts.append((x, base_y - hi * (.18 + .82 * j * j)))
        pts.append((x + step * .5, base_y - hi * .10 * rnd(i + 40, seed)))
        x += step; i += 1
    d = ("M" + f"{x0:.0f},{base_y + hi*.5:.0f}"
         + "".join(f" L{px:.0f},{py:.0f}" for px, py in pts)
         + f" L{x1:.0f},{base_y + hi*.5:.0f} Z")
    g = [f'<path d="{d}" fill="url(#turf)" opacity=".62" filter="url(#turfBlur)"/>']
    for k in range(6 if blades else 0):          # 튀어나온 잎 몇 개
        j = rnd(k, seed + 3)
        bx = x0 + span * (.08 + .84 * rnd(k + 11, seed))
        hg = hi * (1.0 + 1.1 * j)
        ln = (j - .5) * hg * .9
        g.append(f'<path d="M{bx-5:.0f},{base_y+4:.0f} '
                 f'Q{bx+ln*.35:.0f},{base_y-hg*.6:.0f} {bx+ln:.0f},{base_y-hg:.0f} '
                 f'Q{bx+ln*.3:.0f},{base_y-hg*.55:.0f} {bx+5:.0f},{base_y+4:.0f} Z" '
                 f'fill="#7c7c44" opacity="{.35+.25*j:.2f}"/>')
    return "".join(g)


# POOL ----------------------------------------------------------------
def pool(cx, fy, w, d, h, k=.84):
    """물놀이용 작은 사각 풀장. fy=앞테두리 y, w=앞변 폭, d=안쪽 깊이(원근),
       h=벽 높이, k=뒷변/앞변 비율. 모서리를 살짝 부풀려 공기주입식 느낌"""
    fl, fr = (cx - w / 2, fy), (cx + w / 2, fy)
    bl, br = (cx - w * k / 2, fy - d), (cx + w * k / 2, fy - d)
    bow = w * .022
    # 윗면(수면) 외곽 — 네 변을 살짝 바깥으로 휘게
    top = (f'M{fl[0]:.0f},{fl[1]:.0f} '
           f'Q{cx:.0f},{fy + bow*1.3:.0f} {fr[0]:.0f},{fr[1]:.0f} '
           f'Q{fr[0] + bow*.7:.0f},{fy - d/2:.0f} {br[0]:.0f},{br[1]:.0f} '
           f'Q{cx:.0f},{fy - d - bow:.0f} {bl[0]:.0f},{bl[1]:.0f} '
           f'Q{fl[0] - bow*.7:.0f},{fy - d/2:.0f} {fl[0]:.0f},{fl[1]:.0f} Z')
    o = []
    # 접지 그림자
    o.append(f'<ellipse cx="{cx:.0f}" cy="{fy + h*.86:.0f}" rx="{w*.60:.0f}" '
             f'ry="{h*.55 + d*.16:.0f}" fill="#33381f" opacity=".30" '
             f'filter="url(#soft)"/>')
    # 앞·옆 벽
    o.append(f'<path d="M{fl[0]:.0f},{fl[1]:.0f} '
             f'Q{cx:.0f},{fy + bow*1.3:.0f} {fr[0]:.0f},{fr[1]:.0f} '
             f'L{fr[0] - w*.035:.0f},{fy + h:.0f} '
             f'Q{cx:.0f},{fy + h + bow*.5:.0f} {fl[0] + w*.035:.0f},{fy + h:.0f} Z" '
             f'fill="url(#poolWall)"/>')
    # 벽 아래쪽 그늘
    o.append(f'<path d="M{fl[0] + w*.035:.0f},{fy + h:.0f} '
             f'Q{cx:.0f},{fy + h + bow*.5:.0f} {fr[0] - w*.035:.0f},{fy + h:.0f}" '
             f'stroke="#1d5a7d" stroke-width="{h*.30:.0f}" fill="none" opacity=".45"/>')
    # 수면
    o.append(f'<path d="{top}" fill="url(#poolWater)"/>')
    # 안쪽 그늘(앞벽 안쪽 면)
    o.append(f'<path d="M{bl[0]:.0f},{bl[1]:.0f} '
             f'Q{cx:.0f},{fy - d - bow:.0f} {br[0]:.0f},{br[1]:.0f} '
             f'L{br[0] - w*.03:.0f},{fy - d + h*.42:.0f} '
             f'Q{cx:.0f},{fy - d + h*.30:.0f} {bl[0] + w*.03:.0f},{fy - d + h*.42:.0f} Z" '
             f'fill="#1f5f86" opacity=".35"/>')
    # 물결 하이라이트
    for (px, py, pw, op) in [(-.22, .26, .26, .50), (.18, .46, .22, .40),
                             (-.08, .70, .32, .34), (.26, .18, .14, .36),
                             (-.30, .58, .18, .30)]:
        o.append(f'<path d="M{cx + px*w - pw*w/2:.0f},{fy - d*(1-py):.0f} '
                 f'q{pw*w*.5:.0f},{-d*.10:.0f} {pw*w:.0f},0" stroke="#cdeaf7" '
                 f'stroke-width="{w*.012:.0f}" fill="none" stroke-linecap="round" '
                 f'opacity="{op}"/>')
    # 테두리(공기주입 링)
    o.append(f'<path d="{top}" fill="none" stroke="url(#poolRim)" '
             f'stroke-width="{w*.042:.0f}" stroke-linejoin="round"/>')
    o.append(f'<path d="M{fl[0]:.0f},{fl[1]:.0f} '
             f'Q{cx:.0f},{fy + bow*1.3:.0f} {fr[0]:.0f},{fr[1]:.0f}" fill="none" '
             f'stroke="url(#poolRim)" stroke-width="{w*.052:.0f}" '
             f'stroke-linecap="round"/>')
    o.append(f'<path d="M{fl[0]+w*.03:.0f},{fl[1]-w*.008:.0f} '
             f'Q{cx:.0f},{fy + bow*1.1:.0f} {fr[0]-w*.03:.0f},{fr[1]-w*.008:.0f}" '
             f'fill="none" stroke="#eef7fb" stroke-width="{w*.012:.0f}" '
             f'opacity=".45" stroke-linecap="round"/>')
    # 잔디 위 비치볼
    bx2, by2, br2 = cx - w * .66, fy + h * .82, w * .072
    o.append(f'<ellipse cx="{bx2:.0f}" cy="{by2 + br2*.95:.0f}" rx="{br2*1.0:.0f}" '
             f'ry="{br2*.30:.0f}" fill="#33381f" opacity=".28" filter="url(#soft)"/>')
    o.append(f'<circle cx="{bx2:.0f}" cy="{by2:.0f}" r="{br2:.0f}" fill="#f4ecdb"/>')
    for wi, col in enumerate(["#d9755a", "#5e97b3", "#e0b45f"]):
        a1 = -math.pi / 2 + wi * 2 * math.pi / 3
        a2 = a1 + math.pi / 3
        o.append(f'<path d="M{bx2:.0f},{by2:.0f} '
                 f'L{bx2 + br2*math.cos(a1):.0f},{by2 + br2*math.sin(a1):.0f} '
                 f'A{br2:.0f},{br2:.0f} 0 0 1 '
                 f'{bx2 + br2*math.cos(a2):.0f},{by2 + br2*math.sin(a2):.0f} Z" '
                 f'fill="{col}"/>')
    o.append(f'<circle cx="{bx2:.0f}" cy="{by2:.0f}" r="{br2:.0f}" fill="none" '
             f'stroke="#c9bea6" stroke-width="{br2*.09:.1f}" opacity=".6"/>')
    o.append(f'<circle cx="{bx2 - br2*.34:.0f}" cy="{by2 - br2*.40:.0f}" '
             f'r="{br2*.22:.0f}" fill="#fffaf0" opacity=".7"/>')
    # 튜브 하나 띄우기
    tx, ty, tr = cx - w * .30, fy - d * .46, w * .078
    o.append(f'<ellipse cx="{tx:.0f}" cy="{ty:.0f}" rx="{tr:.0f}" ry="{tr*.52:.0f}" '
             f'fill="none" stroke="#e79b7d" stroke-width="{tr*.46:.0f}"/>')
    o.append(f'<ellipse cx="{tx:.0f}" cy="{ty - tr*.12:.0f}" rx="{tr*.78:.0f}" '
             f'ry="{tr*.30:.0f}" fill="none" stroke="#f6d3bc" '
             f'stroke-width="{tr*.16:.0f}" opacity=".7"/>')
    return "\n".join(o)


# ORNAMENT ------------------------------------------------------------
def pine(x, y, s, fill="#dfe8d4"):
    """현수막 좌우 소나무 장식"""
    return (f'<g transform="translate({x:.0f},{y:.0f}) scale({s})" opacity=".8">'
            f'<path d="M0,-52 L26,-8 L11,-8 L32,26 L15,26 L34,58 L-34,58 '
            f'L-15,26 L-32,26 L-11,-8 L-26,-8 Z" fill="{fill}"/>'
            f'<rect x="-5" y="52" width="10" height="20" fill="{fill}"/></g>')


# LANTERN -------------------------------------------------------------
def lantern(x, drop, s=1.0):
    y = rope_y(x)
    w, h = 62 * s, 84 * s
    ty = y + drop
    return (f'<g>'
            f'<path d="M{x:.0f},{y:.0f} L{x:.0f},{ty:.0f}" stroke="#6b5a48" '
            f'stroke-width="{5*s:.0f}"/>'
            f'<path d="M{x-w*.34:.0f},{ty+h*.08:.0f} L{x+w*.34:.0f},{ty+h*.08:.0f} '
            f'L{x+w*.5:.0f},{ty+h*.62:.0f} L{x+w*.3:.0f},{ty+h:.0f} '
            f'L{x-w*.3:.0f},{ty+h:.0f} L{x-w*.5:.0f},{ty+h*.62:.0f} Z" '
            f'fill="#efd9a6" stroke="#8a7350" stroke-width="{3.4*s:.1f}"/>'
            f'<path d="M{x-w*.34:.0f},{ty+h*.08:.0f} L{x+w*.34:.0f},{ty+h*.08:.0f}" '
            f'stroke="#7a6547" stroke-width="{6*s:.0f}" stroke-linecap="round"/>'
            f'<path d="M{x-w*.3:.0f},{ty+h:.0f} L{x+w*.3:.0f},{ty+h:.0f}" '
            f'stroke="#7a6547" stroke-width="{6*s:.0f}" stroke-linecap="round"/>'
            f'</g>')


# ---------------------------------------------------------------------
DEFS = '''
<defs>
  <linearGradient id="cloth" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0"   stop-color="#4b7a6b"/>
    <stop offset=".45" stop-color="#3b6659"/>
    <stop offset="1"   stop-color="#2b4f45"/>
  </linearGradient>
  <linearGradient id="clothFold" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0"    stop-color="#000" stop-opacity=".16"/>
    <stop offset=".06"  stop-color="#fff" stop-opacity=".05"/>
    <stop offset=".18"  stop-color="#000" stop-opacity=".07"/>
    <stop offset=".33"  stop-color="#fff" stop-opacity=".045"/>
    <stop offset=".5"   stop-color="#000" stop-opacity=".04"/>
    <stop offset=".67"  stop-color="#fff" stop-opacity=".05"/>
    <stop offset=".82"  stop-color="#000" stop-opacity=".07"/>
    <stop offset=".94"  stop-color="#fff" stop-opacity=".04"/>
    <stop offset="1"    stop-color="#000" stop-opacity=".18"/>
  </linearGradient>
  <linearGradient id="poolWater" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0"   stop-color="#b9cbd2"/>
    <stop offset=".16" stop-color="#6ba3bf"/>
    <stop offset=".52" stop-color="#4189ac"/>
    <stop offset="1"   stop-color="#31789e"/>
  </linearGradient>
  <linearGradient id="poolWall" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0"   stop-color="#5296b6"/>
    <stop offset="1"   stop-color="#2e6d8d"/>
  </linearGradient>
  <linearGradient id="poolRim" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0"   stop-color="#cfe2ea"/>
    <stop offset="1"   stop-color="#93b3c2"/>
  </linearGradient>
  <linearGradient id="tentShade" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0"   stop-color="#ffffff" stop-opacity=".10"/>
    <stop offset=".55" stop-color="#000000" stop-opacity="0"/>
    <stop offset="1"   stop-color="#241f14" stop-opacity=".22"/>
  </linearGradient>
  <filter id="turfBlur" x="-30%" y="-80%" width="160%" height="260%">
    <feGaussianBlur stdDeviation="5"/>
  </filter>
  <linearGradient id="turf" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0"   stop-color="#8d8b52"/>
    <stop offset=".55" stop-color="#73723c"/>
    <stop offset="1"   stop-color="#5a5b2e"/>
  </linearGradient>
  <!-- 석양은 화면 중앙~우측에서 온다: 천 오른쪽에 따뜻한 빛 -->
  <linearGradient id="clothLight" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0"   stop-color="#000000" stop-opacity=".10"/>
    <stop offset=".42" stop-color="#ffe6bd" stop-opacity="0"/>
    <stop offset="1"   stop-color="#ffdfae" stop-opacity=".16"/>
  </linearGradient>
  <radialGradient id="fireGlow">
    <stop offset="0"   stop-color="#ffbf6a" stop-opacity=".62"/>
    <stop offset=".28" stop-color="#ff9f45" stop-opacity=".34"/>
    <stop offset=".62" stop-color="#e8762a" stop-opacity=".13"/>
    <stop offset="1"   stop-color="#c85a18" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="lampGlow">
    <stop offset="0"   stop-color="#ffe4ac" stop-opacity=".75"/>
    <stop offset=".35" stop-color="#ffcf82" stop-opacity=".32"/>
    <stop offset="1"   stop-color="#f0a94e" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="tentGlow">
    <stop offset="0"   stop-color="#ffd694" stop-opacity=".55"/>
    <stop offset=".45" stop-color="#f7b563" stop-opacity=".22"/>
    <stop offset="1"   stop-color="#e08c37" stop-opacity="0"/>
  </radialGradient>

  <!-- 붓터치 흔들림: 배경이 회화풍이라 기하학적 직선을 피한다 -->
  <filter id="paint" x="-12%" y="-25%" width="124%" height="150%">
    <feTurbulence type="fractalNoise" baseFrequency="0.0042" numOctaves="3"
                  seed="11" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="11"
                       xChannelSelector="R" yChannelSelector="G"/>
    <feGaussianBlur stdDeviation="1.2"/>
  </filter>
  <filter id="paintS" x="-12%" y="-25%" width="124%" height="150%">
    <feTurbulence type="fractalNoise" baseFrequency="0.006" numOctaves="2"
                  seed="4" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="5"
                       xChannelSelector="R" yChannelSelector="G"/>
    <feGaussianBlur stdDeviation="1.0"/>
  </filter>
  <filter id="soft"  x="-60%" y="-140%" width="220%" height="380%">
    <feGaussianBlur stdDeviation="16"/>
  </filter>
  <filter id="flame" x="-60%" y="-40%" width="220%" height="180%">
    <feTurbulence type="fractalNoise" baseFrequency="0.012" numOctaves="2"
                  seed="3" result="n"/>
    <feDisplacementMap in="SourceGraphic" in2="n" scale="14"
                       xChannelSelector="R" yChannelSelector="G"/>
    <feGaussianBlur stdDeviation="2.4"/>
  </filter>
  <filter id="smoke" x="-90%" y="-40%" width="280%" height="180%">
    <feGaussianBlur stdDeviation="34"/>
  </filter>
  <filter id="glowBlur" x="-70%" y="-70%" width="240%" height="240%">
    <feGaussianBlur stdDeviation="26"/>
  </filter>
</defs>
'''

# 배치 상수 -----------------------------------------------------------
#' 내루미는 배경 영상에 구워진 정지 캐릭터다(미세한 숨쉬기 모션만 있음).
#' 풀장 안에 세우려면 뒤쪽 테두리가 몸통을 가로지르는데, 그 부분을 덮어
#' 그리면 캐릭터가 지워진다. 그래서 풀 레이어(back)의 알파에 내루미
#' 실루엣 구멍을 뚫고(수면선 아래는 뚫지 않음 → 다리는 물에 잠김),
#' 모자·물결처럼 몸 위에 올라가야 하는 것만 front 레이어로 뺀다.
TENT_A  = dict(cx=2690, gy=1706, w=470, h=300)    # 오른쪽 큰 텐트
TENT_B  = dict(cx=1500, gy=1596, w=330, h=212)    # 왼쪽 작은(먼) 텐트
POOL    = dict(cx=2025, fy=1786, w=780, d=246, h=76, k=.80)   # 내루미가 든 풀장
NAERU   = dict(cx=2025, top=1399, hw=150, hcx=1995)           # 머리 기준점
WATER_Y = 1645                                    # 내루미 몸에 걸리는 수면선


def cap(hcx, hy, w, txt="문지은T"):
    """야구모자. hcx=머리 중심 x, hy=챙이 걸리는 y, w=모자 폭.
       내루미가 살짝 왼쪽을 보고 있어 챙도 왼쪽으로"""
    hw = w / 2
    crown_top = hy - w * .44
    return (
        f'<g transform="rotate(-8 {hcx} {hy})" filter="url(#paintS)">'
        # 챙
        f'<path d="M{hcx-hw*.72:.0f},{hy-2:.0f} '
        f'Q{hcx-hw*1.34:.0f},{hy-10:.0f} {hcx-hw*1.58:.0f},{hy+6:.0f} '
        f'Q{hcx-hw*1.22:.0f},{hy+16:.0f} {hcx-hw*.60:.0f},{hy+12:.0f} Z" '
        f'fill="#2b574d"/>'
        f'<path d="M{hcx-hw*1.58:.0f},{hy+6:.0f} '
        f'Q{hcx-hw*1.28:.0f},{hy+26:.0f} {hcx-hw*.60:.0f},{hy+16:.0f}" '
        f'fill="none" stroke="#4a7d70" stroke-width="4" opacity=".7"/>'
        # 크라운
        f'<path d="M{hcx-hw:.0f},{hy+2:.0f} '
        f'Q{hcx-hw*1.03:.0f},{crown_top:.0f} {hcx:.0f},{crown_top-4:.0f} '
        f'Q{hcx+hw*1.03:.0f},{crown_top:.0f} {hcx+hw:.0f},{hy+2:.0f} '
        f'Q{hcx:.0f},{hy+18:.0f} {hcx-hw:.0f},{hy+2:.0f} Z" fill="#f1e8d5"/>'
        # 밑단 밴드
        f'<path d="M{hcx-hw:.0f},{hy+2:.0f} Q{hcx:.0f},{hy+18:.0f} '
        f'{hcx+hw:.0f},{hy+2:.0f} L{hcx+hw*.98:.0f},{hy-8:.0f} '
        f'Q{hcx:.0f},{hy+8:.0f} {hcx-hw*.98:.0f},{hy-8:.0f} Z" fill="#2b574d"/>'
        # 꼭지 단추
        f'<circle cx="{hcx:.0f}" cy="{crown_top-1:.0f}" r="{w*.042:.0f}" '
        f'fill="#2b574d"/>'
        # 글자
        f'<text x="{hcx:.0f}" y="{hy-w*.055:.0f}" text-anchor="middle" '
        f'font-family="Pretendard" font-size="{w*.20:.0f}" font-weight="800" '
        f'letter-spacing="-1" fill="#2b574d">{txt}</text>'
        f'</g>')


def splash(cx, wy, rx):
    """수면선에서 몸통을 감싸는 물결. front 레이어(몸 위)에 올라간다"""
    o = []
    for (k, op, wd) in [(1.00, .48, 8), (1.20, .26, 6), (1.42, .15, 5)]:
        o.append(f'<ellipse cx="{cx:.0f}" cy="{wy + (k-1)*22:.0f}" '
                 f'rx="{rx*k:.0f}" ry="{rx*k*.17:.0f}" fill="none" '
                 f'stroke="#d6ecf6" stroke-width="{wd}" opacity="{op}"/>')
    # 몸통 바로 앞 물결 하이라이트
    o.append(f'<path d="M{cx-rx*.72:.0f},{wy+6:.0f} q{rx*.34:.0f},{-14} '
             f'{rx*.68:.0f},0" stroke="#f0fbff" stroke-width="8" fill="none" '
             f'stroke-linecap="round" opacity=".55"/>')
    # 물방울 몇 개
    for (dx, dy, r) in [(-.86, -.34, 7), (.78, -.26, 6), (-.52, -.52, 5),
                        (.98, -.10, 5)]:
        o.append(f'<circle cx="{cx+rx*dx:.0f}" cy="{wy+rx*dy:.0f}" r="{r}" '
                 f'fill="#e6f4fb" opacity=".7"/>')
    return "".join(o)


def build_back():
    """내루미 뒤에 깔리는 것 전부 — 밧줄·현수막·텐트·풀장"""
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}">', DEFS]

    # ── 밧줄 + 삼각깃발 + 랜턴 + 현수막 ───────────────────────────
    o.append('<g filter="url(#paintS)">')
    o.append(f'<polyline points="{poly(edge_path(rope_y, R0[0], R2[0], 60))}" '
             f'fill="none" stroke="#4e4034" stroke-width="8" opacity=".92"/>')
    o.append(f'<polyline points="{poly(edge_path(lambda x: rope_y(x) - 3.5, R0[0], R2[0], 60))}" '
             f'fill="none" stroke="#8a7660" stroke-width="3" opacity=".55"/>')
    o.append('</g>')

    # 삼각깃발 (현수막 바깥 구간)
    FLAG = ["#ecdfc4", "#d99e80", "#93ae8c", "#e2c17e", "#cbd6da", "#e0b0a0"]
    o.append('<g filter="url(#paintS)">')
    k = 0
    for x0, x1 in ((330, 960), (2890, 3520)):
        x = x0
        while x <= x1:
            y = rope_y(x)
            c = FLAG[k % len(FLAG)]
            tilt = (-1) ** k * 2.4
            o.append(f'<g transform="rotate({tilt} {x:.0f} {y:.0f})">'
                     f'<path d="M{x-44:.0f},{y+2:.0f} L{x+44:.0f},{y+2:.0f} '
                     f'L{x:.0f},{y+128:.0f} Z" fill="{c}" opacity=".93"/>'
                     f'<path d="M{x-44:.0f},{y+2:.0f} L{x+44:.0f},{y+2:.0f} '
                     f'L{x+30:.0f},{y+22:.0f} L{x-30:.0f},{y+22:.0f} Z" '
                     f'fill="#000" opacity=".10"/></g>')
            k += 1
            x += 112
    o.append('</g>')

    for lx in (900, 2946):
        o.append(lantern(lx, 96))

    # 현수막 천
    top = edge_path(top_y, BX0, BX1, 40)
    bot = edge_path(bot_y, BX0, BX1, 40)
    cloth = path_of(top + list(reversed(bot)))
    o.append('<g filter="url(#paint)">')
    o.append(f'<path d="{cloth}" fill="url(#cloth)"/>')
    o.append(f'<path d="{cloth}" fill="url(#clothFold)"/>')
    o.append(f'<path d="{cloth}" fill="url(#clothLight)"/>')
    o.append(f'<polyline points="{poly(edge_path(lambda x: top_y(x) + 20, BX0, BX1, 40))}" '
             f'fill="none" stroke="#e7dcc2" stroke-width="13" opacity=".92"/>')
    o.append(f'<polyline points="{poly(edge_path(lambda x: bot_y(x) - 20, BX0, BX1, 40))}" '
             f'fill="none" stroke="#e7dcc2" stroke-width="13" opacity=".92"/>')
    o.append(f'<polyline points="{poly(edge_path(lambda x: top_y(x) + 44, BX0, BX1, 40))}" '
             f'fill="none" stroke="#e0a45c" stroke-width="5" opacity=".8"/>')
    o.append(f'<polyline points="{poly(edge_path(lambda x: bot_y(x) - 44, BX0, BX1, 40))}" '
             f'fill="none" stroke="#e0a45c" stroke-width="5" opacity=".8"/>')
    o.append('</g>')

    # 천을 밧줄에 묶은 고리
    for i in range(9):
        x = BX0 + (BX1 - BX0) * i / 8
        y0, y1 = rope_y(x), top_y(x) + 26
        o.append(f'<path d="M{x:.0f},{y0-6:.0f} Q{x+9:.0f},{(y0+y1)/2:.0f} '
                 f'{x:.0f},{y1:.0f}" stroke="#cdbfa4" stroke-width="6" '
                 f'fill="none" opacity=".8"/>')

    # 글자
    cy = (top_y(1920) + bot_y(1920)) / 2
    o.append(
        f'<g font-family="Pretendard" text-anchor="middle" '
        f'fill="#f7f0dd" filter="url(#paintS)">'
        f'<text x="1920" y="{cy-72:.0f}" font-size="62" font-weight="600" '
        f'letter-spacing="14" fill="#ecd9ae">2026 신덕수양관</text>'
        f'<text x="1920" y="{cy+108:.0f}" font-size="158" font-weight="800" '
        f'letter-spacing="10">여름수련회</text>'
        f'</g>')
    o.append('<g filter="url(#paintS)">')
    for sx in (1210, 2630):
        o.append(pine(sx, (top_y(sx) + bot_y(sx)) / 2 - 10, 0.92))
    o.append('</g>')

    # ── 텐트 ──────────────────────────────────────────────────────
    o.append('<g filter="url(#paint)">')
    o.append(tent(front="#cbab7c", side="#b18f61", ridge="#7b6343",
                  door="#5d4b34", shade="#b99a6e", guy="#9c8b6f", **TENT_A))
    o.append('</g>')
    o.append(grass(TENT_A["cx"] + 10, TENT_A["gy"] + 10, TENT_A["w"] * 1.16,
                   hi=54, seed=3.1))
    o.append('<g filter="url(#paint)" opacity=".93">')
    o.append(tent(front="#b6c2c0", side="#9aa9a8", ridge="#6f7c7b",
                  door="#5a6462", shade="#a7b3b2", guy="#8f9a97", **TENT_B))
    o.append('</g>')
    o.append(grass(TENT_B["cx"] + 6, TENT_B["gy"] + 8, TENT_B["w"] * 1.16,
                   hi=36, seed=7.7))

    # ── 풀장 (내루미가 이 안에 서 있다) ───────────────────────────
    o.append(pool(**POOL))
    o.append(grass(POOL["cx"], POOL["fy"] + POOL["h"] * 1.22,
                   POOL["w"] * 1.06, hi=26, seed=5.3, blades=False))

    o.append('</svg>')
    return "\n".join(o)


def build_front():
    """내루미 위에 올라가는 것 — 모자와 수면선 물결"""
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}">', DEFS]
    o.append(splash(NAERU["cx"], WATER_Y, 168))
    o.append(cap(NAERU["hcx"], NAERU["top"] + 18, NAERU["hw"] * 1.02))
    o.append('</svg>')
    return "\n".join(o)


if __name__ == "__main__":
    which = sys.argv[1]
    out = build_back() if which == "back" else build_front()
    body = ('<style>html,body{margin:0;padding:0;background:transparent;'
            'overflow:hidden}svg{display:block}</style>\n' + out)
    open(sys.argv[2], "w").write(body)
    print("wrote", sys.argv[2], len(body), "bytes")
