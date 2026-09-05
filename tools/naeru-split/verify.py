#!/usr/bin/env python3
# plate ⊕ naeru를 합성해서 원본 프레임과 PSNR로 비교한다.
#   --pass1 (기본): PNG 시퀀스로 — 매트 로직 자체의 정확도
#   --pass2       : 인코딩된 webm을 디코딩해서 — 알파 압축 손실까지 포함
# 기준: 크롭 영역 PSNR 평균 >= 40dB, 최악 프레임 >= 34dB. numpy 없어서
# MSE는 ImageChops.difference -> histogram()으로 구한다(글로벌 지침).
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from PIL import Image, ImageChops, ImageFilter

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
B = HERE / "build"
sys.path.insert(0, str(HERE))
from coords import CROP_ORIGIN, CROP_SIZE, N_FRAMES, VARIANTS

# PNG 시퀀스(pass1)와 인코딩본(pass2)의 기준을 따로 둔다.
#
# 40dB는 계획서 초안값인데, 그건 plate에 캐릭터가 남고 알파에 배경이 섞인
# **축퇴 해**를 재던 값이었다(2026-09-01). 그 상태는 서로의 오차를 상쇄해서
# 원본이 거의 그대로 복원됐다. 제대로 분리하면 매트 경계가 진짜 컷아웃이 되므로
# 복원값은 오히려 조금 내려간다 — 실측 상한이 pass1 41.0dB이고, 여기서 알파
# 압축 손실 1.3dB를 빼면 pass2는 39.6dB다(crf30으로 올려도 39.8dB로 +0.2dB뿐:
# 코덱이 아니라 경계 자체가 상한이다).
#
# (그 뒤 윤곽 평활·시간축 중앙값·발 복원으로 매트를 고치자 pass1 42.5 / pass2
#  40.9dB로 올라갔다 — 발이 스프라이트에서 빠져 있던 게 실제 공백이었다.)
# **분리가 됐는지 아닌지는 이제 GATES가 판정한다** — 이 PSNR은 "겉보기가 예전과
# 같은가"만 본다.
AVG_MIN   = 40.0
AVG_MIN2  = 39.5   # 2026-09-01 매트 개선 후 실측 40.9dB — 여유 1.4dB
# 최악 프레임 하한. 2026-09-05에 34.0 → 32.0으로 내렸다 — **분리 품질이
# 나빠져서가 아니라 색·알파에 시간축 5탭 평활을 일부러 걸었기 때문이다.**
# 평활은 가장 빠르게 움직이는 프레임에서 원본과 가장 많이 벌어지는데(현재
# 최악 f191 dusk 33.4dB), 그 대가로 자글거림이 알파 541.9 → 193.3화소/프레임,
# 합성 71.2 → 5.1로 준다(audit.py 전수 측정). 분리가 실제로 무너지는 경우는
# 아래 GATES와 audit.py의 흘러나옴/구멍 수치가 PSNR과 무관하게 잡는다.
# 평균 기준(AVG_MIN)은 그대로 두었다 — 현재 43.3/41.3으로 여유가 크다.
WORST_MIN = 32.0


def psnr(im1, im2):
    diff = ImageChops.difference(im1.convert("RGB"), im2.convert("RGB"))
    hist = diff.histogram()
    sq_sum = 0
    n = 0
    for ch in range(3):
        for v in range(256):
            c = hist[ch * 256 + v]
            sq_sum += c * v * v
            n += c
    mse = sq_sum / n
    if mse == 0:
        return 99.0
    return 10 * math.log10(255.0 * 255.0 / mse)


def report(label, values, avg_min=AVG_MIN):
    """values: [(frame_idx, variant, psnr), ...]"""
    avg = sum(v for _, _, v in values) / len(values)
    worst = min(values, key=lambda t: t[2])
    ok = avg >= avg_min and worst[2] >= WORST_MIN
    print(f"[{label}] n={len(values)} avg={avg:.2f}dB "
          f"worst={worst[2]:.2f}dB (frame {worst[0]:04d} {worst[1]}) "
          f"{'PASS' if ok else 'FAIL'} (기준: avg>={avg_min} worst>={WORST_MIN})")
    # 변형별 평균도 같이
    by_variant = {}
    for _, v, val in values:
        by_variant.setdefault(v, []).append(val)
    for v in VARIANTS:
        if v in by_variant:
            vv = by_variant[v]
            print(f"    {v:12s} avg={sum(vv)/len(vv):6.2f}dB "
                  f"worst={min(vv):6.2f}dB")
    return ok


