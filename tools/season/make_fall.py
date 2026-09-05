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


# 단풍잎은 **그림 파일에서 가져다 쓴다**(tools/season/leaves/). 다각형으로
# 그려 봤지만 물방울은 "갈색 마름모", 방사형 사인 5갈래는 꽃처럼 보였고,
# 무엇보다 **한 종류·단색**이라 단풍으로 안 읽혔다(2026-09-05 제보).
# 지금은 모양과 색이 제각각인 13장을 무작위로 골라 쓴다.
LEAF_DIR = Path(__file__).resolve().parent / "leaves"
_LEAVES = None


def leaf(size, angle):
    """단풍잎 한 장을 골라 크기·각도를 바꿔 돌려준다."""
    global _LEAVES
    if _LEAVES is None:
        _LEAVES = [Image.open(f).convert("RGBA")
                   for f in sorted(LEAF_DIR.glob("leaf*.png"))]
        if not _LEAVES:
            raise SystemExit(f"{LEAF_DIR}에 잎 그림이 없다")
    src = random.choice(_LEAVES)
    k = 3                                     # 3배로 줄였다 돌려서 계단을 없앤다
    n = max(8, int(size * k))
    im = src.resize((n, int(n * src.height / src.width)), Image.LANCZOS)
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
            sp = leaf(random.uniform(lo, hi), random.uniform(0, 360))
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
