#!/usr/bin/env python3
"""기존 뉴트럴 포즈의 색을 4배 복원하고, 검증된 투명 실루엣을 보존한다."""
import argparse
import hashlib
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image

from vendor.srvgg_arch import SRVGGNetCompact

HERE = Path(__file__).resolve().parent
VARIANTS = ["dawn", "day", "dusk", "night",
            "dawn-rain", "day-rain", "dusk-rain", "night-rain"]
MODEL_SHA256 = "b8a8376811077954d82ca3fcf476f1ac3da3e8a68a4f4d71363008000a18b75d"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=VARIANTS)
parser.add_argument("--output", type=Path, default=HERE.parents[1] / "img")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)

model_path = HERE / "build" / "realesr-animevideov3.pth"
assert hashlib.sha256(model_path.read_bytes()).hexdigest() == MODEL_SHA256
torch.set_num_threads(4)
device = "mps" if torch.backends.mps.is_available() else "cpu"
model = SRVGGNetCompact().to(device).eval()
model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True)["params"])
print(f"Real-ESRGAN animevideov3 / {device} / 4x", flush=True)

for variant in args.variants:
    started = time.monotonic()
    source = Image.open(HERE / "source" / f"naeru-{variant}.png").convert("RGBA")
    assert source.size == (576, 496)
    rgba = np.asarray(source)
    rgb = rgba[:, :, :3].copy()
    alpha = rgba[:, :, 3]

    # 투명 픽셀의 숨은 잔디 RGB를 모델에 주면 윤곽에 녹색 선이 생길 수 있다.
    # 확실한 캐릭터 색을 투명 여백까지 연장한다. 알파는 이 과정에서 바꾸지 않는다.
    opaque = alpha >= 240
    _, labels = cv2.distanceTransformWithLabels(
        (~opaque).astype(np.uint8), cv2.DIST_L2, 5,
        labelType=cv2.DIST_LABEL_PIXEL)
    extended = rgb[opaque][labels - 1]
    weight = np.minimum(alpha.astype(np.float32) / 32, 1)[:, :, None]
    rgb = np.rint(rgb * weight + extended * (1 - weight)).astype(np.uint8)

    tensor = torch.from_numpy(rgb.transpose(2, 0, 1).copy()).float().unsqueeze(0) / 255
    with torch.inference_mode():
        enhanced = model(tensor.to(device)).clamp(0, 1).cpu()
    colors = np.rint(enhanced[0].permute(1, 2, 0).numpy() * 255).astype(np.uint8)

    # AI에 새 실루엣을 맡기지 않는다. 원래 알파를 고품질 보간하여 발끝·여백을
    # 그대로 유지하고, 색과 알파를 따로 합쳐 straight-alpha WebP로 저장한다.
    high_alpha = source.getchannel("A").resize((2304, 1984), Image.Resampling.LANCZOS)
    colors[np.asarray(high_alpha) == 0] = 0
    result = Image.fromarray(colors)
    result.putalpha(high_alpha)
    target = args.output / f"naeru-{variant}-hd.webp"
    # 4배 복원본은 부드러운 면이 많아 WebP 95에서 작아진다. 색만 압축하고
    # 알파는 무손실인지 아래에서 실제 저장본을 대조한다.
    result.save(target, quality=95, method=6)

    saved = Image.open(target).convert("RGBA")
    assert saved.size == (2304, 1984)
    assert np.array_equal(np.asarray(saved.getchannel("A")), np.asarray(high_alpha))
    assert not np.any(np.asarray(saved.getchannel("A"))[[0, -1], :])
    assert not np.any(np.asarray(saved.getchannel("A"))[:, [0, -1]])
    print(f"{target.name}: {target.stat().st_size / 1024:.0f} KiB, "
          f"{time.monotonic() - started:.1f}s, alpha PASS", flush=True)
