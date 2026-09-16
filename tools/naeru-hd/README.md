# 내루미 근접 원화 복원

**기존 포즈·크롭을 보존한 4608×3968 WebP 8장을 만든다.**
정지 애니메이션용 RealESRGAN_x4plus_anime_6B로 눈·입의 선을 복원하고,
animevideov3로 최종 크기를 만든다. 누끼의 넓은 반투명 띠도 좁힌다.
결과는 `img/naeru-<variant>-hd.webp`이며 정지 화면과 근접 원화 실패 시 사용한다.
영상 전체를 업스케일하는 도구는 아니다.

근접에서는 작은 원화의 선까지 확대하지 않도록 별도의 얇은 선 원화를 쓴다.
built-in imagegen으로 기존 원화의 선 굵기를 조정한 입력을
`source/naeru-close-day.png`에 보존했다. `closeup.py`는 생성된 알파의 바깥 점을
제거하고 크롭·눈 위치를 맞춘 뒤, 같은 형태에 시간대 조명을 적용한다.
`img/naeru-{dawn,day,dusk,night}-close.webp` 네 장을 재현하는 명령은 다음과 같다.

```sh
tools/naeru-split/.venv/bin/python tools/naeru-hd/closeup.py
tools/naeru-split/.venv/bin/python tools/check-assets.py --update-version
```

## 재현

저장소 루트에서 실행한다. `source/`에는 발끝 누끼를 보정한 제작 결과의
압축 전 0001 프레임을 8종 보존했다. 입력을 매번 같은 파일에서 읽는다.

```sh
tools/naeru-split/.venv/bin/pip install -r tools/naeru-hd/requirements.txt
mkdir -p tools/naeru-hd/build
curl -fL \
  https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-animevideov3.pth \
  -o tools/naeru-hd/build/realesr-animevideov3.pth
curl -fL \
  https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/RealESRGAN_x4plus_anime_6B.pth \
  -o tools/naeru-hd/build/RealESRGAN_x4plus_anime_6B.pth
tools/naeru-split/.venv/bin/python tools/naeru-hd/build.py
tools/naeru-split/.venv/bin/python tools/check-assets.py --update-version
```

`--variants day night`로 일부만 처리하거나 `--output <directory>`로
비교용 산출물을 다른 곳에 만들 수 있다. 기존 영상과 작은 PNG는 덮어쓰지 않는다.
`--scale 4`는 중간 해상도의 비교용이다. 앱 자산은 기본값인 8배로 생성한다.

두 모델의 SHA-256을 실행할 때 확인한다.

```text
animevideov3: b8a8376811077954d82ca3fcf476f1ac3da3e8a68a4f4d71363008000a18b75d
anime 6B: f872d837d3c90ed2e05227bed711af5671a6fd1c9f7d7e91c911a61f155e99da
```

## 색과 알파

- 투명 영역의 숨은 잔디 RGB가 신경망에 들어가지 않도록 캐릭터 색을 연장한다.
- RRDB 6B로 RGB를 4배 복원 → 2배 중간본 → animevideov3로 최종 8배를 만든다.
  이전처럼 첫 복원의 단순 확대본을 섞지 않는다. 얼굴의 선과 음영을 각각
  최대 접근 스크린샷으로 비교해 선택한 방식이다.
- RRDB는 288px 타일에 100px, SRVGG는 384px 타일에 24px 문맥 여유를 둔다.
  각 모델의 수용 영역 밖에서 잘라 내부 이음매를 막는다.
- 원래 알파를 8배 보간하고 1 원본 픽셀 반경으로 곡선을 연결한다.
  중심선인 128은 유지하고 116~140 구간만 안티앨리어싱에 사용한다.
  이전 64~192 범위는 근접 화면에서 머리·볼 바깥이 넓게 번져 보였다.
- 완전히 투명한 영역의 RGB를 지우고 WebP quality 97로 저장한다.
  저장본의 알파가 보간 결과와 완전히 같은지 검사한다.

`vendor/srvgg_arch.py`는 공식 SRVGGNetCompact 구현에서 BasicSR 등록만
제거한 것이다. 저작권과 BSD-3-Clause 조건은 [LICENSE](vendor/LICENSE)에 보존했다.
`vendor/rrdbnet_arch.py`는 BasicSR의 공식 4배 RRDB 추론이며,
레지스트리·학습용 초기화·사용하지 않는 배율만 제외했다.
저작권과 Apache-2.0 조건은 [LICENSE-basicsr](vendor/LICENSE-basicsr)에 보존했다.
모델과 중간 산출물이 들어가는 `build/`는 Git에서 제외한다.

출처: [정지 애니메이션 모델](https://github.com/xinntao/Real-ESRGAN/blob/master/docs/anime_model.md),
[영상용 모델](https://github.com/xinntao/Real-ESRGAN/blob/master/docs/anime_video_model.md),
[RRDB 구현](https://github.com/XPixelGroup/BasicSR/blob/master/basicsr/archs/rrdbnet_arch.py),
[SRVGG 구현](https://github.com/xinntao/Real-ESRGAN/blob/master/realesrgan/archs/srvgg_arch.py).
