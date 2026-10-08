"""배포 자산과 보존용 제작 입력의 목록. 파일명·크기·소유 제작 경로의 기준."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools/naeru-split"))
from coords import FRAME_SIZE, CROP_SIZE, VARIANTS

SEASONS = ["spring", "summer", "autumn", "winter"]
CLEAR_VARIANTS = ["dawn", "day", "dusk", "night"]
MOVING_SKY_SEASONS = ["spring", "summer", "autumn", "winter"]

images = {f"bg-{v}-{s}.jpg": FRAME_SIZE for v in VARIANTS for s in SEASONS}
for season in SEASONS:
    images.update({f"foreground-{v}-{season}.webp": FRAME_SIZE
                   for v in VARIANTS})
images.update({f"foreground-{v}-christmas.webp": FRAME_SIZE for v in VARIANTS})
images.update({f"bg-{v}-christmas.jpg": FRAME_SIZE
               for v in VARIANTS if v.endswith("-rain")})
for season in MOVING_SKY_SEASONS:
    for v in CLEAR_VARIANTS:
        images[f"landscape-{v}-{season}.webp"] = FRAME_SIZE
        images[f"sky-{v}-{season}.webp"] = (1920, 1080)
for v in CLEAR_VARIANTS:
    images[f"landscape-{v}-christmas.webp"] = FRAME_SIZE
for v in VARIANTS:
    images.update({f"naeru-{v}.png": CROP_SIZE,
                   f"naeru-{v}-hd.webp": (4608, 3968),
                   f"naeru-{v}-nt.png": CROP_SIZE,
                   f"tongue-{v}.png": CROP_SIZE})
for v in ["dawn", "day", "dusk", "night"]:
    images[f"naeru-{v}-close.webp"] = (4608, 3968)
images.update({"og.jpg": (1200, 630), "favicon.png": (64, 64),
               "apple-touch-icon.png": (180, 180),
               "autumn-maple-leaf.png": (1326, 1187),
               "autumn-maple-leaf-gold.png": (1254, 1254),
               "autumn-maple-leaf-crimson.png": (1254, 1254)})
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
for v in VARIANTS:
    images.update({f"naeru-winter-{v}.png": CROP_SIZE,
                   f"naeru-winter-{v}-hd.webp": (4608, 3968),
                   f"naeru-winter-{v}-nt.png": CROP_SIZE})
    videos.extend([
        f"naeru-winter-{v}.{fmt}" for fmt in ["webm", "mp4"]])
for v in CLEAR_VARIANTS:
    images[f"naeru-winter-{v}-close.webp"] = (4608, 3968)
sky_videos = [f"sky-{v}-{season}.mp4"
              for season in MOVING_SKY_SEASONS for v in CLEAR_VARIANTS]
runtime = sorted([*images, *videos, *sky_videos, "alpha-probe.webm"])

# 과거 URL과 새 원화의 정렬·혀 제작 입력을 함께 보존한다. 자동 삭제하지 않는다.
compatibility = sorted(name for name in runtime
    if any(name.startswith(prefix + v) for v in VARIANTS
           for prefix in ["naeru-", "tongue-"]))
inputs = sorted(name for v in VARIANTS for name in [
    f"meadow-{v}.mp4", f"meadow-{v}.hevc.mp4", f"sky-{v}.jpg",
    f"plate-{v}.png", f"bg-{v}.jpg"])
publish = ["index.html", "404.html", "_headers", "_redirects", "game/game.js"] + [
    "img/" + name for name in runtime]


def owner(name):
    """하나의 최종 파일은 하나의 제작 경로만 소유한다."""
    if name in inputs or name in compatibility:
        return "legacy-preserved"
    if "-christmas." in name:
        return "christmas"
    for season in SEASONS:
        if name.startswith((f"naeru-{season}-", f"tongue-{season}-")):
            return season + "-naeru"
        if name.endswith(f"-{season}.webp") and name.startswith("landscape-"):
            return season if season in ["summer", "autumn"] else season + "-landscape"
        if name.startswith("sky-") and f"-{season}." in name:
            return season + "-sky"
        if f"-{season}." in name:
            return season
    if name.startswith("snow-"):
        return "snow"
    return "approved-preserved"


if __name__ == "__main__":
    from collections import Counter
    for label, names in [("현재 화면", set(runtime) - set(compatibility)),
                         ("호환 URL·제작 의존", compatibility),
                         ("배포 제외 제작 입력", inputs)]:
        size = sum((REPO / "img" / n).stat().st_size for n in names)
        print(f"{label}: {len(names)}개 / {size / 1024**2:.2f} MiB")
    print("제작 담당:", dict(sorted(Counter(owner(n) for n in runtime + inputs).items())))
