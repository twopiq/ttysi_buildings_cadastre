"""AT belgilarini (qo'lyozma) kadastr rasmidan topish - xonalarni chizishdan alohida jarayon.

Ikki xil siyoh:
  * ko'k ruchka - rang bo'yicha (bosma chizmada ko'k yo'q);
  * qora ruchka - bosma chizmadan to'qroq va qalinroq bo'ladi (nusxa ko'chirilgan kadastr
    kulrang/xira, ruchka izi esa deyarli qora). Uzun to'g'ri chiziqlar (devorlar) olib tashlanadi,
    shunda devor ustiga yozilgan "X" ham ajraladi. Har bir nomzod baholanadi:
      - eng to'q nuqtasi (ruchka 0..30, bosma 40..100),
      - chiziq qalinligi (ruchka qalinroq),
      - o'qlarga parallellik (bosma bo'laklar - devor burchaklari, eshik kesaklari - faqat
        gorizontal/vertikal; qo'lyozma qiya va egri).
    Bosma chizma qora bo'lsa (toza PDF) - qora qo'lyozmani ajratib bo'lmaydi va hech narsa
    topilmaydi (soxta belgilar chiqmasligi uchun).

Natija - belgilar nomzodlari (markazi, o'lchami, rangi, ishonch). Turi tasdiqlash ekranida beriladi.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

WORK = 2000          # tahlil shu o'lchamdagi rasmda (piksel), natija qayta kattalashtiriladi


@dataclass
class MarkParams:
    blue: bool = True            # ko'k ruchka
    black: bool = True           # qora ruchka (qo'lyozma)
    sensitivity: float = 0.5     # 0..1 - kattaroq: ko'proq (shubhali ham) topiladi
    min_size: float = 0.006      # belgining eng kichik o'lchami (rasm uzun tomoniga nisbatan)
    max_size: float = 0.07       # eng katta o'lchami (strelka, yozuvlar tushib qolsin)


@dataclass
class Mark:
    x: float
    y: float
    w: float
    h: float
    color: str                   # "blue" / "black"
    score: float                 # 0..1 ishonch


def blue_ink(img: np.ndarray, sensitivity: float = 0.5) -> np.ndarray:
    """Ko'k ruchka izlari maskasi (HSV rang va ko'k kanal ustunligi)."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    b, g, r = cv2.split(img.astype(np.int16))
    min_sat = int(110 - 70 * sensitivity)
    mask = ((h >= 95) & (h <= 135) & (s >= min_sat) & (v >= 30) & (v <= 245)
            & ((b - np.maximum(r, g)) >= int(30 - 20 * sensitivity))).astype(np.uint8) * 255
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))


def _group(mask: np.ndarray, join: int):
    """Yaqin izlarni (bitta belgining harflari) birlashtirish: (bbox, guruh maskasi) ro'yxati."""
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (join, join))
    n, lab, st, _ = cv2.connectedComponentsWithStats(cv2.dilate(mask, k), connectivity=8)
    out = []
    for i in range(1, n):
        x, y, w, h, _ = st[i]
        sub = (mask[y:y + h, x:x + w] > 0) & (lab[y:y + h, x:x + w] == i)
        if not sub.any():
            continue
        yy, xx = np.nonzero(sub)
        out.append(((x + xx.min(), y + yy.min(), x + xx.max(), y + yy.max()), sub, (x, y)))
    return out


def find_blue(img: np.ndarray, p: MarkParams) -> list[Mark]:
    big = max(img.shape[:2])
    mask = blue_ink(img, p.sensitivity)
    out = []
    for (x0, y0, x1, y1), sub, _ in _group(mask, max(5, int(big * 0.012)) | 1):
        size = max(x1 - x0, y1 - y0) + 1
        if sub.sum() < max(6, big * 0.004) or size > big * p.max_size * 1.4:
            continue
        out.append(Mark((x0 + x1) / 2, (y0 + y1) / 2, x1 - x0 + 1, y1 - y0 + 1, "blue", 1.0))
    return out


