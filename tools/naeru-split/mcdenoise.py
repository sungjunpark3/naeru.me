#!/usr/bin/env python3
# 모션 보상 시간축 잡음제거. matte.py가 스프라이트 색에 쓴다.
#
# 왜 필요한가 —
#   자글거림의 91%는 몸통에 퍼져 있고(2026-09-05 전 프레임 감사), 그건 원본
#   푸티지가 원래 갖고 있던 프레임간 노이즈다. 배경이 영상이던 시절엔 풀·구름이
#   같이 들끓어 묻혔는데 배경을 정지 이미지로 바꾸고 나니 드러났다.
#   그냥 시간축 평균을 세게 걸면 노이즈와 함께 모션도 뭉갠다. 이웃 프레임을
#   **블록 단위로 정렬한 뒤** 평균내면 모션은 그대로 두고 노이즈만 준다.
#
# 8변형은 같은 푸티지의 색보정본이라 **모션은 한 번만 구해서 공유한다**.
# 변형마다 다시 구하면 8배 느리고 결과도 같다.
import numpy as np
from PIL import Image

BS = 16            # 블록 크기
SEARCH = 5         # 탐색 반경(px) — 프레임간 이동이 이보다 크지 않다(실측 ≤6)
REJECT = 14.0      # 정렬 후에도 이만큼 다르면 그 화소는 평균에 안 넣는다
                   # (가려짐·정렬 실패에서 잔상이 생기는 걸 막는다)


def _blocks(shape):
    h, w = shape
    return h // BS, w // BS


def _block_sad(diff, by, bx):
    return diff[:by * BS, :bx * BS].reshape(by, BS, bx, BS).sum((1, 3))


def _med3(a):
    p = np.pad(a, 1, mode="edge")
    st = np.stack([p[i:i + a.shape[0], j:j + a.shape[1]]
                   for i in range(3) for j in range(3)])
    return np.median(st, 0).astype(np.int16)


def estimate(cur, ref):
    """ref를 cur에 맞추는 블록별 (dx, dy). 전 화면을 한 칸씩 밀어보며
    블록 SAD를 한 번에 구한다 — 블록마다 따로 돌면 파이썬에서 너무 느리다."""
    by, bx = _blocks(cur.shape[:2])
    best = np.full((by, bx), 1e18, np.float32)
    mvx = np.zeros((by, bx), np.int16)
    mvy = np.zeros((by, bx), np.int16)
    for dy in range(-SEARCH, SEARCH + 1):
        for dx in range(-SEARCH, SEARCH + 1):
            sh = np.roll(np.roll(ref, dy, 0), dx, 1)
            sad = _block_sad(np.abs(sh - cur).sum(2), by, bx)
            m = sad < best
            best[m] = sad[m]
            mvx[m] = dx
            mvy[m] = dy
    return _med3(mvx), _med3(mvy)


def warp(ref, mvx, mvy):
    h, w = ref.shape[:2]
    ux = np.repeat(np.repeat(mvx, BS, 0), BS, 1)
    uy = np.repeat(np.repeat(mvy, BS, 0), BS, 1)
    if ux.shape != (h, w):                      # 블록으로 안 떨어지는 나머지 채우기
        ux = np.pad(ux, ((0, h - ux.shape[0]), (0, w - ux.shape[1])), mode="edge")
        uy = np.pad(uy, ((0, h - uy.shape[0]), (0, w - uy.shape[1])), mode="edge")
    yy, xx = np.mgrid[0:h, 0:w]
    return ref[np.clip(yy + uy, 0, h - 1), np.clip(xx + ux, 0, w - 1)]


def neighbours(n, unique):
    """핑퐁 루프의 이웃. 0과 마지막은 양쪽 이웃이 같은 프레임이다
    ([0..158]+[157..1]이라 0의 앞뒤가 둘 다 src1)."""
    if n == 0:
        return 1, 1
    if n == unique - 1:
        return unique - 2, unique - 2
    return n - 1, n + 1


def motion_field(frames):
    """이웃 두 장을 각 프레임에 맞추는 MV를 미리 다 구해 둔다(변형 간 공유)."""
    unique = len(frames)
    mv = []
    for n in range(unique):
        a, b = neighbours(n, unique)
        mv.append((estimate(frames[n], frames[a]), estimate(frames[n], frames[b])))
    return mv


def denoise(frames, mv):
    """MV는 motion_field가 준 것. frames는 float32 RGB 리스트."""
    unique = len(frames)
    out = []
    for n in range(unique):
        a, b = neighbours(n, unique)
        cur = frames[n]
        acc = cur * 2.0
        wsum = np.full(cur.shape[:2] + (1,), 2.0, np.float32)
        for r, (mvx, mvy) in ((a, mv[n][0]), (b, mv[n][1])):
            w = warp(frames[r], mvx, mvy)
            ok = (np.abs(w - cur).max(2) < REJECT)[..., None].astype(np.float32)
            acc += w * ok
            wsum += ok
        out.append(acc / wsum)
    return out
