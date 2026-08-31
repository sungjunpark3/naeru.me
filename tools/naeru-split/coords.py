# plate.py·matte.py가 공유하는 좌표 계약. index.html은 파이썬을 못 읽으므로
# #naeru-move의 %는 이 값을 손으로 옮겨 적은 것이다 — 여기를 고치면
# index.html도 반드시 같이 고치고 §3.2 계산을 다시 대조할 것.
#
# CROP box는 신뢰 키잉창(KEY_RECT_GLOBAL) ± 24px 팽창 ± 16px 여유의 이론적
# 최악값으로 잡았다: 원시 마스크가 키잉창 가장자리를 정확히 스치는 게
# 관측됐는데(하늘·언덕도 분홍이라 창을 넓혀 재확인할 수 없음, PLAN §3.3 경고),
# "클리핑"인지 "진짜 거기까지"인지 구분이 안 돼서 창이 꽉 찼다고 가정한
# 최악의 경우에도 여유가 남게 크게 잡았다 (실측: dilated union bbox
# x1790-2294 y1346-1738, 이 CROP과의 최소 여유 18px).
WORK_ORIGIN = (1650, 1250)          # build.sh가 자른 여유 영역 원점 (마스크 계산용)
WORK_SIZE   = (750, 650)
CROP_ORIGIN = (1744, 1328)          # = matte.py 크롭 = index.html #naeru-move %
CROP_SIZE   = (576, 496)
WIDE_ORIGIN = (1250, 1328)          # plate.py 클론 소스용 여유 영역 원점
WIDE_SIZE   = (1600, 496)
FRAME_SIZE  = (3840, 2160)
N_FRAMES    = 316

VARIANTS = ["dawn", "day", "dusk", "night",
            "dawn-rain", "day-rain", "dusk-rain", "night-rain"]

# 분홍기 키잉 유효 구간 — 하늘·언덕도 분홍이라 이 밖은 무의미(PLAN §8 부록 B)
#
# 상단이 1394인 이유(2026-09-01 실측): 1370~1392에 먼 언덕의 분홍기가 임계를
# 넘는 너덜너덜한 가로 띠가 잡히고, 그게 좁은 목으로 머리와 이어져서 연결성분
# 필터로도 안 떨어진다. 머리 돔의 꼭대기는 316프레임 전부 y1398~1402이므로
# 1394에서 자르면 띠만 없어지고 머리는 6px 여유를 두고 남는다.
KEY_RECT_GLOBAL = (1790, 1394, 2270, 1780)
