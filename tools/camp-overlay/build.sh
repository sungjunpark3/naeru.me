#!/bin/zsh
# 여름수련회(신덕수양관) 장식을 배경 영상에 굽는다.
#   gen_svg.py로 4K 오버레이 SVG → Edge 헤드리스로 투명 PNG → 밴드별 그레이딩
#   → ffmpeg 합성 → x264/x265 인코딩 → 첫 프레임 jpg
# 위에서 아래로 한 번에 읽히도록 단계를 나누지 않았다. 그림만 고칠 땐
# gen_svg.py 수정 후 이 스크립트를 그냥 다시 돌리면 된다.
#
# 밤 변형은 만들지 않는다 (night/night-rain은 원본 그대로 씀).
set -e

HERE=${0:A:h}
REPO=${HERE:h:h}
B=$HERE/build                      # 중간 산출물 (gitignore됨)
mkdir -p $B
cd $REPO

VARIANTS=(dusk day dawn dusk-rain day-rain dawn-rain)


# 1. 오버레이 아트 -----------------------------------------------------
#' 무보정(=dusk) 톤 기준으로 한 장만 그린다. 밴드별 색은 3단계에서 맞춘다.
python3 $HERE/gen_svg.py base $B/ovl_base.html


# 2. Edge 헤드리스 렌더 ------------------------------------------------
#' rsvg/resvg가 없어서 브라우저로 굽는다. feTurbulence 붓터치·한글 폰트가
#' 그대로 나온다. 파일을 쓰고도 프로세스가 안 죽으므로 폴링 후 PID만 kill
#' (사용자 Edge 상시 실행 중 — 광역 pkill 금지)
EDGE="/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
rm -f $B/ovl_base.png
"$EDGE" --headless=new --disable-gpu --hide-scrollbars \
  --default-background-color=00000000 --force-color-profile=srgb \
  --window-size=3840,2160 --screenshot="$B/ovl_base.png" \
  --user-data-dir="$B/edgeprof" "file://$B/ovl_base.html" >/dev/null 2>&1 &
EPID=$!
for i in $(seq 1 120); do [ -s $B/ovl_base.png ] && break; sleep 0.5; done
sleep 1.5; kill $EPID 2>/dev/null || true; wait $EPID 2>/dev/null || true
[ -s $B/ovl_base.png ] || { echo "render failed"; exit 1 }
echo "rendered $B/ovl_base.png"


# 3. 밴드별 그레이딩 ---------------------------------------------------
#' 배경 영상을 만들 때 쓴 체인을 오버레이에 그대로 먹여야 색이 붙는다.
#' 색보정 필터가 RGBA를 안전하게 못 다뤄서 알파를 떼뒀다 다시 붙인다.
grade_of() {
  case $1 in
    dusk)      echo "null" ;;
    dawn)      echo "colortemperature=7800:mix=.75,selectivecolor=reds=0.15 0.10 -0.25 0:yellows=0.10 0.05 -0.30 0:whites=0 0 -0.15 0,colorbalance=rs=-.03:bs=.09:rm=.03:bm=.05:rh=.05:bh=.04,eq=brightness=.05:gamma=1.06:saturation=.93,vibrance=intensity=.10:gbal=2:rbal=.2:bbal=.2,curves=all='0/0.055 0.5/0.54 1/1'" ;;
    day)       echo "colortemperature=12000:mix=.92,selectivecolor=reds=0.45 0 -0.35 0:yellows=0.18 0 -0.22 0:whites=0 -0.06 -0.28 0.06:magentas=0.25 -0.05 0 0,eq=brightness=.08:gamma=1.13:saturation=1.06:contrast=1.02,vibrance=intensity=.15:gbal=1.5,curves=all='0/0 0.5/0.56 1/1'" ;;
    dawn-rain) echo "eq=saturation=.28:brightness=-.02:gamma=.95,colorbalance=bs=.10:bm=.08:bh=.05,curves=all='0/0.05 0.5/0.47 1/0.74'" ;;
    day-rain)  echo "eq=saturation=.30:brightness=.02:gamma=1.02,colorbalance=bs=.06:bm=.05:bh=.04,curves=all='0/0.06 0.5/0.52 1/0.82'" ;;
    dusk-rain) echo "eq=saturation=.28:brightness=-.04:gamma=.90,colorbalance=bs=.09:bm=.07:bh=.05,curves=all='0/0.04 0.5/0.44 1/0.68'" ;;
  esac
}

for V in $VARIANTS; do
  ffmpeg -v error -i $B/ovl_base.png -filter_complex "
    [0:v]format=rgba,split=2[a][b];
    [a]alphaextract[al];
    [b]format=rgb24,$(grade_of $V),format=rgba[gr];
    [gr][al]alphamerge[out]" \
    -map "[out]" -pix_fmt rgba -frames:v 1 -y $B/ovl-$V.png
  echo "graded $V"
done


# 4. 합성 + 인코딩 -----------------------------------------------------
#' 원본은 x264 crf21 / x265 crf23. 재인코딩 세대 손실 상쇄로 한 단씩 올린다.
#' 프레임 수(316)는 절대 바뀌면 안 된다 — 핑퐁 루프가 튄다.
for V in $VARIANTS; do
  echo "=== $V h264 $(date +%T)"
  ffmpeg -v error -i img/meadow-$V.mp4 -i $B/ovl-$V.png \
    -filter_complex "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p[v]" \
    -map "[v]" -an -c:v libx264 -preset slow -crf 20 \
    -movflags +faststart -y img/meadow-$V-camp.mp4

  echo "=== $V hevc $(date +%T)"
  ffmpeg -v error -i img/meadow-$V.mp4 -i $B/ovl-$V.png \
    -filter_complex "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p10le[v]" \
    -map "[v]" -an -c:v libx265 -preset medium -crf 22 -pix_fmt yuv420p10le \
    -tag:v hvc1 -color_primaries bt709 -color_trc bt709 -colorspace bt709 \
    -x265-params log-level=error:colorprim=bt709:transfer=bt709:colormatrix=bt709 \
    -movflags +faststart -y img/meadow-$V-camp.hevc.mp4

  #' 정지 프레임은 반드시 방금 구운 영상의 첫 프레임에서 뽑는다.
  #' (poster + --still + 하늘 프리즈 3역이라 어긋나면 바로 티가 난다)
  ffmpeg -v error -i img/meadow-$V-camp.mp4 -frames:v 1 -q:v 3 \
    -y img/sky-$V-camp.jpg
done

echo "=== DONE $(date +%T)"
ffprobe -v error -select_streams v:0 -count_frames \
  -show_entries stream=nb_read_frames -of csv=p=0 img/meadow-day-camp.mp4
ls -la img/*camp* | awk '{print $5, $9}'
