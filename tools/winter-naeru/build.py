#!/usr/bin/env python3
"""새로 그린 겨울 내루미 한 장으로 맑음·비 여덟 시간대 자산을 만든다.

기존 내루미 위에 장신구를 얹지 않는다. 모자·목도리·몸이 한 그림인
``source/naeru-winter-day-master.png``만 형태 원본으로 쓰고 시간대별로
조명만 바꾼다.
"""
from pathlib import Path
import argparse
import json
import shutil
import subprocess

import cv2
import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SOURCE = HERE / "source"
BUILD = HERE / "build"
MASTER = SOURCE / "naeru-winter-day-master.png"
REFERENCE = REPO / "tools/naeru-hd/source/naeru-close-day.png"
REFERENCE_HD = REPO / "img/naeru-day-hd.webp"
LIGHTING_SOURCE = REPO / "tools/naeru-hd/source"
SIZE = (576, 496)
HD_SIZE = (4608, 3968)
N_FRAMES = 316
FPS = 24
CLEAR_VARIANTS = ("dawn", "day", "dusk", "night")
VARIANTS = CLEAR_VARIANTS + tuple(
    f"{variant}-rain" for variant in CLEAR_VARIANTS)


def main_component(image):
    """생성기 여백의 미세한 점을 버리고 본체 알파만 보존한다."""
    rgba = np.asarray(image.convert("RGBA")).copy()
    alpha = rgba[:, :, 3]
    _, labels, stats, _ = cv2.connectedComponentsWithStats(
        (alpha >= 128).astype(np.uint8), 8)
    main = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    support = cv2.dilate(
        (labels == main).astype(np.uint8), np.ones((5, 5), np.uint8))
    alpha[support == 0] = 0
    rgba[alpha == 0] = 0
    return Image.fromarray(rgba)


def threshold_box(image):
    return image.getchannel("A").point(
        lambda value: 255 if value >= 128 else 0).getbbox()


def place_master():
    """기존 DOM 좌표에 눈·입·발이 맞도록 새 전신 원화를 정렬한다."""
    master = main_component(Image.open(MASTER))
    reference = main_component(Image.open(REFERENCE))
    target = Image.open(REFERENCE_HD).convert("RGBA")
    reference_box = threshold_box(reference)
    target_box = threshold_box(target)
    visible = master.getchannel("A").getbbox()

    # 두 원화가 같은 1351×1164 좌표와 같은 자세를 사용한다. 기존 원화의
    # 좌표→DOM 좌표 변환을 그대로 적용하면 새 그림의 모자까지 포함하면서
    # 눈·입·발 위치는 이전 내루미와 맞는다.
    sx = (target_box[2] - target_box[0]) / (
        reference_box[2] - reference_box[0])
    sy = (target_box[3] - target_box[1]) / (
        reference_box[3] - reference_box[1])
    crop = master.crop(visible).convert("RGBa").resize(
        (round((visible[2] - visible[0]) * sx),
         round((visible[3] - visible[1]) * sy)),
        Image.Resampling.LANCZOS).convert("RGBA")
    offset = (
        round(target_box[0] + (visible[0] - reference_box[0]) * sx) + 32,
        round(target_box[1] + (visible[1] - reference_box[1]) * sy),
    )
    portrait = Image.new("RGBA", HD_SIZE)
    portrait.paste(crop, offset)
    return portrait


def lighting_models():
    """기존 네 시간대 원화의 RGB 대응으로 선형 조명 변환을 구한다."""
    day = np.asarray(
        Image.open(LIGHTING_SOURCE / "naeru-day.png").convert("RGBA"),
        dtype=np.float32)
    mask = cv2.erode(
        (day[:, :, 3] == 255).astype(np.uint8),
        np.ones((7, 7), np.uint8)) > 0
    source = day[:, :, :3][mask] / 255
    design = np.column_stack((source, np.ones(len(source))))
    models = {"day": None}
    for variant in VARIANTS:
        if variant == "day":
            continue
        target = np.asarray(Image.open(
            LIGHTING_SOURCE / f"naeru-{variant}.png").convert("RGBA"),
            dtype=np.float32)[:, :, :3][mask] / 255
        matrix = np.linalg.lstsq(design, target, rcond=None)[0]
        darkest = source.mean(axis=1) <= np.quantile(
            source.mean(axis=1), .015)
        floor = np.median(target[darkest], axis=0)
        error = np.mean(np.abs(np.maximum(design @ matrix, floor) - target))
        models[variant] = (matrix, floor)
        print(f"{variant} lighting MAE: {error * 255:.2f}/255")
    return models


