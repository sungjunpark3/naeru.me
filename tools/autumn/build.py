#!/usr/bin/env python3
"""승인된 가을 원화에서 8개 배경·전경과 풍경 누끼를 만든다."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageChops


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SOURCE = HERE / "source"
IMG = REPO / "img"
CLOUD_SOURCE = REPO / "tools" / "clouds" / "source"
SIZE = (3840, 2160)
VARIANTS = ["dawn", "day", "dusk", "night",
            "dawn-rain", "day-rain", "dusk-rain", "night-rain"]
CLEAR_VARIANTS = VARIANTS[:4]
RAIN_VARIANTS = VARIANTS[4:]


def clean_alpha(image, minimum_area):
    """실제 식물·낙엽은 보존하고 생성기 투명 여백의 점만 버린다."""
    rgba = np.asarray(image.convert("RGBA")).copy()
    alpha = rgba[:, :, 3]
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        (alpha > 8).astype(np.uint8), 8)
    keep = np.zeros_like(alpha, dtype=np.uint8)
    for index in range(1, count):
        if stats[index, cv2.CC_STAT_AREA] >= minimum_area:
            keep[labels == index] = 1
    alpha[keep == 0] = 0
    alpha[alpha < 5] = 0
    maximum = int(alpha.max())
    if maximum:
        alpha = np.clip(np.rint(alpha.astype(np.float32) * 255 / maximum),
                        0, 255).astype(np.uint8)
    rgba[:, :, 3] = alpha
    rgba[alpha == 0] = 0
    return Image.fromarray(rgba)


def resize_rgba(image):
    """반투명 잎·억새의 가장자리 색을 오염시키지 않고 확대한다."""
    return image.convert("RGBa").resize(
        SIZE, Image.Resampling.LANCZOS).convert("RGBA")


def lighting_models():
    """기존 가을 8종의 같은 좌표에서 낮→시간대 RGB 변환을 구한다."""
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
    """형태와 알파는 유지하고 기존 가을 장면의 시간·날씨 조명을 입힌다."""
    if variant == "day":
        return image.copy()
    rgba = np.asarray(image.convert("RGBA")).copy()
    source = rgba[:, :, :3].astype(np.float32) / 255
    matrix = models[variant]
    graded = np.clip(source @ matrix[:3] + matrix[3], 0, 1)

    if variant.endswith("-rain"):
        # 비구름의 회색 조명은 따르되, 들판 고유의 가을색까지 잿빛으로
        # 사라지지 않도록 아래쪽에 같은 시간대 맑은 조명을 조금 돌린다.
        clear_variant = variant.removesuffix("-rain")
        if clear_variant == "day":
            clear = source
        else:
            clear_matrix = models[clear_variant]
            clear = np.clip(
                source @ clear_matrix[:3] + clear_matrix[3], 0, 1)
        yy = np.linspace(0, 1, rgba.shape[0], dtype=np.float32)[:, None]
        land = np.clip((yy - .42) / .38, 0, 1)
        land = land * land * (3 - 2 * land)
        mix = (.05 + .22 * land)[:, :, None]
        graded = graded * (1 - mix) + clear * mix

    rgba[:, :, :3] = np.rint(graded * 255).astype(np.uint8)
    rgba[rgba[:, :, 3] == 0] = 0
    return Image.fromarray(rgba)


def compose_rain_background(clean, landscape_mask, variant, models):
    """새 비구름 아래에 형태가 고정된 나무·산·들판을 다시 올린다."""
    time = variant.removesuffix("-rain")
    rain_sky = Image.open(SOURCE / f"rain-sky-{time}.png").convert("RGB")
    rain_sky = rain_sky.resize(SIZE, Image.Resampling.LANCZOS)
    landscape = apply_lighting(clean, variant, models).convert("RGB")
    landscape = landscape.resize(SIZE, Image.Resampling.LANCZOS)
    return Image.composite(landscape, rain_sky, landscape_mask)


def save_landscape(background, mask, variant):
    """기존 구름 영상 위를 덮을 새 나무·산·들판 레이어를 저장한다."""
    landscape = background.convert("RGBA")
    landscape.putalpha(mask)
    output = IMG / f"landscape-{variant}-autumn.webp"
    landscape.save(output, lossless=True, exact=True, method=6)

    decoded = Image.open(output).convert("RGBA")
    opaque = decoded.getchannel("A").point(
        lambda value: 255 if value == 255 else 0)
    difference = ImageChops.difference(decoded.convert("RGB"), background)
    visible = Image.composite(
        difference, Image.new("RGB", SIZE), opaque)
    assert visible.getbbox() is None
    print(f"{variant} landscape: {output.stat().st_size / 1024:.0f} KiB")


def build():
    clean = Image.open(SOURCE / "day-clean.png").convert("RGBA")
    reeds = clean_alpha(Image.open(SOURCE / "day-reeds.png"), 20)
    landscape_cutout = clean_alpha(
        Image.open(SOURCE / "day-landscape.png"), 20)
    landscape_mask = landscape_cutout.getchannel("A")
    landscape_mask.save(CLOUD_SOURCE / "autumn-landscape-mask.png")
    landscape_mask = landscape_mask.resize(SIZE, Image.Resampling.LANCZOS)
    landscape_mask = landscape_mask.point(
        lambda value: 0 if value <= 4 else 255 if value >= 245 else
        round((value - 4) * 255 / 241))
    assert landscape_mask.getextrema() == (0, 255)

    models = lighting_models()
    expected_alpha = None
    for variant in VARIANTS:
        if variant in RAIN_VARIANTS:
            background = compose_rain_background(
                clean, landscape_mask, variant, models)
        else:
            background = apply_lighting(clean, variant, models).convert("RGB")
            background = background.resize(SIZE, Image.Resampling.LANCZOS)
        output = IMG / f"bg-{variant}-autumn.jpg"
        background.save(output, quality=95, subsampling=0)
        print(f"{variant}: {output.stat().st_size / 1024:.0f} KiB")

        foreground = resize_rgba(apply_lighting(reeds, variant, models))
        output = IMG / f"foreground-{variant}-autumn.webp"
        foreground.save(output, quality=95, method=6)
        alpha = np.asarray(Image.open(output).getchannel("A"))
        if expected_alpha is None:
            expected_alpha = alpha
        assert np.array_equal(alpha, expected_alpha), output
        assert foreground.getchannel("A").crop((0, 0, 3840, 550)).getbbox() is None
        print(f"{variant} foreground: {output.stat().st_size / 1024:.0f} KiB")

        if variant in CLEAR_VARIANTS:
            save_landscape(background, landscape_mask, variant)


if __name__ == "__main__":
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from asset_workspace import require_workspace
    require_workspace(REPO)
    build()
