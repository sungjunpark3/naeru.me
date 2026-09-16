# 최대 접근 화질 개선

**4608×3968이라는 파일 크기를 유지하면서 얼굴의 선과 누끼 경계를 개선했다.**
최대 접근 스크린샷에서 눈·입이 흐리고 머리·볼 가장자리가 넓게 번지는 것을 확인했다.
정지 애니메이션용 RRDB 6B로 먼저 복원하고 SRVGG로 최종 크기를 만드는 방식으로
교체했다. 알파의 중심선은 유지하고 반투명 띠를 좁혔다. 꽃 레이어의 누끼·원근감은
사용자 요청에 따라 후속 작업으로 남긴다.

## 화면에서 확인한 문제

배포 사이트의 실제 최대 접근 상태를 1920×1080 DPR 1·2와 390×844 DPR 3에서
촬영했다. 고해상도 이미지의 불투명도는 1, 원래 영상은 0이었다.
저해상도 영상으로 잘못 표시되는 문제가 아니었다.

전체 스크린샷을 축소해 보면 비교적 매끈하지만, 원본 픽셀 크기의 부분 이미지에서는
눈·입의 흐린 선과 머리·볼의 넓은 반투명 경계가 보였다. 큰 사각 픽셀보다
원화 복원과 누끼의 흐림이 주된 문제였다.

같은 자세에서 `will-change`를 해제해도 눈·볼 부분의 픽셀은 동일했다.
transform 없이 실제 표시 크기로 이미지를 배치한 비교에서도 평균 RGB 차이는
눈 0.118/255, 볼 0.158/255로 작았고 흐림이 그대로 남았다.
검사한 Chromium 환경에서는 DOM 확대 방식 변경으로 해결되지 않았다.

레티나 PC에서는 전체 크롭이 약 5689 물리 픽셀 폭으로 표시되어 4608px 소스를
약 1.23배 확대한다. 모바일 DPR 3에서는 약 3792px로, 소스보다 작게 표시해도
기존 경계의 흐림이 보였다. 파일 치수만으로 화질을 판단하지 않는다.

## 적용한 복원

- RGB: RealESRGAN_x4plus_anime_6B 4배 → 2배 중간본 → animevideov3 4배.
- 기존의 단순 확대본 30% 혼합은 제거한다. 넓은 음영은 유지하고 선을 복원한다.
- 알파: 1 원본 픽셀 반경으로 곡선을 연결하고 116~140 범위를 smoothstep으로
  재매핑한다. 중심선 128은 유지한다. 이전 범위는 64~192였다.
- 완전히 투명한 픽셀의 RGB는 0으로 정리하고, WebP 알파는 무손실로 보존한다.
- 최종 자산은 `img/naeru-{dawn,day,dusk,night}[-rain]-hd.webp` 8장이다.
  영상·크롭 좌표·접근 거리·DOM 그림자·꽃 레이어는 이번 화질 변경 대상이 아니다.

낮 머리 위 경계의 알파 10~90% 전이 폭 중앙값은 원본 파일 기준 12px에서
3px로 줄었다. 기존·개선 알파의 128 기준 실루엣 IoU는 0.99937이다.
이 수치와 별개로 실제 확대 화면의 눈·입·머리 경계도 비교했다.

8종 전체 용량은 2,079,164바이트에서 1,879,100바이트로 약 9.6% 줄었다.
파일 치수는 4608×3968로 같다. 자산 판번호는 `e0812b0bf069`다.

새 원화를 그리는 built-in imagegen 편집은 출력 안전 필터가 `moderation_blocked`
(`other`)로 차단했다. 생성된 캐릭터를 사용하지 않았으며, 사용자가 허용한
로컬 업스케일 경로로 개선했다. CLI/API 생성 대체 경로는 API 키와 명시적인
사용 요청이 필요하며 이번 작업에서는 사용하지 않았다.

시도한 편집 프롬프트는 다음과 같다.

```text
Use case: identity-preserve. Asset type: high-resolution transparent character
sprite for a website that zooms very close to the character. Input image 1 is
the edit target, the existing pink cartoon creature. Repaint this exact creature
as clean, genuinely sharp high-resolution animation artwork. Preserve its
identity, sleepy eyes, expression, long tongue, body proportions, lowered arms,
three-quarter view, curled tail, belly markings, pale mauve palette, soft
daylight shading, and neutral standing pose. Repair the blurry jagged contour
and smudged facial edges with precise smooth linework; keep broad painted
shading gentle, but eye and mouth edges clear. Full body visible including
toes, no extra objects. Fit the entire creature tightly within the canvas with
about 5% transparent padding, so the subject receives maximum real detail.
Use the largest available resolution. Background must be genuinely transparent
with clean alpha edges, no gray halo, no grass, no floor or cast shadow,
no checkerboard painted into the image, no text. This is a crisp faithful
restoration, not a character redesign.
```

## 재현과 한계

제작 명령·모델 SHA-256·출처·라이선스는
[복원 도구 안내](../tools/naeru-hd/README.md)에 보존했다.
원본은 576×496이며 영상 316프레임 전체를 새로 그린 작업은 아니다.
근접 뉴트럴 포즈와 정지 화면의 복원이다. 원본에서 사라진 세부를 정확히
되살렸다고 보장할 수 없고, 머리 윤곽 등 원래 그림의 형태는 유지한다.

## 검증

- 가을 네 시간대 × 레티나 PC(DPR 2)·모바일(DPR 3) 최대 접근·복귀 8/8 통과.
  같은 자세에서 기존 자산을 바꿔 표시해 전후 스크린샷 16장을 저장했다.
- 기존 브라우저 검사의 고해상도 로드 실패·지연·풍경 전환 대응 통과.
- 사계절 32개 배경·필터·고해상도 자산 로드 검사 통과.
- 런타임 자산 88개·크롭 좌표·경로 보호·판번호, 인라인 JS 10개 문법 통과.
- 새 이미지 8종의 크기·알파·외곽 투명 여백·실루엣 보존 검사 통과.
  64px보다 큰 불투명 연결 요소는 모두 캐릭터 한 개뿐이다.

원본 스크린샷·부분 확대·비교 페이지는 저장소 밖의
`~/_reports/naeru.me-pixels-2026-09-16/`에 보존한다.
