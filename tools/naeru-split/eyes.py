#!/usr/bin/env python3
"""생성한 눈 원화를 기존 영상의 눈 윤곽에 맞춰 합성한다.

eye.png는 built-in imagegen 편집 결과의 144×144 축소본이다.
프롬프트: Remove the pale horizontal stripe and curved pale eyelid cap.
Make the existing eye one uninterrupted deep warm dark-brown oval.
Preserve its exact silhouette, location, size, tilt and surrounding pink skin.
No eyelid crease, bands, highlight, lash or added outline.

원본 프레임은 보존하고 build/eyes/<변형>/에 인코딩용 시퀀스를 만든다.
고정 위치에 눈을 덮지 않고 매 프레임의 윤곽·눈 감음·흐림을 따라간다.
"""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
TEXTURE = np.asarray(Image.open(HERE / "eye.png").convert("RGB")
                     .crop((63, 61, 81, 84)), dtype=np.float32)
TEXTURE = TEXTURE - np.median(TEXTURE.reshape(-1, 3), axis=0)


def locate_eye(reference):
    """공통 낮 프레임에서 위치와 합성 마스크를 구해 8종에 같이 적용한다."""
    rgb = np.asarray(reference.convert("RGB"))
    gray = rgb.mean(axis=2).astype(np.uint8)
    roi = gray[95:169, 249:298]
    _, _, stats, _ = cv2.connectedComponentsWithStats((roi < 110).astype(np.uint8))
    candidates = [s for s in stats[1:] if
                  15 < s[4] < 330 and s[2] < 27 and s[3] < 36 and
                  s[1] + s[3] < roi.shape[0]]
    assert len(candidates) == 1, "눈 추적 실패: 다른 얼굴 부위를 수정하지 않는다"
    x, y, width, height, _ = candidates[0]
    x, y = int(x) + 249, int(y) + 95
    box = (x - 4, y - 10, x + int(width) + 4, y + int(height) + 4)
    q = rgb[box[1]:box[3], box[0]:box[2]].astype(np.float32)
    light = q.mean(axis=2)
    skin = np.median(np.concatenate((q[0], q[-1], q[:, 0], q[:, -1])), axis=0)
    core = light < np.quantile(light, .12)
    dark = np.median(q[core], axis=0)
    coverage = np.clip((skin.mean() - light) / (skin.mean() - dark.mean()), 0, 1)

    # 분리된 윗눈꺼풀도 같은 외곽선 안에 포함한다. 감긴 눈은 그 프레임의
    # 납작한 윤곽을 그대로 쓰므로 눈을 억지로 뜨게 하지 않는다.
    points = np.column_stack(np.nonzero(coverage > .25)[::-1]).astype(np.int32)
    hull = cv2.convexHull(points)
    large = np.zeros((q.shape[0] * 8, q.shape[1] * 8), np.uint8)
    cv2.fillConvexPoly(large, hull * 8 + 4, 255)
    large = cv2.GaussianBlur(large, (0, 0), 3)
    filled = cv2.resize(large, (q.shape[1], q.shape[0]),
                        interpolation=cv2.INTER_AREA) / 255
    # 원래 어두운 눈과 바깥 경계는 보존하고, 안쪽의 밝은 띠만 채운다.
    blend = np.clip((filled - coverage) / np.maximum(1 - coverage, .001), 0, 1)
    return box, blend[:, :, None], core


def replace_eye(image, patch):
    """같은 윤곽 안에서 원화의 색만 해당 시간대 눈의 암부색에 맞춘다."""
    box, blend, core = patch
    original = np.asarray(image.convert("RGBA"))
    rgba = original.copy()
    x0, y0, x1, y1 = box
    q = rgba[y0:y1, x0:x1, :3].astype(np.float32)
    dark = np.median(q[core], axis=0)
    fill = cv2.resize(TEXTURE, (x1 - x0, y1 - y0)) + dark
    rgba[y0:y1, x0:x1, :3] = np.rint(np.clip(
        q * (1 - blend) + fill * blend, 0, 255)).astype(np.uint8)
    assert np.array_equal(rgba[:, :, 3], original[:, :, 3])
    return Image.fromarray(rgba)


if __name__ == "__main__":
    from coords import N_FRAMES, VARIANTS

    frames = sorted((HERE / "build" / "naeru-day").glob("*.png"))
    assert len(frames) == N_FRAMES
    patches = [locate_eye(Image.open(p)) for p in frames]
    for variant in VARIANTS:
        output = HERE / "build" / "eyes" / variant
        output.mkdir(parents=True, exist_ok=True)
        for path, patch in zip(frames, patches):
            source = Image.open(HERE / "build" / f"naeru-{variant}" / path.name)
            replace_eye(source, patch).save(output / path.name)
        print(f"{variant}: {len(frames)} frames, original alpha preserved", flush=True)
