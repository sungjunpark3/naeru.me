#!/usr/bin/env python3
# img/bg-<변형>.jpg 재생성 — plate를 원본 첫 프레임에 얹은 것.
#
# 이 파일은 repaint.py의 **입력**이고 런타임엔 안 쓴다(런타임은 bg-<변형>-<계절>).
# plate를 다시 구우면 반드시 같이 돌리고, 이어서 tools/season/repaint.py도 돌린다.
import sys
from pathlib import Path
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
B = HERE / "build"
sys.path.insert(0, str(HERE))
from coords import CROP_ORIGIN, CROP_SIZE, FRAME_SIZE, VARIANTS

for v in VARIANTS:
    frame = sorted((B / "O" / v).glob("*.png"))[0]
    base = Image.open(REPO / "img" / f"sky-{v}.jpg").convert("RGBA")
    assert base.size == FRAME_SIZE, f"sky-{v} 크기 {base.size}"
    plate = Image.open(REPO / "img" / f"plate-{v}.png").convert("RGBA")
    out = Image.alpha_composite(base, plate).convert("RGB")
    out.save(REPO / "img" / f"bg-{v}.jpg", quality=92, subsampling=0, optimize=True)
    print(f"  bg-{v}.jpg")
