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

SEASONS = ["spring", "summer", "autumn", "winter"]
CLEAR_VARIANTS = ["dawn", "day", "dusk", "night"]
MOVING_SKY_SEASONS = ["autumn", "winter"]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--update-version", action="store_true")
parser.add_argument("--videos", action="store_true", help="두 코덱의 실제 프레임 수도 검사")
args = parser.parse_args()

images = {f"bg-{v}-{s}.jpg": FRAME_SIZE for v in VARIANTS for s in SEASONS}
images.update({f"foreground-{v}-autumn.webp": FRAME_SIZE for v in VARIANTS})
images.update({f"foreground-{v}-winter.webp": FRAME_SIZE for v in VARIANTS})
for season in MOVING_SKY_SEASONS:
    for v in CLEAR_VARIANTS:
        images[f"landscape-{v}-{season}.webp"] = FRAME_SIZE
        images[f"sky-{v}-{season}.webp"] = (1920, 1080)
for v in VARIANTS:
    images.update({f"naeru-{v}.png": CROP_SIZE,
                   f"naeru-{v}-hd.webp": (4608, 3968),
                   f"naeru-{v}-nt.png": CROP_SIZE,
                   f"tongue-{v}.png": CROP_SIZE})
for v in ["dawn", "day", "dusk", "night"]:
    images[f"naeru-{v}-close.webp"] = (4608, 3968)
images.update({"og.jpg": (1200, 630), "favicon.png": (64, 64),
               "apple-touch-icon.png": (180, 180)})
images.update({f"{kind}-{depth}.png": (512, 1024)
               for kind in ["rain", "snow"] for depth in ["far", "near"]})
videos = [f"naeru-{v}.{fmt}" for v in VARIANTS for fmt in ["webm", "mp4"]]
for v in VARIANTS:
    images.update({f"naeru-autumn-{v}.png": CROP_SIZE,
                   f"naeru-autumn-{v}-hd.webp": (4608, 3968),
                   f"naeru-autumn-{v}-nt.png": CROP_SIZE,
                   f"tongue-autumn-{v}.png": CROP_SIZE})
    videos.extend([
        f"naeru-autumn-{v}.{fmt}" for fmt in ["webm", "mp4"]])
for v in CLEAR_VARIANTS:
    images[f"naeru-autumn-{v}-close.webp"] = (4608, 3968)
for v in CLEAR_VARIANTS:
    images.update({f"naeru-winter-{v}.png": CROP_SIZE,
                   f"naeru-winter-{v}-hd.webp": (4608, 3968),
                   f"naeru-winter-{v}-close.webp": (4608, 3968),
                   f"naeru-winter-{v}-nt.png": CROP_SIZE})
    videos.extend([
        f"naeru-winter-{v}.{fmt}" for fmt in ["webm", "mp4"]])
sky_videos = [f"sky-{v}-{season}.mp4"
              for season in MOVING_SKY_SEASONS for v in CLEAR_VARIANTS]
runtime = sorted([*images, *videos, *sky_videos, "alpha-probe.webm"])
digest = hashlib.sha256()
foreground_alpha = {}
for name in runtime:
    p = REPO / "img" / name
    assert p.is_file() and p.stat().st_size, f"누락: {name}"
    digest.update(name.encode() + b"\0" + p.read_bytes())
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
                assert alpha.crop((0, 0, 3840, 1000)).getbbox() is None, name
                assert alpha.crop((2150, 0, 2450, 2160)).getbbox() is None, name
                signature = hashlib.sha256(alpha.tobytes()).digest()
                season = "winter" if name.endswith("-winter.webp") else "autumn"
                foreground_alpha.setdefault(season, signature)
                assert signature == foreground_alpha[season], \
                    f"시간대별 전경 형태 불일치: {name}"
            im.verify()

# 가을과 겨울은 각각 한 전신 원화에서 조명만 바꾼다. 시간대별 실루엣이
# 달라지거나 평상시·근접본 사이에서 그림이 바뀌면 접근 중 튀어 보인다.
for season, variants in [("autumn", VARIANTS),
                         ("winter", CLEAR_VARIANTS)]:
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
        assert landscape_mae < 2, \
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

version = digest.hexdigest()[:12]
pattern = r'(var ASSET_V = ")[^"]+(";)'
assert re.search(pattern, html), "ASSET_V 선언을 찾을 수 없음"
if args.update_version:
    html = re.sub(pattern, lambda m: m[1] + version + m[2], html)
    html_path.write_text(html)
else:
    assert f'var ASSET_V = "{version}";' in html, \
        "자산이 바뀌었습니다. check-assets.py --update-version을 실행하세요."
print(f"자산 {len(runtime)}개·좌표·경로 보호 PASS / ASSET_V={version}")
