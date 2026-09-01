#!/usr/bin/env python3
# 내루미가 서 있던 자리를 지우는 정지 패치 PNG를 변형별로 만든다.
#
# 지울 자리(마스크)는 dusk 316프레임의 union 실루엣에서 딱 한 번만 뽑아
# 8변형에 그대로 쓴다 (변형 간 픽셀 정렬 확인됨, PLAN §1).
#
# 채우기 색은 "공간 클론"이 아니라 "시간축에서 최선의 프레임 고르기"로 뽑는다:
# 316프레임짜리 핑퐁 루프라 이 자리는 매 프레임 조금씩 다르게 가려지고
# (union≠intersection, §1), union 바깥의 24px 안전 여유는 아예 한 번도
# 안 가려진다. 그러니 화소마다 "가장 안 가려진(알파가 가장 낮은) 프레임의
# 그 변형 실제 픽셀"을 골라 쓰면 — 옆으로 450px 옮겨 붙이는 것보다 — 진짜
# 그 자리의 풀을 그대로 재사용하는 셈이라 이음매·색 어긋남이 생기지 않는다.
# (처음엔 ±450px 클론 + 행별 색보정으로 시도했으나 PSNR 30dB대에 그쳐 폐기.)
#
# 단, 316프레임 내내 한 번도 안 드러나는 몸통 핵심부는 시간축 어디에도 표본이
# 없어서 캐릭터 색이 남는다. "거기는 naeru 레이어가 늘 덮으니 안 보인다"는
# 제자리에 서 있을 때만 참이고, 폴짝하면(PLAN §4.2) 그 아래에서 내루미 모양
# 얼룩이 그대로 드러난다 — 실제로 그렇게 됐다(2026-09-01 검증). 그래서 그
# 부분만 inpaint_core()가 공간에서 따로 채운다.
import sys
from pathlib import Path
from PIL import Image, ImageChops, ImageFilter, ImageMath

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
B = HERE / "build"
sys.path.insert(0, str(HERE))
from coords import (WORK_ORIGIN, WORK_SIZE, CROP_ORIGIN, CROP_SIZE,
                     FRAME_SIZE, N_FRAMES, VARIANTS, KEY_RECT_GLOBAL)
from matte import build_alpha_sequence, keep_main_component, BODY_SEED

THRESH          = 32     # 분홍기 R-max(G,B) 임계, punch.py와 동일
# 접지 페이드 시작선. 발끝은 y1720인데 여기를 1720으로 두면 페이드가 y1694에서
# 시작해 **발을 반쯤만 지운다** — 하얀 발끝이 잔디에 얼룩으로 남고, 폴짝하면
# 몸은 떠 있는데 발자국만 땅에 남는다(2026-09-01 관측). 1745면 발을 완전히
# 지우면서 그 아래 그림자 띠는 그대로 남는다.
GROUND_Y_GLOBAL = 1745
FADE            = 26
DILATE_PX       = 24
DONOR_DX        = 1024   # WIDE 밴드에서 구조를 빌려올 x (CROP은 494~1070)
HOLE_DILATE     = 20     # 구멍을 넓혀 이음매를 깨끗한 초원 쪽으로 밀어낸다
HOLE_FEATHER    = 12


def pink_score(rgb_img):
    """R - max(G,B). ImageChops.subtract가 음수를 0으로 클램프해준다."""
    r, g, b = rgb_img.split()
    return ImageChops.subtract(r, ImageChops.lighter(g, b))


def row_gradient(size, values):
    """values[y]를 y행에 채우고 가로로 그대로 반복하는 L 이미지."""
    w, h = size
    col = Image.new("L", (1, h))
    col.putdata(values)
    return col.resize((w, h), Image.NEAREST)


