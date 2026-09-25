#!/usr/bin/env python3
"""승인된 고화질 내루미 한 장으로 가을의 모든 캐릭터 자산을 만든다.

모자·목도리가 없는 ``source/naeru-autumn-day-master.png``만 형태 원본으로
쓴다. 맑음·비의 여덟 조명과 평상시·근접·영상이 같은 실루엣을 공유한다.
"""
from pathlib import Path
import argparse
import hashlib
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
MASTER = SOURCE / "naeru-autumn-day-master.png"
SOURCE_MOTION = SOURCE / "naeru-original-motion.webm"
SOURCE_MOTION_SHA256 = (
    "5158ccbdd8752293123f8dee02a0b75df753cfc86db85b5abe5ad20a40f182c9")
REFERENCE = REPO / "tools/naeru-hd/source/naeru-close-day.png"
REFERENCE_HD = REPO / "img/naeru-day-hd.webp"
LIGHTING_SOURCE = REPO / "tools/naeru-hd/source"
SIZE = (576, 496)
HD_SIZE = (4608, 3968)
N_FRAMES = 316
FPS = 24
CLEAR_VARIANTS = ("dawn", "day", "dusk", "night")
VARIANTS = CLEAR_VARIANTS + tuple(f"{variant}-rain" for variant in CLEAR_VARIANTS)
RAIN_GRADE = {
    "dawn-rain": np.array([.90, .91, .93], np.float32),
    "day-rain": np.array([.84, .86, .89], np.float32),
    "dusk-rain": np.array([.92, .92, .94], np.float32),
}


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
    # 좌표→DOM 좌표 변환을 그대로 적용하면 눈·입·발 위치도 이전 내루미와
    # 맞으면서 평상시와 근접 화면의 그림이 하나로 이어진다.
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
        matrix, floor = models[variant]
        adjusted = section @ matrix[:3] + matrix[3] * 255
        adjusted = np.maximum(adjusted, floor * 255)
        # 비 오는 가을 들판은 맑은 장면보다 주변광이 훨씬 어둡다. 기존 선형
        # 대응만 쓰면 특히 낮 캐릭터가 흰 종이처럼 떠 보여, 배경 실측에 맞춰
        # 새벽·낮·해질녘만 조금 어둡고 차가운 비구름빛으로 눌러 준다.
        if variant in RAIN_GRADE:
            adjusted *= RAIN_GRADE[variant]
        rgba[top:top + 256, :, :3] = np.rint(np.clip(
            adjusted, 0, 255)).astype(np.uint8)
    rgba[rgba[:, :, 3] == 0] = 0
    return Image.fromarray(rgba)


def save_stills(portrait, variant):
    paths = [REPO / f"img/naeru-autumn-{variant}-hd.webp"]
    if variant in CLEAR_VARIANTS:
        paths.append(REPO / f"img/naeru-autumn-{variant}-close.webp")
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
        REPO / f"img/naeru-autumn-{variant}.png", optimize=True)
    return runtime


def smooth(a, b, values):
    values = np.clip((values - a) / (b - a), 0, 1)
    return values * values * (3 - 2 * values)


def motion_mix(index):
    """뉴트럴 원화와 원본 동작 화풍을 눈에 띄지 않게 연결한다."""
    if index <= 1:
        return 0
    if index < 100:
        return float(smooth(0, 1, (index - 1) / 99))
    if index <= 215:
        return 1
    return float(smooth(0, 1, np.clip((N_FRAMES - index) / 101, 0, 1)))


