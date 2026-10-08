#!/usr/bin/env python3
"""초록 여름 원화 8종을 배경·전경·풍경과 맑은 구름 제작 입력으로 나눈다."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SOURCE = HERE / "source"
CLOUD_SOURCE = REPO / "tools/clouds/source"
SIZE = (3840, 2160)
CLEAR = ["dawn", "day", "dusk", "night"]
VARIANTS = CLEAR + [v + "-rain" for v in CLEAR]


def rgb(path):
    return np.asarray(Image.open(path).convert("RGB"), np.float32)


def clean_cutout(path):
    """생성 알파를 보존하되 투명 영역의 먼지와 불투명 내부의 틈만 정리한다."""
    rgba = np.asarray(Image.open(path).convert("RGBA")).copy()
    alpha = rgba[:, :, 3]
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        (alpha > 8).astype(np.uint8), 8)
    keep = np.zeros_like(alpha)
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] >= 20:
            keep[labels == label] = 1
    keep = cv2.dilate(keep, np.ones((3, 3), np.uint8))
    alpha[(keep == 0) | (alpha < 5)] = 0
    alpha[alpha >= 245] = 255
    rgba[alpha == 0] = 0
    return Image.fromarray(rgba)


def foreground_lighting(plants, day, target, land):
    """같은 들판 좌표의 조명만 전경에 적용해 8종 모두 같은 실루엣을 쓴다."""
    height, width = day.shape[:2]
    yy, xx = np.indices((height, width))
    sample = (land == 255) & (yy > height * .7) & ((xx + yy) % 8 == 0)
    design = np.column_stack((day[sample] / 255, np.ones(sample.sum())))
    matrix = np.linalg.lstsq(design, target[sample] / 255, rcond=None)[0]
    rgba = np.asarray(plants).copy()
    colors = rgba[:, :, :3].astype(np.float32) / 255
    rgba[:, :, :3] = np.rint(np.clip(
        colors @ matrix[:3] + matrix[3], 0, 1) * 255).astype(np.uint8)
    rgba[rgba[:, :, 3] == 0] = 0
    return Image.fromarray(rgba)


def cloud_sources(backgrounds, landscape_alpha):
    """나무 뒤까지 복원한 구름 누끼에 각 시간대 하늘 조명을 맞춘다."""
    CLOUD_SOURCE.mkdir(parents=True, exist_ok=True)
    Image.fromarray(landscape_alpha).save(CLOUD_SOURCE / "summer-landscape-mask.png")
    sky = landscape_alpha < 5
    height, width = sky.shape
    yy, xx = np.indices(sky.shape)
    day = backgrounds["day"]
    clear_day = rgb(SOURCE / "day-clear-sky.png")
    delta = np.mean(np.abs(day - clear_day), axis=2)
    blue_sky = sky & (yy < height * .57) & (day[:, :, 2] - day[:, :, 0] > 28)
    # 빈 하늘 편집본의 색상 오차는 절댓값으로 가정하지 않고 가장 가까운 맑은 영역을 쓴다.
    clear_sample = (blue_sky & (delta <= np.quantile(delta[blue_sky], .35)) &
                    ((xx + yy) % 4 == 0))
    assert clear_sample.sum() > 100, "빈 하늘 색상 표본 부족"
    cloud_sample = sky & (delta > 25) & ((xx + yy) % 4 == 0)
    cloud_design = np.column_stack((day[cloud_sample] / 255,
                                    np.ones(cloud_sample.sum()),
                                    yy[cloud_sample] / height))
    clouds = clean_cutout(SOURCE / "day-clouds.png")
    clouds = clouds.convert("RGBa").resize((width, height), Image.Resampling.LANCZOS).convert("RGBA")
    cloud_rgba = np.asarray(clouds)
    cloud_colors = cloud_rgba[:, :, :3].astype(np.float32) / 255
    cloud_alpha = cloud_rgba[:, :, 3]

    for variant in CLEAR:
        original = backgrounds[variant]
        empty = rgb(SOURCE / f"{variant}-clear-sky.png")
        # 구름 없는 위치로만 채널별 밝기를 맞춘다. 조명 원화의 색상은 유지한다.
        for channel in range(3):
            design = np.column_stack((empty[:, :, channel][clear_sample],
                                      np.ones(clear_sample.sum())))
            scale, offset = np.linalg.lstsq(
                design, original[:, :, channel][clear_sample], rcond=None)[0]
            empty[:, :, channel] = empty[:, :, channel] * scale + offset
        empty = np.clip(empty, 0, 255)
        cloud_rgb = cloud_colors.copy()
        if variant != "day":
            matrix = np.linalg.lstsq(
                cloud_design, original[cloud_sample] / 255, rcond=None)[0]
            cloud_rgb = (cloud_rgb @ matrix[:3] + matrix[3] +
                         (yy / height)[:, :, None] * matrix[4])
        cloud_rgb = np.rint(np.clip(cloud_rgb, 0, 1) * 255).astype(np.uint8)
        cloud_rgb[cloud_alpha == 0] = 0
        prefix = CLOUD_SOURCE / f"summer-{variant}"
        Image.fromarray(np.rint(empty).astype(np.uint8)).save(str(prefix) + "-clear-sky.png")
        Image.fromarray(np.dstack((cloud_rgb, cloud_alpha))).save(
            str(prefix) + "-clouds.png")
        Image.fromarray(cloud_alpha).save(str(prefix) + "-cloud-mask.png")
        print(f"{variant}: complete cloud shapes / empty sky", flush=True)


def build():
    backgrounds = {v: rgb(SOURCE / ("day-clean.png" if v == "day" else f"{v}.png"))
                   for v in VARIANTS}
    plants = clean_cutout(SOURCE / "day-plants.png")
    cutout = clean_cutout(SOURCE / "day-landscape.png")
    alpha = np.asarray(cutout.getchannel("A"))
    assert all(image.shape == backgrounds["day"].shape for image in backgrounds.values())
    # 투명 출력의 캔버스가 1px 달라질 수 있으므로 기준 캔버스로 정규화한다.
    assert abs(plants.width / plants.height - cutout.width / cutout.height) < .002
    plants = plants.convert("RGBa").resize(cutout.size, Image.Resampling.LANCZOS).convert("RGBA")
    mask = cutout.getchannel("A").resize(SIZE, Image.Resampling.LANCZOS)
    mask = mask.point(lambda value: 0 if value < 4 else 255 if value > 245 else value)
    cloud_sources(backgrounds, alpha)

    for variant in VARIANTS:
        background = Image.fromarray(backgrounds[variant].astype(np.uint8)).resize(
            SIZE, Image.Resampling.LANCZOS)
        output = REPO / f"img/bg-{variant}-summer.jpg"
        background.save(output, quality=95, subsampling=0)
        if variant in CLEAR:
            # 풍경 RGB와 배경을 동일하게 유지하므로 하늘 영상이 늦게 와도 경계가 같다.
            landscape = Image.open(output).convert("RGBA")
            landscape.putalpha(mask)
            landscape.save(REPO / f"img/landscape-{variant}-summer.webp",
                           lossless=True, exact=True, method=6)
        foreground = (plants if variant == "day" else foreground_lighting(
            plants, backgrounds["day"], backgrounds[variant], alpha))
        foreground = foreground.convert("RGBa").resize(
            SIZE, Image.Resampling.LANCZOS).convert("RGBA")
        foreground.save(REPO / f"img/foreground-{variant}-summer.webp", quality=95, method=6)
        assert foreground.getchannel("A").crop((0, 0, 3840, 1000)).getbbox() is None
        assert foreground.getchannel("A").crop((2150, 0, 2450, 2160)).getbbox() is None
        print(f"{variant}: background / foreground" +
              (" / landscape" if variant in CLEAR else ""), flush=True)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(HERE.parent))
    from asset_workspace import require_workspace
    require_workspace(REPO)
    build()