def apply_lighting(portrait, variant, models):
    """큰 원화의 메모리 사용량을 제한하며 색만 바꾸고 알파는 유지한다."""
    if variant == "day":
        return portrait.copy()
    rgba = np.asarray(portrait.convert("RGBA")).copy()
    for top in range(0, rgba.shape[0], 256):
        section = rgba[top:top + 256, :, :3].astype(np.float32)
        if variant in ("night", "night-rain"):
            # 포근한 새 겨울밤 설원은 눈의 반사광이 밝다. 이전 밤 캐릭터의
            # 조명식을 그대로 쓰면 평균 RGB가 22/24/47까지 내려가 얼굴과
            # 방한복 디테일이 사라지므로, 낮 원화에 차가운 달빛을 직접 입힌다.
            strength = ([.38, .42, .56], [5, 8, 12]) if variant == "night" \
                else ([.32, .36, .50], [4, 7, 11])
            adjusted = (section * np.array(strength[0], np.float32) +
                        np.array(strength[1], np.float32))
        else:
            matrix, floor = models[variant]
            adjusted = section @ matrix[:3] + matrix[3] * 255
            adjusted = np.maximum(adjusted, floor * 255)
        rgba[top:top + 256, :, :3] = np.rint(np.clip(
            adjusted, 0, 255)).astype(np.uint8)
    rgba[rgba[:, :, 3] == 0] = 0
    return Image.fromarray(rgba)


def save_stills(portrait, variant):
    paths = [REPO / f"img/naeru-winter-{variant}-hd.webp"]
    if variant in CLEAR_VARIANTS:
        paths.append(REPO / f"img/naeru-winter-{variant}-close.webp")
    for path in paths:
        portrait.save(path, quality=97, method=6)
        saved = Image.open(path).convert("RGBA")
        assert saved.size == HD_SIZE
        assert saved.getchannel("A").getextrema() == (0, 255)
        print(f"{path.name}: {path.stat().st_size / 1024:.0f} KiB")

    # 정지본·영상·근접본이 모두 같은 새 그림에서 출발한다.
    runtime = portrait.convert("RGBa").resize(
        SIZE, Image.Resampling.LANCZOS).convert("RGBA")
    runtime.save(
        REPO / f"img/naeru-winter-{variant}.png", optimize=True)
    runtime.save(
        REPO / f"img/naeru-winter-{variant}-nt.png", optimize=True)
    return runtime


def smooth(a, b, values):
    values = np.clip((values - a) / (b - a), 0, 1)
    return values * values * (3 - 2 * values)


def motion_weights():
    """웹의 근접 리그와 같은 혀·양팔 영향 영역을 만든다."""
    xx, yy = np.meshgrid(
        np.arange(SIZE[0], dtype=np.float32),
        np.arange(SIZE[1], dtype=np.float32))
    tongue_points = np.array([
        [200, 166], [238, 158], [266, 163], [283, 170], [269, 180],
        [253, 194], [242, 216], [237, 240], [236, 272], [233, 302],
        [225, 325], [212, 339], [192, 344], [170, 337], [156, 322],
        [149, 300], [149, 271], [158, 240], [174, 207], [189, 183],
    ], np.int32)
    inside = np.zeros((SIZE[1], SIZE[0]), np.uint8)
    cv2.fillPoly(inside, [tongue_points], 1)
    distance_in = cv2.distanceTransform(inside, cv2.DIST_L2, 5)
    distance_out = cv2.distanceTransform(1 - inside, cv2.DIST_L2, 5)
    signed = np.where(inside > 0, distance_in, -distance_out)
    tongue = smooth(-32, 7, signed) * smooth(160, 220, yy)

    def arm(ax, ay, bx, by, radius):
        dx, dy = bx - ax, by - ay
        position = np.clip(
            ((xx - ax) * dx + (yy - ay) * dy) / (dx * dx + dy * dy),
            0, 1)
        distance = np.hypot(
            xx - ax - position * dx, yy - ay - position * dy)
        return 1 - smooth(radius, radius + 64, distance)

    right = (arm(323, 183, 358, 272, 22) * smooth(168, 217, yy) *
             (1 - tongue))
    left = (arm(184, 198, 141, 258, 14) * smooth(187, 228, yy) *
            (1 - tongue))
    right *= (1 - smooth(294, 318, yy)) * (1 - smooth(380, 430, xx))
    left *= 1 - smooth(278, 307, yy)
    return xx, yy, tongue, right, left


def source_map(xx, yy, weights, motion):
    """웹 리그의 정방향 변형을 역산해 각 출력 화소의 원본을 찾는다."""
    tongue, right, left = weights
    body_motion, arm_motion, tongue_motion = motion
    source_x = xx.copy()
    source_y = yy.copy()

    # 변형량이 작고 매끄러워 고정점 반복 네 번이면 0.02px 안으로 수렴한다.
    for _ in range(4):
        angle = arm_motion * .22
        cosine, sine = np.cos(angle), np.sin(angle)
        right_x, right_y = source_x - 323, source_y - 183
        left_x, left_y = source_x - 184, source_y - 198
        delta_x = right * (
            cosine * right_x + sine * right_y - right_x)
        delta_y = right * (
            -sine * right_x + cosine * right_y - right_y)
        delta_x += left * (
            cosine * left_x - sine * left_y - left_x)
        delta_y += left * (
            sine * left_x + cosine * left_y - left_y)
        tongue_factor = tongue * tongue_motion * np.maximum(
            0, (source_y - 164) / 180)
        delta_x -= tongue_factor * 10
        delta_y -= tongue_factor * 13
        delta_y += body_motion * 7 * (1 - smooth(180, 392, source_y))
        source_x = xx - delta_x
        source_y = yy - delta_y
    return source_x.astype(np.float32), source_y.astype(np.float32)