def remap_rgba(rgba, map_x, map_y):
    """RGB를 알파와 함께 이동해 투명 경계의 검은 번짐을 막는다."""
    pixels = rgba.astype(np.float32) / 255
    alpha = pixels[:, :, 3:4]
    premultiplied = np.concatenate((pixels[:, :, :3] * alpha, alpha), axis=2)
    warped = cv2.remap(
        premultiplied, map_x, map_y, cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    out_alpha = np.clip(warped[:, :, 3:4], 0, 1)
    colors = np.divide(
        warped[:, :, :3], np.maximum(out_alpha, 1 / 255),
        out=np.zeros_like(warped[:, :, :3]), where=out_alpha > 0)
    return np.concatenate((np.clip(colors, 0, 1), out_alpha), axis=2)


def morph_motion_frame(neutral, moving, amount):
    """겹선 없이 뉴트럴 원화의 형태를 원본 움직임으로 천천히 넘긴다."""
    if amount <= .001:
        return neutral.copy()
    if amount >= .999:
        return moving.copy()
    first, second = np.asarray(neutral), np.asarray(moving)
    matte = np.array([244, 239, 220], np.float32)

    def grayscale(rgba):
        alpha = rgba[:, :, 3:4].astype(np.float32) / 255
        composite = rgba[:, :, :3] * alpha + matte * (1 - alpha)
        return cv2.cvtColor(
            composite.astype(np.uint8), cv2.COLOR_RGB2GRAY)

    flow = cv2.calcOpticalFlowFarneback(
        grayscale(first), grayscale(second), None,
        .5, 5, 31, 5, 7, 1.5, 0)
    xx, yy = np.meshgrid(
        np.arange(SIZE[0], dtype=np.float32),
        np.arange(SIZE[1], dtype=np.float32))
    first_warped = remap_rgba(
        first, xx - amount * flow[:, :, 0], yy - amount * flow[:, :, 1])
    second_warped = remap_rgba(
        second, xx + (1 - amount) * flow[:, :, 0],
        yy + (1 - amount) * flow[:, :, 1])
    alpha = (first_warped[:, :, 3:4] * (1 - amount) +
             second_warped[:, :, 3:4] * amount)
    colors = (first_warped[:, :, :3] * first_warped[:, :, 3:4] *
              (1 - amount) + second_warped[:, :, :3] *
              second_warped[:, :, 3:4] * amount)
    colors = np.divide(
        colors, np.maximum(alpha, 1 / 255), out=np.zeros_like(colors),
        where=alpha > 0)
    result = np.concatenate((colors, alpha), axis=2)
    return Image.fromarray(np.rint(np.clip(result, 0, 1) * 255).astype(np.uint8))


def motion_luts(old, new):
    """원본 영상의 명암을 승인된 새 원화의 파스텔 팔레트로 옮긴다."""
    old_rgba, new_rgba = np.asarray(old), np.asarray(new)
    old_mask, new_mask = old_rgba[:, :, 3] >= 192, new_rgba[:, :, 3] >= 192
    luts = []
    for channel in range(3):
        old_hist = np.bincount(
            old_rgba[:, :, channel][old_mask], minlength=256).astype(float)
        new_hist = np.bincount(
            new_rgba[:, :, channel][new_mask], minlength=256).astype(float)
        old_cdf = np.cumsum(old_hist) / old_hist.sum()
        new_cdf = np.cumsum(new_hist) / new_hist.sum()
        luts.append(np.searchsorted(new_cdf, old_cdf).clip(
            0, 255).astype(np.uint8))
    return luts


def prepare_motion(day_runtime):
    """4배 복원한 원본 316프레임을 새 가을 원화와 한 계열로 만든다."""
    assert hashlib.sha256(
        SOURCE_MOTION.read_bytes()).hexdigest() == SOURCE_MOTION_SHA256
    frames = BUILD / "base-motion"
    frames.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-v", "error", "-c:v", "libvpx-vp9", "-i",
        str(SOURCE_MOTION), "-f", "rawvideo", "-pix_fmt", "rgba", "pipe:1",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    frame_size = 2304 * 1984 * 4
    first_data = process.stdout.read(frame_size)
    assert len(first_data) == frame_size
    first = Image.frombytes("RGBA", (2304, 1984), first_data).resize(
        SIZE, Image.Resampling.LANCZOS)
    luts = motion_luts(first, day_runtime)

    for index in range(1, N_FRAMES + 1):
        if index == 1:
            original = first
        else:
            data = process.stdout.read(frame_size)
            assert len(data) == frame_size, f"원본 동작 {index}프레임 누락"
            original = Image.frombytes("RGBA", (2304, 1984), data).resize(
                SIZE, Image.Resampling.LANCZOS)
        rgba = np.asarray(original).copy()
        for channel in range(3):
            rgba[:, :, channel] = luts[channel][rgba[:, :, channel]]
        rgba[rgba[:, :, 3] == 0, :3] = 0
        styled = Image.fromarray(rgba)
        amount = motion_mix(index)
        frame = morph_motion_frame(day_runtime, styled, amount)
        frame.save(frames / f"{index:04d}.png", compress_level=2)
    assert process.wait() == 0
    first = Image.open(frames / "0001.png").convert("RGBA")
    last = Image.open(frames / f"{N_FRAMES:04d}.png").convert("RGBA")
    assert np.array_equal(np.asarray(day_runtime), np.asarray(first))
    assert np.array_equal(np.asarray(first), np.asarray(last))
    print("base motion: restored original arms, tongue and body; loop identical")
    return frames


def render_frames(base_frames, runtime, variant, models):
    frames = BUILD / "frames" / variant
    frames.mkdir(parents=True, exist_ok=True)
    for index in range(N_FRAMES):
        if index in (0, N_FRAMES - 1):
            frame = runtime.copy()
        else:
            day_frame = Image.open(
                base_frames / f"{index + 1:04d}.png").convert("RGBA")
            frame = apply_lighting(day_frame, variant, models)
        frame.save(frames / f"{index + 1:04d}.png", optimize=True)

    first = Image.open(frames / "0001.png").convert("RGBA")
    last = Image.open(frames / f"{N_FRAMES:04d}.png").convert("RGBA")
    assert np.array_equal(np.asarray(runtime), np.asarray(first))
    assert np.array_equal(np.asarray(first), np.asarray(last))
    print(f"{variant} frames: {N_FRAMES}, first/last identical")
    return frames


def fit_guide(image, source_box, target_box):
    """구형 분리 자산의 위치만 새 원화 프레임에 맞춘다."""
    crop = image.crop(source_box).convert("RGBa").resize(
        (target_box[2] - target_box[0], target_box[3] - target_box[1]),
        Image.Resampling.LANCZOS).convert("RGBA")
    canvas = Image.new("RGBA", SIZE)
    canvas.paste(crop, target_box[:2])
    return canvas


def save_tongue_assets(frames, variant):
    """기준 프레임에서 혀와 혀 뒤 몸통을 새 원화 기준으로 다시 분리한다."""
    # 선택형 혀 장난은 79번 프레임에서 영상을 멈춘다. 정지본이 아니라 그
    # 프레임을 분리해야 바꿔치는 순간 팔·몸 자세가 달라지지 않는다.
    frame = Image.open(frames / "0079.png").convert("RGBA")
    old_nt = Image.open(
        REPO / f"img/naeru-{variant}-nt.png").convert("RGBA")
    old_tongue = Image.open(
        REPO / f"img/tongue-{variant}.png").convert("RGBA")
    old_frame = Image.alpha_composite(old_nt, old_tongue)
    source_box = threshold_box(old_frame)
    target_box = threshold_box(frame)
    guide_nt = fit_guide(old_nt, source_box, target_box)
    guide_tongue = fit_guide(old_tongue, source_box, target_box)

    # 구형 혀의 알파는 분리 경계의 위치만 안내한다. 보이는 혀 픽셀은 새
    # 원화의 79번 프레임에서 복사해 기존 저해상도 선이 섞이지 않게 한다.
    frame_rgba = np.asarray(frame).copy()
    # 바깥 실루엣의 반투명 1px은 몸 레이어에 남긴다. 생성 원화의 몸 안쪽
    # 알파가 251~255라 혀 영역만 완전 불투명하게 정규화한다.
    mask = ((np.asarray(guide_tongue.getchannel("A")) >= 16) &
            (np.asarray(guide_nt.getchannel("A")) >= 16) &
            (frame_rgba[:, :, 3] >= 251))
    nt_rgba = frame_rgba.copy()
    guide_rgba = np.asarray(guide_nt)
    nt_rgba[mask] = guide_rgba[mask]
    tongue_rgba = frame_rgba.copy()
    tongue_rgba[:, :, 3] = np.where(mask, 255, 0)
    tongue_rgba[~mask, :3] = 0

    nt = Image.fromarray(nt_rgba)
    tongue = Image.fromarray(tongue_rgba)
    nt_path = REPO / f"img/naeru-autumn-{variant}-nt.png"
    tongue_path = REPO / f"img/tongue-autumn-{variant}.png"
    nt.save(nt_path, optimize=True)
    tongue.save(tongue_path, optimize=True)

    # 혀가 완전히 나온 상태에서는 두 레이어가 기준 프레임과 시각적으로 같다.
    # 차이는 생성 원화 내부 알파를 255로 정규화한 최대 4/255뿐이다.
    restored = Image.alpha_composite(nt, tongue)
    difference = np.abs(np.asarray(restored, dtype=np.int16) -
                        frame_rgba.astype(np.int16))
    assert difference.max() <= 4 and difference.mean() < .1
    print(f"{nt_path.name} + {tongue_path.name}: frame 79 MAE "
          f"{difference.mean():.4f}/255")


def encode_videos(variant, frames):
    webm = REPO / f"img/naeru-autumn-{variant}.webm"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-framerate", str(FPS),
        "-i", str(frames / "%04d.png"), "-c:v", "libvpx-vp9",
        "-pix_fmt", "yuva420p", "-crf", "30", "-b:v", "0",
        "-auto-alt-ref", "0", "-row-mt", "1", "-deadline", "good",
        "-cpu-used", "2", str(webm),
    ], check=True)
    mp4 = REPO / f"img/naeru-autumn-{variant}.mp4"
    command = [
        "ffmpeg", "-v", "error", "-y", "-framerate", str(FPS),
        "-i", str(frames / "%04d.png"), "-vf", "premultiply=inplace=1",
        "-c:v", "hevc_videotoolbox", "-pix_fmt", "bgra",
        "-alpha_quality", "0.85", "-q:v", "40", "-tag:v", "hvc1",
        "-movflags", "+faststart", str(mp4),
    ]
    encoded = subprocess.run(command).returncode == 0 and mp4.stat().st_size > 0
    if not encoded:
        prores = BUILD / f"naeru-autumn-{variant}-prores.mov"
        hevc = BUILD / f"naeru-autumn-{variant}-hevc.mov"
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
        default=list(VARIANTS), help="기본값: 가을의 맑음·비 여덟 장면 전부")
    args = parser.parse_args()
    BUILD.mkdir(parents=True, exist_ok=True)
    master = place_master()
    models = lighting_models()
    day_runtime = master.convert("RGBa").resize(
        SIZE, Image.Resampling.LANCZOS).convert("RGBA")
    base_frames = prepare_motion(day_runtime)
    for variant in args.variants:
        print(f"\n[{variant}]")
        portrait = apply_lighting(master, variant, models)
        runtime = save_stills(portrait, variant)
        frames = render_frames(base_frames, runtime, variant, models)
        save_tongue_assets(frames, variant)
        encode_videos(variant, frames)


if __name__ == "__main__":
    main()
