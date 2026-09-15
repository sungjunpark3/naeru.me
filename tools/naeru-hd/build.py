#!/usr/bin/env python3
"""뉴트럴 포즈를 8배 복원하고, 확대 때 드러나는 누끼 계단과 색 번짐을 정리한다."""
import argparse
import hashlib
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image, ImageFilter

from vendor.srvgg_arch import SRVGGNetCompact

HERE = Path(__file__).resolve().parent
VARIANTS = ["dawn", "day", "dusk", "night",
            "dawn-rain", "day-rain", "dusk-rain", "night-rain"]
MODEL_SHA256 = "b8a8376811077954d82ca3fcf476f1ac3da3e8a68a4f4d71363008000a18b75d"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=VARIANTS)
parser.add_argument("--output", type=Path, default=HERE.parents[1] / "img")
parser.add_argument("--scale", type=int, choices=[4, 8], default=8)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)

model_path = HERE / "build" / "realesr-animevideov3.pth"
assert hashlib.sha256(model_path.read_bytes()).hexdigest() == MODEL_SHA256
torch.set_num_threads(4)
device = "mps" if torch.backends.mps.is_available() else "cpu"
model = SRVGGNetCompact().to(device).eval()
model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True)["params"])
print(f"Real-ESRGAN animevideov3 / {device} / {args.scale}x", flush=True)


def restore_colors(rgb):
    """24px 겹친 타일로 추론한다. 내부 경계는 모델의 18px 수용 영역 밖이다."""
    height, width = rgb.shape[:2]
    output = np.empty((height * 4, width * 4, 3), np.uint8)
    tile, pad = 384, 24
    for y in range(0, height, tile):
        for x in range(0, width, tile):
            right, bottom = min(x + tile, width), min(y + tile, height)
            x0, y0 = max(0, x - pad), max(0, y - pad)
            x1, y1 = min(width, right + pad), min(height, bottom + pad)
            crop = rgb[y0:y1, x0:x1]
            tensor = torch.from_numpy(crop.transpose(2, 0, 1).copy()).float()[None] / 255
            with torch.inference_mode():
                restored = model(tensor.to(device)).clamp(0, 1).cpu()
            pixels = np.rint(restored[0].permute(1, 2, 0).numpy() * 255).astype(np.uint8)
            output[y * 4:bottom * 4, x * 4:right * 4] = pixels[
                (y - y0) * 4:(bottom - y0) * 4, (x - x0) * 4:(right - x0) * 4]
    return output

for variant in args.variants:
    started = time.monotonic()
    source = Image.open(HERE / "source" / f"naeru-{variant}.png").convert("RGBA")
    assert source.size == (576, 496)
    rgba = np.asarray(source)
    rgb = rgba[:, :, :3].copy()
    alpha = rgba[:, :, 3]

    # 투명 픽셀의 숨은 잔디 RGB를 모델에 주면 윤곽에 녹색 선이 생길 수 있다.
    # 아주 옅은 경계의 잔여색만 연결한다. 실제 반투명 외곽선은 보존한다.
    opaque = alpha >= 240
    _, labels = cv2.distanceTransformWithLabels(
        (~opaque).astype(np.uint8), cv2.DIST_L2, 5,
        labelType=cv2.DIST_LABEL_PIXEL)
    extended = rgb[opaque][labels - 1]
    weight = np.clip(alpha.astype(np.float32) / 32, 0, 1)[:, :, None]
    rgb = np.rint(rgb * weight + extended * (1 - weight)).astype(np.uint8)

    colors = restore_colors(rgb)
    if args.scale == 8:
        # 첫 4배 복원에서 찾은 선을 2배 크기의 중간본에 모아 한 번 더 복원한다.
        # 최종 WebP를 단순 확대하는 것과 달리 두 번째 추론이 선과 명암을 다시 푼다.
        middle = Image.fromarray(colors).resize((1152, 992), Image.Resampling.LANCZOS)
        detail = restore_colors(np.asarray(middle))
        soft = np.asarray(Image.fromarray(colors).resize((4608, 3968), Image.Resampling.LANCZOS))
        # 두 번째 복원의 얇은 선이 지나치게 진해지지 않도록 원래 회화 질감을 섞는다.
        colors = np.rint(detail.astype(np.float32) * .7 + soft * .3).astype(np.uint8)

    # 실루엣의 중심선을 유지하면서 원본 픽셀 단위의 계단을 둥글게 연결한다.
    # 넓은 반투명 띠를 좁혀 큰 화면의 회색 테두리를 없앤다.
    size = (576 * args.scale, 496 * args.scale)
    edge = source.getchannel("A").resize(size, Image.Resampling.LANCZOS)
    edge = edge.filter(ImageFilter.GaussianBlur(.65 * args.scale))
    coverage = np.clip((np.asarray(edge, np.float32) - 64) / 128, 0, 1)
    coverage = coverage * coverage * (3 - 2 * coverage)
    high_alpha = Image.fromarray(np.rint(coverage * 255).astype(np.uint8))
    colors[np.asarray(high_alpha) == 0] = 0
    result = Image.fromarray(colors)
    result.putalpha(high_alpha)
    target = args.output / f"naeru-{variant}-hd.webp"
    # 부드러운 면은 WebP 97에서 작게 저장된다. 색만 압축하고
    # 알파는 무손실인지 아래에서 실제 저장본을 대조한다.
    result.save(target, quality=97, method=6)

    saved = Image.open(target).convert("RGBA")
    assert saved.size == size
    assert np.array_equal(np.asarray(saved.getchannel("A")), np.asarray(high_alpha))
    assert not np.any(np.asarray(saved.getchannel("A"))[[0, -1], :])
    assert not np.any(np.asarray(saved.getchannel("A"))[:, [0, -1]])
    print(f"{target.name}: {target.stat().st_size / 1024:.0f} KiB, "
          f"{time.monotonic() - started:.1f}s, alpha PASS", flush=True)
