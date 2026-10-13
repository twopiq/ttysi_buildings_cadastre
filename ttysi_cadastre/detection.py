"""Kadastr rasmidan taxminiy chizma va AT belgilarini topish (mahalliy, OpenCV).

Bosqichlar:
  1. Telefon rasmi bo'lsa - qog'oz burchaklarini topib, perspektivani to'g'rilash.
  2. Yorug'likni tekislash (soya va notekis yorug'likni yo'qotish).
  3. Ko'k ruchka izlarini rang bo'yicha topish -> AT belgisi nomzodlari.
  4. Ko'k izlarni olib tashlab, qora chiziqlardan devorlarni ajratish.
  5. Devorlar orasidagi yopiq bo'shliqlar -> xonalar va koridorlar (ko'pburchak).

Natija taxminiy: foydalanuvchi uni muharrirda tuzatadi.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

WORK_SIZE = 3000        # tahlil shu o'lchamdan katta bo'lmagan rasmda bajariladi
MAX_STORED_SIZE = 3500  # fon rasmi saqlanadigan eng katta o'lcham


@dataclass
class DetectParams:
    # Masshtab ma'lum bo'lsa (PDF + nisbat) - o'lchamlar metrlarda olinadi
    m_per_px: float | None = None  # 1 piksel necha metr
    wall_m: float = 0.6            # devor qalinligi (qo'sh chiziqlar orasini to'ldirish)
    door_m: float = 1.8            # eng keng eshik/teshik
    min_room_m2: float = 2.0       # eng kichik xona
    gap_m: float = 1.0             # devor chizig'idagi eng katta uzilish (uziq chiziq, deraza)
    local_contrast: int = 12       # och chiziqlar uchun mahalliy kontrast chegarasi
    line_coverage: float = 0.7     # devor chizig'i bo'ylab siyohning eng kam ulushi
    # Masshtab noma'lum bo'lsa - rasm o'lchamiga nisbatan
    door_gap: float = 0.04         # eshik/teshiklarni yopish (rasm o'lchamiga nisbatan)
    min_room: float = 0.0015       # eng kichik xona maydoni (rasm maydoniga nisbatan)
    detect_blue: bool = True       # ko'k ruchka belgilarini topish
    detect_black: bool = False     # qora qo'lyozma/matnni ham nomzod qilish (ishonchsiz)
    blue_sensitivity: float = 0.5  # 0..1, kattaroq - ko'proq iz topadi
    orthogonal: bool = True        # devorlarni gorizontal/vertikalga tekislash


@dataclass
class DetectedRoom:
    points: list[tuple[float, float]]
    kind: str = "room"


@dataclass
class DetectionResult:
    rooms: list[DetectedRoom] = field(default_factory=list)
    marks: list[tuple[float, float]] = field(default_factory=list)
    wall_thickness: float = 0.0


# ---------------------------------------------------------------- rasm I/O

def read_image(path: str) -> np.ndarray:
    """Windows'dagi kirill/o'zbekcha nomli fayllarni ham o'qiydi."""
    data = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Rasmni o'qib bo'lmadi: {path}")
    return img


def encode_png(img: np.ndarray) -> bytes:
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("PNG kodlashda xato")
    return buf.tobytes()


def encode_jpg(img: np.ndarray, quality: int = 92) -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("JPG kodlashda xato")
    return buf.tobytes()


def decode_image(data: bytes) -> np.ndarray:
    return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)


def limit_size(img: np.ndarray, max_side: int = MAX_STORED_SIZE) -> np.ndarray:
    h, w = img.shape[:2]
    s = max_side / max(h, w)
    if s >= 1:
        return img
    return cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)


# ---------------------------------------------------------------- perspektiva

def order_corners(pts) -> np.ndarray:
    """Burchaklarni tartiblaydi: yuqori-chap, yuqori-o'ng, past-o'ng, past-chap."""
    pts = np.asarray(pts, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)],
                     pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)


