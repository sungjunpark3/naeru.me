#!/usr/bin/env python3
"""가을 낮 배경에서 하늘 앞의 나무·산등선·들판 레이어를 만든다.

day-outline.jpg는 사용자가 하늘 영역을 표시한 참고본이다. 보존한 마스크는
built-in imagegen으로 실제 나무와 산등선 경계를 찾은 뒤 알파만 추출했다.
출력의 색과 붓질은 생성 이미지에서 가져오지 않고 배포 중인 배경 원본의
픽셀을 그대로 사용한다.
"""
from pathlib import Path

from PIL import Image, ImageChops


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SIZE = (3840, 2160)

source = Image.open(REPO / "img/bg-day-autumn.jpg").convert("RGB")
assert source.size == SIZE

mask = Image.open(HERE / "source/day-landscape-mask.png").convert("L")
mask = mask.resize(SIZE, Image.Resampling.LANCZOS)
# 생성 마스크의 불투명 내부값 253을 255로 정규화하되 경계의 연속 알파는
# 유지한다. 254~255는 리샘플링 중 생긴 오버슈트이므로 그대로 255로 둔다.
mask = mask.point(lambda value: 0 if value <= 4 else
                  255 if value >= 245 else round((value - 4) * 255 / 241))
assert mask.getextrema() == (0, 255)

landscape = source.convert("RGBA")
landscape.putalpha(mask)
output = REPO / "img/landscape-day-autumn.webp"
landscape.save(output, lossless=True, exact=True, method=6)

# WebP 왕복 뒤에도 불투명한 풍경의 원본 픽셀이 달라지지 않아야 한다.
decoded = Image.open(output).convert("RGBA")
opaque = decoded.getchannel("A").point(lambda value: 255 if value == 255 else 0)
difference = ImageChops.difference(decoded.convert("RGB"), source)
visible_difference = Image.composite(difference, Image.new("RGB", SIZE), opaque)
assert visible_difference.getbbox() is None

# 원본 배경 위에 같은 원본 픽셀을 얹으면 정지 화면은 정확히 같아야 한다.
composite = Image.alpha_composite(source.convert("RGBA"), decoded).convert("RGB")
assert ImageChops.difference(composite, source).getbbox() is None
print(f"landscape day/autumn: {output.stat().st_size / 1024:.0f} KiB")
