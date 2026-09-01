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
BLUR_PX          = 1.4
ALPHA_FLOOR      = 38       # ≈0.15*255 — 언프리멀티플라이 나눗셈 클램프 하한
# 316프레임 실루엣 교집합의 무게중심(WORK-local). 모든 프레임에서 몸 안이라는
# 걸 확인했다 — keep_main_component의 flood fill 시드. global (2025,1563)
BODY_SEED        = (375, 313)
SMOOTH_R         = 3.5      # 윤곽 평활 반경 — 이진 임계가 만드는 톱니를 편다
# 발 되살리기: 발은 희어서 분홍기가 0에 가깝고(실측 알파 0이 7525/10500 화소),
# plate가 발을 지우면 스프라이트가 다시 그리질 못한다. 이 구간에서만은 배경과의
# 색거리가 잘 듣는다(p90=62) — 흰 발 vs 초록 잔디라서.
FEET_TOP_GLOBAL  = 1680
FEET_LO, FEET_HI = 25, 70
# 경계 링 복원: 실루엣 바로 바깥 몇 px에서 plate는 **진짜 배경**이다(시간축
# 채우기가 그 자리 원본 화소를 그대로 쓴다 — 링 0~4px와 14~22px 평균밝기가
# 126.7/126.6으로 평탄한 걸로 확인). 그러니 그 좁은 링에서는 |O-P|가 곧
# "전경이 얼마나 섞였나"다. 이진 키는 어두운 외곽선을 조금 잘라내는데(브라우저
# 실측: 실루엣 밖 0~2px가 원본보다 +2.9 밝음 = 옅은 후광), 링에서만 알파를
# **보태면**(max) 배경은 |O-P|≈0이라 안 딸려온다.
RING_OUT, RING_IN = 6, 2
RING_LO, RING_HI  = 8, 40


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
        # 윤곽 평활: 블러 → 재이진화. 분홍기 임계가 노이즈 위에서 갈리며 만든
        # ±2px 톱니를 펴준다. 닫기(9px)는 그 톱니를 4px 블록으로 뭉치게 할 뿐이라
        # 이게 필요하다 — 확대해보면 머리 위 계단이 사라진다
        a = a.filter(ImageFilter.GaussianBlur(SMOOTH_R)).point(
            lambda v: 255 if v > 128 else 0)
        a = a.filter(ImageFilter.GaussianBlur(BLUR_PX))
        a_crop = a.crop((ox, oy, ox + CROP_SIZE[0], oy + CROP_SIZE[1]))
        a_crop.save(out_dir / fp.name)
        if (i + 1) % 79 == 0:
            print(f"  alpha {i + 1}/{N_FRAMES}")
    print(f"alpha: {N_FRAMES}프레임 -> {out_dir}")


def median3(a, b, c):
    """세 장의 화소별 중앙값 = max(min(a,b), min(max(a,b), c))."""
    return ImageChops.lighter(ImageChops.darker(a, b),
                              ImageChops.darker(ImageChops.lighter(a, b), c))


