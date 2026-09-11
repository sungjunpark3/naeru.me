# 내루미 시작페이지

서울의 시간·날씨와 사계절 초원을 보여주는 정적 페이지다. 내루미에게 클릭이나
키보드로 인사하고, 오른쪽 아래 설정에서 계절·풍경의 시간·움직임·시계·날짜를
바꿀 수 있다. 25분·50분 집중 타이머는 새로고침 후에도 이어진다.
앱 실행에 설치나 빌드가 필요하지 않다.

## 로컬 실행

저장소 루트에서 실행한 뒤 <http://127.0.0.1:8000>을 연다.

```sh
python3 -m http.server 8000 --bind 127.0.0.1
```

`?s=winter&v=night&w=rain&still=1`처럼 URL로 특정 풍경을 확인할 수 있다.
`w`를 지정하면 실황 조회를 건너뛴다. 시계는 실제 서울 시각을 표시한다.

구조·작업 원칙은 [CLAUDE.md](CLAUDE.md), 이전 시행착오는
[작업 기록](docs/HISTORY-2026-09-08.md), 수정·검사 결과는
[변경 내역](docs/CHANGES-2026-09-11.md)에 정리했다.
캐릭터의 투명 경계 점검과 발끝 복원은 [누끼 검증 기록](docs/MATTE-2026-09-11.md)에 있다.

가을 맑은 낮에는 5분마다, 그리고 집중 종료 시 내루미가 화면 앞으로 다가와 인사한다.
설정의 **가까이 와줘**로 바로 시험하거나,
`?s=autumn&v=day&w=clear&act=approach&ball=0&flit=0&ff=0`을 열면 한 번
재생된다. [시범 동작·제약](docs/APPROACH-2026-09-11.md)을 참고한다.

## 그림 수정·검사

일반 화면 수정에는 제작 환경이 필요하지 않다. 기존 그림을 재생성하거나
자산 검사를 할 때는 아래 환경을 사용한다.

```sh
python3 -m venv tools/naeru-split/.venv
tools/naeru-split/.venv/bin/pip install -r tools/requirements-assets.txt

# 파일·이미지 크기·좌표 계약·배포 차단 규칙·내용 해시 검사
tools/naeru-split/.venv/bin/python tools/check-assets.py

# 겨울 배경 8장만 재생성한 뒤 캐시 판번호 갱신
tools/naeru-split/.venv/bin/python tools/season/repaint.py --seasons winter
tools/naeru-split/.venv/bin/python tools/check-assets.py --update-version

# 영상 크기·코덱·24fps·316프레임까지 검사
tools/naeru-split/.venv/bin/python tools/check-assets.py --videos
```

배경 제작에는 `ffmpeg`, 영상 검사에는 `ffprobe`가 필요하다.
전체 `tools/naeru-split/build.sh`는 추가로 `pngquant`, macOS HEVC 인코더,
LaMa 인페인팅 환경이 필요하다. LaMa 설치는
[lama_fill.py](tools/naeru-split/lama_fill.py) 첫 주석을 참고한다.
전체 파이프라인은 수천 프레임을 다시 처리하므로 필요한 단계만 실행한다.

## 브라우저 검사

Node.js와 Chromium을 사용한다. 의존성은 개발 검사 디렉터리에만 설치한다.

```sh
npm install --prefix tools/browser-check
./tools/browser-check/node_modules/.bin/playwright install chromium
npm test --prefix tools/browser-check
```

검사는 임시 로컬 HTTP 서버를 띄우고 끝나면 닫는다. 날짜·날씨를 고정한 상태로
32개 풍경, 다섯 화면 크기, 설정, 동작 줄이기, 날씨 오류, 영상 실패,
공의 착지, 탭 복귀, 타이머를 확인한다.
다가오기 네 화면비·자동 복귀·중단·장면 제한·집중 완료 예약도 함께 검사한다.

기존 환경을 사용할 때는 `NAERU_PLAYWRIGHT`에 Playwright 모듈 경로,
`NAERU_BROWSER`에 Chromium 실행 파일 경로를 지정할 수 있다.
`NAERU_CHECK_OUTPUT`에 **저장소 밖 디렉터리**를 지정하면 스크린샷과
`results.json`을 저장한다. 이 출력은 앱 배포에 포함하지 않는다.
`NAERU_CHECK_FILTER`에 검사 이름의 일부를 지정하면 해당 검사만 실행한다.

## 배포

Netlify가 `origin/main` push를 자동 배포한다. 앱 빌드 명령은 없다.
`_headers`는 캐시·검색 제외 정책, `_redirects`는 개발 문서·도구·제작 입력의
강제 404 규칙이다. Python 로컬 서버는 이 Netlify 규칙을 적용하지 않는다.
원본 자산은 재현을 위해 저장소에 남으므로 HTTP 차단 자체로 배포 용량이
줄어들지는 않는다. 실제 차단 응답은 Netlify 배포 후 확인한다.
