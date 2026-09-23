#!/usr/bin/env python3
"""가을 낮의 풍경 누끼와 끊김 없는 구름 영상을 만든다.

day-outline.jpg는 사용자가 표시한 경계 참고본이다. 풍경 마스크, 빈 하늘,
구름 RGBA는 built-in imagegen으로 만들었고, 이 스크립트가 원본 색상에 맞춰
최종 웹 자산으로 합성한다.
"""
import io
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageChops


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
FRAME_SIZE = (3840, 2160)
VIDEO_SIZE = (1920, 1080)
FPS = 24
DURATION = 60
N_FRAMES = FPS * DURATION
CLOUD_TRAVEL = 700


def load_rgb(path, size):
    image = Image.open(path).convert("RGB")
    return np.asarray(image.resize(size, Image.Resampling.LANCZOS), np.float32)


def build_landscape():
    source = Image.open(REPO / "img/bg-day-autumn.jpg").convert("RGB")
    assert source.size == FRAME_SIZE

    mask = Image.open(HERE / "source/day-landscape-mask.png").convert("L")
    mask = mask.resize(FRAME_SIZE, Image.Resampling.LANCZOS)
    # 생성 마스크의 불투명 내부값 253을 255로 정규화하되 경계 알파는 유지한다.
    mask = mask.point(lambda value: 0 if value <= 4 else
                      255 if value >= 245 else round((value - 4) * 255 / 241))
    assert mask.getextrema() == (0, 255)

    landscape = source.convert("RGBA")
    landscape.putalpha(mask)
    output = REPO / "img/landscape-day-autumn.webp"
    landscape.save(output, lossless=True, exact=True, method=6)

    # 풍경의 불투명 픽셀과 정적 합성 결과는 원본과 정확히 같아야 한다.
    decoded = Image.open(output).convert("RGBA")
    opaque = decoded.getchannel("A").point(
        lambda value: 255 if value == 255 else 0)
    difference = ImageChops.difference(decoded.convert("RGB"), source)
    visible = Image.composite(difference, Image.new("RGB", FRAME_SIZE), opaque)
    assert visible.getbbox() is None
    composite = Image.alpha_composite(
        source.convert("RGBA"), decoded).convert("RGB")
    assert ImageChops.difference(composite, source).getbbox() is None
    print(f"landscape day/autumn: {output.stat().st_size / 1024:.0f} KiB")


def prepare_cloud_layers():
    original = load_rgb(REPO / "img/bg-day-autumn.jpg", VIDEO_SIZE)
    clear_sky = load_rgb(HERE / "source/day-clear-sky.png", VIDEO_SIZE)
    clouds = Image.open(HERE / "source/day-clouds.png").convert("RGBA")
    clouds = np.asarray(
        clouds.resize(VIDEO_SIZE, Image.Resampling.LANCZOS), np.float32)
    cloud_mask = Image.open(HERE / "source/day-cloud-mask.png").convert("L")
    cloud_mask = np.asarray(
        cloud_mask.resize(VIDEO_SIZE, Image.Resampling.LANCZOS), np.float32)

    landscape = Image.open(
        REPO / "img/landscape-day-autumn.webp").convert("RGBA")
    landscape = np.asarray(
        landscape.resize(VIDEO_SIZE, Image.Resampling.LANCZOS), np.float32)
    sky = 1 - landscape[:, :, 3] / 255
    coarse = np.clip(cloud_mask / 254, 0, 1)

    # 생성한 빈 하늘의 청색·노을 기울기를 원본의 맑은 부분에 맞춘다.
    clear = (sky > .98) & (coarse < .03)
    yy, xx = np.indices((VIDEO_SIZE[1], VIDEO_SIZE[0]))
    clear &= (xx + yy) % 8 == 0
    design = np.column_stack((clear_sky[clear] / 255,
                              np.ones(clear.sum())))
    matrix = np.linalg.lstsq(
        design, original[clear] / 255, rcond=None)[0]
    clear_sky = np.clip(
        clear_sky @ matrix[:3] + matrix[3] * 255, 0, 255)

    # 생성 누끼에 섞인 들판 성분을 버리고 하늘에 걸친 구름만 보존한다.
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        (coarse > .06).astype(np.uint8), 8)
    keep = np.zeros_like(coarse)
    for index in range(1, n_labels):
        region = labels == index
        if (stats[index, cv2.CC_STAT_AREA] > 120 and
                sky[region].mean() > .32):
            keep[region] = 1
    keep = cv2.dilate(
        keep.astype(np.uint8), np.ones((7, 7), np.uint8))
    alpha = coarse * keep
    # keep에서 버린 들판 성분을 다시 살리지 않는다.
    solid = (coarse > .35) & (keep > 0)
    alpha[solid] = np.maximum(alpha[solid], coarse[solid])
    alpha = np.clip(alpha, 0, 1)

    # 영상은 전체 화면이지만 DOM 풍경 누끼가 이 위를 같은 좌표로 덮는다.
    base = original * (1 - sky[:, :, None]) + clear_sky * sky[:, :, None]
    return base, clouds[:, :, :3], alpha, sky


