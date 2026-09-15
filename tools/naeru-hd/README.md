# 내루미 뉴트럴 포즈 8배 복원

**기존 포즈·크롭을 보존한 4608×3968 WebP 8장을 만든다.**
Real-ESRGAN animevideov3로 두 번 복원하고 원래 누끼의 계단과 반투명 띠를 정리한다.
결과는 `img/naeru-<variant>-hd.webp`이며 접근과 정지 화면에서 사용한다.
영상 전체를 업스케일하는 도구는 아니다.

## 재현

저장소 루트에서 실행한다. `source/`에는 발끝 누끼를 보정한 제작 결과의
압축 전 0001 프레임을 8종 보존했다. 입력을 매번 같은 파일에서 읽는다.

```sh
tools/naeru-split/.venv/bin/pip install -r tools/naeru-hd/requirements.txt
mkdir -p tools/naeru-hd/build
curl -fL \
  https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-animevideov3.pth \
  -o tools/naeru-hd/build/realesr-animevideov3.pth
tools/naeru-split/.venv/bin/python tools/naeru-hd/build.py
tools/naeru-split/.venv/bin/python tools/check-assets.py --update-version
```

`--variants day night`로 일부만 처리하거나 `--output <directory>`로
비교용 산출물을 다른 곳에 만들 수 있다. 기존 영상과 작은 PNG는 덮어쓰지 않는다.
`--scale 4`는 중간 해상도의 비교용이다. 앱 자산은 기본값인 8배로 생성한다.

모델 SHA-256을 실행할 때 확인한다.

```text
b8a8376811077954d82ca3fcf476f1ac3da3e8a68a4f4d71363008000a18b75d
```

## 색과 알파

- 투명 영역의 숨은 잔디 RGB가 신경망에 들어가지 않도록 캐릭터 색을 연장한다.
- RGB 4배 복원 → 2배 크기의 중간본 → 다시 4배 복원하여 최종 8배를 만든다.
  두 번째 결과 70%와 첫 결과의 확대본 30%를 섞어 회화 질감을 유지한다.
- 384px 타일에 24px 여유를 두어 메모리를 제한한다. 내부 이음매는 모델의
  18px 수용 영역 밖에 두고 제거한다.
- 원래 알파를 8배 보간하고 0.65 원본 픽셀 반경으로 경계를 연결한다.
  64~192 알파 구간을 부드럽게 재매핑해 회색 반투명 띠를 좁힌다.
- 완전히 투명한 영역의 RGB를 지우고 WebP quality 97로 저장한다.
  저장본의 알파가 보간 결과와 완전히 같은지 검사한다.

`vendor/srvgg_arch.py`는 공식 SRVGGNetCompact 구현에서 BasicSR 등록만
제거한 것이다. 저작권과 BSD-3-Clause 조건은 [LICENSE](vendor/LICENSE)에 보존했다.
모델과 중간 산출물이 들어가는 `build/`는 Git에서 제외한다.

출처: [공식 모델과 실행 안내](https://github.com/xinntao/Real-ESRGAN/blob/master/docs/anime_video_model.md),
[원본 네트워크 구현](https://github.com/xinntao/Real-ESRGAN/blob/master/realesrgan/archs/srvgg_arch.py).
