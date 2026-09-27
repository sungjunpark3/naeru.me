#!/usr/bin/env python3
"""승인된 봄 낮 원화에서 8개 배경과 공통 투명 전경을 만든다."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SOURCE = HERE / "source"
IMG = REPO / "img"
SIZE = (3840, 2160)
VARIANTS = ["dawn", "day", "dusk", "night",
            "dawn-rain", "day-rain", "dusk-rain", "night-rain"]


def clean_alpha(image):
    """생성기의 투명 여백에 남은 점을 버리고 앞식물 본체만 보존한다."""
    rgba = np.asarray(image.convert("RGBA")).copy()
    alpha = rgba[:, :, 3]
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        (alpha > 16).astype(np.uint8), 8)
    main = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    support = cv2.dilate(
        (labels == main).astype(np.uint8), np.ones((5, 5), np.uint8))
    alpha[support == 0] = 0
    alpha[alpha < 8] = 0
    maximum = int(alpha.max())
    if maximum:
        alpha = np.clip(np.rint(alpha.astype(np.float32) * 255 / maximum),
                        0, 255).astype(np.uint8)
    rgba[:, :, 3] = alpha
    rgba[alpha == 0] = 0
    return Image.fromarray(rgba)


def resize_rgba(image):
    """반투명 꽃잎·풀잎의 가장자리 색을 오염시키지 않고 확대한다."""
    return image.convert("RGBa").resize(
        SIZE, Image.Resampling.LANCZOS).convert("RGBA")


def lighting_models():
    """기존 봄 8종의 동일 좌표에서 낮→시간대 RGB 변환을 구한다."""
    day = np.asarray(Image.open(
        SOURCE / "lighting-day.jpg").convert("RGB"), np.float32)[::8, ::8]
    source = day.reshape(-1, 3) / 255
    design = np.column_stack((source, np.ones(len(source))))
    models = {"day": None}
    for variant in VARIANTS:
        if variant == "day":
            continue
        target = np.asarray(Image.open(
            SOURCE / f"lighting-{variant}.jpg").convert("RGB"),
            np.float32)[::8, ::8].reshape(-1, 3) / 255
        matrix = np.linalg.lstsq(design, target, rcond=None)[0]
        error = np.mean(np.abs(design @ matrix - target)) * 255
        models[variant] = matrix
        print(f"{variant} lighting MAE: {error:.2f}/255")
    return models


def apply_lighting(image, variant, models):
    """형태와 알파는 유지하고 승인된 기존 장면의 조명만 입힌다."""
    if variant == "day":
        return image.copy()
    rgba = np.asarray(image.convert("RGBA")).copy()
    source = rgba[:, :, :3].astype(np.float32) / 255
    matrix = models[variant]
    graded = np.clip(source @ matrix[:3] + matrix[3], 0, 1)

    if variant.endswith("-rain"):
        # 기존 비 장면의 회색 하늘은 따르되, 봄 들판까지 잿빛으로 죽이지
        # 않는다. 아래로 갈수록 같은 시간대의 맑은 조명을 조금 돌려 젖은
        # 옥빛 새잎과 분홍·노랑·흰 꽃의 고유색을 남긴다.
        clear_variant = variant.removesuffix("-rain")
        if clear_variant == "day":
            clear = source
        else:
            clear_matrix = models[clear_variant]
            clear = np.clip(
                source @ clear_matrix[:3] + clear_matrix[3], 0, 1)
        yy = np.linspace(0, 1, rgba.shape[0], dtype=np.float32)[:, None]
        land = np.clip((yy - .38) / .40, 0, 1)
        land = land * land * (3 - 2 * land)
        mix = (.08 + .30 * land)[:, :, None]
        graded = graded * (1 - mix) + clear * mix
        if variant != "night-rain":
            graded = np.power(np.clip(graded, 0, 1), .94)

    rgba[:, :, :3] = np.rint(graded * 255).astype(np.uint8)
    rgba[rgba[:, :, 3] == 0] = 0
    return Image.fromarray(rgba)


def build():
    clean = Image.open(SOURCE / "day-clean.png").convert("RGBA")
    plants = clean_alpha(Image.open(SOURCE / "day-plants.png"))
    models = lighting_models()
    expected_alpha = None

    for variant in VARIANTS:
        background = apply_lighting(clean, variant, models).convert("RGB")
        background = background.resize(SIZE, Image.Resampling.LANCZOS)
        output = IMG / f"bg-{variant}-spring.jpg"
        background.save(output, quality=95, subsampling=0)
        print(f"{variant}: {output.stat().st_size / 1024:.0f} KiB")

        foreground = resize_rgba(apply_lighting(plants, variant, models))
        output = IMG / f"foreground-{variant}-spring.webp"
        foreground.save(output, quality=95, method=6)
        alpha = np.asarray(Image.open(output).getchannel("A"))
        if expected_alpha is None:
            expected_alpha = alpha
        assert np.array_equal(alpha, expected_alpha), output
        assert foreground.getchannel("A").crop((0, 0, 3840, 1000)).getbbox() is None
        print(f"{variant} foreground: {output.stat().st_size / 1024:.0f} KiB")


if __name__ == "__main__":
    build()
