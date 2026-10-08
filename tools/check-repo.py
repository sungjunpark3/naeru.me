#!/usr/bin/env python3
"""제작/배포 경계와 캐시 독립성을 검사한다. --baseline은 정리 전 원화를 대조한다."""
import argparse
import ast
import importlib.util
import os
import re
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import asset_versions
from asset_catalog import REPO, compatibility, inputs, owner, publish, runtime
from asset_workspace import require_workspace
from publish import build_publish


def must_fail(fn, exception):
    try:
        fn()
    except exception:
        return
    raise AssertionError('거부해야 하는 작업이 허용됐습니다.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline')
    args = parser.parse_args()
    assert len(runtime) == len(set(runtime))
    assert set(runtime).isdisjoint(inputs)
    actual = {p.name for p in (REPO / 'img').iterdir() if p.is_file() and p.name != '.DS_Store'}
    assert actual == set(runtime + inputs), f'미분류 자산: {actual ^ set(runtime + inputs)}'
    assert all('img/' + name in publish for name in compatibility)
    assert all(owner(f'bg-{v}-summer.jpg') == 'summer'
               for v in ['dawn', 'day', 'dusk', 'night', 'dawn-rain', 'day-rain', 'dusk-rain', 'night-rain'])

    # 현재 체크아웃에서 제작기를 실행하면 중단한다. 새 작업 사본에서만 허용한다.
    with patch.dict(os.environ, {}, clear=True):
        must_fail(lambda: require_workspace(REPO), SystemExit)
        with tempfile.TemporaryDirectory(prefix='naeru-tools-') as directory:
            root = Path(directory).resolve()
            (root / '.naeru-asset-workspace').write_text('test')
            with patch.dict(os.environ, {'NAERU_ASSET_WORKSPACE': str(root)}):
                require_workspace(root)
                must_fail(lambda: require_workspace(REPO), SystemExit)
            # 알 수 없는 파일을 묵묵히 삭제하거나 배포에 섞지 않는다.
            (root / 'unrelated.txt').write_text('keep')
            must_fail(lambda: build_publish(REPO, root), AssertionError)
            assert (root / 'unrelated.txt').read_text() == 'keep'

    with tempfile.TemporaryDirectory(prefix='naeru-cache-') as directory:
        root = Path(directory)
        (root / 'img').mkdir(); (root / 'game').mkdir()
        for name in ['img/a.webp', 'img/b.webp', 'game/game.js']:
            (root / name).write_bytes(name.encode())
        with patch.object(asset_versions, 'runtime', ['a.webp', 'b.webp']):
            before = asset_versions.versions(root)
            (root / 'img/a.webp').write_bytes(b'new art')
            after = asset_versions.versions(root)
            assert before['img/a.webp'] != after['img/a.webp']
            assert before['img/b.webp'] == after['img/b.webp']
            assert before['game/game.js'] == after['game/game.js']

    # 제작 작업 사본은 원본과 링크를 공유하지 않으며, 기존 폴더를 덮어쓰지 않는다.
    spec = importlib.util.spec_from_file_location('asset_builder', REPO / 'tools/build-assets.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    with tempfile.TemporaryDirectory(prefix='naeru-workspace-') as directory:
        root = Path(directory).resolve()
        source, output = root / 'source', root / 'output'
        source.mkdir()
        subprocess.run(['git', 'init', '-q', str(source)], check=True)
        (source / 'master.png').write_bytes(b'approved original')
        builder.make_workspace(source, output)
        (output / 'master.png').write_bytes(b'generated copy')
        assert (source / 'master.png').read_bytes() == b'approved original'
        must_fail(lambda: builder.make_workspace(source, output), AssertionError)
        must_fail(lambda: builder.make_workspace(source, source / 'nested'), AssertionError)
    assert 'summer' in builder.TARGETS and 'summer-sky' in builder.TARGETS
    assert 'summer-landscape' not in builder.TARGETS
    assert builder.validate_changes({}, {'img/foreground-day-summer.webp': 'new'}, 'summer')
    must_fail(lambda: builder.validate_changes({}, {'img/bg-day-winter.jpg': 'new'}, 'summer'), AssertionError)
    must_fail(lambda: builder.validate_changes({}, {'tools/unregistered.png': 'new'}, 'summer'), AssertionError)
    must_fail(lambda: builder.validate_changes({'img/bg-day-summer.jpg': 'old'}, {}, 'summer'), AssertionError)

    # 앱은 인라인 실행을 유지한다. 모든 스크립트를 실제 Node 구문 검사에 넘긴다.
    html = (REPO / 'index.html').read_text()
    for script in re.findall(r'<script(?:\s[^>]*)?>([\s\S]*?)</script>', html):
        subprocess.run(['node', '--check'], input=script, text=True, check=True)
    subprocess.run(['node', '--check', 'game/game.js'], cwd=REPO, check=True)
    for path in (REPO / 'tools').rglob('*.py'):
        if not any(part in ['.venv', 'node_modules', 'build'] for part in path.parts):
            ast.parse(path.read_text(), filename=str(path))

    if args.baseline:
        # Git blob 식별자는 이미지 디코딩 오차 없이 원본 파일의 바이트를 확인한다.
        records = subprocess.check_output(
            ['git', 'ls-tree', '-r', '-z', args.baseline, '--', 'img', 'tools'], cwd=REPO).split(b'\0')
        suffixes = {'.png', '.webp', '.jpg', '.mp4', '.webm', '.svg'}
        expected = {}
        for record in filter(None, records):
            info, raw_path = record.split(b'\t', 1)
            name = raw_path.decode()
            if Path(name).suffix.lower() in suffixes:
                expected[name] = info.split()[2].decode()
        assert expected, '비교할 기준 자산이 없습니다.'
        current_names = subprocess.check_output(
            ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', 'img', 'tools'], cwd=REPO).decode().split('\0')
        assert set(expected) == {n for n in current_names if Path(n).suffix.lower() in suffixes}, '원화 파일 추가·삭제 감지'
        hashes = subprocess.check_output(['git', 'hash-object', '--stdin-paths'],
            input='\n'.join(expected) + '\n', text=True, cwd=REPO).splitlines()
        changed = [name for name, actual_hash in zip(expected, hashes) if expected[name] != actual_hash]
        assert not changed, '기준본과 다른 원화: ' + ', '.join(changed)
        print(f'{args.baseline}: 이미지·영상·원화 {len(expected)}개 바이트 일치')
    print('제작 경계·계절별 자산 분류·배포 허용 목록·파일별 캐시·스크립트 구문 PASS')


if __name__ == '__main__':
    main()
