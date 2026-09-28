"""파일별 내용 해시를 HTML에 내장한다. file://에서도 추가 요청 없이 사용한다."""
import argparse
import hashlib
import json
import re
from pathlib import Path

from asset_catalog import REPO, runtime

START = "  /* asset-versions:start — tools/asset_versions.py가 관리 */"
END = "  /* asset-versions:end */"


def versions(repo):
    paths = ["img/" + name for name in runtime] + ["game/game.js"]
    return {name: hashlib.sha256((repo / name).read_bytes()).hexdigest()[:12]
            for name in sorted(paths)}


def sync_versions(repo, write=False):
    hashes = versions(repo)
    version = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:12]
    # 전체 판번호는 진단용이며 실제 요청에는 해당 파일의 해시만 사용한다.
    block = START + "\n  var ASSET_HASHES = " + json.dumps(
        hashes, ensure_ascii=False, indent=2).replace("\n", "\n  ") + ";\n" + END
    path = repo / "index.html"
    html = path.read_text()
    pattern = re.escape(START) + r"[\s\S]*?" + re.escape(END)
    assert re.search(pattern, html), "자산 해시 구역 누락"
    expected = re.sub(pattern, lambda _: block, html)
    expected = re.sub(r'(var ASSET_V = ")[^"]+(";)',
                      lambda m: m[1] + version + m[2], expected)
    if write:
        if html != expected:
            path.write_text(expected)
    else:
        assert html == expected, "자산 판번호 불일치: python tools/asset_versions.py --write"
    return version


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    print(sync_versions(REPO, write=args.write))
