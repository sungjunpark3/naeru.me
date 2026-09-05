#!/usr/bin/env python3
# 혀를 몸에서 떼어낸다 — "혀를 집어넣었다 빼는" 동작을 DOM으로 만들기 위한 자산.
#
# 왜 이렇게 하나 —
#   316프레임 루프 어디에도 혀가 들어간 프레임이 없다(혀 영역 프레임간 변화
#   평균 1.81, 실루엣 화소수 75,375~84,075로 혀가 빠질 여지가 없다). 재생
#   구간·속도로는 못 만들고, 혀를 지운 몸을 새로 그려야 한다.
#
#   혀는 몸과 **같은 분홍**이라 색으로는 못 가른다. 어두운 윤곽선으로만
#   갈리는데 전역 임계로는 아래쪽 그늘까지 잡힌다. 그래서 손으로 다각형을
#   잡았다(POLY). 입의 어두운 선은 일부러 남긴다 — 혀가 들어가도 입은 열려
#   있어야 "혀를 집어넣은 얼굴"로 읽힌다.
#
#   지운 자리는 LaMa로 메운다(배경에서 내루미를 지울 때와 같은 venv·모델).
#   혀 뒤에는 팔과 배 줄무늬가 있는데 둘 다 단순한 형태라 잘 이어진다.
#
# **왜 한 프레임만 만드나** —
#   개그는 1초 안쪽이고 루프가 기준 프레임(79)에 왔을 때만 시작한다. 그
#   순간 영상을 세우고 정지본으로 바꿔치기하므로, 필요한 건 그 한 프레임의
#   "혀 없는 몸"과 "혀"뿐이다. 전 프레임을 인페인팅하면 변형당 영상이 한 벌씩
#   더 생기고(+7MB) 추론이 1,272번이 되는데, 얻는 건 개그 1초 동안 몸이
#   계속 숨쉬는 것뿐이라 값이 안 맞는다.
#
#   (전 프레임을 하려면 마스크를 머리 자세에 맞춰 옮겨야 한다 — 정지 마스크는
#   안 된다. 루프 안에서 자세가 바뀌어서 f132에서는 얼굴을 지워버렸다.
#   머리 추적은 입 위쪽 창(HEAD)으로 dx·dy·회전을 맞추면 되고, 8변형이 같은
#   푸티지의 색보정본이라 추적은 159프레임 한 번이면 된다. 실측해 뒀다.)
#
# 산출물:
#   img/naeru-<변형>-nt.png  혀를 지운 기준 프레임 (알파 = 원본 그대로)
#   img/tongue-<변형>.png    혀만 (원본 색 + 차이로 뽑은 알파)
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
B = HERE / "build"
sys.path.insert(0, str(HERE))
from coords import CROP_SIZE, VARIANTS

REF = 79                        # 혀가 가장 안정된 프레임. index.html의 TONGUE_FRAME과 같아야 한다

# 크롭 좌표계(576×496)에서 손으로 잡은 혀 다각형. 두 개인 이유:
#
#   INPAINT — **윗변이 입 아래(y≈174)에 있다.** 입까지 덮으면 LaMa가 입술선을
#     잃고 큼직한 검은 덩어리를 그린다(2026-09-05 제보 "몸부분 텍스쳐가 이상해").
#     입 위쪽 원본을 그대로 두면 열린 입이 살아서 "혀를 집어넣은 얼굴"이 된다.
#   CUT — 잘라낼 혀. 입 안쪽 뿌리까지 포함해야 혀가 입에서 나오는 것처럼 보인다.
#     뿌리 구간(y152~174)은 nt에도 원본 그대로 남지만 겹치면 같은 화소라
#     제자리에선 원본과 똑같고, 혀가 들어가도 그 자국은 실제 크기에서 안 보인다.
INPAINT_POLY = [(186, 176), (250, 172), (284, 182), (266, 204), (244, 244),
                (220, 290), (196, 322), (160, 324), (138, 300), (135, 248),
                (149, 202), (168, 182)]
CUT_POLY = [(190, 152), (248, 148), (282, 168), (266, 198), (244, 242),
            (220, 288), (196, 322), (160, 324), (138, 300), (135, 248),
            (149, 200), (170, 168)]
DILATE = 13                     # 인페인트 마스크: 윤곽선까지 확실히 덮는다
ERODE = 5                       # 혀 컷아웃: 다각형을 조금 줄여 몸 화소를 안 물고 나온다
FEATHER = 1.6

