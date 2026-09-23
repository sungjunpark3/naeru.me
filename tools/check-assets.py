#!/usr/bin/env python3
"""런타임 자산·좌표·배포 경로를 검사하고, 요청한 경우 자산 판번호를 갱신한다."""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools" / "naeru-split"))
from coords import CROP_ORIGIN, CROP_SIZE, FRAME_SIZE, N_FRAMES, VARIANTS

SEASONS = ["spring", "summer", "autumn", "winter"]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--update-version", action="store_true")
parser.add_argument("--videos", action="store_true", help="두 코덱의 실제 프레임 수도 검사")
args = parser.parse_args()

images = {f"bg-{v}-{s}.jpg": FRAME_SIZE for v in VARIANTS for s in SEASONS}
images.update({f"foreground-{v}-autumn.webp": FRAME_SIZE for v in VARIANTS})
images["landscape-day-autumn.webp"] = FRAME_SIZE
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
sky_videos = ["sky-day-autumn.mp4"]
runtime = sorted([*images, *videos, *sky_videos, "alpha-probe.webm"])
digest = hashlib.sha256()
foreground_alpha = None
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
            if name == "landscape-day-autumn.webp":
                alpha = im.getchannel("A")
                assert alpha.getpixel((1920, 500)) == 0, "중앙 하늘이 투명하지 않음"
                assert alpha.getpixel((1920, 1900)) == 255, "들판이 불투명하지 않음"
            if name.startswith("foreground-"):
                # 열린 하늘·중앙 통로에는 전경의 네모판·알파 먼지가 없어야 한다.
                alpha = im.getchannel("A")
                assert alpha.crop((0, 0, 3840, 1000)).getbbox() is None, name
                assert alpha.crop((2150, 0, 2450, 2160)).getbbox() is None, name
                signature = hashlib.sha256(alpha.tobytes()).digest()
                if foreground_alpha is None:
                    foreground_alpha = signature
                assert signature == foreground_alpha, f"시간대별 전경 형태 불일치: {name}"
            im.verify()

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
    print("구름 영상 1개: 1920×1080·H.264·24fps·1440프레임·끝점 일치 PASS")

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