def refine_alpha_sequence():
    """build/alpha → build/alpha2: 시간축 3프레임 중앙값으로 안정화.

    프레임마다 독립으로 키를 뜨면 경계가 지글거린다(boiling). 제자리에 서 있을
    땐 plate가 그 오차를 상쇄해 안 보이지만, 움직이면 테두리가 들끓는 것처럼
    보인다 — 누끼가 더러워졌다는 제보의 절반이 이것이다. 캐릭터 움직임이 느려서
    3프레임 중앙값으로도 모션은 안 뭉개진다(실측: 프레임간 평균차 3.8 유지).

    (배경과의 색거리로 알파를 뽑는 difference matting도 해봤는데, 어두운 외곽선이
     어두운 언덕과 색이 비슷해 거기서 알파가 무너졌다 — 머리 위쪽이 반투명해진다.
     전경 거리 p50=61이라 몸통 절반도 램프 안에 들어간다. 그래서 폐기.)"""
    a_frames = sorted((B / "alpha").glob("*.png"))
    o_frames = sorted((B / "O" / "dusk").glob("*.png"))
    assert len(a_frames) == len(o_frames) == N_FRAMES
    plate = Image.open(REPO / "img" / "plate-dusk.png").convert("RGBA").crop(
        (CROP_ORIGIN[0], CROP_ORIGIN[1],
         CROP_ORIGIN[0] + CROP_SIZE[0], CROP_ORIGIN[1] + CROP_SIZE[1]))
    p_alpha = plate.getchannel("A")

    # 발 구간에서만 색거리로 알파를 보탠다. "plate가 지운 만큼"(p_alpha)을 상한으로
    # 두면 지운 자리만 되살리게 되고, 그 아래 그림자는 건드리지 않는다
    scale = 255.0 / (FEET_HI - FEET_LO)
    ramp = [max(0, min(255, round((v - FEET_LO) * scale))) for v in range(256)]
    rscale = 255.0 / (RING_HI - RING_LO)
    ring_ramp = [max(0, min(255, round((v - RING_LO) * rscale))) for v in range(256)]
    band = Image.new("L", CROP_SIZE, 0)
    ImageDraw.Draw(band).rectangle(
        [0, FEET_TOP_GLOBAL - CROP_ORIGIN[1], CROP_SIZE[0], CROP_SIZE[1]], fill=255)

    raw = []
    for a_fp, o_fp in zip(a_frames, o_frames):
        key = Image.open(a_fp).convert("L")
        o = Image.open(o_fp).convert("RGBA")
        bg = Image.alpha_composite(o, plate).convert("RGB")   # plate가 지운 뒤의 배경
        d = ImageChops.difference(o.convert("RGB"), bg).split()
        dmax = ImageChops.lighter(ImageChops.lighter(d[0], d[1]), d[2])
        d = dmax.point(ramp)
        d_ring = dmax.point(ring_ramp)
        feet = ImageChops.multiply(ImageChops.darker(d, p_alpha), band)

        # 경계 링에서 잘려나간 외곽선을 되찾는다 (보태기만 — 빼지 않는다)
        sil = key.point(lambda v: 255 if v > 128 else 0)
        ring = ImageChops.subtract(sil.filter(ImageFilter.MaxFilter(2 * RING_OUT + 1)),
                                   sil.filter(ImageFilter.MinFilter(2 * RING_IN + 1)))
        edge = ImageChops.multiply(ImageChops.darker(d_ring, p_alpha), ring)
        feet = ImageChops.lighter(feet, edge)
        # 발을 보탠 뒤 윤곽을 다시 편다 — 색거리 램프는 거칠어서 그대로 두면
        # 발끝만 너덜너덜하게 남는다(키 쪽은 이미 평활을 거쳤다)
        a = ImageChops.lighter(key, feet)
        a = a.filter(ImageFilter.GaussianBlur(SMOOTH_R)).point(
            lambda v: 255 if v > 128 else 0).filter(ImageFilter.GaussianBlur(BLUR_PX))
        raw.append(a)
    out_dir = B / "alpha2"
    out_dir.mkdir(exist_ok=True)
    for i, fp in enumerate(a_frames):
        median3(raw[max(0, i - 1)], raw[i], raw[min(N_FRAMES - 1, i + 1)]) \
            .save(out_dir / fp.name)
    print(f"alpha2: {N_FRAMES}프레임 -> {out_dir}")


def unpremultiply(o_band, p_band, a_band):
    """C = P + (O-P)*255/max(A,floor). O<P인 화소(음수 차)도 convert(...,'L')이
    클램프해준다 — 별도 테스트로 확인됨."""
    return ImageMath.lambda_eval(
        lambda a: a["convert"](
            a["P"] + (a["O"] - a["P"]) * 255 / a["max"](a["A"], ALPHA_FLOOR), "L"
        ),
        O=o_band, P=p_band, A=a_band,
    )


