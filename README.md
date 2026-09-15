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

가을의 맑은 새벽·낮·노을·밤에는 처음 한 번, 이후 약 5분마다 내루미가
화면 앞으로 다가와 인사한다. 다른 행동과 영상 속 팔 동작이 끝나 뉴트럴 포즈가
되면 출발하며, 집중 종료에도 같은 방식으로 인사한다.
설정의 **가까이 와줘**로 호출할 수 있다. 첫 인사가 예약된 상태에서도 작동하며,
포즈를 기다릴 때는 “하던 동작을 마치고 다가갈게요”를 표시한다.
`?s=autumn&v=day&w=clear&act=approach&ball=0&flit=0&ff=0`을 열면 한 번
재생된다. `v`를 `dawn`, `dusk`, `night`로 바꾸면 다른 시간대도 볼 수 있다.
[방문 조건·시간대 확장·화질 조사](docs/APPROACH-2026-09-15.md)를 참고한다.
근접·정지 화면에는 8배 복원한 투명 이미지 8종을 사용한다.
사계절 배경의 고정 그림자를 제거하고, 점프해도 지면에 남는 DOM 그림자를 쓴다.
[그림자·고해상도 제작과 검증](docs/SHADOW-HD-2026-09-16.md)에 정리했다.

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
다가오기 네 화면비·가을 네 시간대·뉴트럴 포즈 대기·첫 방문과 5분 간격·
자동 복귀·중단·장면 제한·집중 완료 예약도 함께 검사한다.
첫 인사 대기 중 호출 버튼, 대기 안내와 다른 몸짓의 끼어들기 방지,
포즈 대기 중 탭 숨김·정지 모드·풍경 변경도 확인한다.

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
