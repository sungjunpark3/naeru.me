#!/usr/bin/env python3
"""자산·제작 보호·배포 사본·실제 브라우저를 같은 명령으로 검사한다."""
import argparse
import os
import subprocess
import sys

from asset_catalog import REPO


def run(*command, **kwargs):
    subprocess.run(command, cwd=REPO, check=True, **kwargs)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--videos', action='store_true')
    parser.add_argument('--baseline', help='이미지·영상·원화의 바이트를 대조할 Git 커밋')
    parser.add_argument('--skip-browser', action='store_true')
    args = parser.parse_args()
    run(sys.executable, 'tools/check-assets.py', *(['--videos'] if args.videos else []))
    run(sys.executable, 'tools/check-repo.py', *(['--baseline', args.baseline] if args.baseline else []))
    run(sys.executable, 'tools/publish.py')
    if not args.skip_browser:
        # 실제로 배포되는 폴더에서 검사하므로 누락된 동적 경로도 발견한다.
        run('node', 'tools/browser-check/check.cjs',
            env=dict(os.environ, NAERU_CHECK_ROOT=str(REPO / '.publish')))
