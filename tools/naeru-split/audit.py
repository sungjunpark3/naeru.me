#!/usr/bin/env python3
# 모든 변형 × 316프레임을 한 장씩 검사한다. 추측 대신 수치로 어디가 어떻게
# 어긋났는지 찍어낸다.
#
# 무엇을 "의도된 곳을 벗어난 픽셀"로 보는가 —
#   A. 흘러나온 알파: 캐릭터가 없는 자리에 알파가 있다. 캐릭터의 위치는
#      원본과 plate의 차이로 독립적으로 정의한다(스프라이트를 안 믿는다).
#   B. 몸 안의 구멍: 몸 한가운데인데 알파가 덜 찼다.
#   C. 합성 오차: plate 위에 스프라이트를 얹은 결과가 원본과 다른 화소.
#   D. 시간축 떨림: 이웃 두 프레임의 평균으로 예측되지 않는 성분
#      |X_i - (X_{i-1}+X_{i+1})/2|. 부드러운 모션은 0에 가까우므로 이게 곧
#      자글거림이다. 알파와 합성 밝기 양쪽에서 잰다.
#
# 핑퐁 루프라 양 끝은 순환으로 잇고, **인덱스 0·315는 이음매라 값이 크게
# 나오는 게 정상**이다(0=src0, 1과 315가 둘 다 src1).
#
#   python3 audit.py            8변형 전부
#   python3 audit.py dusk       한 변형만
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
B = HERE / "build"
sys.path.insert(0, str(HERE))
from coords import CROP_ORIGIN, CROP_SIZE, N_FRAMES, VARIANTS

BODY_TH   = 10     # |원본-plate| 이 값을 넘으면 캐릭터가 있는 화소
STRAY_TH  = 8      # 이 알파를 넘으면 "흘러나온" 것으로 센다
HOLE_TH   = 250
COMP_TH   = 24     # 합성 오차가 이 값을 넘으면 이상 화소
SHIM_TH   = 20     # 시간축 떨림이 이 값을 넘으면 자글거리는 화소


def load(p):
    return np.asarray(Image.open(p).convert("RGBA"), np.int16)


def decode(v, fmt, out_dir):
    """실제로 배포되는 것은 PNG가 아니라 인코딩본이다 — 마지막 검사는 이걸로.
    VP9 알파는 -vcodec libvpx-vp9를 입력 앞에 명시해야 나온다(verify.py와 동일)."""
    import shutil
    import subprocess
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)
    src = REPO / "img" / f"naeru-{v}.{fmt}"
    pre = ["-vcodec", "libvpx-vp9"] if fmt == "webm" else []
    subprocess.run(["ffmpeg", "-v", "error", "-y", *pre, "-i", str(src),
                    "-pix_fmt", "rgba", f"{out_dir}/%04d.png"], check=True)


BODY_REF = "dusk"   # 몸 판정은 이 변형 하나로만 한다 — 아래 주석 참고


def body_masks():
    """캐릭터가 어디 있는지는 **dusk 한 벌로만** 판정한다.

    8변형은 같은 푸티지의 색보정본이라 캐릭터 위치가 픽셀 단위로 같은데,
    밤 변형은 대비가 낮아 |원본-plate|가 p50 8.8~11까지 떨어진다(dusk는 30).
    변형마다 따로 재면 임계 10에서 몸 마스크가 무너져 "흘러나온 알파"가
    253만 화소로 뻥튀기된다 — 2026-09-05에 실제로 그렇게 잘못 읽었다."""
    plate = np.asarray(Image.open(REPO / "img" / f"plate-{BODY_REF}.png").convert("RGBA")
                       .crop((CROP_ORIGIN[0], CROP_ORIGIN[1],
                              CROP_ORIGIN[0] + CROP_SIZE[0],
                              CROP_ORIGIN[1] + CROP_SIZE[1])), np.int16)
    pa = plate[..., 3:4] / 255.0
    ds, es = [], []
    for f in sorted((B / "O" / BODY_REF).glob("*.png")):
        O = np.asarray(Image.open(f).convert("RGB"), np.int16)
        bg = O * (1 - pa) + plate[..., :3] * pa
        body = (np.abs(O.astype(np.int32) - bg).max(2) > BODY_TH)
        b8 = Image.fromarray((body * 255).astype(np.uint8))
        ds.append(np.asarray(b8.filter(ImageFilter.MaxFilter(7)), np.uint8) > 0)
        es.append(np.asarray(b8.filter(ImageFilter.MinFilter(13)), np.uint8) > 0)
    return ds, es