def gates():
    """복원 PSNR만으로는 절대 못 잡는 두 가지를 따로 본다.

    왜 필요한가 — 2026-09-01에 실제로 겪은 것: plate에 캐릭터가 남아 있고
    스프라이트 알파에 배경이 딸려 들어간 상태였는데도 복원 PSNR은 41dB로
    통과했다. `C = P + (O-P)/a`라 P≈O이면 알파가 뭐든 O가 복원되기 때문이다.
    둘이 서로의 오차를 상쇄하는 축퇴 해라서, 제자리에 서 있는 동안은 멀쩡하고
    폴짝하는 순간(PLAN §4.2) 무너진다. 그러니 **plate 단독**과 **스프라이트
    단독**을 각각 봐야 한다.

    A. plate의 지운 자리가 아직 캐릭터 색인가 — 분홍기(R-max(G,B))로 잰다.
       실측(dusk): 초원 p50=16, 내루미 p50=41. 지워졌다면 주변 초원과 비슷해야.
    B. 스프라이트가 몸 밖을 달고 다니는가 / 몸 안에 구멍이 났는가."""
    ok = True
    ground_y = 1690 - CROP_ORIGIN[1]      # 접지 페이드 위쪽만 본다(아래는 그림자 보존 구간)
    for v in VARIANTS:
        plate = Image.open(REPO / "img" / f"plate-{v}.png").crop(
            (CROP_ORIGIN[0], CROP_ORIGIN[1],
             CROP_ORIGIN[0] + CROP_SIZE[0], CROP_ORIGIN[1] + CROP_SIZE[1])).convert("RGBA")
        pa = plate.getchannel("A").point(lambda x: 255 if x > 200 else 0)
        core = pa.filter(ImageFilter.MinFilter(41))            # 패치 안쪽 20px
        ring = ImageChops.subtract(pa.filter(ImageFilter.MaxFilter(81)), pa)  # 바깥 40px 띠

        r, g, b = plate.convert("RGB").split()
        pink = ImageChops.subtract(r, ImageChops.lighter(g, b))
        c_pink, r_pink = mean_where(pink, core), mean_where(pink, ring)
        a_ok = c_pink <= r_pink + 6
        ok = ok and a_ok
        print(f"  [A] {v:12s} plate 분홍기 코어={c_pink:5.1f} 링={r_pink:5.1f} "
              f"{'PASS' if a_ok else 'FAIL — plate에 캐릭터가 남아 있다'}")

        outside = ImageChops.invert(pa).crop((0, 0, CROP_SIZE[0], ground_y))
        worst_out, worst_in = 0.0, 255.0
        for fp in sorted((B / f"naeru-{v}").glob("*.png"))[::20]:
            a = Image.open(fp).getchannel("A")
            worst_out = max(worst_out, mean_where(a.crop((0, 0, CROP_SIZE[0], ground_y)),
                                                  outside))
            inner = a.point(lambda x: 255 if x > 200 else 0).filter(ImageFilter.MinFilter(41))
            if inner.getbbox():
                worst_in = min(worst_in, mean_where(a, inner))
        b_ok = worst_out <= 3.0 and worst_in >= 250.0
        ok = ok and b_ok
        print(f"  [B] {v:12s} 스프라이트 몸밖 알파={worst_out:4.1f}(<=3) "
              f"몸안 알파={worst_in:5.1f}(>=250) {'PASS' if b_ok else 'FAIL'}")
    return ok


def mean_where(gray, mask):
    """mask가 255인 화소에서 gray의 평균."""
    hist = ImageChops.multiply(gray, mask.point(lambda x: 255 if x > 128 else 0)) \
        .histogram()
    n = mask.point(lambda x: 255 if x > 128 else 0).histogram()[255]
    if not n:
        return 0.0
    return sum(i * c for i, c in enumerate(hist[1:], start=1)) / n


