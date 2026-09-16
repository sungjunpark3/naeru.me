"""가을 앞풀을 지운 배경과 투명 전경을 같은 조명·좌표로 만든다.

원화 두 장은 built-in imagegen으로 제작했다. 생성기를 다시 호출하지 않고
보존한 원화로 재현한다. 실행: tools/season/repaint.py --seasons autumn
day-reference.jpg는 분리 전 가을 낮이며 조명 변환의 기준이다.
실제 제작 프롬프트는 source/prompts.json에 보존한다.
"""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
SIZE = (3840, 2160)

# 사용자가 표시한 좌우 앞풀 영역. 화면 중앙의 내루미 자리·하늘은 보존한다.
# 원본 프레임의 2048×1152 축소 좌표이며, 경계는 주변 나무·들판에 연결한다.
LEFT = [(0, 585), (155, 615), (205, 560), (264, 595), (296, 627),
        (372, 596), (405, 693), (469, 690), (544, 741), (617, 766),
        (669, 854), (721, 917), (804, 893), (898, 936), (948, 983),
        (1000, 945), (1087, 949), (1130, 1008), (1068, 1050),
        (1020, 1152), (0, 1152)]
RIGHT = [(2048, 735), (1990, 758), (1942, 749), (1906, 787),
         (1833, 814), (1814, 864), (1762, 889), (1708, 899),
         (1670, 949), (1597, 998), (1541, 958), (1480, 1016),
         (1430, 1152), (2048, 1152)]


class AutumnForeground:
    def __init__(self):
        self.reference = np.asarray(Image.open(HERE / 'source/day-reference.jpg')
                                    .convert('RGB'), np.float32)
        clean = Image.open(HERE / 'source/day-clean.png').convert('RGB').resize(
            SIZE, Image.Resampling.LANCZOS)
        clean = np.asarray(clean, np.float32)
        mask = Image.new('L', (2048, 1152))
        draw = ImageDraw.Draw(mask)
        for polygon in [LEFT, RIGHT]:
            draw.polygon(polygon, fill=255)
        mask = mask.filter(ImageFilter.MaxFilter(41)).filter(ImageFilter.GaussianBlur(12))
        self.coverage = np.asarray(mask.resize(SIZE, Image.Resampling.BICUBIC),
                                   np.float32)[:, :, None] / 255

        # 생성 과정에서 달라진 전체 명암만 기존 낮 그림에 맞춘다. 선·형태를
        # 매번 생성하지 않으며, 새 그림은 위 마스크 안에서만 사용한다.
        reference_small = self.reference[::8, ::8]
        clean_small = clean[::8, ::8]
        context = self.coverage[::8, ::8, 0] < .01
        design = np.column_stack((clean_small[context] / 255, np.ones(context.sum())))
        matrix = np.linalg.lstsq(design, reference_small[context] / 255, rcond=None)[0]
        self.clean = np.clip(clean @ matrix[:3] + matrix[3] * 255, 0, 255)

        plants = Image.open(HERE / 'source/day-plants.png').convert('RGBA')
        rgba = np.asarray(plants).copy()
        alpha = rgba[:, :, 3]
        count, labels, stats, _ = cv2.connectedComponentsWithStats((alpha > 32).astype(np.uint8))
        # 분리된 투명 여백의 점만 제거한다. 꽃잎 사이의 구멍은 채우지 않는다.
        keep = np.flatnonzero(stats[:, cv2.CC_STAT_AREA] > 500)
        keep = keep[keep != 0]
        support = cv2.dilate(np.isin(labels, keep).astype(np.uint8), np.ones((5, 5), np.uint8))
        alpha[support == 0] = 0
        # 생성 원화의 불투명 내부값은 253이다. 1%의 배경 비침만 바로잡되
        # 꽃잎과 가는 풀 끝의 연속 알파는 유지한다.
        rgba[:, :, 3] = np.clip(np.rint(alpha.astype(np.float32) * 255 / 253), 0, 255)
        rgba[rgba[:, :, 3] == 0] = 0
        plants = Image.fromarray(rgba).convert('RGBa').resize(
            SIZE, Image.Resampling.LANCZOS).convert('RGBA')
        self.plants = np.asarray(plants, np.float32)[:, :, :3]
        self.alpha = plants.getchannel('A')

    def paint(self, background_path, variant):
        background_path = Path(background_path)
        original = np.asarray(Image.open(background_path).convert('RGB'), np.float32)
        reference = self.reference[::8, ::8]
        target = original[::8, ::8]
        # 앞풀과 같은 높이의 나무·잔디·꽃에서 시간대와 강수 조명을 구한다.
        reference = reference[135:].reshape(-1, 3) / 255
        target = target[135:].reshape(-1, 3) / 255
        design = np.column_stack((reference, np.ones(len(reference))))
        matrix = np.linalg.lstsq(design, target, rcond=None)[0]
        error = np.mean(np.abs(design @ matrix - target)) * 255
        clean = np.clip(self.clean @ matrix[:3] + matrix[3] * 255, 0, 255)
        background = original * (1 - self.coverage) + clean * self.coverage
        Image.fromarray(np.rint(background).astype(np.uint8)).save(background_path, quality=95)

        # 꽃은 나무보다 분홍·보라가 강하다. 전체 풍경의 선형식을 외삽하면
        # 밤 꽃이 갈색으로 변하므로 원래 앞풀의 가까운 색에서 조명 비율을
        # 얻는다. 33³ 색상표를 보간해 새 꽃의 명암·붓질과 알파는 보존한다.
        area = self.coverage[::8, ::8, 0] > .5
        source_colors = self.reference[::8, ::8][area]
        target_colors = original[::8, ::8][area]
        cv2.setRNGSeed(20260916)
        tree = cv2.flann_Index(source_colors, dict(algorithm=1, trees=4))
        levels = np.linspace(0, 255, 33, dtype=np.float32)
        blue, green, red = np.meshgrid(levels, levels, levels, indexing='ij')
        grid = np.stack((red, green, blue), axis=-1).reshape(-1, 3)
        neighbors, distance = tree.knnSearch(grid, 16, params=dict(checks=64))
        weight = 1 / (distance + 16)
        weight /= weight.sum(axis=1, keepdims=True)
        ratios = target_colors / np.maximum(source_colors, 16)
        ratio = (ratios[neighbors] * weight[:, :, None]).sum(axis=1)
        table = np.clip(grid * ratio / 255, 0, 1).ravel()
        lookup = ImageFilter.Color3DLUT(33, table, channels=3)
        colors = np.asarray(Image.fromarray(self.plants.astype(np.uint8))
                            .filter(lookup)).copy()
        colors[np.asarray(self.alpha) == 0] = 0
        plants = Image.fromarray(colors)
        plants.putalpha(self.alpha)
        output = background_path.parent / f'foreground-{variant}-autumn.webp'
        plants.save(output, quality=95, method=6)
        assert np.array_equal(np.asarray(Image.open(output).getchannel('A')),
                              np.asarray(self.alpha)), output
        print(f'    foreground {variant}: lighting MAE {error:.2f}/255, '
              f'{output.stat().st_size / 1024:.0f} KiB', flush=True)
