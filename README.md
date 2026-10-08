# 내루미 시작페이지

서울의 시각·날씨와 계절 풍경, 고화질 내루미를 표시하는 정적 사이트다.
클릭·키보드 인사, 방향키·터치 산책, 화면 설정, 25·50분 집중 타이머를 제공한다.
앱은 설치나 번들링 없이 `index.html`로 실행된다.

## 로컬 실행

```sh
python3 -m http.server 8000 --bind 127.0.0.1
```

<http://127.0.0.1:8000/?s=autumn&v=day&w=clear>에서 확인한다.
`s`: `spring/summer/autumn/winter`, `v`: `dawn/day/dusk/night`,
`w`: `clear/rain`. `w`를 지정하면 실황 조회를 건너뛴다.
`still=1`은 정지 화면, `xmas=1`은 겨울 크리스마스판이다.
`file://` 미리보기도 유지하며 WebGL이 제한되면 고화질 이미지로 표시한다.

## 현재 구현 범위

| 계절 | 원화·전경 | 맑은 하늘 | 내루미 |
|---|---|---|---|
| 봄 | 새 원화·들판 꽃·분리 전경 | 4시간대 60초 루프 | 승인된 무장식 가을 내루미 공유 |
| 여름 | 초록 나무·들판·고사리 전경·작은 흰 꽃·비구름 | 4시간대 60초 루프 | 승인된 무장식 가을 내루미 공유 |
| 가을 | 새 단풍 원화·분리 억새·비구름 원화 | 4시간대 60초 루프 | 무장식 고화질 원화 |
| 겨울 | 포근한 원화·분리 눈풀 | 4시간대 60초 루프 | 모자·목도리 전용 원화 |

- 비·눈 하늘은 정적이다. 겨울 강수는 눈으로 표시한다.
- 가을·겨울 맑은 네 시간대에 처음 한 번, 이후 약 5분마다 뉴트럴 포즈에서
  다가와 인사한다. 설정의 **가까이 와줘**, 집중 종료로도 호출한다.
- 산책은 사계절 공통으로 발끝 Y=1.01, 최대 원근 배율 2.35다.
  배경을 확대하지 않으며 자동 인사 거리는 별도로 유지한다.
- 가을 전경 억새는 원래 레이어 위치에서 높이의 17.5% 아래로 이동한다.
  단풍잎은 한 장씩 떨어지고, 맑은 날에는 가끔 혀로 받는다.
- 매년 12월 20~31일에는 겨울 나무·설원·전경만 크리스마스 원화로 바뀐다.
  하늘·구름·내루미는 겨울 자산을 유지한다.
- 늦게 도착한 전경·풍경은 현재 장면일 때 복구한다. 느린 구름 영상도 요청을
  유지하고, 준비되면 정지 포스터에서 영상으로 교체한다.

## 구조

```text
index.html                 인라인 CSS·독립 IIFE·공통 장면 설정·파일별 자산 해시
game/game.js              지연 로드하는 산책 코드
img/                       현재 자산 + 호환 URL + 보존용 제작 입력
tools/asset_catalog.py    자산 분류·규격·공식 제작 담당·배포 허용 목록
tools/asset_versions.py   파일별 캐시 해시 갱신
tools/build-assets.py     필요한 단계만 별도 사본에서 제작
tools/{spring,summer,autumn,winter,christmas}/  원화와 제작 코드
tools/{autumn-naeru,winter-naeru}/      승인 캐릭터 원화와 제작 코드
tools/clouds/             풍경 마스크·구름 루프 제작
tools/check.py            통합 검사
tools/browser-check/      실제 브라우저·기준 커밋 화면 비교
tools/publish.py          배포 파일 선별 복사
netlify.toml              배포 명령과 .publish 경로
docs/                     과거 작업 기록(현재 실행 지침 아님)
```

현재 작업 규칙은 [CLAUDE.md](CLAUDE.md)를 따른다.
`img/`의 예전 파일도 새 캐릭터 정렬·혀 제작 등에 쓰이므로 문자열 검색만으로
삭제하지 않는다. 분류와 용량은 `python3 tools/asset_catalog.py`로 확인한다.

## 검사

검사용 Python은 3.13, Node는 22.14.0을 CI에서 사용한다.
Playwright와 하위 의존성은 `package-lock.json`으로 고정한다.

```sh
python3 -m venv tools/naeru-split/.venv
tools/naeru-split/.venv/bin/pip install -r tools/requirements-assets.txt
npm ci --prefix tools/browser-check
# Chrome/Edge가 없는 환경의 검사 브라우저 설치
./tools/browser-check/node_modules/.bin/playwright install --with-deps chromium

# 자산·제작 보호·배포 사본·브라우저 검사
# --videos: ffmpeg/ffprobe로 코덱·프레임 수·구름 첫/끝 프레임까지 검사
tools/naeru-split/.venv/bin/python tools/check.py --videos
```

