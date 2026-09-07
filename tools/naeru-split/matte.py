#!/usr/bin/env python3
# 프레임별 알파 매트 + 언프리멀티플라이 색 → naeru-<변형> PNG 시퀀스.
#
# 알파는 dusk 316프레임에서 딱 한 벌만 계산해 8변형에 그대로 쓴다(§1 정렬
# 확인됨). 색은 변형별 O(그 변형의 원본 프레임)와 공용 plate P를 언프리멀티플라이
# 해서 뽑는다 — 배경 스필이 빠지고, P 위에 다시 얹으면 O가 그대로 복원된다.
#
# **실루엣은 plate와의 차이로 뜬다.** plate가 캐릭터를 지운 그림이므로
# |O - (O 위에 plate 얹은 것)|이 곧 캐릭터다. 색이 뭐든(흰 발, 어두운 갈색
# 윤곽선) 배경과 다르기만 하면 잡힌다. 분홍기 키는 2026-09-06에 버렸다.
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
from coords import (WORK_ORIGIN, WORK_SIZE, CROP_ORIGIN, CROP_SIZE, N_FRAMES,
                     VARIANTS, KEY_RECT_GLOBAL)

# 실루엣은 **plate와의 차이**로 뜬다: plate가 캐릭터를 지운 그림이므로
# |원본 - plate 얹은 것|이 곧 캐릭터다. 분홍기 키(R-max(G,B))를 2026-09-06에
# 버렸다 — §5 참고. 임계는 실측으로 정했다(dusk 316프레임):
#   캐릭터에서 12px 이상 떨어진 배경   p50 3   p99 9   최대 14
#   윤곽선 등고선 10/14/20이 전부 어두운 테두리 바깥 끝에 1px 안쪽으로 겹침
# 즉 이 키는 경계가 원래 선명해서 임계에 둔감하다. 6은 배경으로 삐져나간다.
DIFF_THRESH      = 12
KEY_THRESH       = 30       # 부트스트랩(분홍기) 전용 — plate.py만 쓴다
HOLE_THRESH      = 180      # 이 미만은 flood-fill 후보(배 크림 줄무늬까지 걸리게 넉넉히)
BLUR_PX          = 1.4
ALPHA_FLOOR      = 38       # ≈0.15*255 — 언프리멀티플라이 나눗셈 클램프 하한
# 316프레임 실루엣 교집합의 무게중심(WORK-local). 모든 프레임에서 몸 안이라는
# 걸 확인했다 — keep_main_component의 flood fill 시드. global (2025,1563)
BODY_SEED        = (375, 313)
# 윤곽 평활 반경. 차이 키는 분홍기와 달리 톱니가 거의 없어서 3.5 → 2.0으로
# 줄였다 — 3.5는 발가락처럼 작은 돌출부를 뭉갠다
SMOOTH_R         = 2.0
# 접지선. plate는 여기 아래를 일부러 안 지운다(그림자를 남기려고)
FEET_TOP_GLOBAL  = 1680
# 접지밴드 상한 — 여기서만 분홍기 키를 다시 쓴다.
#
# plate는 접지 그림자를 남기려고 발밑을 도너로 안 채우고 **주변에서 확산**시킨다
# (plate.py inpaint_core). 그래서 그 구간의 plate는 실제 잔디의 밝기·붓질을
# 재현하지 못하고, 순수 잔디에서도 |O-P|가 20~52까지 뜬다. 반대로 캐릭터의
# 어두운 윤곽선은 plate 쪽도 어두워서 차이가 12~18밖에 안 난다 —
# **잔디의 오차가 캐릭터의 신호보다 크다.** 임계를 어디에 둬도 못 가른다
# (2026-09-06 실측, dusk f79 y372 스캔라인).
#
# 그래서 이 구간에서만 분홍기 키(+흰 발 색거리 복원)를 **상한**으로 씌운다.
# 위쪽에서는 상한을 넉넉히 부풀려 안 걸리게 한다 — 거기선 차이 키가 분홍기보다
# 2~9px 넓은 게 맞다(분홍기가 못 잡는 어두운 윤곽선).
# 초원의 초록기 거부. plate가 국소적으로 잘못 복원한 자리(캐릭터 바로 아래
# 18px 띠에서 원본 194,159,119 vs plate 167,139,97 — 밝은 잔디를 30~40 어둡게
# 그렸다)는 차이 키도 분홍기 키도 캐릭터로 오인한다(그 잔디는 R-max(G,B)=35라
# 분홍기 임계 30도 넘긴다). 초록기 G-B로는 갈린다 — 캐릭터 안쪽이 p50 9 p99 36,
# 그 잔디가 38~61이다. 흰 발(+5)·크림 배(+10)·어두운 윤곽선(+17)은 안전하다.
# **거부는 fill_holes 앞에서 한다** — 몸 안에 갇힌 초록 화소는 되살아나고,
# 초원으로 열린 주머니만 배경으로 남는다.
GREEN_VETO       = 38
GROUND_FADE      = (310, 350)   # 크롭 y. 이 위에서는 상한을 부풀려 안 걸리게 한다
# 상한 평활. 분홍기 ∪ 흰 발 마스크는 접지밴드에서 너덜너덜해서 발가락 사이를
# 톱니처럼 물어뜯는다(2026-09-07 제보). **상한을 푸는 걸로 고치면 안 된다** —
# 풀었더니 배 아래 밝은 잔디 띠가 통째로 딸려 들어왔다. 316프레임에 걸친
# 화소 변동으로 판정했다: 그 띠는 표준편차 1.08로 확실한 배경(1.79)과 같은
# 수준이다(캐릭터 경계는 13.79). 닫기+평활로 톱니만 없앤다.
CAP_CLOSE        = 13
CAP_SMOOTH       = 3
GROUND_DILATE    = 2       # 접지밴드에서 남기는 여유
GROUND_LOOSE     = 5       # 그 위에서의 여유 — 사실상 상한이 안 걸린다
FEET_LO, FEET_HI = 25, 70  # 흰 발 색거리 램프 (분홍기가 0을 주는 구간)
# 시간축 저역통과가 벌려 놓은 램프를 되세운다. 예전(2.2)만큼 셀 필요가 없다 —
# 8px 오오라의 주범은 키가 아니라 refine의 hi/lo 강제였고 그건 통째로 뺐다(§5)
# 피복률 알파 — 이진 실루엣의 "치마"를 없앤다.
#
# 원화는 윤곽선이 배경으로 6px에 걸쳐 부드럽게 번져 있다. 특히 등·귀 뒤쪽은
# 언덕도 회색이고 윤곽선도 회색이라 |O-P|가 14~22밖에 안 나서 경계가 뭉개진다.
# 이진 임계는 그 6px을 통째로 불투명으로 만들어, 검은 바탕에 얹으면
# **#AFA39B짜리 회색 치마**가 실루엣을 두른다(2026-09-07 제보).
#
# diff = 피복률 × |캐릭터색 - 배경색| 이므로, 경계 화소의 diff를 **바로 안쪽
# 몸의 diff**로 나누면 피복률이 그대로 나온다. 나누는 값(D)은 경계에서
# COV_IN px 안쪽 화소의 diff만 모아 COV_R px 팽창해 만든다 — 경계 밴드의
# 값이 섞이면 안 되기 때문. 국소 최대를 그냥 쓰면 몸 안쪽까지 무너진다(실측:
# 불투명 화소가 74,389 → 1,139).
COV_IN           = 4
COV_R            = 7
COV_FLOOR        = 30      # 대비가 없는 자리에서 나눗셈이 폭주하지 않게
EDGE_GAIN        = 1.5


