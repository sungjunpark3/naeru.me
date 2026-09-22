#!/usr/bin/env python3
"""원본 팔·혀 동작 316프레임을 4배 복원해 근접용 투명 영상으로 만든다.

정지원화를 변형해 동작을 흉내 내지 않고, 눈 수정이 반영된 원본 시퀀스를 쓴다.
--stage restore: 낮 프레임 복원 / --stage encode: 네 시간대 색·코덱 생성.
"""
import argparse
import hashlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
BUILD = HERE / "build" / "motion"
SIZE = (2304, 1984)
BANDS = ["dawn", "day", "dusk", "night"]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--stage", choices=["all", "restore", "encode"], default="all")
args = parser.parse_args()
BUILD.mkdir(parents=True, exist_ok=True)

if args.stage in ["all", "restore"]:
    import torch
    from vendor.srvgg_arch import SRVGGNetCompact

    weights = HERE / "build" / "realesr-animevideov3.pth"
    assert hashlib.sha256(weights.read_bytes()).hexdigest() == (
        "b8a8376811077954d82ca3fcf476f1ac3da3e8a68a4f4d71363008000a18b75d")
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    torch.set_num_threads(4)
    model = SRVGGNetCompact().to(device).eval()
    model.load_state_dict(torch.load(weights, map_location=device, weights_only=True)["params"])
    frames = sorted((REPO / "tools/naeru-split/build/eyes/day").glob("*.png"))
    assert len(frames) == 316, "먼저 naeru-split/eyes.py로 원본 시퀀스를 준비한다"
    for i, path in enumerate(frames, 1):
        source = Image.open(path).convert("RGBA")
        rgba = np.asarray(source)
        rgb, alpha = rgba[:, :, :3].copy(), rgba[:, :, 3]
        opaque = alpha >= 240
        _, labels = cv2.distanceTransformWithLabels(
            (~opaque).astype(np.uint8), cv2.DIST_L2, 5,
            labelType=cv2.DIST_LABEL_PIXEL)
        extended = rgb[opaque][labels - 1]
        weight = np.clip(alpha.astype(np.float32) / 32, 0, 1)[:, :, None]
        rgb = np.rint(rgb * weight + extended * (1 - weight)).astype(np.uint8)
        tensor = torch.from_numpy(rgb.transpose(2, 0, 1).copy()).float()[None] / 255
        with torch.inference_mode():
            restored = model(tensor.to(device)).clamp(0, 1).cpu()
        colors = np.rint(restored[0].permute(1, 2, 0).numpy() * 255).astype(np.uint8)
        # 정지 HD와 같은 경계 정리. RGB와 별도로 알파를 보존한다.
        edge = source.getchannel("A").resize(SIZE, Image.Resampling.LANCZOS)
        edge = edge.filter(ImageFilter.GaussianBlur(4))
        coverage = np.clip((np.asarray(edge, np.float32) - 116) / 24, 0, 1)
        coverage = coverage * coverage * (3 - 2 * coverage)
        high_alpha = np.rint(coverage * 255).astype(np.uint8)
        colors[high_alpha == 0] = 0
        output = Image.fromarray(colors)
        output.putalpha(Image.fromarray(high_alpha))
        output.save(BUILD / path.name)
        if i % 24 == 0 or i == len(frames):
            print(f"restore {i}/316 ({device})", flush=True)

if args.stage in ["all", "encode"]:
    frames = sorted(BUILD.glob("*.png"))
    assert len(frames) == 316
    day = np.asarray(Image.open(HERE / "source/naeru-day.png"), np.float32)
    mask = cv2.erode((day[:, :, 3] == 255).astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    samples = day[:, :, :3][mask] / 255
    design = np.column_stack((samples, np.ones(len(samples))))

    def encode(band):
        target = np.asarray(Image.open(HERE / "source" / f"naeru-{band}.png"), np.float32)
        matrix = np.linalg.lstsq(design, target[:, :, :3][mask] / 255, rcond=None)[0]
        base = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgba",
                "-s", "2304x1984", "-r", "24", "-i", "pipe:0", "-an"]
        commands = [
            base + ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-crf", "24",
                    "-b:v", "0", "-auto-alt-ref", "0", "-row-mt", "1", "-threads", "2",
                    "-deadline", "good", "-cpu-used", "4",
                    str(REPO / "img" / f"naeru-{band}-close.webm")],
            base + ["-vf", "premultiply=inplace=1", "-c:v", "hevc_videotoolbox",
                    "-pix_fmt", "bgra", "-alpha_quality", "0.95", "-q:v", "60",
                    "-tag:v", "hvc1", "-movflags", "+faststart",
                    str(REPO / "img" / f"naeru-{band}-close.mp4")]
        ]
        processes = [subprocess.Popen(cmd, stdin=subprocess.PIPE) for cmd in commands]
        try:
            for i, path in enumerate(frames, 1):
                rgba = np.array(Image.open(path).convert("RGBA"))
                if band != "day":
                    colors = rgba[:, :, :3].astype(np.float32)
                    rgba[:, :, :3] = np.rint(np.clip(
                        colors @ matrix[:3] + 255 * matrix[3], 0, 255)).astype(np.uint8)
                    rgba[rgba[:, :, 3] == 0, :3] = 0
                data = rgba.tobytes()
                for process in processes:
                    process.stdin.write(data)
                if i % 48 == 0 or i == len(frames):
                    print(f"encode {band} {i}/316", flush=True)
            for process in processes:
                process.stdin.close()
            for process in processes:
                assert process.wait() == 0, f"{band}: encode failed"
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    process.wait()

    # 복원은 한 번만 하고, 각 시간대는 동일한 프레임·알파에 조명만 입힌다.
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(encode, BANDS))
