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
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageMath

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
B = HERE / "build"
sys.path.insert(0, str(HERE))
from coords import (WORK_ORIGIN, WORK_SIZE, CROP_ORIGIN, CROP_SIZE, CTX_ORIGIN,
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
HOLE_DILATE     = 20     # 구멍을 넓혀 이음매를 깨끗한 초원 쪽으로 밀어낸다
HOLE_FEATHER    = 12
# 머리 위 구간(global y1400 위)은 무조건 합성으로 채운다.
# 키잉창 상단이 1394라 머리 꼭대기(1392부터 시작)가 2~3px 잘리는데, 잘린 그
# 조각은 min_alpha가 0이라 구멍으로 안 잡히고 **프레임 1의 픽셀 그대로** 남는다.
# 제자리에선 스프라이트 머리가 덮어 안 보이지만, 점프하면 머리가 있던 자리에
# 분홍 조각이 남는다(2026-09-01 제보: "점프할 때 머리쪽 누끼가 깨진다").
# 이 구간을 통째로 합성해두면 조각이 사라지고, 스프라이트 쪽 머리 꼭대기는
# matte.py의 링 복원이 되찾아온다(그 자리 plate가 깨끗해야 링이 작동한다).
HEAD_BAND_BOT   = 1400


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


def run_lama():
    """LaMa 인페인팅을 전용 venv에서 돌린다(torch가 필요해 시스템 파이썬엔 없다).
    build/plate-alpha-debug.png(덮개 마스크)를 읽어 build/lama/<변형>.png를 만든다."""
    py = HERE / ".venv" / "bin" / "python"
    assert py.exists(), (
        f"LaMa용 venv가 없다: {py}\n"
        "  python3 -m venv tools/naeru-split/.venv\n"
        "  tools/naeru-split/.venv/bin/pip install torch pillow numpy opencv-python-headless\n"
        "  tools/naeru-split/.venv/bin/pip install --no-deps simple-lama-inpainting")
    subprocess.run([str(py), str(HERE / "lama_fill.py")], check=True)


def inpaint_core(filled, min_alpha, lama):
    """한 번도 안 드러난 자리를 LaMa 결과로 갈아끼운다.

    링(316프레임 중 한 번이라도 드러난 자리)은 시간축 채우기가 **진짜 배경
    화소**를 갖고 있으므로 그쪽이 낫다. 몸통 핵심부만 모델에 맡긴다.

    이전에는 옆에서 떠온 조각(도너)을 색 맞춰 붙였는데, 구조는 맞아도 뿌옇고
    도너에 있던 나무·풀숲이 딸려와 "물감 지운 자국"으로 보였다(2026-09-04).
    LaMa는 언덕 능선과 풀선을 이어 그려준다 — 같은 자리 비교로 확인."""
    hole = min_alpha.point(lambda v: 255 if v > 24 else 0)   # 한 번이라도 가려졌으면 불신
    hole = hole.filter(ImageFilter.MaxFilter(2 * HOLE_DILATE + 1))
    # 머리 위(y1400 위)는 키잉창에 잘려 min_alpha가 0이라 구멍으로 안 잡힌다.
    # 그대로 두면 프레임 1의 머리 조각이 남아 점프할 때 드러난다
    head = Image.new("L", filled.size, 0)
    ImageDraw.Draw(head).rectangle(
        [0, 0, filled.size[0], HEAD_BAND_BOT - CROP_ORIGIN[1]], fill=255)
    hole = ImageChops.lighter(hole, head)
    return Image.composite(lama, filled, hole.filter(ImageFilter.GaussianBlur(HOLE_FEATHER)))


def temporal_fill(variant):
    """그 화소가 **안 가려진 프레임들의 평균**으로 배경을 만든다.

    처음엔 화소마다 "가장 안 가려진 한 프레임"을 골라 썼는데, 이웃 화소가 서로
    수백 프레임 떨어진 값에서 오다 보니 잡티와 세로 줄무늬가 생겼다 — 제자리에서
    캐릭터를 두르고 보이는 그 얼룩이 이것이었다(2026-09-04 제보). 평균은 이웃끼리
    같은 표본 집합을 공유해서 매끈하고, 배경이 루프 내내 거의 안 움직이므로
    (프레임간 mean 0.28, 반주기 드리프트 1.38) 흐려지지도 않는다.

    한 번도 안 드러난 화소는 표본이 0개다 → 그 자리는 inpaint_core가 채운다."""
    o_frames = sorted((B / "O" / variant).glob("*.png"))
    a_frames = sorted((B / "alpha").glob("*.png"))
    assert len(o_frames) == len(a_frames) == N_FRAMES, f"O/{variant} 프레임 수"

    W, H = CROP_SIZE
    acc = [Image.new("I", (W, H), 0) for _ in range(3)]
    cnt = Image.new("I", (W, H), 0)
    for o_fp, a_fp in zip(o_frames, a_frames):
        free = Image.open(a_fp).convert("L").point(lambda v: 0 if v > 24 else 1)
        bands = Image.open(o_fp).convert("RGB").split()
        for i in range(3):
            acc[i] = ImageMath.lambda_eval(
                lambda a: a["convert"](a["A"] + a["V"] * a["M"], "I"),
                A=acc[i], V=bands[i], M=free)
        cnt = ImageMath.lambda_eval(
            lambda a: a["convert"](a["C"] + a["M"], "I"), C=cnt, M=free)

    return Image.merge("RGB", [
        ImageMath.lambda_eval(
            lambda a: a["convert"](a["A"] / a["max"](a["C"], 1), "L"), A=acc[i], C=cnt)
        for i in range(3)])


def min_alpha_map():
    """화소별 최소 알파 = 그 자리가 316프레임 내내 얼마나 가려졌나."""
    best = None
    for fp in sorted((B / "alpha").glob("*.png")):
        a = Image.open(fp).convert("L")
        best = a if best is None else ImageChops.darker(best, a)
    return best


def save_variant(variant, crop_mask, min_alpha):
    filled = temporal_fill(variant)
    lama = Image.open(B / "lama" / f"{variant}.png").convert("RGB").crop(
        (CROP_ORIGIN[0] - CTX_ORIGIN[0], CROP_ORIGIN[1] - CTX_ORIGIN[1],
         CROP_ORIGIN[0] - CTX_ORIGIN[0] + CROP_SIZE[0],
         CROP_ORIGIN[1] - CTX_ORIGIN[1] + CROP_SIZE[1]))
    filled = inpaint_core(filled, min_alpha, lama)

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
    run_lama()                  # 덮개 마스크를 읽어 build/lama/를 채운다
    min_alpha = min_alpha_map()
    min_alpha.save(B / "plate-minalpha-debug.png")
    for v in VARIANTS:
        save_variant(v, crop_mask, min_alpha)


if __name__ == "__main__":
    main()