# 혀가 왼팔을 거의 다 가리고 있어서, 혀를 지우면 원본에 **없는 팔**을 그려야
# 한다. LaMa는 그 자리에 배 줄무늬를 늘려 발라놨다. 실루엣(알파)은 안 바뀌므로
# 필요한 건 팔과 몸을 가르는 윤곽선과 그 왼쪽의 팔 색뿐이다. 사용자가 준
# 참고그림에서 왼팔은 옆구리에 붙은 통통한 로브다.
ARM_EDGE = [(178, 186), (166, 216), (157, 252), (155, 288), (166, 314), (188, 330)]
ARM_TAIL = [(198, 338), (150, 342), (116, 300), (110, 246), (126, 192), (152, 176)]


def draw_arm(base, sp, alpha, arm_shape, arm_line):
    """팔 색은 실루엣 왼쪽 가장자리(원본에 남아 있는 팔 조각)에서 가져와 가로로
    늘린다 — 세로 방향 밝기 변화가 살아서 통통한 느낌이 남는다. 변형마다 색이
    다르므로 변형별로 다시 뽑는다."""
    a = np.asarray(alpha, np.uint8)
    src = np.asarray(sp.convert("RGB"), np.float32)
    fill = src.copy()
    for y in range(src.shape[0]):
        xs = np.nonzero(a[y] > 200)[0]
        if len(xs) == 0:
            continue
        fill[y, :] = src[y, xs.min():xs.min() + 14].mean(0)
    fill = Image.fromarray(fill.astype(np.uint8)).filter(ImageFilter.GaussianBlur(7))

    inside = (a > 200).astype(np.uint8)
    shape = Image.fromarray((np.asarray(arm_shape, np.uint8) * inside)) \
                 .filter(ImageFilter.GaussianBlur(1.4))
    out = Image.composite(fill, base, shape)

    stroke = tuple(int(x) for x in np.percentile(
        np.asarray(base, np.float32)[240:300, 300:360].reshape(-1, 3), 6, axis=0))
    line = Image.fromarray((np.asarray(arm_line, np.uint8) * inside)) \
                .filter(ImageFilter.GaussianBlur(1.5))
    return Image.composite(Image.new("RGB", base.size, stroke), out, line)


def main():
    poly = Image.new("L", CROP_SIZE, 0)
    ImageDraw.Draw(poly).polygon(INPAINT_POLY, fill=255)
    mask = poly.filter(ImageFilter.MaxFilter(DILATE))       # 지울 범위
    mask.save(B / "tongue-mask.png")
    cutpoly = Image.new("L", CROP_SIZE, 0)
    ImageDraw.Draw(cutpoly).polygon(CUT_POLY, fill=255)
    arm_shape = Image.new("L", CROP_SIZE, 0)
    ImageDraw.Draw(arm_shape).polygon(ARM_EDGE + ARM_TAIL, fill=255)
    arm_line = Image.new("L", CROP_SIZE, 0)
    ImageDraw.Draw(arm_line).line(ARM_EDGE, fill=200, width=4, joint="curve")
    # 잘라낼 범위는 팽창 전 다각형을 조금 줄인 것. **차이(|원본-인페인팅|)로
    # 알파를 만들면 안 된다** — 혀와 메워진 몸이 거의 같은 색이라 차이가
    # 윤곽선에만 잡혀서 속이 빈 혀가 나온다(2026-09-05 실측).
    cut = cutpoly.filter(ImageFilter.MinFilter(2 * ERODE + 1)) \
                 .filter(ImageFilter.GaussianBlur(FEATHER))

    from simple_lama_inpainting import SimpleLama
    lama = SimpleLama()

    for v in VARIANTS:
        src = sorted((B / f"naeru-{v}").glob("*.png"))[REF]
        sp = Image.open(src).convert("RGBA")
        rgb, alpha = sp.convert("RGB"), sp.getchannel("A")

        filled = lama(rgb, mask).crop((0, 0, CROP_SIZE[0], CROP_SIZE[1]))
        nt = draw_arm(Image.composite(filled, rgb, mask), sp, alpha,
                      arm_shape, arm_line)
        # 혀는 실루엣 안쪽이라 알파가 안 바뀐다 — 원본 알파를 그대로 쓴다
        nt.putalpha(alpha)
        nt.save(REPO / "img" / f"naeru-{v}-nt.png")

        t_alpha = ImageChops.multiply(cut, alpha)
        tongue = rgb.copy()
        tongue.putalpha(t_alpha)
        tongue.save(REPO / "img" / f"tongue-{v}.png")

        cov = np.asarray(t_alpha, np.uint8)
        print(f"{v}: 혀 화소 {int((cov > 128).sum()):6d}  -> naeru-{v}-nt.png / tongue-{v}.png")


if __name__ == "__main__":
    main()
