#!/usr/bin/env python3
# 혀를 몸에서 떼어낸다 — "혀 집어넣었다 빼는" 동작을 DOM으로 만들기 위한 자산.
#
# 왜 이렇게 하나 —
#   316프레임 루프 어디에도 혀가 들어간 프레임이 없다(혀 영역 프레임간 변화
#   평균 1.81, 실루엣 화소수 75,375~84,075로 혀가 빠질 여지가 없다). 재생
#   구간·속도로는 못 만들고, 혀를 지운 몸을 새로 그려야 한다.
#
#   혀는 몸과 **같은 분홍**이라 색으로는 못 가른다. 어두운 윤곽선으로만
#   갈리는데 전역 임계로는 아래쪽 그늘까지 잡힌다. 그래서 손으로 다각형을
#   잡고(POLY), 그걸 **머리 자세를 따라 옮긴다** — 정지 마스크로 두면 자세가
#   바뀌는 프레임에서 얼굴을 지워버린다(f132에서 실제로 그랬다).
#
#   지운 자리는 LaMa로 메운다(배경에서 내루미를 지울 때와 같은 venv·모델).
#   혀 뒤에는 팔과 배 줄무늬가 있는데 둘 다 단순한 형태라 잘 이어진다.
#
# 산출물: build/notongue-<변형>/%04d.png — 알파는 원본 그대로 두고 RGB만
#   바뀐다(혀는 실루엣 안쪽이라 알파가 안 변한다).
#
#   python3 tongue.py --fit    머리 추적 + 마스크 정렬 몽타주만 (빠름)
#   python3 tongue.py          전체 (LaMa 8변형 × 316프레임)
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
B = HERE / "build"
sys.path.insert(0, str(HERE))
from coords import CROP_ORIGIN, CROP_SIZE, N_FRAMES, VARIANTS

UNIQUE = 159                    # 핑퐁 원본 프레임 수 ([0..158] + [157..1])
REF    = 79                     # 마스크를 그린 기준 프레임

# 크롭 좌표계(576×496)에서 손으로 잡은 혀 다각형.
# 입의 어두운 선(y≈133~158)은 일부러 남긴다 — 혀가 들어가도 입은 열려 있어야
# "혀를 집어넣은 얼굴"로 읽힌다.
POLY = [(190, 152), (248, 148), (282, 168), (266, 198), (244, 242),
        (220, 288), (196, 322), (160, 324), (138, 300), (135, 248),
        (149, 200), (170, 168)]
DILATE = 13                     # 혀 자체의 흔들림(±6px) 여유

# 머리 추적 창 — 입 위쪽만 쓴다(혀가 안 들어가야 강체로 취급할 수 있다)
HEAD   = (175, 55, 320, 150)
CENTER = (247, 102)             # 회전 중심(머리 한가운데)


def build_mask():
    m = Image.new("L", CROP_SIZE, 0)
    ImageDraw.Draw(m).polygon(POLY, fill=255)
    return m.filter(ImageFilter.MaxFilter(DILATE))


def fit_head(gray):
    """기준 프레임 대비 (dx, dy, 회전). 거칠게 훑고 그 주변만 촘촘히 본다 —
    전 범위를 촘촘히 훑으면 프레임당 1만 번이 넘어 159프레임이 몇 분씩 걸린다."""
    ref = gray[REF][HEAD[1]:HEAD[3], HEAD[0]:HEAD[2]]

    def err(img, dx, dy, th):
        r = np.asarray(Image.fromarray(img).rotate(th, resample=Image.BILINEAR,
                                                   center=CENTER), np.float32)
        s = np.roll(np.roll(r, dy, 0), dx, 1)[HEAD[1]:HEAD[3], HEAD[0]:HEAD[2]]
        return np.abs(s - ref).mean()

    out = []
    for n in range(UNIQUE):
        img = gray[n]
        best = (1e18, 0, 0, 0.0)
        for th in np.arange(-16, 16.1, 4.0):                  # 거칠게
            for dy in range(-24, 25, 4):
                for dx in range(-24, 25, 4):
                    e = err(img, dx, dy, th)
                    if e < best[0]: best = (e, dx, dy, th)
        _, bx, by, bt = best
        for th in np.arange(bt - 3, bt + 3.1, 1.0):           # 그 주변만 촘촘히
            for dy in range(by - 3, by + 4):
                for dx in range(bx - 3, bx + 4):
                    e = err(img, dx, dy, th)
                    if e < best[0]: best = (e, dx, dy, th)
        out.append(best)
        if n % 20 == 0:
            print(f"  f{n:3d} dx={best[1]:+3d} dy={best[2]:+3d} "
                  f"rot={best[3]:+5.1f}° 잔차 {best[0]:5.2f}")
    return out


