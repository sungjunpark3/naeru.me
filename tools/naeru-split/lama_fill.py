#!/usr/bin/env python3
# 내루미를 지운 자리를 LaMa 인페인팅으로 채운다. plate.py가 서브프로세스로 부른다.
#
# 왜 모델을 쓰나 — 이 자리는 언덕·풀선·꽃이 섞인 회화풍 배경이고, 캐릭터가
# 316프레임 내내 같은 자리에 서 있어서 시간축에서 가져올 표본이 없다. 옆에서
# 떠온 조각을 색 맞춰 붙이는 방식(도너+확산)은 구조는 맞지만 뿌옇고, 도너에
# 있던 나무·풀숲이 딸려와 "물감 지운 자국"으로 보였다(2026-09-04 제보).
# LaMa는 언덕 능선과 풀선을 이어 그려준다.
#
# **전용 venv가 필요하다**(torch ~900MB, .venv/는 gitignore).
#   python3 -m venv tools/naeru-split/.venv
#   tools/naeru-split/.venv/bin/pip install torch pillow numpy opencv-python-headless
#   tools/naeru-split/.venv/bin/pip install --no-deps simple-lama-inpainting
# simple-lama가 pillow<10을 고집하므로 --no-deps로 넣는다(신 pillow에서도 동작).
import subprocess
import sys
from pathlib import Path

from PIL import Image
from simple_lama_inpainting import SimpleLama

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
B = HERE / "build"
sys.path.insert(0, str(HERE))
from coords import CROP_ORIGIN, CROP_SIZE, CTX_ORIGIN, CTX_SIZE, VARIANTS

FRAME_N    = 79          # 어느 프레임이든 배경은 같다. 캐릭터가 가장 안 흔들린 언저리


def main():
    mask_crop = Image.open(B / "plate-alpha-debug.png").convert("L")
    # 마스크는 CROP 좌표계 → 맥락 좌표계로 옮긴다. 지울 곳이 255
    mask = Image.new("L", CTX_SIZE, 0)
    mask.paste(mask_crop.point(lambda v: 255 if v > 8 else 0),
               (CROP_ORIGIN[0] - CTX_ORIGIN[0], CROP_ORIGIN[1] - CTX_ORIGIN[1]))
    print(f"인페인트 마스크 {mask.histogram()[255]}화소")

    out_dir = B / "lama"
    out_dir.mkdir(exist_ok=True)
    lama = SimpleLama()
    for v in VARIANTS:
        ctx = B / "lama" / f"ctx-{v}.png"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(REPO / "img" / f"meadow-{v}.mp4"),
             "-vf", f"select=eq(n\\,{FRAME_N}),"
                    f"crop={CTX_SIZE[0]}:{CTX_SIZE[1]}:{CTX_ORIGIN[0]}:{CTX_ORIGIN[1]}",
             "-vsync", "0", "-frames:v", "1", str(ctx)], check=True)
        res = lama(Image.open(ctx).convert("RGB"), mask)
        # LaMa는 8의 배수로 패딩해서 돌려주므로 맥락 크기로 자른다
        res.crop((0, 0, CTX_SIZE[0], CTX_SIZE[1])).save(out_dir / f"{v}.png")
        ctx.unlink()
        print(f"  {v} 완료")


if __name__ == "__main__":
    main()
