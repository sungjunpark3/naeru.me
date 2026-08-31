#!/usr/bin/env python3
# 프레임별 알파 매트 + 언프리멀티플라이 색 → naeru-<변형> PNG 시퀀스.
#
# 알파는 dusk 316프레임에서 딱 한 벌만 계산해 8변형에 그대로 쓴다(§1 정렬
# 확인됨). 색은 변형별 O(그 변형의 원본 프레임)와 공용 plate P를 언프리멀티플라이
# 해서 뽑는다 — 배경 스필이 빠지고, P 위에 다시 얹으면 O가 그대로 복원된다.
#
# 입력 (build.sh가 미리 ffmpeg로 잘라둔 것):
#   dusk-work/%04d.png     dusk WORK 크롭 — 알파 계산용 여유 영역
#   O/<v>/%04d.png          변형별 CROP 크롭 — 언프리멀티플라이의 O
#   img/plate-<v>.png       plate.py 산출물 — 언프리멀티플라이의 P
import sys
from pathlib import Path
from PIL import Image, ImageChops, ImageFilter, ImageDraw, ImageMath

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
B = HERE / "build"
sys.path.insert(0, str(HERE))
from coords import (WORK_ORIGIN, CROP_ORIGIN, CROP_SIZE, N_FRAMES,
                     VARIANTS, KEY_RECT_GLOBAL)

KEY_THRESH       = 30       # 분홍기 이진 임계 — 아래 주석의 실측값에서 나온 것
HOLE_THRESH      = 180      # 이 미만은 flood-fill 후보(배 크림 줄무늬까지 걸리게 넉넉히)
BLUR_PX          = 1.2
ALPHA_FLOOR      = 38       # ≈0.15*255 — 언프리멀티플라이 나눗셈 클램프 하한
# 316프레임 실루엣 교집합의 무게중심(WORK-local). 모든 프레임에서 몸 안이라는
# 걸 확인했다 — keep_main_component의 flood fill 시드. global (2025,1563)
BODY_SEED        = (375, 313)


def silhouette(rgb_img, canvas_size):
    """분홍기 p = R-max(G,B)의 이진 실루엣. 신뢰 키잉창 밖은 강제 0
    (하늘·언덕도 분홍이라 그 밖에서는 키가 무의미, PLAN §8 부록 B).

    소프트 램프(22→40)를 쓰지 않는 이유 — dusk 3프레임 실측(2026-09-01):
      배경(잔디·언덕)  p50=16  p95=23  p99=25~27
      몸(캐릭터)       p50=41  p95=64  **p5=17~18**
    두 분포가 꼬리에서 겹친다. 램프 하한을 22에 두면 배경이 알파 10~50%로
    통째로 딸려 들어와서(스프라이트에 반투명 후광 + 키잉창 사각 자국) 캐릭터가
    움직이는 순간 배경 조각을 달고 다닌다. 그래서 배경 p99보다 위인 30에서
    이진으로 자르고, 겹치는 몸 하위 5%(어두운 외곽선·배 크림줄무늬)는
    fill_holes가 되찾는다. 경계 안티에일리어싱은 이진 마스크의 블러로 얻는다."""
    r, g, b = rgb_img.split()
    p = ImageChops.subtract(r, ImageChops.lighter(g, b))
    a = p.point(lambda v: 255 if v > KEY_THRESH else 0)

    kx0 = KEY_RECT_GLOBAL[0] - WORK_ORIGIN[0]
    ky0 = KEY_RECT_GLOBAL[1] - WORK_ORIGIN[1]
    kx1 = KEY_RECT_GLOBAL[2] - WORK_ORIGIN[0]
    ky1 = KEY_RECT_GLOBAL[3] - WORK_ORIGIN[1]
    crop = a.crop((kx0, ky0, kx1, ky1))
    canvas = Image.new("L", canvas_size, 0)
    canvas.paste(crop, (kx0, ky0))
    return canvas


def fill_holes(mask):
    """닫기로 잡티 정리 후, 캔버스 바깥(=크롭 바깥)에서 flood fill해서 배경과
    안 이어진 내부 저알파 영역(배 크림색 줄무늬 등)을 실루엣에 편입한다."""
    closed = mask.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    bg_candidate = closed.point(lambda v: 255 if v < HOLE_THRESH else 0)
    filled = bg_candidate.copy()
    ImageDraw.floodfill(filled, (0, 0), 128, thresh=0)
    hole = filled.point(lambda v: 255 if v == 255 else 0)
    return ImageChops.lighter(closed, hole)


