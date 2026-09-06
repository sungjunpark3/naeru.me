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
#     할 뿐 하늘은 그대로 뭉게구름이다. 그렇다고 구름을 그려 넣으면 화면을
#     잡아먹는다 — storm_sky() 주석 참고.
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


def snow_white(a, sky, shape):
    """이 변형에서 눈이 어떤 색이어야 하는가.

    **고정된 흰색으로 칠하면 안 된다** — 밤인데 땅만 대낮처럼 하얘진다
    (2026-09-06 제보 "위만 밤이고 아래는 낮이야?"). 눈은 스스로 빛나지 않고
    하늘빛을 받아 보이므로, 그 변형의 **하늘 밝기와 색조**에서 끌어온다.
    하늘보다 45는 밝게 두는 하한이 있어야 달빛 눈이 어둠에 묻히지 않는다."""
    H, W = shape
    core = sky > 0.6
    m = a[core].mean(0) if core.any() else np.array([180.0, 180.0, 190.0])
    level = float(np.clip(max(m.mean() * 1.35, m.mean() + 45), 60, 252))
    tint = m / max(m.mean(), 1.0)
    col = np.clip(tint * level, 0, 255)
    col[2] = min(255.0, col[2] * 1.03)        # 눈 그늘은 살짝 푸르다
    return np.broadcast_to(col, (H, W, 3)).copy()


def winter_snow(a, L, yy, tree, shape, rng, sky):
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

    # 앞쪽 꽃밭은 눈이 두껍게 쌓여 **꽃이 묻힌다**. 그냥 하얗게만 하면 활짝 핀
    # 데이지가 그대로 보여서 겨울로 안 읽힌다(2026-09-06 제보). 형태를 흐려
    # 눈더미로 만들고 눈을 더 얹는다
    front = ramp(yy, 1560, 1880)[..., None]
    soft = np.asarray(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
                      .filter(ImageFilter.GaussianBlur(11)), np.float32)
    a = a * (1 - front * 0.78) + soft * (front * 0.78)
    snow = np.clip(snow + front[..., 0] * 0.55, 0, 1)

    white = snow_white(a, sky, (H, W))
    keep = L[..., None] / 255 * 0.30 + 0.70      # 원본 명암을 조금 남긴다
    return a * (1 - snow[..., None]) + white * keep * 0.93 * snow[..., None]


def storm_sky(a, L0, yy, variant, season):
    """비·눈이 올 땐 하늘을 무겁게 내려앉은 잿빛으로 만든다.

    두 번 실패하고 세 번째다(전부 2026-09-05 제보):
      1. 밝기를 **선형으로 늘려** 대비를 키웠더니 밝은 구름과 그늘이 양극단으로
         벌어져 색반전처럼 보였고, 마스크를 지평선에서 끊어 상단만 칠해진
         가로 띠가 생겼다.
      2. 생성한 먹구름 그림을 통째로 갈아끼웠더니 (a) 잉크 윤곽선이 파스텔풍
         원화와 이질적이었고, (b) 선을 지운 뒤에도 구름 덩어리가 너무 세서
         "그림에서 먹구름만 보인다"가 됐다.

    실제로 비 오는 하늘은 조각 같은 구름이 아니라 **평평한 잿빛**이다. 그래서
    원화의 하늘을 그대로 쓰되 **국소 대비를 줄이고**(FLAT) 어둡게 눌러(DIM)
    탈채도한다. 구름 형태는 희미하게 남아 하늘이 죽지 않고, 화면의 주인공은
    초원과 내루미로 돌아온다.

    가중치는 위에서 아래로 부드럽게 빠져 지평선을 지나 사라진다 — 여기서
    끊으면 1번의 가로 띠가 다시 생긴다. 어두운 나무(L<95)는 덜 건드려
    실루엣이 남는다."""
    # 겨울은 밝게 둔다. 눈 오는 낮은 흐리지만 **어둡지 않다** — 여기서 0.60을
    # 쓰면 하늘은 110, 눈 덮인 땅은 190이 되어 화면 위아래가 딴 그림이 된다
    # (2026-09-06 제보 "상단 60%와 하단 40%에 전혀 다른 필터").
    FLAT = 0.85
    DIM = 0.82 if season == "winter" else 0.60
    L = a.mean(2)
    big = np.asarray(Image.fromarray(L.astype(np.uint8))
                     .filter(ImageFilter.GaussianBlur(70)), np.float32)
    tgt = (big + (L - big) * FLAT) * DIM
    gray = a * 0.25 + a.mean(2, keepdims=True) * 0.75
    stormy = np.clip(gray * (tgt / np.maximum(L, 1))[..., None], 0, 255)
    stormy[..., 2] *= 1.04                       # 살짝 푸른 잿빛
    # **가중치에 바닥값을 둔다.** 0으로 떨어뜨리면 하늘만 어두워지고 땅은
    # 그대로라 지평선에서 화면이 두 동강 난다. 폭풍 아래에선 땅도 같이 어둡다
    FLOOR = 0.28
    w = FLOOR + (1 - FLOOR) * np.clip(1 - ramp(yy, 1150, 1560), 0, 1)
    w = blur(w * np.maximum(ramp(L0, 95, 135), 0.45), 14)
    return a * (1 - w[..., None]) + stormy * w[..., None]


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
                a = winter_snow(a, L, yy, tree, shape, rng, sky)

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
                Image.fromarray(np.clip(storm_sky(b, L, yy, v, s), 0, 255).astype(np.uint8)) \
                     .save(out, quality=93)
        print(f"  {v} → {' '.join(SEASONS)}")
    print("=== 완료")


if __name__ == "__main__":
    main()
