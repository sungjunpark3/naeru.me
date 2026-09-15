"""보존한 잔디 복원본으로 배경의 캐릭터 그림자만 지운다. 계절 채색 전에 적용한다."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
RECT = (1456, 1512, 2256, 1912)
SIZE = (800, 400)
# 입력 크롭 안에서 그림자가 차지하던 자리. 꽃·앞풀·나무 그림자는 포함하지 않는다.
FOOTPRINT = [(128, 231), (180, 204), (238, 188), (305, 169), (390, 165),
             (464, 157), (589, 161), (625, 181), (638, 211), (591, 232),
             (461, 247), (355, 256), (248, 269), (153, 269)]


def repair_ground(base):
    """RGB float 배열을 받아 같은 크기로 돌려준다. 수정 영역 밖은 그대로다."""
    x0, y0, x1, y1 = RECT
    target = base[y0:y1, x0:x1]
    assert target.shape == (SIZE[1], SIZE[0], 3), "배경 크롭 좌표 불일치"
    source = Image.open(HERE / "source" / "day-repair.png").convert("RGB")
    source = np.asarray(source.resize(SIZE, Image.Resampling.LANCZOS), np.float32)
    mask = Image.new("L", SIZE)
    ImageDraw.Draw(mask).polygon(FOOTPRINT, fill=255)
    # 완전히 지우는 범위를 넉넉히 두고, 경계만 주변 원본에 이어 붙인다.
    mask = mask.filter(ImageFilter.MaxFilter(31)).filter(ImageFilter.GaussianBlur(12))
    coverage = np.asarray(mask, np.float32) / 255
    yy, xx = np.mgrid[:SIZE[1], :SIZE[0]]
    ring = (coverage == 0) & (yy > 125) & (yy < 315) & (xx > 70) & (xx < 730)
    # 새벽·밤·비의 명암을 추측하지 않고 그 변형의 주변 잔디에서 맞춘다.
    # 채널별 선형 보정은 RGB를 섞지 않아 낮은 대비에서 색이 폭주하지 않는다.
    adjusted = source.copy()
    for channel in range(3):
        s = source[:, :, channel][ring]
        t = target[:, :, channel][ring]
        gain = np.clip(np.std(t) / max(float(np.std(s)), 1), .15, 2)
        offset = np.mean(t) - np.mean(s) * gain
        adjusted[:, :, channel] = source[:, :, channel] * gain + offset
    alpha = coverage[:, :, None]
    result = base.copy()
    result[y0:y1, x0:x1] = target * (1 - alpha) + np.clip(adjusted, 0, 255) * alpha
    return result