macOS에서는 설치된 Chrome/Edge를 우선 사용한다. H.264 지원이 없으면 즉시
실패하며, `NAERU_BROWSER`로 실행 파일을 지정할 수 있다. 실행 시 브라우저
버전도 출력한다. `NAERU_PLAYWRIGHT`는 별도 설치된 모듈 경로 지정용이다.

`NAERU_CHECK_FILTER`는 검사 이름으로 범위를 좁힌다.
`NAERU_CHECK_ROOT`는 검사할 정적 폴더를 지정한다. 통합 검사는 실제 배포 폴더를
사용한다. `NAERU_CHECK_OUTPUT`을 지정할 경우 반드시 저장소 밖 임시 경로를 쓴다.
일반 검사는 보고 파일을 만들지 않는다. 브라우저 검사 외에 Safari/iOS의 실제
알파 재생과 모바일 접근·산책 화면도 확인한다.

구조 정리처럼 그림 보존이 필요한 변경은 기준 커밋과 추가 비교한다.

```sh
tools/naeru-split/.venv/bin/python tools/check-repo.py --baseline <기준커밋>
node tools/browser-check/compare.cjs <기준커밋>
```

첫 명령은 모든 이미지·영상·원화의 바이트를 비교한다. 두 번째는 기준 커밋의
HTML·산책 코드와 `.publish`를 40개 장면 × 데스크톱·모바일에서 비교한다.
GPU 색상 반올림의 흔들림을 피하도록 정지 화면의 픽셀 비교는 소프트웨어 합성으로
고정한다. 좌표·자산 URL도 대조하며, 실제 GPU 움직임·로딩 실패·느린 응답·입력은
별도의 브라우저 통합 검사가 담당한다. 임시 비교 이미지는 통과 시 지우고, 실패 시 출력한 임시 경로에서 차이를 확인한다.

## 자산 제작

일반 코드·문서 정리에는 원화를 재생성하지 않는다. 제작 환경은 위 Python
환경과 ffmpeg를 사용하며, 캐릭터의 HEVC 알파 인코딩은 macOS가 필요하다.

```sh
# 실행 계획만 표시: 현재 파일은 바뀌지 않는다.
tools/naeru-split/.venv/bin/python tools/build-assets.py autumn

# 실제 제작은 저장소 밖의 새 작업 사본에서만 실행한다.
tools/naeru-split/.venv/bin/python tools/build-assets.py autumn --output /tmp/naeru-autumn-work
```

| 대상 | 생성하는 파일 | 선행 입력 |
|---|---|---|
| `spring` | 봄 배경·전경·구름 제작 입력 | 봄 승인 원화 |
| `summer` | 여름 배경·전경·풍경 레이어·구름 제작 입력 | 여름 시간대별 원화·누끼·빈 하늘 |
| `autumn` | 가을 배경·전경·무손실 풍경 레이어 | 가을 승인 원화·비구름 |
| `winter` | 겨울 배경·전경·구름 제작 입력 | 겨울 승인 원화 |
| `christmas` | 장식 풍경·전경 | 현재 겨울 자산·장식 원화 |
| `spring-landscape`, `winter-landscape` | 풍경 레이어 | 해당 계절 배경·마스크 |
| `spring-sky`, `summer-sky`, `autumn-sky`, `winter-sky` | 60초 구름 영상·포스터 | 해당 계절 풍경·구름 입력 |
| `autumn-naeru`, `winter-naeru` | 고화질 캐릭터·영상 | 승인 전신 원화·보존된 정렬 입력 |
| `snow` | 눈 타일 2장 | 기존 절차적 생성 코드 |

무분별한 `all` 대상은 제공하지 않는다. 여름·가을 풍경은 해당 계절 제작기가
생성하고 구름 제작기는 이를 재사용한다. 구형 `season/repaint.py`와
`naeru-split/build.sh`는 과거 기록으로 보존하되 직접 실행은 중단한다.

작업 사본의 변경 목록·그림을 검토하고 필요한 결과만 원래 경로에 반영한다.
작업 사본은 현재 저장소로 자동 복사하거나 푸시하지 않는다. 그림·산책 코드를
변경한 뒤에는 아래 명령으로 파일별 해시를 갱신하고 통합 검사를 실행한다.

```sh
python3 tools/asset_versions.py --write
```

## 배포

Netlify는 `origin/main` push를 자동 배포한다. `netlify.toml`의 명령이
`tools/publish.py`를 실행해 허용 목록만 `.publish/`로 복사한다.
번들링·압축·원화 재생성은 하지 않으며 기존 URL과 파일 바이트를 유지한다.

`_headers`의 캐시·검색 제외와 `_redirects`의 강제 404 규칙도 그대로 복사한다.
제작 입력 40개·도구·문서는 저장소에 보존하면서 배포 폴더에서 제외한다.
현재 사용하지 않는 공개 캐릭터 파일도 기존 URL·제작 의존성을 위해 유지한다.
배포 폴더에 알 수 없는 파일이 있거나 자산 해시가 오래됐으면 배포 준비를 중단한다.
