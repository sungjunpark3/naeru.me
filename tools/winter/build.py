#!/usr/bin/env python3
"""새 겨울 원화 8종과 공통 앞풀·풍경 마스크를 런타임 자산으로 만든다."""
from pathlib import Path
import sys

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


def clean_alpha(image, minimum_area):
    rgba = np.asarray(image.convert("RGBA")).copy()
    alpha = rgba[:, :, 3]
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        (alpha > 32).astype(np.uint8), 8)
    keep = [index for index in range(1, count)
            if stats[index, cv2.CC_STAT_AREA] >= minimum_area]
    support = cv2.dilate(
        np.isin(labels, keep).astype(np.uint8), np.ones((5, 5), np.uint8))
    alpha[support == 0] = 0
    alpha[alpha < 12] = 0
    maximum = int(alpha.max())
    if maximum:
        alpha = np.clip(np.rint(alpha.astype(np.float32) * 255 / maximum),
                        0, 255).astype(np.uint8)
    rgba[:, :, 3] = alpha
    rgba[alpha == 0] = 0
    return Image.fromarray(rgba)


def save_backgrounds():
    for variant in VARIANTS:
        source = Image.open(SOURCE / f"{variant}.png").convert("RGB")
        source = source.resize(SIZE, Image.Resampling.LANCZOS)
        output = IMG / f"bg-{variant}-winter.jpg"
        source.save(output, quality=95, subsampling=0)
        print(f"background {variant}: {output.stat().st_size / 1024:.0f} KiB")


def save_foregrounds():
    foreground = clean_alpha(Image.open(SOURCE / "foreground.png"), 500)
    lowered = Image.new("RGBA", foreground.size)
    lowered.paste(foreground, (0, 32))
    foreground = lowered
    foreground = foreground.convert("RGBa").resize(
        SIZE, Image.Resampling.LANCZOS).convert("RGBA")
    foreground_path = REPO / "tools/foreground/source/winter-day-plants.png"
    foreground.save(foreground_path)

    clean = Image.open(SOURCE / "day.png").convert("RGB").resize(
        SIZE, Image.Resampling.LANCZOS)
    clean_path = REPO / "tools/foreground/source/winter-day-clean.png"
    clean.save(clean_path)
    reference = Image.alpha_composite(clean.convert("RGBA"), foreground).convert("RGB")
    reference_path = REPO / "tools/foreground/source/winter-day-reference.jpg"
    reference.save(reference_path, quality=95, subsampling=0)

    sys.path.insert(0, str(REPO / "tools/foreground"))
    from build import WinterForeground
    painter = WinterForeground()
    for variant in VARIANTS:
        painter.paint(IMG / f"bg-{variant}-winter.jpg", variant)


def save_landscape_mask():
    landscape = clean_alpha(Image.open(SOURCE / "landscape.png"), 500)
    mask = landscape.getchannel("A").resize(SIZE, Image.Resampling.LANCZOS)
    output = REPO / "tools/clouds/source/winter-landscape-mask.png"
    mask.save(output)
    assert mask.getextrema() == (0, 255)
    print(f"landscape mask: {output.stat().st_size / 1024:.0f} KiB")


def clean_clouds():
    cloud_source = REPO / "tools/clouds/source"
    for variant in ["dawn", "day", "dusk", "night"]:
        path = cloud_source / f"winter-{variant}-clouds.png"
        clouds = clean_alpha(Image.open(path), 100)
        clouds.save(path)
        clouds.getchannel("A").save(
            cloud_source / f"winter-{variant}-cloud-mask.png")
        print(f"cloud alpha {variant}: {clouds.getchannel('A').getbbox()}")


def main():
    save_backgrounds()
    save_foregrounds()
    save_landscape_mask()
    clean_clouds()


if __name__ == "__main__":
    main()