# ── 부트스트랩 키 (plate.py 전용) ──────────────────────────────────────────
#
# 닭과 달걀: 최종 알파는 plate와의 차이로 뜨는데, 그 plate를 만들려면 먼저
# 캐릭터가 어디 있는지 알아야 한다. 그래서 plate.py는 아래 분홍기 키로 대충
# 실루엣을 잡아 덮개 마스크를 만들고(넉넉히 팽창하므로 정밀할 필요 없다),
# matte.py는 완성된 plate로 정밀한 알파를 다시 뜬다.
#
# **최종 알파에는 절대 쓰지 말 것.** 분홍기는 흰 발(알파의 72%가 0)과 어두운
# 갈색 윤곽선을 놓친다 — 2026-09-06까지 하체가 파먹혀 있던 원인이다.


def pink_silhouette(rgb_img, canvas_size):
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


def bootstrap_alpha_sequence():
    frames = sorted((B / "dusk-work").glob("*.png"))
    assert len(frames) == N_FRAMES, \
        f"dusk-work에 {len(frames)}프레임, {N_FRAMES}장 기대"
    canvas_size = Image.open(frames[0]).size

    out_dir = B / "alpha-boot"
    out_dir.mkdir(exist_ok=True)
    ox = CROP_ORIGIN[0] - WORK_ORIGIN[0]
    oy = CROP_ORIGIN[1] - WORK_ORIGIN[1]

    for i, fp in enumerate(frames):
        im = Image.open(fp).convert("RGB")
        a = pink_silhouette(im, canvas_size)
        a = fill_holes(a)
        a = keep_main_component(a, BODY_SEED)
        # 윤곽 평활: 블러 → 재이진화. 분홍기 임계가 노이즈 위에서 갈리며 만든
        # ±2px 톱니를 펴준다. 닫기(9px)는 그 톱니를 4px 블록으로 뭉치게 할 뿐이라
        # 이게 필요하다 — 확대해보면 머리 위 계단이 사라진다
        a = a.filter(ImageFilter.GaussianBlur(3.5)).point(
            lambda v: 255 if v > 128 else 0)
        a = a.filter(ImageFilter.GaussianBlur(BLUR_PX))
        a_crop = a.crop((ox, oy, ox + CROP_SIZE[0], oy + CROP_SIZE[1]))
        a_crop.save(out_dir / fp.name)
        if (i + 1) % 79 == 0:
            print(f"  boot {i + 1}/{N_FRAMES}")
    print(f"부트스트랩 알파: {N_FRAMES}프레임 -> {out_dir}")


