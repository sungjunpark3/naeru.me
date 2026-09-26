#!/usr/bin/env python3
"""승인된 고화질 내루미 한 장으로 가을 캐릭터 자산을 만든다.

평상시·근접 이미지와 영상의 모든 프레임은
``source/naeru-autumn-day-master.png``를 기준으로 한다. 큰 동작은 같은 원화에서
분리한 팔·혀와 복원 몸통을 관절 변형한 뒤 매 프레임 한 장으로 합성한다.
구형 영상의 저해상도 픽셀이나 서로 다른 완성 캐릭터를 섞지 않는다.
"""
from pathlib import Path
import argparse
from functools import lru_cache
import json
import shutil
import subprocess

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SOURCE = HERE / "source"
BUILD = HERE / "build"
MASTER = SOURCE / "naeru-autumn-day-master.png"
ARTICULATED_BASE = SOURCE / "naeru-autumn-articulated-base.png"
REFERENCE = REPO / "tools/naeru-hd/source/naeru-close-day.png"
REFERENCE_HD = REPO / "img/naeru-day-hd.webp"
LIGHTING_SOURCE = REPO / "tools/naeru-hd/source"
SIZE = (576, 496)
MOTION_SIZE = (1152, 992)
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


def save_stills(portrait, variant, runtime=None):
    paths = [REPO / f"img/naeru-autumn-{variant}-hd.webp"]
    if variant in CLEAR_VARIANTS:
        paths.append(REPO / f"img/naeru-autumn-{variant}-close.webp")
    for path in paths:
        portrait.save(path, quality=97, method=6)
        saved = Image.open(path).convert("RGBA")
        assert saved.size == HD_SIZE
        assert saved.getchannel("A").getextrema() == (0, 255)
        print(f"{path.name}: {path.stat().st_size / 1024:.0f} KiB")

    # 작은 정지본은 영상 첫 프레임과 맞추고, HD·근접본은 승인 원화를 쓴다.
    if runtime is None:
        runtime = resize_rgba(portrait, SIZE)
    runtime.save(
        REPO / f"img/naeru-autumn-{variant}.png", optimize=True)
    return runtime


def resize_rgba(image, size):
    """미리 곱한 알파로 축소해 투명 경계의 검은 번짐을 막는다."""
    return image.convert("RGBa").resize(
        size, Image.Resampling.LANCZOS).convert("RGBA")


TONGUE_POINTS = [
    (385, 370), (430, 366), (500, 366), (575, 373), (642, 386),
    (687, 402), (706, 421), (701, 444), (680, 462), (641, 482),
    (608, 505), (585, 539), (570, 585), (563, 650), (558, 730),
    (553, 805), (540, 858), (516, 897), (482, 922), (443, 936),
    (401, 935), (366, 922), (338, 900), (318, 871), (306, 835),
    (299, 790), (298, 742), (304, 692), (315, 640), (327, 587),
    (341, 529), (351, 478), (360, 430), (371, 391),
]
RIGHT_ARM_POINTS = [
    (779, 420), (815, 423), (851, 438), (886, 460), (918, 489),
    (943, 524), (963, 565), (976, 610), (983, 657), (984, 703),
    (976, 741), (958, 770), (934, 792), (907, 802), (881, 800),
    (855, 788), (834, 767), (817, 738), (811, 701), (801, 662),
    (787, 625), (772, 591), (761, 558), (758, 526), (764, 491),
]
LEFT_ARM_POINTS = [
    (365, 428), (340, 444), (314, 466), (286, 494), (259, 526),
    (236, 560), (215, 598), (200, 635), (193, 667), (196, 695),
    (207, 716), (223, 726), (241, 723), (257, 710), (270, 690),
    (282, 662), (294, 628), (310, 587), (327, 545), (343, 503),
    (358, 464), (376, 438),
]


def soft_polygon(size, points):
    """원화 윤곽을 1px만 부드럽게 잘라 확대해도 톱니가 생기지 않게 한다."""
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    return mask.filter(ImageFilter.GaussianBlur(1))


