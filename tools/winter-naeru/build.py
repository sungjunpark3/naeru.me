#!/usr/bin/env python3
"""겨울 맑은 낮의 모자·목도리를 정지본·몸짓·근접 원화에 합성한다."""
from pathlib import Path
import json
import shutil
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SOURCE = HERE / "source"
BUILD = HERE / "build"
FRAMES = BUILD / "frames"
BASE_FRAMES = REPO / "tools/naeru-split/build/eyes/day"
SIZE = (576, 496)
HD_SIZE = (4608, 3968)
N_FRAMES = 316
FPS = 24

sys.path.insert(0, str(REPO / "tools/naeru-split"))
from eyes import locate_eye


def main_component(image):
    rgba = np.asarray(image.convert("RGBA")).copy()
    alpha = rgba[:, :, 3]
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        (alpha >= 128).astype(np.uint8), 8)
    main = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    support = cv2.dilate(
        (labels == main).astype(np.uint8), np.ones((5, 5), np.uint8))
    alpha[support == 0] = 0
    rgba[alpha == 0] = 0
    return Image.fromarray(rgba)


def clean_accessory(close_source):
    dressed = np.asarray(Image.open(
        SOURCE / "naeru-day-dressed.png").convert("RGBA"))
    accessory = np.asarray(Image.open(
        SOURCE / "naeru-day-accessories-raw.png").convert("RGBA")).copy()
    assert dressed.shape == accessory.shape == np.asarray(close_source).shape

    alpha = accessory[:, :, 3]
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        (alpha > 32).astype(np.uint8), 8)
    main = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    support = cv2.dilate(
        (labels == main).astype(np.uint8), np.ones((5, 5), np.uint8))
    alpha[support == 0] = 0

    # 액세서리만 다시 그린 결과가 혀 뒤의 가려진 목도리까지 추측해 채웠다.
    # 완성 디자인에서 실제로 보이는 픽셀만 색 차이로 남긴다.
    difference = np.abs(
        dressed[:, :, :3].astype(np.int16) -
        accessory[:, :, :3].astype(np.int16)).mean(axis=2)
    visible = (difference < 72).astype(np.uint8)
    visible = cv2.morphologyEx(
        visible, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    visible = cv2.dilate(visible, np.ones((3, 3), np.uint8))
    alpha = np.rint(alpha.astype(np.float32) * visible).astype(np.uint8)

    # 목도리는 혀 뒤에 있다. 원화의 혀 영역에는 생성기가 추측한 픽셀을
    # 하나도 남기지 않아 평상시·근접 몸짓 모두 같은 앞뒤 관계를 쓴다.
    scale = close_source.width / SIZE[0]
    tongue_points = [
        [200, 166], [238, 158], [266, 163], [283, 170], [269, 180],
        [253, 194], [242, 216], [237, 240], [236, 272], [233, 302],
        [225, 325], [212, 339], [192, 344], [170, 337], [156, 322],
        [149, 300], [149, 271], [158, 240], [174, 207], [189, 183],
    ]
    polygon = np.array([[(round(x * scale), round(y * scale))
                         for x, y in tongue_points]], np.int32)
    tongue = np.zeros_like(alpha)
    cv2.fillPoly(tongue, polygon, 255)
    tongue = cv2.dilate(tongue, np.ones((9, 9), np.uint8))
    alpha[tongue > 0] = 0
    alpha[alpha < 8] = 0
    accessory[:, :, 3] = alpha
    accessory[alpha == 0] = 0
    result = Image.fromarray(accessory)
    assert result.getchannel("A").getbbox() == (420, 72, 961, 649)
    return result


def transform_layer(layer, source_box, target_box):
    sx = (target_box[2] - target_box[0]) / (source_box[2] - source_box[0])
    sy = (target_box[3] - target_box[1]) / (source_box[3] - source_box[1])
    box = layer.getchannel("A").getbbox()
    crop = layer.crop(box).convert("RGBa").resize(
        (round((box[2] - box[0]) * sx),
         round((box[3] - box[1]) * sy)),
        Image.Resampling.LANCZOS).convert("RGBA")
    offset = (
        round(target_box[0] + (box[0] - source_box[0]) * sx) + 32,
        round(target_box[1] + (box[1] - source_box[1]) * sy),
    )
    output = Image.new("RGBA", HD_SIZE)
    output.paste(crop, offset)
    return output


def save_stills(accessory):
    close_source = main_component(Image.open(
        REPO / "tools/naeru-hd/source/naeru-close-day.png"))
    hd_source = Image.open(REPO / "img/naeru-day-hd.webp").convert("RGBA")
    source_box = close_source.getchannel("A").point(
        lambda value: 255 if value >= 128 else 0).getbbox()
    target_box = hd_source.getchannel("A").point(
        lambda value: 255 if value >= 128 else 0).getbbox()

    hd_accessory = transform_layer(accessory, source_box, target_box)
    hd = Image.alpha_composite(hd_source, hd_accessory)
    hd_path = REPO / "img/naeru-winter-day-hd.webp"
    hd.save(hd_path, quality=97, method=6)

    close = main_component(Image.alpha_composite(close_source, accessory))
    close_box = close.getchannel("A").getbbox()
    sx = (target_box[2] - target_box[0]) / (source_box[2] - source_box[0])
    sy = (target_box[3] - target_box[1]) / (source_box[3] - source_box[1])
    crop = close.crop(close_box).convert("RGBa").resize(
        (round((close_box[2] - close_box[0]) * sx),
         round((close_box[3] - close_box[1]) * sy)),
        Image.Resampling.LANCZOS).convert("RGBA")
    offset = (
        round(target_box[0] + (close_box[0] - source_box[0]) * sx) + 32,
        round(target_box[1] + (close_box[1] - source_box[1]) * sy),
    )
    portrait = Image.new("RGBA", HD_SIZE)
    portrait.paste(crop, offset)
    close_path = REPO / "img/naeru-winter-day-close.webp"
    portrait.save(close_path, quality=97, method=6)

    for path in [hd_path, close_path]:
        saved = Image.open(path).convert("RGBA")
        assert saved.size == HD_SIZE
        assert saved.getchannel("A").getextrema() == (0, 255)
        print(f"{path.name}: {path.stat().st_size / 1024:.0f} KiB")
    return hd_accessory.resize(SIZE, Image.Resampling.LANCZOS)


def render_frames(accessory):
    paths = sorted(BASE_FRAMES.glob("*.png"))
    assert len(paths) == N_FRAMES, \
        "tools/naeru-split/build/eyes/day의 316프레임이 필요합니다"
    FRAMES.mkdir(parents=True, exist_ok=True)
    reference_box = locate_eye(Image.open(paths[0]))[0]
    reference_center = ((reference_box[0] + reference_box[2]) / 2,
                        (reference_box[1] + reference_box[3]) / 2)
    for path in paths:
        frame = Image.open(path).convert("RGBA")
        box = locate_eye(frame)[0]
        center = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        moved = Image.new("RGBA", SIZE)
        moved.alpha_composite(
            accessory,
            (round(center[0] - reference_center[0]),
             round(center[1] - reference_center[1])))
        Image.alpha_composite(frame, moved).save(FRAMES / path.name)

    first = Image.open(FRAMES / "0001.png").convert("RGBA")
    # 기존 영상의 양 끝에는 평균 0.33/255의 미세한 색 차이가 있다. 새 겨울
    # 자산은 마지막 장을 첫 장으로 맞춰 모자와 목도리까지 정확히 이어 붙인다.
    first.save(FRAMES / f"{N_FRAMES:04d}.png")
    last = Image.open(FRAMES / f"{N_FRAMES:04d}.png").convert("RGBA")
    assert np.array_equal(np.asarray(first), np.asarray(last))
    first.save(REPO / "img/naeru-winter-day.png", optimize=True)

    neutral = Image.open(REPO / "img/naeru-day-nt.png").convert("RGBA")
    Image.alpha_composite(neutral, accessory).save(
        REPO / "img/naeru-winter-day-nt.png", optimize=True)
    print(f"frames: {len(paths)}, first/last identical")


def encode_videos():
    webm = REPO / "img/naeru-winter-day.webm"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-framerate", str(FPS),
        "-i", str(FRAMES / "%04d.png"), "-c:v", "libvpx-vp9",
        "-pix_fmt", "yuva420p", "-crf", "34", "-b:v", "0",
        "-auto-alt-ref", "0", "-row-mt", "1", "-deadline", "good",
        "-cpu-used", "2", str(webm),
    ], check=True)
    mp4 = REPO / "img/naeru-winter-day.mp4"
    command = [
        "ffmpeg", "-v", "error", "-y", "-framerate", str(FPS),
        "-i", str(FRAMES / "%04d.png"), "-vf", "premultiply=inplace=1",
        "-c:v", "hevc_videotoolbox", "-pix_fmt", "bgra",
        "-alpha_quality", "0.85", "-q:v", "40", "-tag:v", "hvc1",
        "-movflags", "+faststart", str(mp4),
    ]
    encoded = subprocess.run(command).returncode == 0 and mp4.stat().st_size > 0
    if not encoded:
        # 일부 macOS 세션은 ffmpeg의 VideoToolbox 초기화를 -12908로 거부한다.
        # AVFoundation은 같은 HEVC-with-alpha 인코더를 안정적으로 연다.
        prores = BUILD / "naeru-winter-day-prores.mov"
        hevc = BUILD / "naeru-winter-day-hevc.mov"
        subprocess.run([
            "ffmpeg", "-v", "error", "-y", "-framerate", str(FPS),
            "-i", str(FRAMES / "%04d.png"), "-c:v", "prores_ks",
            "-profile:v", "4", "-pix_fmt", "yuva444p10le", str(prores),
        ], check=True)
        subprocess.run([
            "/usr/bin/avconvert", "--source", str(prores),
            "--preset", "PresetHEVCHighestQualityWithAlpha",
            "--output", str(hevc), "--replace",
        ], check=True)
        # HEVC 알파의 보조 계층은 ffmpeg로 MP4에 재먹싱하면 사라진다.
        # Safari는 QuickTime 컨테이너를 .mp4 경로와 video/mp4 MIME으로도 읽는다.
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
    BUILD.mkdir(parents=True, exist_ok=True)
    close_source = Image.open(
        REPO / "tools/naeru-hd/source/naeru-close-day.png").convert("RGBA")
    accessory = clean_accessory(close_source)
    accessory.save(BUILD / "accessories-clean.png")
    runtime_accessory = save_stills(accessory)
    render_frames(runtime_accessory)
    encode_videos()


if __name__ == "__main__":
    main()
