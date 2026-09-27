#!/usr/bin/env python3
"""승인된 봄 낮 원화에서 8개 배경·전경과 맑은 하늘 소스를 만든다."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SOURCE = HERE / "source"
IMG = REPO / "img"
CLOUD_SOURCE = REPO / "tools" / "clouds" / "source"
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


def build_cloud_sources(clean, models):
    """봄 풍경 경계와 승인 원화의 구름을 4개 맑은 시간대로 분리한다."""
    landscape = clean_alpha(Image.open(SOURCE / "day-landscape.png"))
    landscape_alpha = np.asarray(landscape.getchannel("A"))
    Image.fromarray(landscape_alpha).save(
        CLOUD_SOURCE / "spring-landscape-mask.png")

    original = np.asarray(clean.convert("RGB"), np.float32)
    clear_image = Image.open(SOURCE / "day-clear-sky.png").convert("RGB")
    clear = np.asarray(clear_image, np.float32)
    height, width = landscape_alpha.shape
    yy, xx = np.indices((height, width))
    sky = landscape_alpha < 8

    # 생성한 빈 하늘을 원화의 구름 없는 파란 영역에 먼저 맞춘다. 그 차이로
    # 구름 위치를 잡으면 생성 누끼가 조금 다시 그려져도 원화 구름은 움직이지
    # 않고 정확한 위치와 색을 유지한다.
    red, green, blue = [original[:, :, index] for index in range(3)]
    sample = (sky & (blue - red > 28) & (blue - green > 8) &
              (yy < height * .64) & ((xx + yy) % 4 == 0))
    design = np.column_stack((
        clear[sample] / 255, np.ones(sample.sum()),
        xx[sample] / width, yy[sample] / height))
    matrix = np.linalg.lstsq(
        design, original[sample] / 255, rcond=None)[0]
    fitted = np.clip(
        (clear / 255) @ matrix[:3] + matrix[3] +
        (xx / width)[:, :, None] * matrix[4] +
        (yy / height)[:, :, None] * matrix[5], 0, 1) * 255
    difference = np.mean(np.abs(original - fitted), axis=2)

    seeds = ((difference > 12) & sky).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(seeds, 8)
    support = np.zeros_like(seeds)
    for index in range(1, count):
        if stats[index, cv2.CC_STAT_AREA] >= 45:
            support[labels == index] = 1
    support = cv2.dilate(support, np.ones((7, 7), np.uint8))
    alpha = np.clip((difference - 5) / 18, 0, 1)
    alpha *= support * sky
    alpha = cv2.GaussianBlur(alpha.astype(np.float32), (0, 0), 1.15)
    alpha *= sky
    alpha = np.rint(np.clip(alpha, 0, 1) * 255).astype(np.uint8)
    alpha[alpha < 3] = 0

    clouds = np.dstack((original.astype(np.uint8), alpha))
    clouds = Image.fromarray(clouds, "RGBA")
    for variant in VARIANTS[:4]:
        prefix = f"spring-{variant}"
        if variant in ["dusk", "night"]:
            variant_sky = Image.open(
                SOURCE / f"{variant}-clear-sky.png").convert("RGB")
        else:
            variant_sky = apply_lighting(
                clear_image.convert("RGBA"), variant, models).convert("RGB")
        variant_sky.save(CLOUD_SOURCE / f"{prefix}-clear-sky.png")
        graded_clouds = apply_lighting(clouds, variant, models)
        rgba = np.asarray(graded_clouds).copy()
        if variant == "night":
            rgb = rgba[:, :, :3].astype(np.float32)
            light = (rgb[:, :, 0] * .2126 + rgb[:, :, 1] * .7152 +
                     rgb[:, :, 2] * .0722)
            rgba[:, :, :3] = np.clip(np.stack((
                light * .52, light * .62, light * .78), axis=2),
                0, 255).astype(np.uint8)
        rgba[rgba[:, :, 3] == 0] = 0
        graded_clouds = Image.fromarray(rgba)
        graded_clouds.save(CLOUD_SOURCE / f"{prefix}-clouds.png")
        graded_clouds.getchannel("A").save(
            CLOUD_SOURCE / f"{prefix}-cloud-mask.png")
    print("spring cloud sources: landscape mask + 4 clear skies/cloud layers")


def build():
    clean = Image.open(SOURCE / "day-clean.png").convert("RGBA")
    plants = clean_alpha(Image.open(SOURCE / "day-plants.png"))
    models = lighting_models()
    build_cloud_sources(clean, models)
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
