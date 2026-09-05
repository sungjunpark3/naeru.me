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

# 크롭 좌표계(576×496)에서 손으로 잡은 혀 다각형
POLY = [(190, 152), (248, 148), (282, 168), (266, 198), (244, 242),
        (220, 288), (196, 322), (160, 324), (138, 300), (135, 248),
        (149, 200), (170, 168)]
DILATE = 13                     # 인페인트 마스크: 윤곽선까지 확실히 덮는다
ERODE = 5                       # 혀 컷아웃: 다각형을 조금 줄여 몸 화소를 안 물고 나온다
FEATHER = 1.6


def main():
    poly = Image.new("L", CROP_SIZE, 0)
    ImageDraw.Draw(poly).polygon(POLY, fill=255)
    mask = poly.filter(ImageFilter.MaxFilter(DILATE))       # 지울 범위
    mask.save(B / "tongue-mask.png")
    # 잘라낼 범위는 팽창 전 다각형을 조금 줄인 것. **차이(|원본-인페인팅|)로
    # 알파를 만들면 안 된다** — 혀와 메워진 몸이 거의 같은 색이라 차이가
    # 윤곽선에만 잡혀서 속이 빈 혀가 나온다(2026-09-05 실측).
    cut = poly.filter(ImageFilter.MinFilter(2 * ERODE + 1)) \
              .filter(ImageFilter.GaussianBlur(FEATHER))

    from simple_lama_inpainting import SimpleLama
    lama = SimpleLama()

    for v in VARIANTS:
        src = sorted((B / f"naeru-{v}").glob("*.png"))[REF]
        sp = Image.open(src).convert("RGBA")
        rgb, alpha = sp.convert("RGB"), sp.getchannel("A")

        filled = lama(rgb, mask).crop((0, 0, CROP_SIZE[0], CROP_SIZE[1]))
        nt = Image.composite(filled, rgb, mask)
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
