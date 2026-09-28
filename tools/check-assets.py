#!/usr/bin/env python3
"""런타임 자산·좌표·배포 경로를 검사하고, 요청한 경우 자산 판번호를 갱신한다."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools" / "naeru-split"))
from coords import CROP_ORIGIN, CROP_SIZE, FRAME_SIZE, N_FRAMES, VARIANTS

from asset_catalog import (images, videos, sky_videos, runtime, inputs,
                           CLEAR_VARIANTS, MOVING_SKY_SEASONS)
from asset_versions import sync_versions
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--update-version", action="store_true")
parser.add_argument("--videos", action="store_true", help="두 코덱의 실제 프레임 수도 검사")
args = parser.parse_args()

foreground_alpha = {}
for name in runtime:
    p = REPO / "img" / name
    assert p.is_file() and p.stat().st_size, f"누락: {name}"
    if name in images:
        with Image.open(p) as im:
            assert im.size == images[name], f"크기 불일치: {name} {im.size}"
            if (name.endswith(("-hd.webp", "-close.webp")) or
                    name.startswith(("foreground-", "landscape-"))):
                assert im.mode == "RGBA", f"투명 자산 알파 누락: {name}"
                assert im.getchannel("A").getextrema() == (0, 255), name
            if name.startswith("landscape-"):
                alpha = im.getchannel("A")
                assert alpha.getpixel((1920, 500)) == 0, "중앙 하늘이 투명하지 않음"
                assert alpha.getpixel((1920, 1900)) == 255, "들판이 불투명하지 않음"
            if name.startswith("foreground-"):
                # 열린 하늘·중앙 통로에는 전경의 네모판·알파 먼지가 없어야 한다.
                alpha = im.getchannel("A")
                season = name.removesuffix(".webp").rsplit("-", 1)[-1]
                # 가을 억새는 꽃보다 높이 솟지만 하늘까지 침범하지 않는다.
                clear_top = 550 if season == "autumn" else 1000
                assert alpha.crop((0, 0, 3840, clear_top)).getbbox() is None, name
                # 봄꽃·가을 억새는 화면 아래에서 발을 가릴 수 있지만 상체와
                # 이동 통로는 열려 있어야 한다. 겨울·크리스마스는 중앙 전체가 빈다.
                if season not in ["spring", "autumn"]:
                    assert alpha.crop((2150, 0, 2450, 2160)).getbbox() is None, name
                else:
                    assert alpha.crop((1700, 0, 2600, 1450)).getbbox() is None, name
                signature = hashlib.sha256(alpha.tobytes()).digest()
                foreground_alpha.setdefault(season, signature)
                assert signature == foreground_alpha[season], \
                    f"시간대별 전경 형태 불일치: {name}"
            if name.startswith("autumn-maple-leaf"):
                assert im.mode == "RGBA", "단풍잎 투명 알파 누락"
                assert im.getchannel("A").getextrema() == (0, 255), \
                    "단풍잎 누끼 범위 오류"
        # getchannel() 등으로 디코드한 이미지에는 verify()를 다시 호출할 수 없다.
        # 파일 손상 검사는 새 핸들에서 수행한다.
        with Image.open(p) as verified:
            verified.verify()

# 지연 로드하는 산책 코드도 파일별 판번호 검사에 포함한다.
game_path = REPO / "game" / "game.js"
assert game_path.is_file() and game_path.stat().st_size, "누락: game/game.js"

# 가을과 겨울은 각각 한 전신 원화에서 조명만 바꾼다. 시간대별 실루엣이
# 달라지거나 평상시·근접본 사이에서 그림이 바뀌면 접근 중 튀어 보인다.
for season, variants in [("autumn", VARIANTS),
                         ("winter", VARIANTS)]:
    season_alpha = None
    for variant in variants:
        hd_path = REPO / f"img/naeru-{season}-{variant}-hd.webp"
        if variant in CLEAR_VARIANTS:
            close_path = REPO / f"img/naeru-{season}-{variant}-close.webp"
            assert hd_path.read_bytes() == close_path.read_bytes(), \
                f"평상시·근접 원화 불일치: {season}/{variant}"
        with Image.open(hd_path) as image:
            signature = hashlib.sha256(
                image.getchannel("A").tobytes()).digest()
        if season_alpha is None:
            season_alpha = signature
        assert signature == season_alpha, \
            f"시간대별 형태 불일치: {season}/{variant}"

# 흐린 가을 낮의 내루미가 맑은 낮과 같은 광량으로 떠 보이지 않아야 한다.
with Image.open(REPO / "img/naeru-autumn-day.png") as clear_image, \
        Image.open(REPO / "img/naeru-autumn-day-rain.png") as rain_image:
    mask = clear_image.getchannel("A").point(
        lambda value: 255 if value >= 192 else 0)
    clear_light = sum(ImageStat.Stat(clear_image.convert("RGB"), mask).mean) / 3
    rain_light = sum(ImageStat.Stat(rain_image.convert("RGB"), mask).mean) / 3
assert rain_light < clear_light * .85, \
    f"가을 낮 비 조명이 너무 밝음: clear={clear_light:.1f}, rain={rain_light:.1f}"

# 구름 영상은 누끼 뒤에 놓이지만, 첫 화면에서 누끼가 나타나는 동안에도
# 구름이 풀밭·나무 위에 비치지 않아야 한다.
for season in MOVING_SKY_SEASONS:
    for variant in CLEAR_VARIANTS:
        with Image.open(
                REPO / f"img/sky-{variant}-{season}.webp") as image:
            sky_poster = image.convert("RGB")
        with Image.open(
                REPO / f"img/bg-{variant}-{season}.jpg") as image:
            original = image.convert("RGB").resize(
                sky_poster.size, Image.Resampling.LANCZOS)
        with Image.open(
                REPO / f"img/landscape-{variant}-{season}.webp") as image:
            opaque_landscape = image.getchannel("A").resize(
                sky_poster.size, Image.Resampling.LANCZOS)
        opaque_landscape = opaque_landscape.point(
            lambda value: 255 if value > 250 else 0)
        landscape_difference = ImageChops.difference(sky_poster, original)
        landscape_mae = sum(ImageStat.Stat(
            landscape_difference, mask=opaque_landscape).mean) / 3
        # 밝은 봄 초록과 새 가을 단풍·노을은 H.264 YUV420 왕복에서 평균
        # 오차가 2단계를 조금 넘는다. 구름 잔상과 구분되는 범위만 허용한다.
        limit = 3 if season in ["spring", "autumn"] else 2
        assert landscape_mae < limit, \
            f"풍경 위 구름 잔상: {season}/{variant} MAE={landscape_mae:.2f}"

html_path = REPO / "index.html"
html = html_path.read_text()
box = re.search(r"#naeru-move\s*\{([^}]+)\}", html).group(1)
expected = dict(zip(["left", "top", "width", "height"],
                    [CROP_ORIGIN[0] / FRAME_SIZE[0] * 100,
                     CROP_ORIGIN[1] / FRAME_SIZE[1] * 100,
                     CROP_SIZE[0] / FRAME_SIZE[0] * 100,
                     CROP_SIZE[1] / FRAME_SIZE[1] * 100]))
for name, value in expected.items():
    actual = float(re.search(rf"{name}:\s*([\d.]+)%", box).group(1))
    assert abs(actual - value) < 0.0001, f"크롭 좌표 불일치: {name}"

# 런타임 자산은 제공하고, 제작 입력 40개는 강제 404 규칙으로 보호한다.
rules = [line.split() for line in (REPO / "_redirects").read_text().splitlines()
         if line.strip() and not line.lstrip().startswith("#")]
protected = {r[0] for r in rules if r[1:] == ["/404.html", "404!"]}
for route in ["/CLAUDE.md", "/README.md", "/tools/*", "/docs/*"]:
    assert route in protected, f"개발 경로 보호 누락: {route}"
for v in VARIANTS:
    for name in [f"meadow-{v}.mp4", f"meadow-{v}.hevc.mp4", f"sky-{v}.jpg",
                 f"plate-{v}.png", f"bg-{v}.jpg"]:
        assert "/img/" + name in protected, f"제작 입력 경로 보호 누락: {name}"
for name in runtime:
    assert "/img/" + name not in protected, f"런타임 자산이 차단됨: {name}"

if args.videos:
    for name in videos:
        result = subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
            "-show_entries", "stream=codec_name,width,height,nb_read_frames,r_frame_rate",
            "-of", "json", str(REPO / "img" / name)
        ], text=True)
        stream = json.loads(result)["streams"][0]
        assert (stream["width"], stream["height"]) == CROP_SIZE, name
        assert int(stream["nb_read_frames"]) == N_FRAMES, name
        assert stream["r_frame_rate"] == "24/1", name
        assert stream["codec_name"] == ("vp9" if name.endswith("webm") else "hevc"), name
    print(f"영상 {len(videos)}개: 크롭·코덱·24fps·{N_FRAMES}프레임 PASS")

    for name in sky_videos:
        result = subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
            "-show_entries", "stream=codec_name,width,height,nb_read_frames,r_frame_rate",
            "-of", "json", str(REPO / "img" / name)
        ], text=True)
        stream = json.loads(result)["streams"][0]
        assert (stream["width"], stream["height"]) == (1920, 1080), name
        assert int(stream["nb_read_frames"]) == 1440, name
        assert stream["r_frame_rate"] == "24/1", name
        assert stream["codec_name"] == "h264", name
        decoded = []
        for frame in [0, 1439]:
            decoded.append(subprocess.check_output([
                "ffmpeg", "-v", "error", "-i", str(REPO / "img" / name),
                "-vf", f"select=eq(n\\,{frame})", "-frames:v", "1",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-"
            ]))
        assert decoded[0] == decoded[1], f"루프 끝점 불일치: {name}"
    print(f"구름 영상 {len(sky_videos)}개: "
          "1920×1080·H.264·24fps·1440프레임·끝점 일치 PASS")

version = sync_versions(REPO, write=args.update_version)
print(f"자산 {len(runtime)}개·좌표·경로 보호 PASS / ASSET_V={version}")