def pass1():
    plates = {}
    values = []
    for v in VARIANTS:
        plate = Image.open(REPO / "img" / f"plate-{v}.png").crop(
            (CROP_ORIGIN[0], CROP_ORIGIN[1],
             CROP_ORIGIN[0] + CROP_SIZE[0], CROP_ORIGIN[1] + CROP_SIZE[1])
        ).convert("RGBA")
        plates[v] = plate
        o_frames = sorted((B / "O" / v).glob("*.png"))
        n_frames = sorted((B / f"naeru-{v}").glob("*.png"))
        assert len(o_frames) == N_FRAMES == len(n_frames), v
        for i, (o_fp, n_fp) in enumerate(zip(o_frames, n_frames), start=1):
            orig = Image.open(o_fp).convert("RGB")
            naeru = Image.open(n_fp).convert("RGBA")
            # 실제 레이어 순서: 원본 배경 위에 plate로 지우고 naeru로 다시 그린다.
            # plate만으로 시작하면 plate가 투명한(대부분의) 영역이 검정으로
            # 찍혀 PSNR이 터무니없이 낮게 나온다 — 실제로 겪은 버그.
            recon = orig.convert("RGBA").copy()
            recon.alpha_composite(plate)
            recon.alpha_composite(naeru)
            values.append((i, v, psnr(recon.convert("RGB"), orig)))
    return report("PASS1 PNG시퀀스", values)


def decode_webm(path, out_dir):
    """-vcodec libvpx-vp9를 입력 앞에 명시해야 알파가 나온다 — 기본 내장 vp9
    디코더는 이 환경에서 알파 블록을 읽지 않고 전부 불투명(255)으로 내놓는다
    (실측으로 발견, 최소 합성 테스트로 재현·확인함)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-vcodec", "libvpx-vp9",
         "-i", str(path), "-pix_fmt", "yuva420p", f"{out_dir}/%04d.png"],
        check=True,
    )


def pass2():
    values = []
    tmp_root = Path(tempfile.mkdtemp(prefix="naeru-verify-"))
    for v in VARIANTS:
        webm = REPO / "img" / f"naeru-{v}.webm"
        if not webm.exists():
            print(f"  (건너뜀: {webm.name} 없음 — build.sh를 먼저 돌릴 것)")
            continue
        out_dir = tmp_root / v
        decode_webm(webm, out_dir)
        decoded = sorted(out_dir.glob("*.png"))
        plate = Image.open(REPO / "img" / f"plate-{v}.png").crop(
            (CROP_ORIGIN[0], CROP_ORIGIN[1],
             CROP_ORIGIN[0] + CROP_SIZE[0], CROP_ORIGIN[1] + CROP_SIZE[1])
        ).convert("RGBA")
        o_frames = sorted((B / "O" / v).glob("*.png"))
        assert len(decoded) == N_FRAMES == len(o_frames), \
            f"{v}: webm 디코딩 {len(decoded)}프레임, 기대 {N_FRAMES}"
        for i, (o_fp, d_fp) in enumerate(zip(o_frames, decoded), start=1):
            orig = Image.open(o_fp).convert("RGB")
            naeru = Image.open(d_fp).convert("RGBA")
            recon = orig.convert("RGBA").copy()
            recon.alpha_composite(plate)
            recon.alpha_composite(naeru)
            values.append((i, v, psnr(recon.convert("RGB"), orig)))
    if not values:
        print("PASS2: 검사할 webm이 없음")
        return True
    return report("PASS2 webm디코딩", values, AVG_MIN2)


if __name__ == "__main__":
    args = sys.argv[1:]
    ok = True
    if not args or "--pass1" in args:
        print("[GATES] plate 단독 / 스프라이트 단독 — 복원 PSNR이 못 잡는 것")
        ok = gates() and ok
        ok = pass1() and ok
    if not args or "--pass2" in args:
        ok = pass2() and ok
    sys.exit(0 if ok else 1)
