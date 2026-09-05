#!/usr/bin/env python3
# 계절별 배경 정지본 32장을 굽는다 (8변형 × 4계절).
#
#   img/bg-<변형>.jpg          원본(여름·맑음 톤). **파이프라인 입력이며 런타임엔
#                              안 쓴다** — 여기서 32장을 만들어 내는 재료다.
#   img/bg-<변형>-<계절>.jpg    런타임이 쓰는 것
#
# 왜 색보정만으로 안 되나(2026-09-05 제보) —
#   · 가을: 초록을 노랑으로 미는 것만으로는 **나무가 올리브색**에 머문다.
#     단풍이 들려면 잎의 색상 자체를 빨강·주황으로 옮겨야 한다.
#   · 겨울: 채도를 빼면 "빛바랜 여름"이지 눈 덮인 겨울이 아니다. 들판과 나무에
#     **눈을 실제로 얹어야** 한다.
#   · 비·눈이 올 땐 하늘이 먹구름이어야 한다. 기존 -rain 보정은 전체를 어둡게만
#     할 뿐 하늘은 그대로 뭉게구름이다.
#
# 마스크는 **bg-day.jpg 한 장에서만** 만들어 8변형이 공유한다. 8변형은 같은
# 그림의 색보정본이라 형태가 픽셀 단위로 같고, 밤 변형은 대비가 낮아 따로
# 만들면 마스크가 무너진다(누끼 감사에서 겪은 것과 같은 함정).
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
IMG = REPO / "img"
sys.path.insert(0, str(REPO / "tools" / "naeru-split"))
from coords import VARIANTS

SEASONS = ["spring", "summer", "autumn", "winter"]
HORIZON = 1290

# ffmpeg 색보정 체인. selectivecolor의 부호에 주의 — 초록을 노랑 쪽으로 밀려면
# **시안을 빼야** 한다(더하면 더 초록이 된다).
CHAINS = {
    "spring": "selectivecolor=greens=-0.22 -0.10 0.24 -0.05:"
              "yellows=-0.05 -0.05 0.14 -0.03,"
              "eq=saturation=1.12:brightness=.03:gamma=1.03,"
              "vibrance=intensity=.16:gbal=1.6",
    "summer": None,
    # cyans는 건드리지 않는다 — 하늘이 시안이라 같이 덥혀져 한낮이 노을이 된다
    "autumn": "selectivecolor=greens=-0.85 0.34 0.95 0.05:"
              "yellows=-0.22 0.18 0.45 0.02,"
              "colortemperature=4400:mix=.28,eq=saturation=1.10:gamma=1.01",
    "winter": "selectivecolor=greens=-0.06 0.02 -0.10 0.06:"
              "yellows=-0.08 0 -0.12 0.05,"
              "eq=saturation=.42:brightness=.045:contrast=.94,"
              "colorbalance=bs=.10:bm=.07:bh=.05:rs=-.05:rm=-.04:rh=-.03,"
              "curves=all='0/0.07 0.5/0.57 1/1'",
}


def blur(m, r):
    return np.asarray(Image.fromarray(np.clip(m * 255, 0, 255).astype(np.uint8))
                      .filter(ImageFilter.GaussianBlur(r)), np.float32) / 255


def ramp(v, lo, hi):
    return np.clip((v - lo) / (hi - lo), 0, 1)


def build_masks():
    """하늘 / 나무 / 초원. 이 그림은 채색이 탁해서 색상만으론 못 가른다 —
    밝기(하늘 166~199, 나무 79~117, 초원 107~160)와 높이를 같이 쓴다."""
    a = np.asarray(Image.open(IMG / "bg-day.jpg").convert("RGB"), np.float32)
    L = a.mean(2)
    H, W = L.shape
    g = a[..., 1] - np.maximum(a[..., 0], a[..., 2])
    yy = np.arange(H)[:, None] * np.ones((1, W), np.float32)
    sky = blur(ramp(L, 120, 150) * (1 - ramp(yy, HORIZON - 90, HORIZON + 60)), 8)
    tree = blur(ramp(132 - L, 0, 22) * (1 - ramp(yy, 1500, 1680)), 5)
    return L, yy, sky, tree, (H, W)