# ── 최종 매트 ─────────────────────────────────────────────────────────────


def diff_map(rgb_img, plate_work):
    """|원본 - plate 얹은 것| 의 채널별 최대. plate가 캐릭터를 지웠으므로
    이 값이 곧 "그 화소에 캐릭터가 얼마나 있나"다(= a·|C-bg|).

    분홍기 키(R-max(G,B))를 버린 이유 — 그건 **분홍인 것**을 찾지 캐릭터를
    찾지 않는다. 흰 발은 분홍기가 0이라 통째로 빠지고(발 알파의 72%가 0이었다),
    어두운 갈색 윤곽선도 분홍기가 낮아 잘려나가서 하체가 파먹혔다. 잘린 자리는
    언프리멀티플라이가 배경색을 크게 외삽해 채우므로 여름 잔디 위에선 안
    보이지만 겨울 눈 위에선 초록 잔디 얼룩으로 드러난다(2026-09-06 제보).
    차이 키는 흰 발·어두운 윤곽선 둘 다 배경과 크게 달라서 한 번에 잡힌다."""
    bg = Image.alpha_composite(rgb_img.convert("RGBA"), plate_work).convert("RGB")
    d = ImageChops.difference(rgb_img, bg).split()
    return ImageChops.lighter(ImageChops.lighter(d[0], d[1]), d[2])