def warp(image, maps):
    rgba = np.asarray(image, dtype=np.float32) / 255
    alpha = rgba[:, :, 3:4]
    premultiplied = np.concatenate((rgba[:, :, :3] * alpha, alpha), axis=2)
    mapped = cv2.remap(
        premultiplied, maps[0], maps[1], cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    out_alpha = np.clip(mapped[:, :, 3:4], 0, 1)
    colors = np.divide(
        mapped[:, :, :3], np.maximum(out_alpha, 1 / 255),
        out=np.zeros_like(mapped[:, :, :3]), where=out_alpha > 0)
    result = np.concatenate((np.clip(colors, 0, 1), out_alpha), axis=2)
    return Image.fromarray(np.rint(result * 255).astype(np.uint8))


def pulse(value, start, end):
    if value <= start or value >= end:
        return 0
    phase = (value - start) / (end - start)
    return np.sin(phase * np.pi) ** 2


def render_frames(runtime, variant):
    frames = BUILD / "frames" / variant
    frames.mkdir(parents=True, exist_ok=True)
    xx, yy, tongue, right, left = motion_weights()
    for index in range(N_FRAMES):
        time = index / (N_FRAMES - 1)
        # 몸이 먼저 살짝 움츠러들고 양팔과 혀가 뒤따라 움직인다. 시작·끝은
        # motion=0이라 첫 프레임과 마지막 프레임이 바이트 단위로 일치한다.
        motion = (
            .72 * pulse(time, .08, .88),
            .62 * pulse(time, .12, .92),
            .50 * pulse(time, .16, .96),
        )
        if index in (0, N_FRAMES - 1):
            frame = runtime.copy()
        else:
            maps = source_map(xx, yy, (tongue, right, left), motion)
            frame = warp(runtime, maps)
        frame.save(frames / f"{index + 1:04d}.png", optimize=True)

    first = Image.open(frames / "0001.png").convert("RGBA")
    last = Image.open(frames / f"{N_FRAMES:04d}.png").convert("RGBA")
    assert np.array_equal(np.asarray(runtime), np.asarray(first))
    assert np.array_equal(np.asarray(first), np.asarray(last))
    print(f"{variant} frames: {N_FRAMES}, first/last identical")
    return frames


def encode_videos(variant, frames):
    webm = REPO / f"img/naeru-winter-{variant}.webm"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-framerate", str(FPS),
        "-i", str(frames / "%04d.png"), "-c:v", "libvpx-vp9",
        "-pix_fmt", "yuva420p", "-crf", "30", "-b:v", "0",
        "-auto-alt-ref", "0", "-row-mt", "1", "-deadline", "good",
        "-cpu-used", "2", str(webm),
    ], check=True)
    mp4 = REPO / f"img/naeru-winter-{variant}.mp4"
    command = [
        "ffmpeg", "-v", "error", "-y", "-framerate", str(FPS),
        "-i", str(frames / "%04d.png"), "-vf", "premultiply=inplace=1",
        "-c:v", "hevc_videotoolbox", "-pix_fmt", "bgra",
        "-alpha_quality", "0.85", "-q:v", "40", "-tag:v", "hvc1",
        "-movflags", "+faststart", str(mp4),
    ]
    encoded = subprocess.run(command).returncode == 0 and mp4.stat().st_size > 0
    if not encoded:
        prores = BUILD / f"naeru-winter-{variant}-prores.mov"
        hevc = BUILD / f"naeru-winter-{variant}-hevc.mov"
        subprocess.run([
            "ffmpeg", "-v", "error", "-y", "-framerate", str(FPS),
            "-i", str(frames / "%04d.png"), "-c:v", "prores_ks",
            "-profile:v", "4", "-pix_fmt", "yuva444p10le", str(prores),
        ], check=True)
        subprocess.run([
            "/usr/bin/avconvert", "--source", str(prores),
            "--preset", "PresetHEVCHighestQualityWithAlpha",
            "--output", str(hevc), "--replace",
        ], check=True)
        shutil.copyfile(hevc, mp4)
    for path in [webm, mp4]:
        probe = json.loads(subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-count_frames", "-show_entries", "stream=nb_read_frames",
            "-of", "json", str(path),
        ], text=True))
        assert int(probe["streams"][0]["nb_read_frames"]) == N_FRAMES
        print(f"{path.name}: {path.stat().st_size / 1024:.0f} KiB")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "variants", nargs="*", choices=VARIANTS,
        default=list(VARIANTS), help="기본값: 겨울의 맑음·비 여덟 장면 전부")
    args = parser.parse_args()
    BUILD.mkdir(parents=True, exist_ok=True)
    master = place_master()
    models = lighting_models()
    for variant in args.variants:
        print(f"\n[{variant}]")
        portrait = apply_lighting(master, variant, models)
        runtime = save_stills(portrait, variant)
        frames = render_frames(runtime, variant)
        encode_videos(variant, frames)


if __name__ == "__main__":
    main()