def extract_layer(master, mask):
    """투명 RGB까지 정리한 원화 조각을 만든다."""
    rgba = np.asarray(master).copy()
    rgba[:, :, 3] = np.rint(
        rgba[:, :, 3].astype(np.float32) *
        np.asarray(mask, dtype=np.float32) / 255).astype(np.uint8)
    rgba[rgba[:, :, 3] == 0, :3] = 0
    return Image.fromarray(rgba)


def transform_about(pivot, angle, scale=1, dx=0, dy=0, flip=False):
    """관절을 고정한 채 회전·반사하는 2×3 행렬을 만든다."""
    px, py = pivot
    reflected = (np.array([
        [-1., 0., 2 * px], [0., 1., 0.], [0., 0., 1.]
    ]) if flip else np.eye(3))
    rotated = np.vstack([
        cv2.getRotationMatrix2D((px, py), angle, scale), [0, 0, 1]
    ])
    translated = np.array([
        [1., 0., dx], [0., 1., dy], [0., 0., 1.]
    ])
    return (translated @ rotated @ reflected)[:2].astype(np.float32)


def premultiplied_warp(image, matrix):
    """관절 가장자리에 검은 번짐이 생기지 않도록 알파를 미리 곱해 변형한다."""
    rgba = np.asarray(image.convert("RGBA"), dtype=np.float32).copy()
    alpha = rgba[:, :, 3:4] / 255
    rgba[:, :, :3] *= alpha
    warped = cv2.warpAffine(
        rgba, matrix, image.size, flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    alpha = warped[:, :, 3:4] / 255
    warped[:, :, :3] = np.divide(
        warped[:, :, :3], alpha, out=np.zeros_like(warped[:, :, :3]),
        where=alpha > 1e-5)
    warped = np.rint(np.clip(warped, 0, 255)).astype(np.uint8)
    warped[warped[:, :, 3] == 0, :3] = 0
    return Image.fromarray(warped)


def premultiplied_blend(first, second, amount):
    """두 완성 프레임을 투명 경계의 검은 테두리 없이 섞는다."""
    first_rgba = np.asarray(first.convert("RGBA"), dtype=np.float32)
    second_rgba = np.asarray(second.convert("RGBA"), dtype=np.float32)
    first_alpha = first_rgba[:, :, 3:4] / 255
    second_alpha = second_rgba[:, :, 3:4] / 255
    first_rgb = first_rgba[:, :, :3] * first_alpha
    second_rgb = second_rgba[:, :, :3] * second_alpha
    alpha = first_alpha * (1 - amount) + second_alpha * amount
    rgb = first_rgb * (1 - amount) + second_rgb * amount
    rgb = np.divide(rgb, alpha, out=np.zeros_like(rgb), where=alpha > 1e-5)
    result = np.concatenate((rgb, alpha * 255), axis=2)
    result = np.rint(np.clip(result, 0, 255)).astype(np.uint8)
    result[result[:, :, 3] == 0, :3] = 0
    return Image.fromarray(result)


@lru_cache(maxsize=None)
def artwork_layout(size):
    """반복 프레임에서 같은 원화→DOM 좌표 계산을 재사용한다."""
    reference_box = threshold_box(main_component(Image.open(REFERENCE)))
    target_box = threshold_box(Image.open(REFERENCE_HD).convert("RGBA"))
    sx = (target_box[2] - target_box[0]) / (
        reference_box[2] - reference_box[0])
    sy = (target_box[3] - target_box[1]) / (
        reference_box[3] - reference_box[1])
    scale_x, scale_y = size[0] / HD_SIZE[0], size[1] / HD_SIZE[1]
    rendered_size = (
        round(1351 * sx * scale_x), round(1164 * sy * scale_y))
    offset = (
        round((target_box[0] - reference_box[0] * sx + 32) * scale_x),
        round((target_box[1] - reference_box[1] * sy) * scale_y),
    )
    return rendered_size, offset


def place_artwork(artwork, size):
    """원화 좌표를 기존 DOM 프레임 좌표로 옮긴다."""
    rendered_size, offset = artwork_layout(size)
    rendered = artwork.convert("RGBa").resize(
        rendered_size, Image.Resampling.LANCZOS).convert("RGBA")
    canvas = Image.new("RGBA", size)
    canvas.paste(rendered, offset, rendered)
    return canvas


def motion_amount(seconds):
    """4.5~8.4초에 움츠렸다가 두 팔과 혀를 크게 펴고 돌아온다."""
    def smooth(start, end):
        value = np.clip((seconds - start) / (end - start), 0, 1)
        return value * value * (3 - 2 * value)

    envelope = smooth(4.45, 5.35) * (1 - smooth(7.45, 8.35))
    if envelope <= 0:
        return 0
    # 정점에서 한 번 더 힘을 줘 기계적인 정지 자세가 되지 않게 한다.
    pulse = .94 + .06 * np.sin(np.clip(
        (seconds - 5.35) / 2.1, 0, 1) * np.pi * 3) ** 2
    return float(envelope * pulse)


def breathing_amount(index):
    """정지 기준 프레임들에서 정확히 0이 되는 연속 호흡 곡선이다."""
    anchors = (0, 78, 236, N_FRAMES - 1)
    for start, end in zip(anchors, anchors[1:]):
        if start <= index <= end:
            progress = (index - start) / (end - start)
            return float(np.sin(progress * np.pi) ** 2)
    raise AssertionError(f"호흡 프레임 범위 오류: {index}")


def smooth_unit(value):
    """0~1 값을 속도가 끊기지 않는 곡선으로 바꾼다."""
    value = np.clip(value, 0, 1)
    return float(value * value * (3 - 2 * value))


def articulate(master, base, tongue, left_arm, right_arm, amount):
    """고화질 원화 조각을 움직여 한 장의 완성 동작 프레임으로 합친다."""
    if amount <= 0:
        return master.copy()

    # 원본 자세와 관절용 몸통을 먼저 같은 자세로 맞춘 뒤 팔을 움직인다.
    # 이 짧은 준비 구간 덕분에 첫 동작 프레임에서 팔의 크기나 모양이 갑자기
    # 바뀌지 않는다. 실제 관절 회전은 전환이 끝날 무렵부터 시작한다.
    rig_weight = smooth_unit(amount / .10)
    pose = smooth_unit((amount - .07) / .93)
    foot = (650, 1040)
    scale_x = 1 + .015 * pose
    scale_y = 1 - .040 * pose
    crouch = np.array([
        [scale_x, 0, foot[0] * (1 - scale_x)],
        [0, scale_y, foot[1] * (1 - scale_y) + 20 * pose],
    ], dtype=np.float32)
    body = premultiplied_warp(base, crouch)
    left = premultiplied_warp(left_arm, transform_about(
        (360, 440), -52 * pose, scale=1 + .06 * pose,
        dx=-5 * pose, dy=-2 * pose))
    right = premultiplied_warp(right_arm, transform_about(
        (785, 435), 48 * pose, dx=6 * pose, dy=-5 * pose))
    moving_tongue = premultiplied_warp(tongue, transform_about(
        (505, 405), -24 * pose, dx=-3 * pose, dy=-2 * pose))
    right = premultiplied_warp(right, crouch)
    left = premultiplied_warp(left, crouch)
    moving_tongue = premultiplied_warp(moving_tongue, crouch)
    body.alpha_composite(left)
    body.alpha_composite(right)
    body.alpha_composite(moving_tongue)
    if rig_weight < 1:
        return premultiplied_blend(master, body, rig_weight)
    return body


def prepare_motion():
    """고화질 기준 원화만 사용해 316장의 단일 합성 프레임을 만든다."""
    frames = BUILD / "base-motion"
    frames.mkdir(parents=True, exist_ok=True)
    master = main_component(Image.open(MASTER))
    base = main_component(Image.open(ARTICULATED_BASE))
    assert master.size == base.size == (1351, 1164)
    tongue = extract_layer(master, soft_polygon(master.size, TONGUE_POINTS))
    left_arm = extract_layer(
        master, soft_polygon(master.size, LEFT_ARM_POINTS))
    right_arm = extract_layer(
        master, soft_polygon(master.size, RIGHT_ARM_POINTS))
    previous = None
    frame_differences = []

    for index in range(N_FRAMES):
        seconds = index / FPS
        amount = motion_amount(seconds)
        artwork = articulate(
            master, base, tongue, left_arm, right_arm, amount)

        # 호흡은 큰 몸짓 전후에도 끊지 않는다. 기준 프레임에서는 곡선의 값과
        # 속도가 모두 0이라 정지본 전환과 영상 루프에서도 한 프레임도 튀지 않는다.
        breath = breathing_amount(index)
        if breath > 0:
            matrix = np.array([
                [1 + .002 * breath, 0, -.9 * breath],
                [0, 1 - .007 * breath, 5.5 * breath],
            ], dtype=np.float32)
            artwork = premultiplied_warp(artwork, matrix)
        frame = place_artwork(artwork, MOTION_SIZE)
        frame.save(frames / f"{index + 1:04d}.png", compress_level=2)

        # 팔·혀가 실제로 몸에서 떨어지지 않았는지 매 프레임 검사한다.
        # 9px 침식 뒤에도 하나의 덩어리여야 가느다란 우연한 접점이 아니다.
        rgba = np.asarray(frame)
        alpha = (rgba[:, :, 3] >= 64).astype(np.uint8)
        alpha = cv2.erode(alpha, np.ones((9, 9), np.uint8))
        _, _, stats, _ = cv2.connectedComponentsWithStats(alpha, 8)
        components = sum(
            area > 20 for area in stats[1:, cv2.CC_STAT_AREA])
        assert components == 1, \
            f"{index + 1}번 프레임에서 신체가 분리됨: {components}개"
        if previous is not None:
            difference = np.abs(
                rgba.astype(np.int16) - previous.astype(np.int16)).mean()
            frame_differences.append(float(difference))
        previous = rgba

    first = Image.open(frames / "0001.png").convert("RGBA")
    last = Image.open(frames / f"{N_FRAMES:04d}.png").convert("RGBA")
    assert np.array_equal(np.asarray(first), np.asarray(last))
    accelerations = np.abs(np.diff(frame_differences))
    assert max(frame_differences) < 3, \
        f"프레임 간 동작이 튐: {max(frame_differences):.3f}"
    assert max(accelerations) < .6, \
        f"프레임 간 속도가 갑자기 바뀜: {max(accelerations):.3f}"
    print("base motion: approved HD master only; separate left/right arms, "
          "tongue and body; connected every frame; loop identical; "
          f"max step {max(frame_differences):.3f}, "
          f"max acceleration {max(accelerations):.3f}")
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
        frame.save(frames / f"{index + 1:04d}.png", compress_level=2)

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
    frame = resize_rgba(
        Image.open(frames / "0079.png").convert("RGBA"), SIZE)
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
        "-auto-alt-ref", "0", "-g", str(N_FRAMES - 1), "-row-mt", "1",
        "-deadline", "good", "-cpu-used", "2", str(webm),
    ], check=True)
    mp4 = REPO / f"img/naeru-autumn-{variant}.mp4"
    command = [
        "ffmpeg", "-v", "error", "-y", "-framerate", str(FPS),
        "-i", str(frames / "%04d.png"), "-vf", "premultiply=inplace=1",
        "-c:v", "hevc_videotoolbox", "-pix_fmt", "bgra",
        "-alpha_quality", "0.85", "-q:v", "40", "-g",
        str(N_FRAMES - 1), "-tag:v", "hvc1", "-movflags", "+faststart",
        str(mp4),
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
    base_frames = prepare_motion()
    for variant in args.variants:
        print(f"\n[{variant}]")
        portrait = apply_lighting(master, variant, models)
        first_motion = Image.open(base_frames / "0001.png").convert("RGBA")
        first_motion = apply_lighting(first_motion, variant, models)
        runtime = resize_rgba(first_motion, SIZE)
        save_stills(portrait, variant, runtime)
        frames = render_frames(base_frames, first_motion, variant, models)
        save_tongue_assets(frames, variant)
        encode_videos(variant, frames)


if __name__ == "__main__":
    main()
