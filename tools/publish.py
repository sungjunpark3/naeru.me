#!/usr/bin/env python3
"""원본을 변환하지 않고 기존 공개 URL에 필요한 파일만 배포 폴더에 복사한다."""
import argparse
import hashlib
import shutil
from pathlib import Path

from asset_catalog import REPO, publish, runtime, inputs
from asset_versions import sync_versions


def build_publish(repo, output):
    output = output.absolute()
    assert not output.is_symlink(), "배포 경로는 심볼릭 링크일 수 없습니다."
    output = output.resolve()
    assert output != repo and output not in repo.parents, "원본 경로에 배포할 수 없습니다."
    assert not any(p.is_symlink() for p in output.rglob('*')), "배포 폴더의 링크를 제거하세요."
    expected = set(publish)
    existing = {str(p.relative_to(output)) for p in output.rglob('*') if p.is_file()}
    assert existing <= expected, "배포 폴더에 알 수 없는 파일이 있습니다. 빈 폴더를 사용하세요."
    actual_images = {p.name for p in (repo / 'img').iterdir() if p.is_file() and p.name != '.DS_Store'}
    assert actual_images == set(runtime + inputs), "분류되지 않은 이미지: asset_catalog.py를 갱신하세요."
    sync_versions(repo)
    for name in publish:
        source, target = repo / name, output / name
        assert source.is_file() and not source.is_symlink(), f"배포 원본 누락/링크: {name}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        assert hashlib.sha256(source.read_bytes()).digest() == hashlib.sha256(target.read_bytes()).digest(), name
    assert {str(p.relative_to(output)) for p in output.rglob('*') if p.is_file()} == expected
    size = sum((output / name).stat().st_size for name in publish)
    print(f"배포 {len(publish)}개 / {size / 1024**2:.2f} MiB: {output} (원본 바이트·URL 유지)")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=REPO / '.publish')
    args = parser.parse_args()
    build_publish(REPO, args.output)