def audit(v, verbose=True, src_dir=None, masks=None):
    plate = np.asarray(Image.open(REPO / "img" / f"plate-{v}.png").convert("RGBA")
                       .crop((CROP_ORIGIN[0], CROP_ORIGIN[1],
                              CROP_ORIGIN[0] + CROP_SIZE[0],
                              CROP_ORIGIN[1] + CROP_SIZE[1])), np.int16)
    body_d_all, body_e_all = masks if masks else body_masks()
    o_fps = sorted((B / "O" / v).glob("*.png"))
    n_fps = sorted((src_dir or (B / f"naeru-{v}")).glob("*.png"))
    assert len(o_fps) == len(n_fps) == N_FRAMES, v

    O = np.stack([np.asarray(Image.open(f).convert("RGB"), np.int16) for f in o_fps])
    A = np.zeros((N_FRAMES,) + CROP_SIZE[::-1], np.int16)
    C = np.zeros((N_FRAMES,) + CROP_SIZE[::-1], np.float32)   # 합성 밝기
    stray = np.zeros(N_FRAMES, np.int64)
    hole  = np.zeros(N_FRAMES, np.int64)
    comp  = np.zeros(N_FRAMES, np.int64)
    cmax  = np.zeros(N_FRAMES, np.int64)

    # plate를 원본 위에 얹은 것이 "지워진 배경"이다(verify.py와 같은 순서)
    pa = plate[..., 3:4] / 255.0
    for i in range(N_FRAMES):
        bg = O[i] * (1 - pa) + plate[..., :3] * pa
        sp = load(n_fps[i])
        a = sp[..., 3]
        A[i] = a
        recon = bg * (1 - a[..., None] / 255.0) + sp[..., :3] * (a[..., None] / 255.0)
        C[i] = recon.mean(2)

        body_d, body_e = body_d_all[i], body_e_all[i]
        stray[i] = int(((a > STRAY_TH) & ~body_d).sum())
        hole[i]  = int(((a < HOLE_TH) & body_e).sum())
        d = np.abs(recon - O[i]).max(2)
        comp[i] = int((d > COMP_TH).sum())
        cmax[i] = int(d.max())

    prv = [N_FRAMES - 1] + list(range(N_FRAMES - 1))
    nxt = list(range(1, N_FRAMES)) + [0]
    lapA = np.abs(A - (A[prv] + A[nxt]) / 2)
    lapC = np.abs(C - (C[prv] + C[nxt]) / 2)
    edge = (A.min(0) < 250) & (A.max(0) > 5)          # 한 번이라도 경계였던 곳
    inside = A.min(0) > 250
    shimA = (lapA > SHIM_TH).sum((1, 2))
    shimC = (lapC > SHIM_TH).sum((1, 2))

    seam = {0, N_FRAMES - 1}
    body_frames = [i for i in range(N_FRAMES) if i not in seam]
    if verbose:
        print(f"\n=== {v} ===")
        print(f"  A 흘러나온 알파   총 {stray.sum():8d}  최악 {stray.max():5d}@f{stray.argmax()}")
        print(f"  B 몸 안 구멍      총 {hole.sum():8d}  최악 {hole.max():5d}@f{hole.argmax()}")
        print(f"  C 합성 오차>{COMP_TH}   총 {comp.sum():8d}  최악 {comp.max():5d}@f{comp.argmax()}"
              f"  최대편차 {cmax.max()}")
        print(f"  D 떨림(알파)      평균 {shimA[body_frames].mean():7.1f}화소/프레임"
              f"  최악 {max(shimA[i] for i in body_frames)}@f"
              f"{max(body_frames, key=lambda i: shimA[i])}")
        print(f"  D 떨림(합성)      평균 {shimC[body_frames].mean():7.1f}화소/프레임"
              f"  최악 {max(shimC[i] for i in body_frames)}@f"
              f"{max(body_frames, key=lambda i: shimC[i])}")
        print(f"    경계밴드 라플라시안 p50 {np.median(lapA[:, edge]):.1f}"
              f" p95 {np.percentile(lapA[:, edge], 95):.1f}"
              f" p99 {np.percentile(lapA[:, edge], 99):.1f}")
        print(f"    몸안 밝기 라플라시안 p50 {np.median(lapC[:, inside]):.2f}"
              f" p95 {np.percentile(lapC[:, inside], 95):.2f}"
              f" p99 {np.percentile(lapC[:, inside], 99):.2f}")
    return dict(stray=stray, hole=hole, comp=comp, cmax=cmax,
                shimA=shimA, shimC=shimC, lapA=lapA, lapC=lapC,
                edge=edge, inside=inside)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fmt = next((a[2:] for a in sys.argv[1:] if a in ("--webm", "--mp4")), None)
    vs = args or VARIANTS
    tot = {}
    masks = body_masks()
    for v in vs:
        src = None
        if fmt:
            src = B / f"dec-{v}-{fmt}"
            decode(v, fmt, src)
        tot[v] = audit(v, src_dir=src, masks=masks)
    print("\n=== 요약 (프레임당 자글거리는 화소 수) ===")
    for v in vs:
        r = tot[v]
        keep = [i for i in range(N_FRAMES) if i not in (0, N_FRAMES - 1)]
        print(f"  {v:11s} 알파 {r['shimA'][keep].mean():7.1f}  합성 {r['shimC'][keep].mean():7.1f}"
              f"  흘러나옴 {r['stray'].sum():7d}  구멍 {r['hole'].sum():7d}")


if __name__ == "__main__":
    main()