def fill_holes(mask):
    """닫기로 잡티 정리 후, 캔버스 바깥(=크롭 바깥)에서 flood fill해서 배경과
    안 이어진 내부 저알파 영역(배 크림색 줄무늬 등)을 실루엣에 편입한다."""
    closed = mask.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    bg_candidate = closed.point(lambda v: 255 if v < HOLE_THRESH else 0)
    filled = bg_candidate.copy()
    ImageDraw.floodfill(filled, (0, 0), 128, thresh=0)
    hole = filled.point(lambda v: 255 if v == 255 else 0)
    return ImageChops.lighter(closed, hole)


def close_holes(mask, thresh=HOLE_THRESH):
    """몸에 둘러싸인 투명 구멍만 메운다(닫기 연산 없이 flood fill만).

    ground_cap은 바깥 경계를 조이려고 씌우는 상한인데, 몸 **안쪽**의 어두운
    주름(배 아래 그늘)까지 같이 깎아서 구멍을 냈다 — 316프레임 중 29장에
    y344~365 / x222~272 자리에 최대 260화소짜리 구멍이 생겼다(2026-09-07 제보,
    검은 바탕 대조판에서 f128~f140·f177~f186에서 보임). 몸에 둘러싸인 자리는
    무조건 몸이므로 상한을 씌운 뒤 되메운다. fill_holes와 달리 닫기(9px)를
    안 하므로 윤곽이 둥글어지지 않는다."""
    cand = mask.point(lambda v: 255 if v < thresh else 0)
    filled = cand.copy()
    ImageDraw.floodfill(filled, (0, 0), 128, thresh=0)
    return ImageChops.lighter(mask, filled.point(lambda v: 255 if v == 255 else 0))


def keep_main_component(mask, seed):
    """캐릭터와 이어지지 않은 덩어리를 버린다.

    키잉창 안이라도 먼 언덕 일부는 분홍기가 임계를 넘어서(하늘·언덕도 분홍)
    실루엣에 붙는다 — 크롭 위쪽에 가로로 남는 사각 띠가 그것이다. 몸 안쪽
    한 점에서 flood fill 해 그 연결성분만 남기면 깨끗하게 떨어진다."""
    assert mask.getpixel(seed) > 128, f"시드 {seed}가 몸 안이 아니다 — 좌표 확인"
    m = mask.copy()
    ImageDraw.floodfill(m, seed, 128, thresh=0)
    return m.point(lambda v: 255 if v == 128 else 0)


def ground_cap(rgb_img, diff, plate_alpha, canvas_size):
    """접지밴드에서 차이 키가 잔디로 번지는 걸 막는 상한 마스크.

    분홍기 키 ∪ 흰 발(색거리 25~70 램프, plate가 지운 만큼을 상한으로) 이고,
    GROUND_FADE 위쪽에서는 GROUND_DILATE만큼 부풀려 안 걸리게 한다."""
    pink = keep_main_component(fill_holes(pink_silhouette(rgb_img, canvas_size)),
                               BODY_SEED)
    scale = 255.0 / (FEET_HI - FEET_LO)
    ramp = [max(0, min(255, round((v - FEET_LO) * scale))) for v in range(256)]
    band = Image.new("L", canvas_size, 0)
    ImageDraw.Draw(band).rectangle(
        [0, FEET_TOP_GLOBAL - WORK_ORIGIN[1], canvas_size[0], canvas_size[1]],
        fill=255)
    feet = ImageChops.multiply(ImageChops.darker(diff.point(ramp), plate_alpha),
                               band).point(lambda v: 255 if v > 128 else 0)
    tight = ImageChops.lighter(pink, feet)
    # 톱니 제거: 닫기로 오목한 흠집을 메우고 블러→재이진화로 계단을 편다
    tight = tight.filter(ImageFilter.MaxFilter(CAP_CLOSE)) \
                 .filter(ImageFilter.MinFilter(CAP_CLOSE)) \
                 .filter(ImageFilter.GaussianBlur(CAP_SMOOTH)) \
                 .point(lambda v: 255 if v > 128 else 0)

    # 위쪽은 넉넉하게, 접지밴드는 딱 맞게 — 세로 램프로 부드럽게 넘긴다
    y0 = GROUND_FADE[0] + CROP_ORIGIN[1] - WORK_ORIGIN[1]
    y1 = GROUND_FADE[1] + CROP_ORIGIN[1] - WORK_ORIGIN[1]
    up = Image.linear_gradient("L").resize((canvas_size[0], y1 - y0)) \
              .point(lambda v: 255 - v)
    above = Image.new("L", canvas_size, 255)
    above.paste(up, (0, y0))
    above.paste(Image.new("L", (canvas_size[0], canvas_size[1] - y1), 0), (0, y1))
    loose = ImageChops.multiply(
        tight.filter(ImageFilter.MaxFilter(2 * GROUND_LOOSE + 1)), above)
    # 접지밴드에서도 2px는 남긴다 — 분홍기가 발가락 윤곽을 한 겹 깎기 때문에
    # 딱 붙이면 발가락이 잘린다(실측: y390 폭 40 → 8)
    return ImageChops.lighter(
        tight.filter(ImageFilter.MaxFilter(2 * GROUND_DILATE + 1)), loose)