def hsv_recolor(a, mask, hue, sat_gain, val_gain):
    """마스크 안에서 **색상만** 목표로 옮기고 명암은 유지한다. 명암을 건드리면
    회화의 붓질이 뭉개진다."""
    r, g, b = a[..., 0] / 255, a[..., 1] / 255, a[..., 2] / 255
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    v = mx
    s2 = np.clip(s * sat_gain + 0.10, 0, 1)
    v2 = np.clip(v * val_gain, 0, 1)
    i = np.floor(hue * 6).astype(int) % 6
    f = hue * 6 - np.floor(hue * 6)
    p, q, t = v2 * (1 - s2), v2 * (1 - f * s2), v2 * (1 - (1 - f) * s2)
    out = np.zeros_like(a)
    for k, (R, G, B) in enumerate([(v2, t, p), (q, v2, p), (p, v2, t),
                                   (p, q, v2), (t, p, v2), (v2, p, q)]):
        m = i == k
        out[..., 0][m] = R[m]; out[..., 1][m] = G[m]; out[..., 2][m] = B[m]
    out *= 255
    m3 = mask[..., None]
    return a * (1 - m3) + out * m3


def autumn_leaves(a, tree, shape, rng):
    """나뭇잎을 단풍색으로. 저주파 노이즈로 색을 얼룩덜룩하게 섞어야 한 그루가
    통째로 빨간 조화(造花)처럼 안 보인다."""
    H, W = shape
    def noise(cells):
        n = rng.random((cells, int(cells * W / H) + 1))
        return np.asarray(Image.fromarray((n * 255).astype(np.uint8))
                          .resize((W, H), Image.BICUBIC), np.float32) / 255
    nz = 0.65 * noise(7) + 0.35 * noise(18)
    nz = (nz - nz.min()) / (nz.max() - nz.min())
    hue = 0.0 + nz * 0.125            # 빨강(0) ~ 노란초록(0.125)
    return hsv_recolor(a, tree * 0.92, hue, 2.1, 1.03)


def winter_snow(a, L, yy, tree, shape, rng):
    """들판·나무에 눈을 얹는다.

    나무 눈을 무작위 잡음으로 뿌리면 잔모래처럼 보인다 — **원화에서 밝게
    칠해진 잎 덩어리**(빛을 받는 윗면)를 따라 앉혀야 눈처럼 읽힌다.
    거기에 수관의 위쪽 실루엣을 더한다."""
    H, W = shape
    def shift_down(m, k):
        out = np.zeros_like(m); out[k:] = m[:-k]; return out
    def noise(cells):
        n = rng.random((cells, int(cells * W / H) + 1))
        return np.asarray(Image.fromarray((n * 255).astype(np.uint8))
                          .resize((W, H), Image.BICUBIC), np.float32) / 255

    ground = ramp(yy, 1150, 1380)
    tree_top = np.clip(tree - shift_down(tree, 16), 0, 1)
    lit = ramp(L, 95, 150)
    lown = 0.5 + 0.5 * noise(22)
    snow_g = ground * (0.45 + 0.55 * ramp(L, 80, 175)) * 0.86
    snow_t = (blur(tree_top, 7) * 1.7 + tree * lit * lown * 0.95) * 1.35
    snow = np.clip(snow_g + blur(snow_t, 2), 0, 1)
    white = np.stack([np.full((H, W), 246.0), np.full((H, W), 249.0),
                      np.full((H, W), 255.0)], -1)
    keep = L[..., None] / 255 * 0.30 + 0.70      # 원본 명암을 조금 남긴다
    return a * (1 - snow[..., None]) + white * keep * 0.93 * snow[..., None]


_STORM = None