def find_paper_corners(img: np.ndarray) -> np.ndarray:
    """Rasmdagi qog'oz varag'ining 4 burchagini taxmin qiladi.

    Topilmasa - rasmning o'z burchaklari qaytariladi (skaner rasmi uchun to'g'ri).
    """
    h, w = img.shape[:2]
    full = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    s = 800 / max(h, w)
    small = cv2.resize(img, (max(1, round(w * s)), max(1, round(h * s)))) if s < 1 else img.copy()
    s = min(s, 1.0)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    # Qog'oz - fondan yorug'roq katta maydon
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return full
    c = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(c)
    sh, sw = small.shape[:2]
    # Qog'oz deyarli butun rasmni egallasa - skaner, burchaklar = rasm burchaklari
    if area < 0.2 * sw * sh or area > 0.97 * sw * sh:
        return full
    peri = cv2.arcLength(c, True)
    for eps in (0.02, 0.03, 0.05, 0.08):
        approx = cv2.approxPolyDP(c, eps * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            return order_corners(approx.reshape(4, 2) / s)
    return full


def warp_to_rect(img: np.ndarray, corners) -> np.ndarray:
    """4 burchak bo'yicha perspektivani to'g'rilaydi."""
    tl, tr, br, bl = order_corners(corners)
    w = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    h = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    w, h = max(w, 10), max(h, 10)
    dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl], dtype=np.float32), dst)
    return cv2.warpPerspective(img, m, (w, h), flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)


# ---------------------------------------------------------------- yordamchilar

