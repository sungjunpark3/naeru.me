# 배경의 고정 그림자 제거

**`repair.py`가 내루미 그림자 자리만 복원하고, 계절 배경 32장에 같은 경계를 쓴다.**
`source/day-context.png`는 원래 낮 배경의 800×400 크롭,
`source/day-repair.png`는 built-in imagegen으로 그 그림자만 지운 잔디다.
실행할 때 API나 이미지 생성 도구를 호출하지 않는다.

```sh
tools/naeru-split/.venv/bin/python tools/season/repaint.py
tools/naeru-split/.venv/bin/python tools/check-assets.py --update-version
```

원본 프레임 3840×2160에서 크롭은 `(1456,1512)–(2256,1912)`다.
복원본을 800×400으로 맞추고, 그림자 주변의 원래 잔디로 채널별 명암을 맞춘다.
다각형·팽창·경계 페이드로 필요한 부분만 합성한다. 주변 꽃·나무 그림자는 유지한다.
계절 채색 전에 처리하므로 겨울 눈 마스크에도 옛 그림자가 다시 들어가지 않는다.

캐릭터 누끼 계산의 기준인 `plate`와 계절 제작 입력 `bg-<variant>.jpg`는
그대로 보존한다. 런타임이 읽는 `bg-<variant>-<season>.jpg`만 새로 만든다.
최종 프롬프트와 검사 결과는 [제작 기록](../../docs/SHADOW-HD-2026-09-16.md)에 있다.