def storm_canvas(shape):
    """먹구름 그림을 화면 크기에 맞춰 한 번만 준비한다.

    **있는 구름을 어둡게 눌러서는 안 된다** — 밝기를 선형으로 늘리면 밝은 구름과
    그늘이 양극단으로 벌어져 색반전처럼 보이고, 마스크가 끝나는 자리에 가로 띠가
    생긴다(2026-09-05 제보 "왜 상단 60%만 검게 된 거야"). 그래서 하늘을 **통째로
    갈아끼운다**. 그림은 tools/season/storm-sky.jpg(생성본)이고, 잉크선이 원화보다
    세서 흐림을 섞어 눌러 둔다."""
    global _STORM
    if _STORM is not None:
        return _STORM
    H, W = shape
    src = Image.open(HERE / "storm-sky.jpg").convert("RGB")
    src = src.crop((0, 0, src.width, int(src.height * 0.86))) \
             .resize((W, 1450), Image.LANCZOS)
    c = np.zeros((H, W, 3), np.float32)
    c[:1450] = np.asarray(src, np.float32)
    c[1450:] = c[1449]                       # 아래는 마지막 줄로 채운다(가중치 0)
    sm = np.asarray(Image.fromarray(c.astype(np.uint8))
                    .filter(ImageFilter.GaussianBlur(3)), np.float32)
    _STORM = c * 0.35 + sm * 0.65
    return _STORM


def storm_sky(a, L0, yy, variant):
    """하늘을 먹구름으로 갈아끼운다.

    가중치는 위에서 아래로 **부드럽게** 빠져 지평선을 지나 사라진다 — 마스크를
    지평선에서 끊으면 가로 띠가 생긴다. 어두운 나무(L<95)는 덜 건드려 실루엣이
    남는다.

    먹구름 그림은 한 장뿐이라 8변형에 그대로 쓰면 밤과 낮이 같아진다. 그래서
    **원래 하늘의 채널별 평균에 맞춰** 색과 밝기를 옮긴다 — 노을은 노을대로,
    밤은 밤대로 어두워진다."""
    H, W = L0.shape
    canvas = storm_canvas((H, W)).copy()
    w = blur(np.clip(1 - ramp(yy, 1150, 1560), 0, 1) * ramp(L0, 95, 135), 14)
    core = w > 0.6
    if core.any():
        dim = 0.85 if variant.startswith("night") else 0.62
        want = a[core].mean(0) * dim
        have = np.maximum(canvas[core].mean(0), 1)
        canvas *= (want / have)
    canvas = np.clip(canvas, 0, 255)
    # 원본을 조금 섞어야 생성본의 잉크선이 원화 톤에 묻힌다
    mixed = canvas * 0.65 + a * 0.35
    return a * (1 - w[..., None]) + mixed * w[..., None]


def main():
    L, yy, sky, tree, shape = build_masks()   # sky는 지금 안 쓴다(하늘은 통째 교체)
    tmp = Path(tempfile.mkdtemp())
    for v in VARIANTS:
        base = np.asarray(Image.open(IMG / f"bg-{v}.jpg").convert("RGB"), np.float32)
        for s in SEASONS:
            rng = np.random.default_rng(20260905)   # 계절마다 같은 얼룩을 쓴다
            a = base
            if s == "autumn":
                a = autumn_leaves(a, tree, shape, rng)
            elif s == "winter":
                a = winter_snow(a, L, yy, tree, shape, rng)

            src = tmp / "in.png"
            Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(src)
            out = IMG / f"bg-{v}-{s}.jpg"
            if CHAINS[s]:
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src),
                                "-vf", CHAINS[s], "-q:v", "3", str(out)], check=True)
            else:
                subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src),
                                "-q:v", "3", str(out)], check=True)

            if v.endswith("-rain"):
                b = np.asarray(Image.open(out).convert("RGB"), np.float32)
                Image.fromarray(np.clip(storm_sky(b, L, yy, v), 0, 255).astype(np.uint8)) \
                     .save(out, quality=93)
        print(f"  {v} → {' '.join(SEASONS)}")
    print("=== 완료")


if __name__ == "__main__":
    main()
