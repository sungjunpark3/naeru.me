# 풀 레이어(back)의 알파에서 내루미 실루엣을 뚫는다.
#   구멍 = (분홍기 키잉 실루엣) ∩ (수면선 위쪽)
# 구멍이 뚫린 자리엔 원본 영상 픽셀이 그대로 보이므로 내루미의 미세한
# 숨쉬기 모션이 죽지 않는다. 실루엣을 살짝 부풀리고 흐려서, 몇 px 흔들려도
# 몸 가장자리가 테두리에 먹히지 않게 한다.
from PIL import Image, ImageFilter
import sys

SC = sys.argv[1] if len(sys.argv) > 1 else "."
WATER_Y   = 1645      # 몸에 걸리는 수면선
FADE      = 26        # 수면선 위아래 부드럽게 사라지는 폭
KEY_LO, KEY_HI = 1400, 1700     # 키잉을 시도한 y 범위
THRESH    = 32        # 분홍기(R - max(G,B)) 임계 — 잔디 18~24 / 내루미 40~67

base = Image.open(f"{SC}/base4k.png").convert("RGB")
W, H = base.size
px = base.load()

m = Image.new("L", (W, H), 0)
mp = m.load()
for y in range(KEY_LO, KEY_HI):
    for x in range(1790, 2270):
        r, g, b = px[x, y]
        if r - max(g, b) > THRESH:
            mp[x, y] = 255

# 닫기 → 열기로 구멍·잡티 정리, 살짝 부풀린 뒤 경계 흐리기
m = m.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
m = m.filter(ImageFilter.MinFilter(5)).filter(ImageFilter.MaxFilter(5))
m = m.filter(ImageFilter.MaxFilter(7))          # 팽창 3px
m = m.filter(ImageFilter.GaussianBlur(4))

# 수면선 아래는 뚫지 않는다 → 다리가 물에 잠긴다
mp = m.load()
for y in range(WATER_Y - FADE, H):
    k = 0.0 if y > WATER_Y + FADE else (WATER_Y + FADE - y) / (2.0 * FADE)
    for x in range(1790, 2270):
        if mp[x, y]:
            mp[x, y] = int(mp[x, y] * k)
m.save(f"{SC}/naeru_mask.png")

# back 레이어 알파에서 마스크만큼 깎아낸다 (alpha × (1 - mask))
back = Image.open(f"{SC}/ovl_back.png").convert("RGBA")
r, g, b, a = back.split()
a = Image.composite(Image.new("L", (W, H), 0), a, m)
Image.merge("RGBA", (r, g, b, a)).save(f"{SC}/ovl_back_holed.png")
print("punched:", m.getbbox())