def bleed_transparent(rgb, a):
    """투명한 자리의 RGB를 몸 색으로 번지게 채운다.

    언프리멀티플라이는 알파가 0에 가까우면 `255/max(a,38)` = 최대 6.7배로
    외삽하므로 투명 영역에 극단색이 남는다(실측: (230,183,149)·(225,168,183)).
    VP9 알파는 알파가 0인 화소의 색을 안 쓰지만, **HEVC 알파는 4:2:0 크로마라
    그 색이 경계 화소로 번져** 내루미 둘레에 색이 튄다 — 사파리에서 관측됐다.

    알파로 가중한 블러(∑aC/∑a)로 몸 색을 바깥으로 밀어 채우고, 몸에서 멀어
    가중치가 없는 자리는 몸 평균색으로 덮는다. 보이는 화소(a>=16)는 그대로 둔다."""
    num = [ImageChops.multiply(ch, a).filter(ImageFilter.GaussianBlur(16))
           for ch in rgb.split()]
    den = a.filter(ImageFilter.GaussianBlur(16))
    bleed = Image.merge("RGB", [
        ImageMath.lambda_eval(
            lambda x: x["convert"](x["N"] * 255 / x["max"](x["D"], 1), "L"), N=n, D=den)
        for n in num])

    body = a.point(lambda v: 255 if v >= 200 else 0)
    n_body = body.histogram()[255] or 1
    mean = tuple(sum(i * c for i, c in enumerate(
        ImageChops.multiply(ch, body).histogram()[1:], start=1)) // n_body
        for ch in rgb.split())
    far = Image.composite(bleed, Image.new("RGB", rgb.size, mean),
                          den.point(lambda v: 255 if v > 8 else 0))

    # 알파가 낮을수록 bleed 쪽으로 섞는다. 언프리멀티플라이는 알파가 작을수록
    # 크게 나눠서 색이 요동치는데, 그 화소가 바로 움직일 때 눈에 띄는 경계다.
    # a>=96이면 계산값을 그대로 쓰고(디테일 보존), 그 아래에서만 안정화한다.
    w = a.point([min(255, round(v * 255 / 96)) for v in range(256)])
    return Image.merge("RGB", [
        ImageMath.lambda_eval(
            lambda x: x["convert"]((x["F"] * x["W"] + x["G"] * (255 - x["W"])) / 255, "L"),
            F=f, G=g, W=w)
        for f, g in zip(rgb.split(), far.split())])


def build_variant(variant):
    plate = Image.open(REPO / "img" / f"plate-{variant}.png").convert("RGB")
    p_crop = plate.crop((CROP_ORIGIN[0], CROP_ORIGIN[1],
                          CROP_ORIGIN[0] + CROP_SIZE[0], CROP_ORIGIN[1] + CROP_SIZE[1]))
    pr, pg, pb = p_crop.split()

    o_frames = sorted((B / "O" / variant).glob("*.png"))
    a_frames = sorted((B / "alpha2").glob("*.png"))
    assert len(o_frames) == N_FRAMES, f"O/{variant}에 {len(o_frames)}프레임"
    assert len(a_frames) == N_FRAMES, f"alpha2에 {len(a_frames)}프레임 — matte.py를 통째로 돌릴 것"

    out_dir = B / f"naeru-{variant}"
    out_dir.mkdir(exist_ok=True)
    for o_fp, a_fp in zip(o_frames, a_frames):
        o = Image.open(o_fp).convert("RGB")
        a = Image.open(a_fp).convert("L")
        orr, og, ob = o.split()
        rgb = Image.merge("RGB", (unpremultiply(orr, pr, a),
                                  unpremultiply(og, pg, a),
                                  unpremultiply(ob, pb, a)))
        rgb = bleed_transparent(rgb, a)
        rgb.putalpha(a)
        rgb.save(out_dir / o_fp.name)
    print(f"{variant}: {N_FRAMES}프레임 -> {out_dir}")


def main():
    build_alpha_sequence()      # 1단계: 이진 키 (plate.py도 이걸 쓴다)
    refine_alpha_sequence()     # 2단계: plate와의 색거리로 경계를 다듬는다
    for v in VARIANTS:
        build_variant(v)


if __name__ == "__main__":
    main()
