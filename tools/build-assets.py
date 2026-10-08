#!/usr/bin/env python3
"""지정한 단계만 별도 작업 사본에서 제작한다."""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from asset_catalog import REPO, runtime, inputs, owner

TARGETS = {
    'spring': [('tools/spring/build.py',)],
    'summer': [('tools/summer/build.py',)],
    'autumn': [('tools/autumn/build.py',)],
    'winter': [('tools/winter/build.py',)],
    'christmas': [('tools/christmas/build.py',)],
    'autumn-naeru': [('tools/autumn-naeru/build.py',)],
    'winter-naeru': [('tools/winter-naeru/build.py',)],
    'snow': [('tools/season/make_fall.py',)],
}
for season in ['spring', 'summer', 'autumn', 'winter']:
    for stage in ['sky', 'landscape']:
        if season in ['summer', 'autumn'] and stage == 'landscape':
            continue  # 여름·가을 풍경은 해당 계절 제작기가 소유한다.
        TARGETS[f'{season}-{stage}'] = [
            ('tools/clouds/build.py', '--season', season, '--only', stage,
             'dawn', 'day', 'dusk', 'night')]

# 새 계절을 처음 제작할 때에도 선언한 파일만 추가하도록 허용한다.
SOURCE_OUTPUTS = {
    'summer': {'tools/clouds/source/summer-landscape-mask.png'} | {
        f'tools/clouds/source/summer-{variant}-{kind}.png'
        for variant in ['dawn', 'day', 'dusk', 'night']
        for kind in ['clear-sky', 'clouds', 'cloud-mask']},
}


def validate_changes(before, after, target):
    assert before.keys() <= after.keys(), '제작 파일 삭제: 작업 사본에서 확인하세요.'
    changed = [name for name in after if after[name] != before.get(name)]
    for name in changed:
        if name.startswith('img/'):
            assert Path(name).name in runtime, f'미등록 런타임 자산 추가: {name}'
            assert owner(Path(name).name) == target, f'다른 제작 단계 자산 변경: {name}'
        elif name not in before:
            assert name in SOURCE_OUTPUTS.get(target, set()), f'미등록 제작 입력 추가: {name}'
    return changed


def snapshot(repo):
    return {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ['img', 'tools'] for p in (repo / folder).rglob('*')
            if p.is_file() and p.suffix.lower() in ['.png', '.jpg', '.webp', '.mp4', '.webm', '.svg']
            and not any(part in ['build', '.venv', 'node_modules'] for part in p.parts)}


def make_workspace(repo, output):
    assert not output.is_symlink(), '작업 폴더에 링크를 사용할 수 없습니다.'
    output = output.resolve()
    assert repo not in output.parents and output != repo and output not in repo.parents, '저장소 밖의 새 폴더를 지정하세요.'
    assert not output.exists(), '작업 폴더는 새 경로여야 합니다.'
    files = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=repo).decode().split('\0')
    for name in filter(None, files):
        source, target = repo / name, output / name
        if source.is_file():
            assert not source.is_symlink(), f'제작 입력 링크: {name}'
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)  # 하드링크는 원본까지 수정하므로 사용하지 않는다.
    (output / '.naeru-asset-workspace').write_text('isolated asset build\n')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', choices=sorted(TARGETS))
    parser.add_argument('--output', type=Path, help='저장소 밖 새 폴더. 생략하면 실행 계획만 표시')
    args = parser.parse_args()
    for command in TARGETS[args.target]:
        print('단계:', ' '.join(command), flush=True)
    if not args.output:
        print('--output /tmp/새-폴더 를 지정하면 원본을 보존한 채 실행합니다.')
        return
    workspace = make_workspace(REPO, args.output)
    before = snapshot(workspace)
    environment = dict(os.environ, NAERU_ASSET_WORKSPACE=str(workspace))
    for command in TARGETS[args.target]:
        subprocess.run([sys.executable, *command], cwd=workspace, env=environment, check=True)
    after = snapshot(workspace)
    changed = validate_changes(before, after, args.target)
    # 목록은 콘솔에만 표시한다. 작업 사본을 검토한 뒤 필요한 파일만 수동 반영한다.
    print('변경 파일:\n' + ('\n'.join(changed) or '(없음)'))
    missing = [name for name in runtime if not (workspace / 'img' / name).is_file()]
    if missing:
        print('후속 단계 제작 전이므로 자산 해시 갱신은 보류합니다: ' + ', '.join(missing))
    else:
        subprocess.run([sys.executable, 'tools/asset_versions.py', '--write'], cwd=workspace, check=True)
    print(f'제작 완료: {workspace}\n현재 저장소에는 반영하지 않았습니다.')


if __name__ == '__main__':
    main()
