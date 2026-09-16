#!/usr/bin/env python3
"""근접용 얇은 선 원화를 크롭 좌표에 정렬하고 네 시간대의 조명을 맞춘다.

source/naeru-close-day.png: built-in imagegen으로 기존 day HD를 편집한 원화.
제작 프롬프트:
Edit target: the provided transparent cartoon character sprite. Change only the
line treatment for a large close-up view. The gray-brown outline around its head,
left cheek and tail is currently an excessively wide band. Replace the inner part
of those thick bands with continuation of the adjoining pink or pale highlighted
skin, leaving a delicate thin contour at the original outer edge. Likewise reduce
thick drawn separators around arms and tongue, preserving the mouth interior and
all actual shaded surfaces. Keep the exact outer silhouette, pose, proportions,
eye shapes, face expression, colors, soft cel shading, tail shape, feet positions,
canvas framing and transparent margins unchanged. Do not shrink or erode the
silhouette, make eyes smaller, crop, move the character, add details, add shadows,
or sharpen with halos. Produce a refined thin-lined version of the same image
suitable for filling a screen, with genuinely transparent background.
Preserve the input resolution if possible.
"""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SIZE = (4608, 3968)
source = Image.open(HERE / "source" / "naeru-close-day.png").convert("RGBA")
rgba = np.asarray(source).copy()
alpha = rgba[:, :, 3]

# 생성된 투명 여백의 작은 점만 제거한다. 캐릭터 안쪽을 침식하지 않는다.
count, labels, stats, _ = cv2.connectedComponentsWithStats((alpha >= 128).astype(np.uint8))
main = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
support = cv2.dilate((labels == main).astype(np.uint8), np.ones((5, 5), np.uint8))
alpha[support == 0] = 0
rgba[alpha == 0] = 0
source = Image.fromarray(rgba)

# 영상과 같은 발끝·머리 높이를 유지한다. 여백까지 확대하지 않고 실루엣으로 맞춘다.
reference = Image.open(REPO / "img" / "naeru-day-hd.webp").convert("RGBA")
target_box = reference.getchannel("A").point(lambda x: 255 if x >= 128 else 0).getbbox()
source_box = source.getchannel("A").point(lambda x: 255 if x >= 128 else 0).getbbox()
sx = (target_box[2] - target_box[0]) / (source_box[2] - source_box[0])
sy = (target_box[3] - target_box[1]) / (source_box[3] - source_box[1])
visible = source.getchannel("A").getbbox()
crop = source.crop(visible)
crop = crop.convert("RGBa").resize(
    (round(crop.width * sx), round(crop.height * sy)), Image.Resampling.LANCZOS
).convert("RGBA")
offset = (round(target_box[0] + (visible[0] - source_box[0]) * sx),
          round(target_box[1] + (visible[1] - source_box[1]) * sy))
# 실루엣 맞춤 뒤 두 눈의 중심이 원본보다 약 4 원본 픽셀 왼쪽이었다.
# 전신을 같은 양만큼 이동해 얼굴 내부의 비율을 바꾸지 않고 눈 위치를 맞춘다.
offset = (offset[0] + 32, offset[1])
portrait = Image.new("RGBA", SIZE)
portrait.paste(crop, offset)
colors = np.asarray(portrait, dtype=np.float32)[:, :, :3]
final_alpha = portrait.getchannel("A")

# 기존 네 시간대는 같은 원화의 조명 변형이다. 확실한 몸 안쪽에서 색 대응을
# 구해 새 원화에만 적용한다. 생성기를 시간대마다 다시 호출해 형태가 달라지는
# 것을 피하고, 투명도·윤곽선 위치는 네 장 모두 동일하게 유지한다.
day = np.asarray(Image.open(HERE / "source" / "naeru-day.png"), dtype=np.float32)
mask = cv2.erode((day[:, :, 3] == 255).astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
x = day[:, :, :3][mask] / 255
design = np.column_stack((x, np.ones(len(x))))
for variant in ["day", "dawn", "dusk", "night"]:
    if variant == "day":
        adjusted = colors
        error = 0
    else:
        original = np.asarray(Image.open(HERE / "source" / f"naeru-{variant}.png"), dtype=np.float32)
        y = original[:, :, :3][mask] / 255
        matrix = np.linalg.lstsq(design, y, rcond=None)[0]
        # 새 그림의 갈색 선은 원래 색 표본 밖일 수 있다. 조명 변환의 음수
        # 외삽을 검정으로 잘라 버리지 않고, 해당 시간대의 실제 암부색에 잇는다.
        dark = np.median(y[x.mean(axis=1) <= np.quantile(x.mean(axis=1), .015)], axis=0)
        error = np.mean(np.abs(np.maximum(design @ matrix, dark) - y)) * 255
        adjusted = colors @ matrix[:3] + matrix[3] * 255
        adjusted = np.maximum(adjusted, dark * 255)
    pixels = np.rint(np.clip(adjusted, 0, 255)).astype(np.uint8)
    pixels[np.asarray(final_alpha) == 0] = 0
    result = Image.fromarray(pixels)
    result.putalpha(final_alpha)
    target = REPO / "img" / f"naeru-{variant}-close.webp"
    result.save(target, quality=97, method=6)
    saved = Image.open(target).convert("RGBA")
    assert saved.size == SIZE
    assert np.array_equal(np.asarray(saved.getchannel("A")), np.asarray(final_alpha))
    print(f"{target.name}: {target.stat().st_size / 1024:.0f} KiB, "
          f"lighting MAE {error:.2f}/255, alpha PASS", flush=True)
