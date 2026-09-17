#!/usr/bin/env python3
"""정지 그림의 선을 복원한 뒤 8배로 확대하고, 근접용 누끼 경계를 정리한다."""
import argparse
import hashlib
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image, ImageFilter

from vendor.srvgg_arch import SRVGGNetCompact
from vendor.rrdbnet_arch import RRDBNet

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "naeru-split"))
from eyes import locate_eye, replace_eye

eye_patch = locate_eye(Image.open(HERE / "source" / "naeru-day.png"))
VARIANTS = ["dawn", "day", "dusk", "night",
            "dawn-rain", "day-rain", "dusk-rain", "night-rain"]
MODEL_SHA256 = "b8a8376811077954d82ca3fcf476f1ac3da3e8a68a4f4d71363008000a18b75d"
IMAGE_SHA256 = "f872d837d3c90ed2e05227bed711af5671a6fd1c9f7d7e91c911a61f155e99da"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=VARIANTS)
parser.add_argument("--output", type=Path, default=HERE.parents[1] / "img")
parser.add_argument("--scale", type=int, choices=[4, 8], default=8)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)

model_path = HERE / "build" / "realesr-animevideov3.pth"
assert hashlib.sha256(model_path.read_bytes()).hexdigest() == MODEL_SHA256
image_path = HERE / "build" / "RealESRGAN_x4plus_anime_6B.pth"
assert hashlib.sha256(image_path.read_bytes()).hexdigest() == IMAGE_SHA256
torch.set_num_threads(4)
device = "mps" if torch.backends.mps.is_available() else "cpu"
model = SRVGGNetCompact().to(device).eval()
model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True)["params"])
image_model = RRDBNet(3, 3, num_block=6).to(device).eval()
image_model.load_state_dict(torch.load(image_path, map_location=device,
                                       weights_only=True)["params_ema"])
print(f"Real-ESRGAN anime 6B + animevideov3 / {device} / {args.scale}x", flush=True)


def restore_colors(rgb, network, tile, pad):
    """각 모델의 수용 영역보다 넓게 겹쳐, 타일 경계의 불연속을 막는다."""
    height, width = rgb.shape[:2]
    output = np.empty((height * 4, width * 4, 3), np.uint8)
    for y in range(0, height, tile):
        for x in range(0, width, tile):
            right, bottom = min(x + tile, width), min(y + tile, height)
            x0, y0 = max(0, x - pad), max(0, y - pad)
            x1, y1 = min(width, right + pad), min(height, bottom + pad)
            crop = rgb[y0:y1, x0:x1]
            tensor = torch.from_numpy(crop.transpose(2, 0, 1).copy()).float()[None] / 255
            with torch.inference_mode():
                restored = network(tensor.to(device)).clamp(0, 1).cpu()
            pixels = np.rint(restored[0].permute(1, 2, 0).numpy() * 255).astype(np.uint8)
            output[y * 4:bottom * 4, x * 4:right * 4] = pixels[
                (y - y0) * 4:(bottom - y0) * 4, (x - x0) * 4:(right - x0) * 4]
    return output

for variant in args.variants:
    started = time.monotonic()
    source = Image.open(HERE / "source" / f"naeru-{variant}.png").convert("RGBA")
    source = replace_eye(source, eye_patch)
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

    # 근접에서 보이는 눈·입의 선은 정지 애니메이션용 RRDB 모델로 먼저 복원한다.
    # 6개 RRDB의 저해상도 수용 반경(약 94px) 밖으로 문맥을 확보한다.
    colors = restore_colors(rgb, image_model, 288, 100)
    if args.scale == 8:
        # 첫 4배 복원에서 찾은 선을 2배 크기의 중간본에 모아 한 번 더 복원한다.
        # 최종 WebP를 단순 확대하는 것과 달리 두 번째 추론이 선과 명암을 다시 푼다.
        middle = Image.fromarray(colors).resize((1152, 992), Image.Resampling.LANCZOS)
        colors = restore_colors(np.asarray(middle), model, 384, 24)

    # 실루엣의 중심선을 유지하면서 원본 픽셀 단위의 계단을 둥글게 연결한다.
    # 곡선의 중심은 알파 128에 두고, 실제 안티앨리어싱 띠만 좁힌다.
    # 이전 64~192 범위는 최대 접근 시 머리·볼에 넓은 반투명 띠로 남았다.
    size = (576 * args.scale, 496 * args.scale)
    edge = source.getchannel("A").resize(size, Image.Resampling.LANCZOS)
    edge = edge.filter(ImageFilter.GaussianBlur(args.scale))
    coverage = np.clip((np.asarray(edge, np.float32) - 116) / 24, 0, 1)
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