def keep_main_component(mask, seed):
    """캐릭터와 이어지지 않은 덩어리를 버린다.

    키잉창 안이라도 먼 언덕 일부는 분홍기가 임계를 넘어서(하늘·언덕도 분홍)
    실루엣에 붙는다 — 크롭 위쪽에 가로로 남는 사각 띠가 그것이다. 몸 안쪽
    한 점에서 flood fill 해 그 연결성분만 남기면 깨끗하게 떨어진다."""
    assert mask.getpixel(seed) > 128, f"시드 {seed}가 몸 안이 아니다 — 좌표 확인"
    m = mask.copy()
    ImageDraw.floodfill(m, seed, 128, thresh=0)
    return m.point(lambda v: 255 if v == 128 else 0)


def build_alpha_sequence():
    frames = sorted((B / "dusk-work").glob("*.png"))
    assert len(frames) == N_FRAMES, \
        f"dusk-work에 {len(frames)}프레임, {N_FRAMES}장 기대"
    canvas_size = Image.open(frames[0]).size

    out_dir = B / "alpha"
    out_dir.mkdir(exist_ok=True)
    ox = CROP_ORIGIN[0] - WORK_ORIGIN[0]
    oy = CROP_ORIGIN[1] - WORK_ORIGIN[1]

    for i, fp in enumerate(frames):
        im = Image.open(fp).convert("RGB")
        a = silhouette(im, canvas_size)
        a = fill_holes(a)
        a = keep_main_component(a, BODY_SEED)
        a = a.filter(ImageFilter.GaussianBlur(BLUR_PX))
        a_crop = a.crop((ox, oy, ox + CROP_SIZE[0], oy + CROP_SIZE[1]))
        a_crop.save(out_dir / fp.name)
        if (i + 1) % 79 == 0:
            print(f"  alpha {i + 1}/{N_FRAMES}")
    print(f"alpha: {N_FRAMES}프레임 -> {out_dir}")


def unpremultiply(o_band, p_band, a_band):
    """C = P + (O-P)*255/max(A,floor). O<P인 화소(음수 차)도 convert(...,'L')이
    클램프해준다 — 별도 테스트로 확인됨."""
    return ImageMath.lambda_eval(
        lambda a: a["convert"](
            a["P"] + (a["O"] - a["P"]) * 255 / a["max"](a["A"], ALPHA_FLOOR), "L"
        ),
        O=o_band, P=p_band, A=a_band,
    )


def build_variant(variant):
    plate = Image.open(REPO / "img" / f"plate-{variant}.png").convert("RGB")
    p_crop = plate.crop((CROP_ORIGIN[0], CROP_ORIGIN[1],
                          CROP_ORIGIN[0] + CROP_SIZE[0], CROP_ORIGIN[1] + CROP_SIZE[1]))
    pr, pg, pb = p_crop.split()

    o_frames = sorted((B / "O" / variant).glob("*.png"))
    a_frames = sorted((B / "alpha").glob("*.png"))
    assert len(o_frames) == N_FRAMES, f"O/{variant}에 {len(o_frames)}프레임"
    assert len(a_frames) == N_FRAMES, f"alpha에 {len(a_frames)}프레임"

    out_dir = B / f"naeru-{variant}"
    out_dir.mkdir(exist_ok=True)
    for o_fp, a_fp in zip(o_frames, a_frames):
        o = Image.open(o_fp).convert("RGB")
        a = Image.open(a_fp).convert("L")
        orr, og, ob = o.split()
        cr = unpremultiply(orr, pr, a)
        cg = unpremultiply(og, pg, a)
        cb = unpremultiply(ob, pb, a)
        Image.merge("RGBA", (cr, cg, cb, a)).save(out_dir / o_fp.name)
    print(f"{variant}: {N_FRAMES}프레임 -> {out_dir}")


def main():
    build_alpha_sequence()
    for v in VARIANTS:
        build_variant(v)


if __name__ == "__main__":
    main()
