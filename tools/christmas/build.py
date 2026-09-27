#!/usr/bin/env python3
"""12월 20~31일용 겨울 풍경을 기존 구름과 분리해 만든다."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SOURCE = HERE / "source"
IMG = REPO / "img"
SIZE = (3840, 2160)
CLEAR = ["dawn", "day", "dusk", "night"]
RAIN = [f"{variant}-rain" for variant in CLEAR]
NIGHT_GUIDE = SOURCE / "night-cozy-concept.png"


def resize_rgba(image, size):
    """반투명 가장자리의 RGB 번짐 없이 리사이즈한다."""
    return image.convert("RGBa").resize(
        size, Image.Resampling.LANCZOS).convert("RGBA")


def extract_decoration_art(filename, kernel_size, blur_radius):
    """imagegen 원화에서 붉은 장식과 금빛 전구만 꺼낸다."""
    image = Image.open(SOURCE / filename).convert("RGBA")
    rgba = np.asarray(image).copy()
    rgb = rgba[:, :, :3].astype(np.int16)
    red, green, blue = [rgb[:, :, index] for index in range(3)]

    red_seed = ((red > 80) & (red > green * 1.24 + 8) &
                (red > blue * 1.14 + 6))
    gold_seed = ((red > 175) & (green > 105) & (red > green * 1.04) &
                 (green > blue * 1.13) & (red - blue > 45))
    seed = ((red_seed | gold_seed) & (rgba[:, :, 3] > 24)).astype(np.uint8)

    # 장식의 어두운 테두리와 전구의 부드러운 빛까지 포함하되 나무 원화는
    # 가져오지 않는다. 같은 좌표의 기존 나무와 눈 형태가 그대로 남는다.
    support = cv2.dilate(
        seed, np.ones((kernel_size, kernel_size), np.uint8))
    support = Image.fromarray(support * 255).filter(
        ImageFilter.GaussianBlur(blur_radius))
    alpha = (rgba[:, :, 3].astype(np.float32) *
             (np.asarray(support, np.float32) / 255))
    rgba[:, :, 3] = np.rint(alpha).astype(np.uint8)
    rgba[rgba[:, :, 3] == 0] = 0
    return Image.fromarray(rgba)


def extract_decorations():
    sides = extract_decoration_art("decorations.png", 19, 5)
    trees = extract_decoration_art("tree-decorations.png", 9, 3)
    trees.save(SOURCE / "tree-decorations-only.png")
    decoration = Image.alpha_composite(sides, trees)
    decoration.save(SOURCE / "decorations-only.png")
    return decoration


def fit_light(source, target):
    """낮 원화에서 대상 시간대·날씨로 가는 RGB 선형식을 구한다."""
    source = np.asarray(source.convert("RGB"), np.float32)[::6, ::6] / 255
    target = np.asarray(target.convert("RGB"), np.float32)[::6, ::6] / 255
    design = np.column_stack((source.reshape(-1, 3),
                              np.ones(source.shape[0] * source.shape[1])))
    return np.linalg.lstsq(design, target.reshape(-1, 3), rcond=None)[0]


def grade_overlay(overlay, matrix, scene_light):
    rgba = np.asarray(overlay.convert("RGBA")).copy()
    source = rgba[:, :, :3].astype(np.float32) / 255
    graded = np.clip(source @ matrix[:3] + matrix[3], 0, 1)

    # 밤에도 전구는 꺼지지 않는다. 원본의 따뜻한 고휘도 픽셀만 발광색을
    # 보존하고 리본·나뭇가지 색은 장면 조명을 그대로 받는다.
    red, green, blue = [source[:, :, index] for index in range(3)]
    warm = np.clip((red - np.maximum(green, blue) - .05) / .22, 0, 1)
    warm = np.maximum(warm,
                      np.clip((green - blue - .10) / .28, 0, 1))
    source_peak = np.maximum(source.max(axis=2, keepdims=True), .08)
    graded_peak = graded.max(axis=2, keepdims=True)
    warm_limit = source_peak * (.32 + .68 * np.clip(scene_light, .25, 1.15))
    graded_peak = np.minimum(graded_peak, warm_limit)
    warm_color = np.clip(source * graded_peak / source_peak, 0, 1)
    graded = graded * (1 - warm[:, :, None] * .78) + \
        warm_color * warm[:, :, None] * .78
    glow = np.clip((red - .62) / .28, 0, 1)
    glow *= np.clip((green - blue - .08) / .24, 0, 1)
    glow = glow[:, :, None]
    rgba[:, :, :3] = np.rint(
        np.clip(graded * (1 - glow) + source * glow, 0, 1) * 255
    ).astype(np.uint8)
    rgba[rgba[:, :, 3] == 0] = 0
    return Image.fromarray(rgba)


def composite(base, overlay):
    return Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")


def make_cozy_night(base, decorated, landscape_mask, strength=1):
    """생성 시안의 색온도만 빌려 밤 지상부를 포근하게 보정한다."""
    guide = Image.open(NIGHT_GUIDE).convert("RGB").resize(base.size)
    mask = landscape_mask.resize(base.size, Image.Resampling.LANCZOS)

    base_rgb = np.asarray(base.convert("RGB"), np.float32)
    current_rgb = np.asarray(decorated.convert("RGB"), np.float32)
    guide_rgb = np.asarray(guide, np.float32)
    mask_array = np.asarray(mask, np.float32) / 255
    current_luma = current_rgb @ np.array([.2126, .7152, .0722])
    sample = (mask_array > .65) & (current_luma < 210)

    # 시안 전체를 섞으면 나무 형태와 장식 수가 달라진다. 지상부 평균의
    # 따뜻한 변화량만 약하게 가져와 기존 원화의 픽셀 구조를 보존한다.
    guide_shift = np.mean(
        guide_rgb[sample] - current_rgb[sample], axis=0) * .38
    guide_shift = np.clip(guide_shift, [-2, -2, -10], [14, 8, 3])

    lifted = 255 * np.power(np.clip(base_rgb / 255, 0, 1), .94)
    shadow_weight = np.clip(1 - current_luma / 225, .15, .72)
    warm = base_rgb + (lifted - base_rgb) * .52
    warm += guide_shift * shadow_weight[:, :, None]
    amount = mask_array[:, :, None] * strength
    result = base_rgb * (1 - amount) + warm * amount
    return Image.fromarray(np.rint(np.clip(result, 0, 255)).astype(np.uint8))


def add_amber_glow(base, overlay, radius, opacity):
    """기존 금빛 전구 좌표에만 부드러운 광륜과 반사광을 더한다."""
    rgba = np.asarray(overlay.convert("RGBA"))
    rgb = rgba[:, :, :3].astype(np.float32)
    red, green, blue = [rgb[:, :, index] for index in range(3)]
    seed = ((red > 155) & (green > 85) & (green > blue * 1.12) &
            (red - blue > 38))
    seed = seed.astype(np.float32) * (rgba[:, :, 3].astype(np.float32) / 255)
    seed = cv2.dilate(seed, np.ones((5, 5), np.uint8))
    seed = cv2.GaussianBlur(seed, (0, 0), radius)
    alpha = np.clip(seed * opacity, 0, .42)[:, :, None]

    base_rgba = np.asarray(base.convert("RGBA")).copy()
    source = base_rgba[:, :, :3].astype(np.float32)
    amber = np.array([255, 170, 72], np.float32)
    lit = source * (1 - alpha) + amber * alpha
    if base.mode == "RGBA":
        base_rgba[:, :, :3] = np.rint(np.clip(lit, 0, 255)).astype(np.uint8)
        return Image.fromarray(base_rgba)
    return Image.fromarray(np.rint(np.clip(lit, 0, 255)).astype(np.uint8))


def draw_foreground_decorations():
    """전경의 실제 눈풀 위에만 전선 없는 작은 전구·열매를 더한다."""
    scale = 2
    layer = Image.new("RGBA", (SIZE[0] * scale, SIZE[1] * scale))
    draw = ImageDraw.Draw(layer, "RGBA")

    foreground = Image.open(
        IMG / "foreground-day-winter.webp").convert("RGBA")
    alpha = np.asarray(foreground.getchannel("A"))

    def plant_top(x):
        strip = alpha[:, max(0, x - 20):min(SIZE[0], x + 21)]
        rows = np.flatnonzero(strip.max(axis=1) > 80)
        return int(rows[0]) if len(rows) else None

    light_x = [100, 250, 400, 550, 3150, 3300, 3450, 3600, 3750]
    for index, x in enumerate(light_x):
        top = plant_top(x)
        if top is None or top > 1980:
            continue
        y = top + 42
        x *= scale
        y *= scale
        radius = (8 if index % 2 else 9) * scale
        glow = radius * 4
        draw.ellipse((x - glow, y - glow, x + glow, y + glow),
                     fill=(255, 190, 84, 14))
        draw.ellipse((x - radius, y - radius, x + radius, y + radius),
                     fill=(255, 207, 112, 245))
        draw.ellipse((x - radius // 3, y - radius // 2,
                      x + radius // 4, y + radius // 5),
                     fill=(255, 248, 207, 230))

    berry_x = [150, 350, 600, 3050, 3250, 3500, 3720]
    for x in berry_x:
        top = plant_top(x)
        if top is None or top > 1990:
            continue
        y = min(top + 115, 2110)
        x *= scale
        y *= scale
        for dx, dy in [(-11, 2), (10, -5), (1, 13)]:
            radius = 10 * scale
            cx, cy = x + dx * scale, y + dy * scale
            draw.ellipse((cx - radius, cy - radius,
                          cx + radius, cy + radius),
                         fill=(151, 42, 43, 238))
            draw.ellipse((cx - radius // 2, cy - radius // 2,
                          cx, cy), fill=(236, 116, 91, 150))

    return layer.resize(SIZE, Image.Resampling.LANCZOS)


def build():
    day = Image.open(REPO / "tools/winter/source/day.png").convert("RGB")
    decorations = extract_decorations()
    foreground_decorations = draw_foreground_decorations()
    landscape_mask = Image.open(
        REPO / "tools/clouds/source/winter-landscape-mask.png").convert("L")
    landscape_mask = landscape_mask.point(
        lambda value: 0 if value <= 4 else
        255 if value >= 245 else round((value - 4) * 255 / 241))

    for variant in CLEAR + RAIN:
        target_source = Image.open(
            REPO / f"tools/winter/source/{variant}.png").convert("RGB")
        matrix = fit_light(day, target_source)
        scene_light = (np.asarray(target_source, np.float32).mean() /
                       np.asarray(day, np.float32).mean())
        graded_overlay = grade_overlay(decorations, matrix, scene_light)
        preview = composite(target_source, graded_overlay)
        if variant.startswith("night"):
            rain_strength = .78 if variant.endswith("rain") else 1
            target_source = make_cozy_night(
                target_source, preview, landscape_mask, rain_strength)
            target_source = add_amber_glow(
                target_source, graded_overlay, 8, .32 * rain_strength)
        decorated = composite(target_source, graded_overlay)
        decorated = decorated.resize(SIZE, Image.Resampling.LANCZOS)

        if variant in CLEAR:
            overlay_alpha = resize_rgba(decorations, SIZE).getchannel("A")
            alpha = Image.fromarray(np.maximum(
                np.asarray(landscape_mask), np.asarray(overlay_alpha)))
            landscape = decorated.convert("RGBA")
            landscape.putalpha(alpha)
            output = IMG / f"landscape-{variant}-christmas.webp"
            landscape.save(output, lossless=True, exact=True, method=6)
        else:
            output = IMG / f"bg-{variant}-christmas.jpg"
            decorated.save(output, quality=95, subsampling=0)
        print(f"{variant}: {output.stat().st_size / 1024:.0f} KiB")

        foreground = Image.open(
            IMG / f"foreground-{variant}-winter.webp").convert("RGBA")
        front_overlay = grade_overlay(
            foreground_decorations, matrix, scene_light)
        if variant.startswith("night"):
            rain_strength = .78 if variant.endswith("rain") else 1
            foreground = add_amber_glow(
                foreground, front_overlay, 18, .28 * rain_strength)
        foreground = Image.alpha_composite(foreground, front_overlay)
        output = IMG / f"foreground-{variant}-christmas.webp"
        foreground.save(output, quality=95, method=6)
        print(f"{variant} foreground: {output.stat().st_size / 1024:.0f} KiB")


if __name__ == "__main__":
    build()
