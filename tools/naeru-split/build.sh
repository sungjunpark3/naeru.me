#!/bin/zsh
# 내루미를 배경 영상에서 떼어 DOM으로 얹기 위한 자산 파이프라인. 한 방 실행.
#   1. ffmpeg로 dusk WORK밴드 + 8변형 CROP밴드 316프레임씩 추출
#   2. plate.py  — 정지 패치 8장 (알파 시퀀스 build/alpha/도 이 안에서 만들어짐)
#   3. matte.py  — 내루미 알파 PNG 시퀀스 8×316장
#   4. verify.py --pass1 — PNG 시퀀스 단계에서 먼저 게이트. 여기서 실패하면
#      인코딩 전에 멈춘다(인코딩이 제일 오래 걸리는 단계라 낭비 안 하려는 것)
#   5. 인코딩: VP9 webm + HEVC mp4 + 정지본, alpha-probe
#   6. verify.py --pass2 — 인코딩(알파 압축 손실 포함) 결과까지 검증
#
# 그림만 고칠 땐 처음부터 다시 돌릴 필요 없다 — plate.py/matte.py/인코딩
# 구간만 따로 다시 실행해도 된다(주석 참고).
set -e

HERE=${0:A:h}
REPO=${HERE:h:h}
B=$HERE/build
mkdir -p $B
cd $REPO

VARIANTS=(dawn day dusk night dawn-rain day-rain dusk-rain night-rain)

# 좌표 계약 — coords.py와 반드시 같은 값. 바꾸면 양쪽 다 고치고 §3.2 여유를
# 다시 확인할 것. zsh에서 "$VAR[n]"은 첨자로 해석돼 변수가 사라지므로
# filter_complex 라벨 앞에서는 반드시 "${VAR}[n]" 형태로 쓴다.
CROP="576:496:1744:1328"
WORK="750:650:1650:1250"


# 1. 프레임 추출 ---------------------------------------------------------
mkdir -p $B/dusk-work
for V in $VARIANTS; do
  mkdir -p $B/O/$V
  if [ "$V" = "dusk" ]; then
    # dusk는 CROP(색 재료)과 WORK(알파 계산용 여유 영역)를 한 번의 디코딩으로
    ffmpeg -v error -y -i img/meadow-$V.mp4 -filter_complex \
      "[0:v]split=2[a][b];[a]crop=${CROP}[crop];[b]crop=${WORK}[work]" \
      -map "[crop]" $B/O/$V/%04d.png -map "[work]" $B/dusk-work/%04d.png
  else
    ffmpeg -v error -y -i img/meadow-$V.mp4 -vf "crop=${CROP}" $B/O/$V/%04d.png
  fi
  echo "extracted $V ($(ls $B/O/$V | wc -l | tr -d ' ') frames)"
done


# 2-3. 패치 + 매트 --------------------------------------------------------
python3 $HERE/plate.py
python3 $HERE/matte.py


# 4. PNG 시퀀스 단계 검증 --------------------------------------------------
python3 $HERE/verify.py --pass1


# 5. 인코딩 ---------------------------------------------------------------
# VP9 crf 34 / HEVC q:v 40 — crf26·q65(계획 초안값)는 이 CROP 크기에서
# 변형당 각각 ~2-3MB·~5-6MB로 너무 커서 실측 후 낮췄다(육안 확인 통과).
for V in $VARIANTS; do
  echo "=== $V webm $(date +%T)"
  ffmpeg -v error -y -framerate 24 -i $B/naeru-$V/%04d.png \
    -c:v libvpx-vp9 -pix_fmt yuva420p -crf 34 -b:v 0 \
    -auto-alt-ref 0 -row-mt 1 -deadline good -cpu-used 2 \
    img/naeru-$V.webm

  echo "=== $V mp4(hevc) $(date +%T)"
  #' 사파리는 HEVC 알파를 **프리멀티플라이로 합성한다**(dst = src + (1-a)*bg).
  #' 스트레이트로 넣으면 경계에서 스프라이트 색과 배경이 더해져 실루엣을 두르는
  #' 밝은 크림색 테두리가 생긴다(2026-09-01 사파리 18.6에서 나란히 찍어 확인).
  #' webm(VP9)은 스트레이트가 맞으므로 여기서만 건다.
  #' 확인법: 인코딩 뒤 투명 영역 RGB가 (0,0,0)이어야 한다.
  ffmpeg -v error -y -framerate 24 -i $B/naeru-$V/%04d.png \
    -vf "premultiply=inplace=1" \
    -c:v hevc_videotoolbox -pix_fmt bgra -alpha_quality 0.85 -q:v 40 \
    -tag:v hvc1 -movflags +faststart \
    img/naeru-$V.mp4
  #   -q:v가 거부되면 -b:v 1500k 로 대체

  pngquant --quality=70-95 --strip --force -o img/naeru-$V.png -- $B/naeru-$V/0001.png
done

# 16x16 완전 투명 1프레임 — 알파 지원 판정용(Safari가 VP9 알파를 무시하고
# 검은 사각형으로 그리는 걸 본편 받기 전에 걸러내는 프로브)
mkdir -p $B/alpha-probe-src
python3 -c "
from PIL import Image
Image.new('RGBA', (16, 16), (0, 0, 0, 0)).save('$B/alpha-probe-src/0001.png')
"
ffmpeg -v error -y -framerate 24 -i $B/alpha-probe-src/%04d.png \
  -c:v libvpx-vp9 -pix_fmt yuva420p -crf 40 -b:v 0 -auto-alt-ref 0 \
  -frames:v 1 img/alpha-probe.webm


# 6. 인코딩 결과 검증 -------------------------------------------------------
# VP9 알파는 디코딩 시 -vcodec libvpx-vp9를 명시해야 한다(기본 vp9 디코더는
# 알파 블록을 안 읽음 — 실측으로 발견). verify.py의 decode_webm이 이미 반영.
python3 $HERE/verify.py --pass2


echo "=== DONE $(date +%T)"
ls -la img/naeru-*.webm img/naeru-*.mp4 img/naeru-*.png img/alpha-probe.webm 2>/dev/null \
  | awk '{print $5, $9}'
echo "--- frame count check (316 유지 확인) ---"
for V in $VARIANTS; do
  n=$(ffprobe -v error -select_streams v:0 -count_frames \
      -show_entries stream=nb_read_frames -of csv=p=0 img/naeru-$V.webm)
  echo "$V.webm: $n frames"
done