def normalize_illumination(gray: np.ndarray) -> np.ndarray:
    """Soyalarni yo'qotadi: rasmni uning xiralashtirilgan foniga bo'ladi."""
    k = max(31, (min(gray.shape) // 12) | 1)
    # Devorlardan qalinroq yadro bilan yopish - devorlar fonga qo'shilmasin
    c = max(15, max(gray.shape) // 40)
    small = cv2.resize(gray, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    bg = cv2.morphologyEx(small, cv2.MORPH_CLOSE, np.ones((c // 4 + 1, c // 4 + 1), np.uint8))
    bg = cv2.resize(bg, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR)
    bg = cv2.GaussianBlur(bg, (k, k), 0)
    norm = cv2.divide(gray, bg, scale=255)
    return norm


def blue_mask(img: np.ndarray, sensitivity: float = 0.5) -> np.ndarray:
    """Ko'k ruchka izlari maskasi."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    b, g, r = cv2.split(img.astype(np.int16))
    min_sat = int(110 - 70 * sensitivity)      # 40..110
    hue_ok = (h >= 95) & (h <= 135)
    sat_ok = s >= min_sat
    val_ok = (v >= 30) & (v <= 245)
    dominance = (b - np.maximum(r, g)) >= int(30 - 20 * sensitivity)
    mask = (hue_ok & sat_ok & val_ok & dominance).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return mask


def cluster_blobs(mask: np.ndarray, join: int, min_area: int, max_area: int):
    """Yaqin izlarni (masalan "K.x." harflari) bitta belgiga birlashtiradi."""
    joined = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (join, join)))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    ys, xs = np.nonzero(mask)
    lab = labels[ys, xs]
    ink = np.bincount(lab, minlength=n)
    sx = np.bincount(lab, weights=xs, minlength=n)
    sy = np.bincount(lab, weights=ys, minlength=n)
    out = []
    for i in range(1, n):
        if ink[i] < min_area or stats[i, cv2.CC_STAT_AREA] > max_area:
            continue
        out.append((float(sx[i] / ink[i]), float(sy[i] / ink[i])))
    return out


def orthogonalize(poly: np.ndarray, tol_deg: float = 12.0) -> list[tuple[float, float]]:
    """Deyarli gorizontal/vertikal qirralarni aniq gorizontal/vertikal qiladi."""
    pts = [tuple(map(float, p)) for p in poly]
    n = len(pts)
    if n < 3:
        return pts
    tol = np.tan(np.radians(tol_deg))
    kinds = []  # har qirra uchun: ('h', y) / ('v', x) / ('o', None)
    for i in range(n):
        (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % n]
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        if dy <= dx * tol:
            kinds.append(("h", (y0 + y1) / 2))
        elif dx <= dy * tol:
            kinds.append(("v", (x0 + x1) / 2))
        else:
            kinds.append(("o", None))
    new = []
    for i in range(n):
        prev_k, prev_v = kinds[i - 1]
        next_k, next_v = kinds[i]
        x, y = pts[i]
        for k, v in ((prev_k, prev_v), (next_k, next_v)):
            if k == "h":
                y = v
            elif k == "v":
                x = v
        new.append((x, y))
    return simplify_collinear(new)


def simplify_collinear(pts, eps: float = 1.0):
    """Takrorlangan va bir chiziqda yotgan nuqtalarni olib tashlaydi."""
    changed = True
    pts = list(pts)
    while changed and len(pts) > 3:
        changed = False
        for i in range(len(pts)):
            a, b, c = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
            if abs(a[0] - b[0]) < eps and abs(a[1] - b[1]) < eps:
                pts.pop(i)
                changed = True
                break
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            ab = np.hypot(b[0] - a[0], b[1] - a[1]) + 1e-9
            if abs(cross) / ab < eps:
                pts.pop(i)
                changed = True
                break
    return pts


def straight_walls(mask: np.ndarray, mpp: float, gap_m: float, min_coverage: float = 0.6) -> np.ndarray:
    """Devor chiziqlarini Hough usuli bilan topadi va qayta chizadi.

    - qiyshiqlikka chidamli (telefon rasmi, ±12°);
    - uziq-uziq chiziqni va deraza/eshik bo'shliqlarini (gap_m gacha) bitta chiziqqa ulaydi;
    - egri eshik yoylari, matn va qo'lyozma (1 m dan qisqa) tushib qoladi.
    """
    lines = cv2.HoughLinesP(mask, 1, np.pi / 360, threshold=max(10, int(0.6 / mpp)),
                            minLineLength=max(10, int(1.0 / mpp)), maxLineGap=max(3, int(gap_m / mpp)))
    out = np.zeros_like(mask)
    if lines is None:
        return out
    tol = np.tan(np.radians(12))
    th = max(2, int(round(0.06 / mpp)))
    h, w = mask.shape
    for x0, y0, x1, y1 in lines.reshape(-1, 4):
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        if not (dy <= dx * tol or dx <= dy * tol):
            continue
        # chiziq bo'ylab siyoh ulushi: devor (hatto uziq) - ko'p, yozuvlar orqali "ulangan" soxta chiziq - kam
        n = int(max(dx, dy)) + 1
        xs = np.clip(np.linspace(x0, x1, n).round().astype(int), 0, w - 1)
        ys = np.clip(np.linspace(y0, y1, n).round().astype(int), 0, h - 1)
        if (mask[ys, xs] > 0).mean() < min_coverage:
            continue
        cv2.line(out, (int(x0), int(y0)), (int(x1), int(y1)), 255, th)
    return out


def merge_wide_contacts(labels: np.ndarray, n: int, outside: np.ndarray, door_px: float) -> np.ndarray:
    """Keng tutashgan qo'shni bo'laklarni birlashtiradi.

    Xona va koridor eshik (tor bo'g'iz) orqali tutashadi. Koridorning bo'laklari esa deyarli
    butun eni bo'yicha tutashadi - ular bitta maydon.
    """
    pairs = []
    for a, b in ((labels[:, 1:], labels[:, :-1]), (labels[1:, :], labels[:-1, :])):
        m = (a != b) & (a > 0) & (b > 0)
        pairs.append(np.stack([np.minimum(a[m], b[m]), np.maximum(a[m], b[m])], axis=1))
    pairs = np.concatenate(pairs)
    if not len(pairs):
        return labels
    keys, contact = np.unique(pairs[:, 0].astype(np.int64) * n + pairs[:, 1], return_counts=True)
    # har bo'lakning eni (eng kichik to'rtburchak qisqa tomoni)
    width = np.zeros(n)
    ys, xs = np.nonzero(labels)
    lab = labels[ys, xs]
    order = np.argsort(lab, kind="stable")
    lab, xs, ys = lab[order], xs[order], ys[order]
    bounds = np.flatnonzero(np.diff(lab)) + 1
    for gx, gy, gl in zip(np.split(xs, bounds), np.split(ys, bounds), np.split(lab, bounds)):
        if len(gx) < 5:
            continue
        (_, _), (rw, rh), _ = cv2.minAreaRect(np.column_stack([gx, gy]).astype(np.float32))
        width[gl[0]] = min(rw, rh)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for key, c in zip(keys, contact):
        a, b = int(key // n), int(key % n)
        if outside[a] or outside[b]:
            continue
        if c >= door_px * 1.05 and c >= 0.7 * min(width[a], width[b]):
            parent[find(a)] = find(b)
    lut = np.array([find(i) for i in range(n)], np.int32)
    return lut[labels]


# ---------------------------------------------------------------- asosiy tahlil

def detect(img: np.ndarray, params: DetectParams | None = None) -> DetectionResult:
    """Rasmdan xonalar va AT belgilari nomzodlarini topadi.

    `img` - perspektivasi to'g'rilangan rasm. Natija koordinatalari shu rasm piksellarida.
    """
    p = params or DetectParams()
    H, W = img.shape[:2]
    scale = min(1.0, WORK_SIZE / max(H, W))
    work = cv2.resize(img, (round(W * scale), round(H * scale)), interpolation=cv2.INTER_AREA) \
        if scale < 1 else img.copy()
    h, w = work.shape[:2]
    big = max(h, w)
    result = DetectionResult()

    # --- ko'k ruchka
    bmask = blue_mask(work, p.blue_sensitivity)
    if p.detect_blue:
        join = max(5, int(big * 0.012)) | 1
        marks = cluster_blobs(bmask, join, min_area=max(6, int(big * 0.004)),
                              max_area=int(h * w * 0.01))
        result.marks.extend(marks)

    # --- qora chiziqlar (ko'k izlar olib tashlanadi)
    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    gray[cv2.dilate(bmask, np.ones((3, 3), np.uint8)) > 0] = 255
    norm = normalize_illumination(gray)
    thr, _ = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    dark = (norm < min(thr, 200)).astype(np.uint8) * 255

    # O'lchamlar piksellarda
    if p.m_per_px:
        mpp = p.m_per_px / scale
        wall_px = p.wall_m / mpp
        door_px = p.door_m / mpp
        text_limit = 1.4 / mpp
        min_area = p.min_room_m2 / mpp ** 2
    else:
        mpp = None
        wall_px = big * 0.006
        door_px = big * p.door_gap
        text_limit = big * 0.03
        min_area = h * w * p.min_room

    # Skanerda 1 pikselli chiziqlar uziq-uziq bo'ladi - avval ularni ulaymiz
    if p.m_per_px:
        # telefon rasmining oqargan joylarida chiziqlar och - mahalliy fondan qoraroq bo'lsa yetarli
        block = max(15, int(0.5 / mpp)) | 1
        local = cv2.adaptiveThreshold(norm, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV,
                                      block, p.local_contrast)
        local = cv2.morphologyEx(local, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        dark = cv2.bitwise_or(dark, local)
        dark = cv2.dilate(dark, np.ones((3, 3), np.uint8))

    # Kichik bo'laklar (matn, raqamlar, qo'lyozma, ustunlar) - devor emas
    n, labels, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
    long_side = np.maximum(stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT])
    short_side = np.minimum(stats[:, cv2.CC_STAT_WIDTH], stats[:, cv2.CC_STAT_HEIGHT])
    is_text = long_side < text_limit
    if p.m_per_px:
        # telefon rasmida devor chizig'i uziq-uziq bo'lakka bo'linadi - cho'ziq bo'lak matn emas
        is_text &= ~((long_side >= 4 * short_side) & (long_side >= 0.5 / mpp))
    is_text[0] = False
    is_wall = ~is_text
    is_wall[0] = False
    text = (is_text[labels] * 255).astype(np.uint8)
    walls = (is_wall[labels] * 255).astype(np.uint8)

    if p.detect_black:
        join = max(5, int(big * 0.01)) | 1
        result.marks.extend(cluster_blobs(text, join, min_area=max(8, int(big * 0.005)),
                                          max_area=int(h * w * 0.004)))

    # Faqat to'g'ri (gorizontal/vertikal) chiziqlar - devorlar. Egri eshik yoylari va
    # qiya shtrixlar tushib qoladi, aks holda ular koridorni bo'laklab yuboradi.
    if p.m_per_px:
        # matn filtridan oldingi to'liq maska: uziq-uziq chiziq bo'laklari ham kirsin
        walls = straight_walls(dark, mpp, p.gap_m, p.line_coverage)

    # Qo'sh ingichka chiziqli devorlarni yaxlit devorga aylantirish
    k = max(3, int(round(wall_px)))
    walls = cv2.morphologyEx(walls, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))

    # Devor qalinligini baholash
    dist = cv2.distanceTransform(walls, cv2.DIST_L2, 3)
    vals = dist[dist > 0]
    thick = float(2 * np.percentile(vals, 90)) if vals.size else 3.0
    thick = float(np.clip(thick, 2, max(wall_px * 1.5, 3)))
    result.wall_thickness = thick / scale

    # Xonalarni eshiklar (tor bo'g'izlar) bo'yicha ajratish:
    # bo'sh joyning eshikdan kengroq qismlari - xona "urug'lari", keyin ular devorgacha o'stiriladi.
    free = cv2.bitwise_not(cv2.dilate(walls, np.ones((3, 3), np.uint8)))
    free[0, :] = free[-1, :] = 0
    free[:, 0] = free[:, -1] = 0
    fdist = cv2.distanceTransform(free, cv2.DIST_L2, 5)
    r = max(2.0, door_px / 2)
    n, seeds, sstats, _ = cv2.connectedComponentsWithStats((fdist > r).astype(np.uint8), connectivity=4)
    # tashqi maydon: rasm chetiga yaqin urug'
    edge = 2 * r + 3
    outside = np.zeros(n, bool)
    for i in range(1, n):
        x, y, bw, bh, _ = sstats[i]
        if x <= edge or y <= edge or x + bw >= w - edge or y + bh >= h - edge \
                or (bw > 0.85 * w and bh > 0.85 * h):
            outside[i] = True
    labels = seeds.astype(np.float32)
    free_mask = free > 0
    kernel = np.ones((3, 3), np.uint8)
    for _ in range(int(r * 1.6) + 4):
        grown = cv2.dilate(labels, kernel)
        upd = (labels == 0) & free_mask & (grown > 0)
        if not upd.any():
            break
        labels[upd] = grown[upd]
    labels = labels.astype(np.int32)
    labels = merge_wide_contacts(labels, n, outside, door_px)
    stats = np.zeros((n, 5), np.int64)
    ys, xs = np.nonzero(labels)
    lab = labels[ys, xs]
    cnt = np.bincount(lab, minlength=n)
    for i in range(1, n):
        stats[i, 4] = cnt[i]
    mins_x = np.full(n, w); maxs_x = np.zeros(n, int); mins_y = np.full(n, h); maxs_y = np.zeros(n, int)
    np.minimum.at(mins_x, lab, xs); np.maximum.at(maxs_x, lab, xs)
    np.minimum.at(mins_y, lab, ys); np.maximum.at(maxs_y, lab, ys)

    min_radius = max(thick * 0.9, 0.5 / mpp) if mpp else max(thick * 1.5, big * 0.006)
    grow = max(1, int(round(thick / 2 + 1)))
    grow_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2 * grow + 1, 2 * grow + 1))
    rooms: list[DetectedRoom] = []
    for i in range(1, n):
        if outside[i] or stats[i, 4] < min_area:
            continue
        x, y = int(mins_x[i]), int(mins_y[i])
        bw, bh = int(maxs_x[i]) - x + 1, int(maxs_y[i]) - y + 1
        comp = np.zeros((bh + 2 * grow + 2, bw + 2 * grow + 2), np.uint8)
        ox, oy = x - grow - 1, y - grow - 1
        comp[grow + 1:grow + 1 + bh, grow + 1:grow + 1 + bw][labels[y:y + bh, x:x + bw] == i] = 255
        if cv2.distanceTransform(comp, cv2.DIST_L2, 3).max() < min_radius:
            continue  # tor bo'shliq (devor chiziqlari orasi)
        # eshik bo'g'izidan qolgan do'mboqlarni silliqlash
        o = max(3, int(r)) | 1
        comp = cv2.morphologyEx(comp, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (o, o)))
        comp = cv2.dilate(comp, grow_kernel)  # devorning o'rtasigacha kengaytirish
        contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        c = max(contours, key=cv2.contourArea)
        hull_area = cv2.contourArea(cv2.convexHull(c))
        solidity = cv2.contourArea(c) / hull_area if hull_area else 1
        approx = cv2.approxPolyDP(c, max(2.0, thick * 0.6), True).reshape(-1, 2).astype(np.float64)
        approx += (ox, oy)
        pts = orthogonalize(approx) if p.orthogonal else [tuple(map(float, q)) for q in approx]
        if len(pts) < 3:
            continue
        (_, _), (rw, rh), _ = cv2.minAreaRect(c)
        aspect = max(rw, rh) / max(1.0, min(rw, rh))
        kind = "corridor" if aspect >= 3.2 or solidity < 0.6 else "room"
        pts = [(px / scale, py / scale) for px, py in pts]
        rooms.append(DetectedRoom(points=pts, kind=kind))

    # Yuqoridan pastga, chapdan o'ngga tartiblash (raqamlash uchun)
    rooms.sort(key=lambda r: (round(min(q[1] for q in r.points) / (big / scale * 0.05)),
                              min(q[0] for q in r.points)))
    result.rooms = rooms
    result.marks = [(mx / scale, my / scale) for mx, my in result.marks]
    return result
