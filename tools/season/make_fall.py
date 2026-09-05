#!/usr/bin/env python3
# 겨울 눈 / 가을 낙엽 타일 텍스처. 비 레이어(rain-far/near.png)와 같은 규격이라
# CSS·애니메이션을 그대로 재사용한다: 512×1024 RGBA, 세로로 굴려도 이어진다.
#
# 이어붙임(seamless)이 핵심 — background-position을 텍스처 높이만큼 굴려서
# 완벽 루프를 만들기 때문에, 가장자리를 넘어가는 알갱이는 반대편에도 같이
# 그려야 한다. paste_wrapped()가 그 일을 한다.
#
#   python3 make_fall.py
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

REPO = Path(__file__).resolve().parent.parent.parent
W, H = 512, 1024
random.seed(20260905)          # 재현 가능하게


def paste_wrapped(canvas, sprite, x, y):
    """가장자리를 넘어가면 반대편에도 같이 붙인다 — 타일 이음매를 없앤다."""
    for dx in (-W, 0, W):
        for dy in (-H, 0, H):
            canvas.alpha_composite(sprite, (int(x + dx), int(y + dy)))


def dot(r, alpha):
    """가장자리로 갈수록 옅어지는 눈송이 한 알."""
    k = 4
    d = int(r * 2 * k)
    im = Image.new("L", (d, d), 0)
    g = ImageDraw.Draw(im)
    steps = 8
    for i in range(steps, 0, -1):
        f = i / steps
        g.ellipse([d / 2 - r * k * f, d / 2 - r * k * f,
                   d / 2 + r * k * f, d / 2 + r * k * f],
                  fill=int(alpha * (1 - f) ** 1.5 + alpha * 0.15))
    im = im.resize((int(r * 2), int(r * 2)), Image.LANCZOS) \
           .filter(ImageFilter.GaussianBlur(0.6))
    out = Image.new("RGBA", im.size, (255, 255, 255, 0))
    out.putalpha(im)
    return out


# 단풍잎 실루엣(정규화 0~1, y는 아래로, 잎끝이 위·잎자루가 아래).
# 물방울 모양은 "갈색 마름모"로 보이고(2026-09-05 제보), 방사형 사인 곡선으로
# 만든 5갈래는 꽃처럼 보인다 — 갈래 사이가 너무 깊어서다. 캐나다 국기식으로
# 갈래를 넓게 잡고 톱니를 얕게 둬야 단풍으로 읽힌다.
MAPLE = [(0.50, 0.02), (0.57, 0.26), (0.70, 0.22), (0.66, 0.38), (0.86, 0.34),
         (0.79, 0.48), (0.96, 0.55), (0.73, 0.60), (0.76, 0.72), (0.59, 0.66),
         (0.60, 0.82), (0.52, 0.76), (0.52, 1.00), (0.48, 1.00), (0.48, 0.76),
         (0.40, 0.82), (0.41, 0.66), (0.24, 0.72), (0.27, 0.60), (0.04, 0.55),
         (0.21, 0.48), (0.14, 0.34), (0.34, 0.38), (0.30, 0.22), (0.43, 0.26)]


def leaf(size, color, angle):
    """단풍잎. 4배로 그린 뒤 줄여서 갈래가 뭉개지지 않게 한다.

    **화면에서 20px 아래로 내려가면 어떤 단풍 윤곽도 별 얼룩이 된다.** 그래서
    물방울 시절보다 크게 쓴다(원경 22~30, 근경 42~58). 잎맥은 28px 이상일 때만
    긋는다 — 작을 땐 잡티로만 보인다."""
    k = 4
    px = int(size * k)
    im = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    g = ImageDraw.Draw(im)
    g.polygon([(x * px, y * px) for x, y in MAPLE], fill=color + (238,))
    if size >= 28:
        vein = (max(0, color[0] - 70), max(0, color[1] - 26), max(0, color[2] - 18), 140)
        for tx, ty in ((0.50, 0.12), (0.80, 0.42), (0.20, 0.42)):
            g.line([(0.50 * px, 0.78 * px), (tx * px, ty * px)],
                   fill=vein, width=max(1, k // 2))
    im = im.rotate(angle, expand=True, resample=Image.BICUBIC)
    return im.resize((max(1, im.width // k), max(1, im.height // k)), Image.LANCZOS)


def build(name, kind, n, lo, hi):
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for _ in range(n):
        x, y = random.uniform(0, W), random.uniform(0, H)
        if kind == "snow":
            r = random.uniform(lo, hi)
            sp = dot(r, random.randint(150, 255))
            paste_wrapped(canvas, sp, x - r, y - r)
        else:
            size = random.uniform(lo, hi)
            # 원화가 탁한 편이라 순색 빨강은 혼자 튄다 — 한 단계 죽인 팔레트
            col = random.choice([(176, 72, 48), (198, 110, 54),
                                 (206, 150, 72), (160, 88, 50)])
            sp = leaf(size, col, random.uniform(0, 360))
            paste_wrapped(canvas, sp, x - sp.width / 2, y - sp.height / 2)
    canvas.save(REPO / "img" / name)
    print(f"  {name}  {n}개")


if __name__ == "__main__":
    # 원경은 작고 촘촘하게, 근경은 크고 성기게 — 비 레이어와 같은 깊이 구성.
    #
    # **개수는 화면에 깔리는 타일 수를 곱해서 생각해야 한다.** background-size를
    # 안 주므로 512×1024 원본 크기로 타일링되고, 1368×770 화면이면 가로 3~4번
    # 반복된다. 낙엽을 타일당 30개 넣었더니 화면에서 색종이가 됐다(2026-09-05).
    build("snow-far.png",  "snow", 60, 1.6, 3.2)     # 화면에 약 240송이
    build("snow-near.png", "snow", 20, 3.4, 6.4)     # 약 80송이
    # 단풍은 갈래가 읽혀야 하므로 크게, 대신 성기게
    build("leaf-far.png",  "leaf", 4,  22.0, 30.0)   # 화면에 약 16장
    build("leaf-near.png", "leaf", 2,  42.0, 58.0)   # 약 8장