def build_crop_mask():
    """패치의 알파(=지울 모양). dusk WORK 크롭 316프레임의 union 실루엣을
    닫기→24px 팽창→접지선 페이드→블러 해서 CROP box로 잘라낸다."""
    frames = sorted((B / "dusk-work").glob("*.png"))
    assert len(frames) == N_FRAMES, \
        f"dusk-work에 {len(frames)}프레임, {N_FRAMES}장 기대"

    kx0 = KEY_RECT_GLOBAL[0] - WORK_ORIGIN[0]
    ky0 = KEY_RECT_GLOBAL[1] - WORK_ORIGIN[1]
    kx1 = KEY_RECT_GLOBAL[2] - WORK_ORIGIN[0]
    ky1 = KEY_RECT_GLOBAL[3] - WORK_ORIGIN[1]
    print(f"키잉 유효구간 WORK-local: ({kx0},{ky0})-({kx1},{ky1})")

    union = Image.new("L", WORK_SIZE, 0)
    for fp in frames:
        im = Image.open(fp).convert("RGB").crop((kx0, ky0, kx1, ky1))
        hit = pink_score(im).point(lambda v: 255 if v > THRESH else 0)
        canvas = Image.new("L", WORK_SIZE, 0)
        canvas.paste(hit, (kx0, ky0))
        union = ImageChops.lighter(union, canvas)
    print("raw union bbox (WORK-local):", union.getbbox())

    # 닫기(Max9→Min9)로 잡티 정리 → 캐릭터와 안 이어진 덩어리 제거 → 24px 팽창
    # (연결성분 필터가 없으면 키잉창 안에 남은 언덕 조각이 팽창되어 패치에
    #  엉뚱한 사각 블록으로 굳는다 — 2026-09-01 실측)
    closed = union.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    closed = keep_main_component(closed, BODY_SEED)
    dilated = closed.filter(ImageFilter.MaxFilter(2 * DILATE_PX + 1))
    bbox = dilated.getbbox()
    print("dilated union bbox (WORK-local):", bbox)
    if bbox:
        gx0, gy0 = bbox[0] + WORK_ORIGIN[0], bbox[1] + WORK_ORIGIN[1]
        gx1, gy1 = bbox[2] + WORK_ORIGIN[0], bbox[3] + WORK_ORIGIN[1]
        cx0, cy0 = CROP_ORIGIN
        cx1, cy1 = cx0 + CROP_SIZE[0], cy0 + CROP_SIZE[1]
        margin = min(gx0 - cx0, cx1 - gx1, gy0 - cy0, cy1 - gy1)
        print(f"dilated union bbox (global): x{gx0}-{gx1} y{gy0}-{gy1}")
        print(f"CROP box: x{cx0}-{cx1} y{cy0}-{cy1}  margin={margin}px "
              f"({'OK' if margin >= 16 else '!! TOO TIGHT — CROP box를 키우고 index.html/matte.py와 대조할 것'})")

    # 접지선(발끝) 아래로 갈수록 마스크를 0으로 — 그림자 보존
    fade_vals = []
    for y in range(WORK_SIZE[1]):
        gy = y + WORK_ORIGIN[1]
        if gy <= GROUND_Y_GLOBAL - FADE:
            k = 1.0
        elif gy >= GROUND_Y_GLOBAL + FADE:
            k = 0.0
        else:
            k = (GROUND_Y_GLOBAL + FADE - gy) / (2.0 * FADE)
        fade_vals.append(round(k * 255))
    faded = ImageChops.multiply(dilated, row_gradient(WORK_SIZE, fade_vals))

    # 패치 자체 경계도 살짝 흐려서 주변 초원과 뭉개지듯 섞이게
    final_mask = faded.filter(ImageFilter.GaussianBlur(3))

    ox = CROP_ORIGIN[0] - WORK_ORIGIN[0]
    oy = CROP_ORIGIN[1] - WORK_ORIGIN[1]
    return final_mask.crop((ox, oy, ox + CROP_SIZE[0], oy + CROP_SIZE[1]))


