#!/bin/zsh
# 계절별 배경 정지본을 만든다. 원본(bg-<변형>.jpg)이 여름이므로 여름은 안 만들고
# 봄·가을·겨울 세 벌만 굽는다 → img/bg-<변형>-<계절>.jpg (24장).
#
# 왜 그레이딩인가 — 풀·나무의 **형태**는 그대로 두고 색조만 바꾼다. 새로 그리면
# 스프라이트(내루미)와 형태가 안 맞고, 스프라이트까지 계절별로 구우면 알파 영상이
# 32벌(약 25MB)이 된다. 스프라이트는 CSS 필터로 계절 델타만 입힌다(index.html).
#
# 색 방향:
#   봄   — 연둣빛으로 밝고 맑게. 채도를 살짝 올리고 초록을 노란 쪽으로 조금.
#   가을 — 초록을 통째로 황금빛으로. selectivecolor의 greens/cyans를 크게 민다.
#   겨울 — 차고 창백하게. 채도를 크게 낮추고 푸른 캐스트 + 아래쪽을 밝혀
#          땅에 눈이 앉은 느낌(그레이딩만으로는 눈을 못 그리므로 밝기로 흉내).
set -e
HERE=${0:A:h}
REPO=${HERE:h:h}
cd $REPO

VARIANTS=(dawn day dusk night dawn-rain day-rain dusk-rain night-rain)

# selectivecolor의 부호에 주의: 초록을 노랑 쪽으로 밀려면 **시안을 빼야** 한다
# (더하면 더 초록이 된다). 처음에 반대로 넣어서 가을이 거의 안 바뀌었다.
SPRING="selectivecolor=greens=-0.22 -0.10 0.24 -0.05:yellows=-0.05 -0.05 0.14 -0.03,\
eq=saturation=1.12:brightness=.03:gamma=1.03,\
vibrance=intensity=.16:gbal=1.6"

# **cyans는 건드리지 않는다** — 하늘이 시안이라 같이 덥혀져서 한낮이 노을처럼
# 된다. colortemperature도 전역이라 mix를 낮게 둔다. 초록·노랑만 밀면 초원과
# 나무는 황금빛이 되고 하늘은 남는다.
AUTUMN="selectivecolor=greens=-0.85 0.34 0.95 0.05:yellows=-0.22 0.18 0.45 0.02,\
colortemperature=4400:mix=.28,\
eq=saturation=1.10:gamma=1.01"

WINTER="selectivecolor=greens=-0.06 0.02 -0.10 0.06:yellows=-0.08 0 -0.12 0.05,\
eq=saturation=.42:brightness=.045:contrast=.94,\
colorbalance=bs=.10:bm=.07:bh=.05:rs=-.05:rm=-.04:rh=-.03,\
curves=all='0/0.07 0.5/0.57 1/1'"

for V in $VARIANTS; do
  for S in spring autumn winter; do
    case $S in
      spring) CHAIN=$SPRING ;;
      autumn) CHAIN=$AUTUMN ;;
      winter) CHAIN=$WINTER ;;
    esac
    ffmpeg -v error -y -i img/bg-$V.jpg -vf "$CHAIN" -q:v 3 img/bg-$V-$S.jpg
  done
  echo "  $V → spring/autumn/winter"
done
echo "=== 완료"
du -ch img/bg-*.jpg | tail -1