def warp_mask(mask0, dx, dy, th):
    """기준 프레임의 마스크를 프레임 n의 자세로 옮긴다. fit는
    roll(rotate(frame)) ≈ ref를 풀었으므로 역변환은 rotate(roll(mask), -th)."""
    m = np.asarray(mask0, np.uint8)
    m = np.roll(np.roll(m, -dy, 0), -dx, 1)
    return Image.fromarray(m).rotate(-th, resample=Image.BILINEAR, center=CENTER)


def montage(gray_imgs, mask0, fits, path):
    """마스크가 자세를 제대로 따라갔는지 한 장으로 확인 — LaMa를 30분 돌리기
    전에 반드시 눈으로 볼 것. 어긋나면 얼굴이 지워진다."""
    ns = list(range(0, UNIQUE, UNIQUE // 12))[:12]
    w, h = CROP_SIZE
    sheet = Image.new("RGB", (w * 4, h * 3))
    for k, n in enumerate(ns):
        base = gray_imgs[n].convert("RGB")
        m = warp_mask(mask0, fits[n][1], fits[n][2], fits[n][3])
        base.paste(Image.new("RGB", CROP_SIZE, (220, 40, 60)), (0, 0), m)
        d = ImageDraw.Draw(base)
        d.text((8, 8), f"f{n}  잔차 {fits[n][0]:.1f}", fill=(255, 255, 0))
        sheet.paste(base, (w * (k % 4), h * (k // 4)))
    sheet.resize((sheet.width // 3, sheet.height // 3), Image.LANCZOS).save(path)
    print(f"몽타주 -> {path}")


def main():
    fit_only = "--fit" in sys.argv
    src = sorted((B / "naeru-dusk").glob("*.png"))
    assert len(src) == N_FRAMES, f"naeru-dusk에 {len(src)}프레임 — matte.py를 먼저"
    gray = [np.asarray(Image.open(f).convert("L"), np.float32) for f in src[:UNIQUE]]
    mask0 = build_mask()
    mask0.save(B / "tongue-mask.png")

    print("머리 추적 (159프레임)")
    fits = fit_head(gray)
    np.save(B / "tongue-fits.npy", np.array([[f[1], f[2], f[3]] for f in fits]))
    worst = max(fits, key=lambda f: f[0])
    print(f"  최악 잔차 {worst[0]:.2f} (dx={worst[1]} dy={worst[2]} rot={worst[3]}°)")

    montage([Image.open(f) for f in src[:UNIQUE]], mask0, fits,
            B / "tongue-align.png")
    if fit_only:
        return

    from simple_lama_inpainting import SimpleLama
    lama = SimpleLama()
    # 핑퐁이라 [0..158]만 만들고 뒤쪽 157장은 되짚어 복사한다
    order = list(range(UNIQUE)) + list(range(UNIQUE - 2, 0, -1))
    assert len(order) == N_FRAMES

    for v in VARIANTS:
        out_dir = B / f"notongue-{v}"
        out_dir.mkdir(exist_ok=True)
        frames = sorted((B / f"naeru-{v}").glob("*.png"))
        done = {}
        for i, n in enumerate(order):
            if n in done:
                done[n].save(out_dir / frames[i].name)
                continue
            sp = Image.open(frames[n]).convert("RGBA")
            a = sp.getchannel("A")
            m = warp_mask(mask0, fits[n][1], fits[n][2], fits[n][3])
            # 혀는 실루엣 안쪽이라 알파가 안 변한다 — RGB만 바꾸고 알파는 그대로
            filled = lama(sp.convert("RGB"), m).crop((0, 0, CROP_SIZE[0], CROP_SIZE[1]))
            res = Image.composite(filled, sp.convert("RGB"), m)
            res.putalpha(a)
            res.save(out_dir / frames[i].name)
            done[n] = res
        print(f"{v}: {N_FRAMES}프레임 -> {out_dir}")


if __name__ == "__main__":
    main()