def shift(layer, distance):
    matrix = np.float32([[1, 0, distance], [0, 1, 0]])
    return cv2.warpAffine(
        layer, matrix, VIDEO_SIZE, flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def smooth(value):
    value = np.clip(value, 0, 1)
    return value * value * (3 - 2 * value)


def render_cloud_frame(base, color, alpha, sky, progress):
    fade = smooth((progress - .7) / .3)
    layers = [
        (CLOUD_TRAVEL * progress, 1 - fade),
        (-CLOUD_TRAVEL + CLOUD_TRAVEL * progress, fade),
    ]
    frame = base.copy()
    for distance, opacity in layers:
        # 풍경 누끼가 아직 나타나지 않은 첫 화면에서도 구름은 하늘 안에만
        # 있어야 한다. 이동한 뒤 고정된 하늘 개구부로 다시 마스킹한다.
        moved_alpha = shift(alpha, distance) * opacity * sky
        moved_color = shift(color, distance)
        frame = (moved_color * moved_alpha[:, :, None] +
                 frame * (1 - moved_alpha[:, :, None]))
    return np.clip(frame, 0, 255).astype(np.uint8)


def build_cloud_video():
    base, color, alpha, sky = prepare_cloud_layers()
    first = render_cloud_frame(base, color, alpha, sky, 0)
    last = render_cloud_frame(base, color, alpha, sky, 1)
    assert np.array_equal(first, last), "루프 원본의 첫·마지막 프레임이 다름"
    ground = sky == 0
    base_frame = np.clip(base, 0, 255).astype(np.uint8)
    assert np.array_equal(first[ground], base_frame[ground]), \
        "하늘 밖 풍경에 구름 픽셀이 남음"

    output = REPO / "img/sky-day-autumn.mp4"
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pixel_format", "rgb24",
        "-video_size", f"{VIDEO_SIZE[0]}x{VIDEO_SIZE[1]}",
        "-framerate", str(FPS), "-i", "-", "-an",
        "-c:v", "libx264", "-preset", "slow", "-qp", "18",
        "-pix_fmt", "yuv420p",
        "-x264-params",
        f"keyint={N_FRAMES - 1}:min-keyint={N_FRAMES - 1}:scenecut=0:open-gop=0",
        "-movflags", "+faststart", str(output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    for index in range(N_FRAMES):
        progress = index / (N_FRAMES - 1)
        process.stdin.write(
            render_cloud_frame(base, color, alpha, sky, progress).tobytes())
    process.stdin.close()
    assert process.wait() == 0, "ffmpeg 인코딩 실패"

    # 첫·마지막을 각각 IDR로 인코딩해 실제 디코딩 결과까지 같게 만든다.
    capture = cv2.VideoCapture(str(output))
    ok, decoded_first = capture.read()
    assert ok
    capture.set(cv2.CAP_PROP_POS_FRAMES, N_FRAMES - 1)
    ok, decoded_last = capture.read()
    capture.release()
    assert ok and np.array_equal(decoded_first, decoded_last), \
        "인코딩된 루프의 첫·마지막 프레임이 다름"
    # ffmpeg와 브라우저의 영상 색 변환에 맞춘 첫 프레임을 정지본으로 쓴다.
    # OpenCV의 YUV 변환은 평균 약 2단계 밝기 차이가 생겨 교체 순간이 보인다.
    poster_png = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(output),
        "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"
    ])
    poster_output = REPO / "img/sky-day-autumn.webp"
    Image.open(io.BytesIO(poster_png)).convert("RGB").save(
        poster_output, lossless=True, exact=True, method=6)
    print(f"sky day/autumn: {output.stat().st_size / 1024 / 1024:.1f} MiB, "
          f"{DURATION}s, {FPS}fps, decoded endpoints identical")
    print(f"sky day/autumn poster: "
          f"{poster_output.stat().st_size / 1024:.0f} KiB")


build_landscape()
build_cloud_video()
