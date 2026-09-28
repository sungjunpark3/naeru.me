"""제작 코드는 현재 체크아웃 대신 명시적으로 만든 작업 사본에서만 실행한다."""
import os
from pathlib import Path


def require_workspace(repo):
    repo = Path(repo).resolve()
    if (os.environ.get('NAERU_ASSET_WORKSPACE') != str(repo) or
            not (repo / '.naeru-asset-workspace').is_file()):
        raise SystemExit('현재 자산 덮어쓰기를 막았습니다. tools/build-assets.py로 작업 사본을 만드세요.')