def coverage_alpha(binary, diff):
    """이진 실루엣의 경계 밴드만 피복률로 다시 칠한다 (COV_* 주석 참고).

    안쪽 COV_IN px부터는 무조건 불투명으로 두므로 몸통은 안 건드린다."""
    inner = binary.filter(ImageFilter.MinFilter(2 * COV_IN + 1)) \
                  .point(lambda v: 255 if v > 128 else 0)
    core = ImageChops.multiply(diff, inner)          # 완전 피복 구간의 diff만
    D = core.filter(ImageFilter.MaxFilter(2 * COV_R + 1)) \
            .filter(ImageFilter.GaussianBlur(COV_R / 2)) \
            .point(lambda v: max(v, COV_FLOOR))
    cov = ImageMath.lambda_eval(
        lambda x: x["convert"](
            x["min"](x["float"](x["d"]) * 255.0 / x["float"](x["D"]), 255.0), "L"),
        d=diff, D=D, min=lambda p, q: p * (p < q) + q * (q <= p))
    return ImageChops.lighter(ImageChops.darker(binary, cov), inner)


def build_alpha_sequence():
    frames = sorted((B / "dusk-work").glob("*.png"))
    assert len(frames) == N_FRAMES, \
        f"dusk-work에 {len(frames)}프레임, {N_FRAMES}장 기대"

    # plate를 WORK 크롭으로 잘라 둔다. 알파 계산은 WORK 공간에서 하고(경계
    # 연산이 크롭 가장자리에 물리지 않게) 마지막에 CROP으로 잘라 낸다
    plate = Image.open(REPO / "img" / "plate-dusk.png").convert("RGBA").crop(
        (WORK_ORIGIN[0], WORK_ORIGIN[1],
         WORK_ORIGIN[0] + WORK_SIZE[0], WORK_ORIGIN[1] + WORK_SIZE[1]))
    p_alpha = plate.getchannel("A")
    canvas_size = Image.open(frames[0]).size

    out_dir = B / "alpha"
    out_dir.mkdir(exist_ok=True)
    ox = CROP_ORIGIN[0] - WORK_ORIGIN[0]
    oy = CROP_ORIGIN[1] - WORK_ORIGIN[1]

    for i, fp in enumerate(frames):
        im = Image.open(fp).convert("RGB")
        diff = diff_map(im, plate)
        a = diff.point(lambda v: 255 if v > DIFF_THRESH else 0)
        g, b = im.split()[1], im.split()[2]
        a = ImageChops.darker(a, ImageChops.subtract(g, b).point(
            lambda v: 0 if v > GREEN_VETO else 255))
        a = fill_holes(a)
        a = keep_main_component(a, BODY_SEED)
        a = ImageChops.darker(a, ground_cap(im, diff, p_alpha, canvas_size))
        a = close_holes(a)          # 상한이 몸 안쪽에 낸 구멍을 되메운다
        # 윤곽 평활: 블러 → 재이진화. 임계가 노이즈 위에서 갈리며 만든 톱니를
        # 편다. 닫기(9px)는 그 톱니를 4px 블록으로 뭉치게 할 뿐이라 이게 필요하다
        a = a.filter(ImageFilter.GaussianBlur(SMOOTH_R)).point(
            lambda v: 255 if v > 128 else 0)
        a = coverage_alpha(a, diff)     # 경계 밴드를 피복률로 (회색 치마 제거)
        a = close_holes(a)              # 피복률이 다시 뚫은 자리도 되메운다
        a = a.filter(ImageFilter.GaussianBlur(BLUR_PX))
        a_crop = a.crop((ox, oy, ox + CROP_SIZE[0], oy + CROP_SIZE[1]))
        a_crop.save(out_dir / fp.name)
        if (i + 1) % 79 == 0:
            print(f"  alpha {i + 1}/{N_FRAMES}")
    print(f"alpha: {N_FRAMES}프레임 -> {out_dir}")