def find_black(img: np.ndarray, p: MarkParams, debug: dict | None = None) -> list[Mark]:
    from .detection import normalize_illumination
    gray = normalize_illumination(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    h, w = gray.shape
    big = max(h, w)
    block = max(15, int(big * 0.015)) | 1
    ink = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, block, 12)
    vals = gray[ink > 0]
    if vals.size < 50:
        return []
    base = float(np.median(vals))                      # bosma siyohning odatiy to'qligi
    t_hi = min(base - 75 + 30 * p.sensitivity, 120 + 30 * p.sensitivity)    # ruchka "yadrosi"
    if t_hi < 40:
        return []                                      # bosma chizma o'zi qora - ajratib bo'lmaydi
    t_lo = base - 35
    # uzun gorizontal/vertikal chiziqlar (devorlar) - olib tashlanadi
    L = max(15, int(big * 0.025))
    lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, L), np.uint8)) | \
        cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((L, 1), np.uint8))
    rest = (ink > 0) & (cv2.dilate(lines, np.ones((3, 3), np.uint8)) == 0)

    core = (rest & (gray <= t_hi)).astype(np.uint8) * 255
    n, lab, st, _ = cv2.connectedComponentsWithStats(core, connectivity=8)
    bw, bh, area = st[:, 2], st[:, 3], st[:, 4]
    asp = bw / np.maximum(1, bh)
    column = ((area / np.maximum(1, bw * bh)) > 0.5) & (asp > 0.6) & (asp < 1.6) & (np.maximum(bw, bh) > 6)
    keep = (area >= 4) & ~column                       # shtrixlangan kvadrat ustunlar - belgi emas
    keep[0] = False
    core = (keep[lab] * 255).astype(np.uint8)
    join = max(5, int(big * 0.008)) | 1
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (join, join))
    ext = (rest & (gray <= t_lo)).astype(np.uint8) * 255
    mmask = cv2.bitwise_or(core, cv2.bitwise_and(ext, cv2.dilate(core, k)))

    gx = cv2.Sobel(gray.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    ang = (np.degrees(np.arctan2(gy, gx)) + 180) % 90
    axial = (ang < 12) | (ang > 78)
    thr = 0.62 - 0.3 * p.sensitivity                   # sezgirlik 0.5 -> 0.47
    out = []
    for (x0, y0, x1, y1), sub, (ox, oy) in _group(mmask, join):
        mw, mh = x1 - x0 + 1, y1 - y0 + 1
        if max(mw, mh) < big * p.min_size or max(mw, mh) > big * p.max_size:
            continue
        sl = (slice(y0, y1 + 1), slice(x0, x1 + 1))
        g = gray[sl]
        sub = sub[y0 - oy:y1 - oy + 1, x0 - ox:x1 - ox + 1]
        c = sub & (g <= t_hi)
        if c.sum() < big * 0.006:
            continue
        darkest = float(g[sub].min())
        dist = cv2.distanceTransform(c.astype(np.uint8), cv2.DIST_L2, 3)
        stroke = 2 * float(dist[dist > 0].mean()) if (dist > 0).any() else 0.0
        m = mag[sl] * (g <= t_lo)
        axis = float((m * axial[sl]).sum() / max(1e-6, m.sum()))
        score = 0.6 * np.clip((90 - darkest) / 60, 0, 1) + 0.4 * np.clip((stroke - 1.9) / 0.4, 0, 1)
        if axis > 0.6:                                 # devor burchagi, eshik kesagi - bosma bo'lak
            score -= 0.4
        if debug is not None:
            debug.setdefault("all", []).append(((x0 + x1) / 2, (y0 + y1) / 2, mw, mh, darkest, stroke, axis, score))
        if score >= thr:
            out.append(Mark((x0 + x1) / 2, (y0 + y1) / 2, mw, mh, "black", float(min(1.0, score))))
    return out


def detect_marks(img: np.ndarray, p: MarkParams | None = None) -> list[Mark]:
    """Rasmdan AT belgisi nomzodlari (rasm piksellarida)."""
    p = p or MarkParams()
    H, W = img.shape[:2]
    k = min(1.0, WORK / max(H, W))
    work = cv2.resize(img, (round(W * k), round(H * k)), interpolation=cv2.INTER_AREA) if k < 1 else img
    marks: list[Mark] = []
    if p.blue:
        marks += find_blue(work, p)
    if p.black:
        # ko'k izlar qora qidiruvda ham ko'rinmasligi uchun oqartiriladi
        clean = work
        if p.blue:
            clean = work.copy()
            clean[cv2.dilate(blue_ink(work, p.sensitivity), np.ones((5, 5), np.uint8)) > 0] = 255
        for m in find_black(clean, p):
            if all(abs(m.x - o.x) > (m.w + o.w) / 2 or abs(m.y - o.y) > (m.h + o.h) / 2 for o in marks):
                marks.append(m)
    return [Mark(m.x / k, m.y / k, m.w / k, m.h / k, m.color, m.score) for m in marks]
