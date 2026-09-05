#!/usr/bin/env python3
# 겨울 눈 타일 텍스처. 비 레이어(rain-far/near.png)와 같은 규격이라
# CSS·애니메이션을 그대로 재사용한다: 512×1024 RGBA, 세로로 굴려도 이어진다.
#
# 이어붙임(seamless)이 핵심 — background-position을 텍스처 높이만큼 굴려서
# 완벽 루프를 만들기 때문에, 가장자리를 넘어가는 알갱이는 반대편에도 같이
# 그려야 한다. paste_wrapped()가 그 일을 한다.
#
# 가을 낙엽도 여기서 만들었지만 2026-09-05에 뺐다 — 배경의 단풍만 남기고
# 하늘에서 내리는 잎은 안 쓴다는 결정. 잎 그림은 tools/season/leaves/에 남아 있다.
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


def build(name, n, lo, hi):
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for _ in range(n):
        x, y = random.uniform(0, W), random.uniform(0, H)
        r = random.uniform(lo, hi)
        sp = dot(r, random.randint(150, 255))
        paste_wrapped(canvas, sp, x - r, y - r)
    canvas.save(REPO / "img" / name)
    print(f"  {name}  {n}개")


if __name__ == "__main__":
    # 원경은 작고 촘촘하게, 근경은 크고 성기게 — 비 레이어와 같은 깊이 구성.
    #
    # **개수는 화면에 깔리는 타일 수를 곱해서 생각해야 한다.** background-size를
    # 안 주므로 512×1024 원본 크기로 타일링되고, 1368×770 화면이면 가로 3~4번
    # 반복된다. 낙엽을 타일당 30개 넣었더니 화면에서 색종이가 됐다(2026-09-05).
    build("snow-far.png",  60, 1.6, 3.2)     # 화면에 약 240송이
    build("snow-near.png", 20, 3.4, 6.4)     # 약 80송이