def tap5(a, b, c, d, e):
    """시간축 5탭 저역통과 (1-3-4-3-1)/12.

    3탭(1-2-1)에서 5탭으로 올린 이유(2026-09-05 전 프레임 감사): 몸통 떨림이
    원색 1.211 → 3탭 0.605 → 5탭 0.426으로 더 준다. 7탭(0.305)까지 가면 혀
    주름과 배 줄무늬가 눈에 띄게 뭉개져서 5탭에서 멈췄다. 모션보상 정렬도
    해봤는데 캐릭터가 비강체로 변형돼서 블록 정합이 오히려 오차를 넣는다
    (±1에서 1.082, ±3에서 1.131 — 단순 평균만 못하다)."""
    return ImageMath.lambda_eval(
        lambda x: x["convert"]((x["A"] + 3 * x["B"] + 4 * x["C"] +
                                3 * x["D"] + x["E"]) / 12, "L"),
        A=a, B=b, C=c, D=d, E=e)


def median3(a, b, c):
    """세 장의 화소별 중앙값 = max(min(a,b), min(max(a,b), c))."""
    return ImageChops.lighter(ImageChops.darker(a, b),
                              ImageChops.darker(ImageChops.lighter(a, b), c))


def refine_alpha_sequence():
    """build/alpha → build/alpha2: 시간축으로만 안정화한다.

    프레임마다 독립으로 키를 뜨면 경계가 지글거린다(boiling). 제자리에 서 있을
    땐 plate가 그 오차를 상쇄해 안 보이지만, 움직이면 테두리가 들끓는 것처럼
    보인다. 3프레임 중앙값이 한 프레임짜리 튐을 없애고, 5탭 저역통과가 매
    프레임 ±1px씩 떠는 자글거림을 없앤다. 캐릭터 움직임이 느려서 모션은
    안 뭉개진다(실측: 프레임간 평균차 3.8 유지).

    **예전에 여기 있던 세 가지(발 되살리기·경계 링 복원·plate 강제)는
    2026-09-06에 전부 뺐다.** 셋 다 분홍기 키가 흰 발과 어두운 윤곽선을 놓치는
    걸 나중에 기워 붙이는 장치였는데, 키 자체를 plate 차이로 바꾸니 놓치는 게
    없어져서 할 일이 없다. 특히 plate 강제의 깃털 먹인 상한/하한(hi/lo)이
    알파 램프를 8px로 벌려 놓은 주범이었다 — 겨울 눈 위에서 "몸에서 오오라가
    나온다"던 게 이것이다(실측: 경계에서 -6px까지 가야 알파 230)."""
    a_frames = sorted((B / "alpha").glob("*.png"))
    assert len(a_frames) == N_FRAMES

    raw = [Image.open(fp).convert("L") for fp in a_frames]
    med = [median3(raw[(i - 1) % N_FRAMES], raw[i], raw[(i + 1) % N_FRAMES])
           for i in range(N_FRAMES)]     # 핑퐁 루프라 양 끝은 순환으로 잇는다

    out_dir = B / "alpha2"
    out_dir.mkdir(exist_ok=True)
    for i, fp in enumerate(a_frames):
        out = tap5(med[(i - 2) % N_FRAMES], med[(i - 1) % N_FRAMES], med[i],
                   med[(i + 1) % N_FRAMES], med[(i + 2) % N_FRAMES])
        # 저역통과가 벌려 놓은 램프를 되세운다(50% 윤곽 위치는 그대로)
        out = out.point(lambda v: max(0, min(255, round(128 + (v - 128) * EDGE_GAIN))))
        # 시간축 필터도 구멍을 다시 뚫는다(이웃 프레임의 구멍이 섞여 들어온다).
        # 몸에 둘러싸인 자리는 무조건 몸이므로 마지막에 한 번 더 되메운다 —
        # 29프레임 → 5프레임까지만 줄었던 이유가 이것이다(2026-09-07 실측).
        # 임계를 128로 낮춰 부른다 — 기본값(180)이면 알파 128~180짜리 좁은
        # 목으로 바깥과 이어져 있다고 봐서 안 메운다(f186에 143화소가 남았다).
        out = close_holes(out, 128)
        out.save(out_dir / fp.name)
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
    colors = []
    for o_fp, a_fp in zip(o_frames, a_frames):
        o = Image.open(o_fp).convert("RGB")
        a = Image.open(a_fp).convert("L")
        orr, og, ob = o.split()
        rgb = Image.merge("RGB", (unpremultiply(orr, pr, a),
                                  unpremultiply(og, pg, a),
                                  unpremultiply(ob, pb, a)))
        colors.append(bleed_transparent(rgb, a))

    # 색에도 시간축 5탭 저역통과를 건다(알파와 같은 필터).
    #
    # 왜 필요해졌나 — 이 노이즈는 원본 푸티지가 원래 갖고 있던 것이다(실측:
    # 구워져 있던 원본 경계 3.28 vs 지금 3.59). 배경이 영상이던 시절엔 풀·구름이
    # 같이 들끓어서 안 보였는데, 배경을 정지 이미지로 바꾸고 나니 화면에서
    # 움직이는 게 내루미뿐이라 몸통 안쪽 윤곽선의 프레임간 떨림이 그대로
    # 드러난다(2026-09-04 제보 "자글거림이 여전히 남아있어" — 실제 화면을
    # 30fps로 녹화해 재보니 떨림이 실루엣 테두리가 아니라 몸 안쪽에 퍼져 있었다).
    # 인코딩 화질로는 못 줄인다(crf16과 crf34가 같은 값).
    # 실측(전 프레임 감사): 원색 1.211 → 3탭 0.605 → 5탭 0.426, PSNR 1.2dB 손해.
    def c(i):
        return colors[i % N_FRAMES]

    for i, (o_fp, a_fp) in enumerate(zip(o_frames, a_frames)):
        a = Image.open(a_fp).convert("L")
        bands = [x.split() for x in (c(i - 2), c(i - 1), c(i), c(i + 1), c(i + 2))]
        rgb = Image.merge("RGB", [tap5(*[b[ch] for b in bands]) for ch in range(3)])
        rgb.putalpha(a)
        rgb.save(out_dir / o_fp.name)
    print(f"{variant}: {N_FRAMES}프레임 -> {out_dir}")


def main():
    build_alpha_sequence()      # 1단계: plate 차이로 실루엣
    refine_alpha_sequence()     # 2단계: 시간축 안정화
    for v in VARIANTS:
        build_variant(v)


if __name__ == "__main__":
    main()