def inpaint_core(filled, min_alpha, wide):
    """시간축 채우기로도 못 메우는 자리를 공간에서 채운다.

    화소마다 '가장 안 가려진 프레임'을 골라도, 316프레임 내내 한 번도 안
    드러나는 몸통 핵심부는 캐릭터 색이 그대로 남는다. 제자리에 서 있는 동안은
    naeru 레이어가 늘 그 위를 덮으므로 안 보이지만, 폴짝하면(PLAN §4.2 —
    자기 키의 13%, 4K로 64px) 그 아래에서 내루미 모양 얼룩이 그대로 드러난다.
    실제로 그렇게 됐다(2026-09-01 검증).

    채우는 방식: **같은 행**의 깨끗한 초원(WIDE 밴드 오른쪽)을 통째로 가져다
    쓰고, 두 자리의 색 차이만 구멍 안으로 확산시켜 보정한다.

    왜 도너를 통째로 쓰나 — 구멍 한가운데를 언덕–초원 경계선이 가로지른다.
    주변 색만 확산시키는 조화 보간(처음 시도)은 그 경계를 뭉개서 내루미 모양
    얼룩으로 남았고, 행별 가로 보간(그 전 시도)은 가로 줄무늬가 됐다. 도너는
    y가 같으므로 언덕·경계선·풀의 높이가 원래 맞는다 — 구조를 그대로 얻고
    색만 맞추면 된다. 색 보정량(filled-donor)은 성한 화소에서만 알 수 있으므로
    그 값을 구멍 안으로 확산시켜 매끄럽게 잇는다."""
    W, H = filled.size
    # 구멍을 그대로 쓰면 경계가 시간축 채우기의 오염된 띠와 맞닿아 내루미
    # 모양 테두리가 남는다. 20px 넓혀 이음매를 확실히 깨끗한 자리로 옮긴다
    hole  = min_alpha.point(lambda v: 255 if v > 24 else 0)  # 한 번이라도 가려진 적 있으면 불신
    hole  = hole.filter(ImageFilter.MaxFilter(2 * HOLE_DILATE + 1))
    known = ImageChops.invert(hole)
    donor = wide.crop((DONOR_DX, 0, DONOR_DX + W, H))

    # 색 보정장: 성한 자리의 (filled - donor)를 128 기준 오프셋으로 담고,
    # 그 값을 고정한 채 반복 블러해서 구멍 안쪽으로 번지게 한다
    corr = Image.merge("RGB", [
        ImageMath.lambda_eval(lambda a: a["convert"](a["F"] - a["D"] + 128, "L"), F=f, D=d)
        for f, d in zip(filled.split(), donor.split())])
    # 반경을 구멍 폭(~300px)에 맞게 크게 시작해야 보정이 한가운데까지 닿는다.
    # 28에서 시작했더니 dusk 언덕 한복판에 도너의 따뜻한 색이 그대로 남았다
    # (게이트 A: 코어 분홍기 33.8 vs 링 22.4 → 96부터 시작하면 20.1 vs 22.2)
    spread = corr.copy()
    for radius in (96, 64, 40, 24, 14, 8):
        for _ in range(4):
            spread = Image.composite(corr, spread.filter(ImageFilter.GaussianBlur(radius)),
                                     known)
    patched = Image.merge("RGB", [
        ImageMath.lambda_eval(lambda a: a["convert"](a["D"] + a["C"] - 128, "L"), D=d, C=c)
        for d, c in zip(donor.split(), spread.split())])

    return Image.composite(patched, filled, hole.filter(ImageFilter.GaussianBlur(HOLE_FEATHER)))


def best_frame_masks():
    """화소마다 "지금까지 중 알파가 가장 낮은(=가장 안 가려진) 프레임"이
    갱신되는 지점의 마스크 316(-1)장. dusk 알파에서만 계산 — 8변형에 그대로
    재사용(변형은 색만 바뀌지 프레임별로 가려지는 모양은 같다)."""
    a_frames = sorted((B / "alpha").glob("*.png"))
    assert len(a_frames) == N_FRAMES
    best_alpha = Image.open(a_frames[0]).convert("L")
    masks = []
    for fp in a_frames[1:]:
        a = Image.open(fp).convert("L")
        better = ImageChops.subtract(best_alpha, a).point(lambda v: 255 if v > 0 else 0)
        masks.append(better)
        best_alpha = ImageChops.darker(best_alpha, a)
    return masks, best_alpha


def temporal_fill(variant, masks):
    """화소마다 best_frame_masks가 고른 프레임의 그 변형 실제 픽셀을 쓴다."""
    o_frames = sorted((B / "O" / variant).glob("*.png"))
    assert len(o_frames) == N_FRAMES, f"O/{variant}에 {len(o_frames)}프레임"
    filled = Image.open(o_frames[0]).convert("RGB")
    for fp, better in zip(o_frames[1:], masks):
        o = Image.open(fp).convert("RGB")
        filled = Image.composite(o, filled, better)
    return filled


def save_variant(variant, crop_mask, masks, min_alpha):
    filled = temporal_fill(variant, masks)
    wide = Image.open(B / "first-wide" / f"{variant}.png").convert("RGB")
    filled = inpaint_core(filled, min_alpha, wide)

    patch = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
    piece = filled.convert("RGBA")
    piece.putalpha(crop_mask)
    patch.paste(piece, CROP_ORIGIN)

    out = REPO / "img" / f"plate-{variant}.png"
    patch.save(out, optimize=True)
    print(f"{variant}: {out.name}  {out.stat().st_size / 1024:.0f}KB")


def main():
    build_alpha_sequence()   # build/alpha/ 채움 — matte.py와 공유하는 계산
    crop_mask = build_crop_mask()
    crop_mask.save(B / "plate-alpha-debug.png")
    masks, min_alpha = best_frame_masks()
    min_alpha.save(B / "plate-minalpha-debug.png")
    for v in VARIANTS:
        save_variant(v, crop_mask, masks, min_alpha)


if __name__ == "__main__":
    main()
