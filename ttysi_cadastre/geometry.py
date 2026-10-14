"""Xonalar ustida geometrik amallar: bo'lish va birlashtirish."""

from __future__ import annotations

import math

from shapely.geometry import LineString, Polygon
from shapely.ops import split, unary_union


def _clean(poly: Polygon) -> list[tuple[float, float]]:
    poly = poly.simplify(0.5)
    return [(float(x), float(y)) for x, y in list(poly.exterior.coords)[:-1]]


def split_room(points, a, b) -> list[list[tuple[float, float]]]:
    """Xonani a-b chizig'i bo'yicha ikki (yoki ko'proq) qismga bo'ladi.

    Chiziq xonani kesib o'tmasa - bo'sh ro'yxat qaytariladi.
    """
    poly = Polygon(points).buffer(0)
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    # chiziqni har ikki tomonga uzaytirish - foydalanuvchi devorgacha aniq yetkazmasa ham ishlasin
    k = 10000.0 / max(1e-9, (dx * dx + dy * dy) ** 0.5)
    line = LineString([(ax - dx * k, ay - dy * k), (bx + dx * k, by + dy * k)])
    parts = [g for g in split(poly, line).geoms if g.area > 1]
    if len(parts) < 2:
        return []
    return [_clean(g) for g in parts]


def merge_rooms(rooms_points: list, tolerance: float) -> list[tuple[float, float]] | None:
    """Bir-biriga tegib turgan xonalarni bitta xonaga birlashtiradi.

    `tolerance` - xonalar orasidagi ruxsat etilgan bo'shliq (devor qalinligi).
    """
    polys = [Polygon(p).buffer(0) for p in rooms_points]
    u = unary_union([p.buffer(tolerance, join_style="mitre") for p in polys])
    if u.geom_type != "Polygon":
        return None
    u = u.buffer(-tolerance, join_style="mitre")
    if u.geom_type != "Polygon" or u.is_empty:
        return None
    return _clean(Polygon(u.exterior))


# ---------------------------------------------------------------- eshik va zina shakllari

def _to_floor(door, pts):
    """Eshikning mahalliy koordinatalari (x - devor bo'ylab, y - devorga tik) -> etaj koordinatalari."""
    a = math.radians(door.angle)
    ca, sa = math.cos(a), math.sin(a)
    return [(door.x + x * ca - y * sa, door.y + x * sa + y * ca) for x, y in pts]


def door_cut(door, wall: float) -> list[tuple[float, float]]:
    """Devordagi eshik o'rni (oq to'rtburchak)."""
    w, t = door.width / 2, wall * 0.5 + 0.5   # faqat devor qalinligi, xona foni kesilmaydi
    return _to_floor(door, [(-w, -t), (w, -t), (w, t), (-w, t)])


def door_lines(door, wall: float) -> list[list[tuple[float, float]]]:
    """Eshik chiziqlari: kesak (jamb) belgilari, tabaqalar va ochilish yoylari."""
    w = door.width
    s = -1.0 if door.flip else 1.0
    t = wall / 2
    lines = [[(-w / 2, -t), (-w / 2, t)], [(w / 2, -t), (w / 2, t)]]
    if door.leaves == 2:
        leaves = [(-w / 2, 1.0, w / 2), (w / 2, -1.0, w / 2)]
    else:
        leaves = [(w / 2, -1.0, w) if door.mirror else (-w / 2, 1.0, w)]
    for hx, d, L in leaves:
        lines.append([(hx, s * t), (hx, s * (t + L))])               # ochiq tabaqa
        arc = [(hx + d * L * math.cos(math.radians(k)), s * (t + L * math.sin(math.radians(k))))
               for k in range(0, 91, 10)]
        lines.append(arc)                                            # ochilish yoyi
    return [_to_floor(door, ln) for ln in lines]


def _orientation(poly: Polygon) -> float:
    """Ko'pburchakning asosiy yo'nalishi (gradus): eng kichik buriluvchan to'rtburchakning tomoni."""
    rect = list(poly.minimum_rotated_rectangle.exterior.coords)
    (x0, y0), (x1, y1) = rect[0], rect[1]
    a = math.degrees(math.atan2(y1 - y0, x1 - x0))
    return ((a + 45) % 90) - 45   # -45..45 oralig'iga: 0 - to'g'ri turgan zina


STAIR_DIRECTIONS = ("right", "down", "left", "up")   # soat strelkasi bo'yicha


def auto_stair_direction(points) -> str:
    """Avtomatik yo'nalish: uzun tomon bo'ylab (gorizontal - o'ngga, vertikal - yuqoriga)."""
    poly = Polygon(points).buffer(0)
    if poly.is_empty:
        return "right"
    a = _orientation(poly)
    c = poly.centroid
    pts = rotate_points(list(poly.exterior.coords)[:-1], -a, (c.x, c.y)) if abs(a) > 0.5 \
        else list(poly.exterior.coords)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return "right" if (max(xs) - min(xs)) >= (max(ys) - min(ys)) else "up"


def stair_lines(points, step: float, direction: str = "") -> list[list[tuple[float, float]]]:
    """Zina pog'onalari va ko'tarilish yo'nalishi strelkasi; burilgan zinada ham.

    direction: "" - avtomatik (uzun tomon bo'ylab), yoki right/left/down/up (zinaning o'z o'qlarida).
    """
    poly = Polygon(points).buffer(0)
    if poly.is_empty or step <= 0:
        return []
    a = _orientation(poly)
    if abs(a) > 0.5:
        # burilgan zina: to'g'rilab hisoblaymiz va natijani qayta buramiz
        c = poly.centroid
        straight = rotate_points(list(poly.exterior.coords)[:-1], -a, (c.x, c.y))
        return [rotate_points(ln, a, (c.x, c.y)) for ln in _stair_lines_axis(Polygon(straight), step, direction)]
    return _stair_lines_axis(poly, step, direction)


def _stair_lines_axis(poly: Polygon, step: float, direction: str = "") -> list[list[tuple[float, float]]]:
    x0, y0, x1, y1 = poly.bounds
    if direction not in STAIR_DIRECTIONS:
        direction = "right" if (x1 - x0) >= (y1 - y0) else "up"
    horizontal = direction in ("right", "left")   # pog'onalar yurish yo'nalishiga tik
    out = []
    n = int(((x1 - x0) if horizontal else (y1 - y0)) / step)
    for i in range(1, n + 1):
        if horizontal:
            seg = LineString([(x0 + i * step, y0 - 1), (x0 + i * step, y1 + 1)])
        else:
            seg = LineString([(x0 - 1, y0 + i * step), (x1 + 1, y0 + i * step)])
        cut = seg.intersection(poly)
        for g in getattr(cut, "geoms", [cut]):
            if g.geom_type == "LineString" and g.length > 1:
                out.append([(float(x), float(y)) for x, y in g.coords])
    # strelka: markaz chizig'i bo'ylab, ko'tarilish tomoniga
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    k = step * 0.6
    if direction == "right":
        a, b = (x0 + step, cy), (x1 - step, cy)
        head = [(b[0] - step, cy - k), b, (b[0] - step, cy + k)]
    elif direction == "left":
        a, b = (x1 - step, cy), (x0 + step, cy)
        head = [(b[0] + step, cy - k), b, (b[0] + step, cy + k)]
    elif direction == "down":
        a, b = (cx, y0 + step), (cx, y1 - step)
        head = [(cx - k, b[1] - step), b, (cx + k, b[1] - step)]
    else:   # up
        a, b = (cx, y1 - step), (cx, y0 + step)
        head = [(cx - k, b[1] + step), b, (cx + k, b[1] + step)]
    out += [[a, b], head]
    return out


def wall_segments(rooms, walls=()):
    """Barcha devor kesmalari: xona qirralari (yopiq) va mustaqil devorlar (ochiq siniq chiziq)."""
    for room in rooms:
        pts = room.points
        for i in range(len(pts)):
            yield pts[i], pts[(i + 1) % len(pts)], None
    for w in walls:
        for a, b in zip(w.points, w.points[1:]):
            yield a, b, w


def nearest_wall(rooms, x: float, y: float, walls=()):
    """Nuqtaga eng yaqin devor: (nuqta x, nuqta y, burchak gradusda, masofa, mustaqil devor yoki None)."""
    best = None
    for (ax, ay), (bx, by), owner in wall_segments(rooms, walls):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        if L2 < 1e-9:
            continue
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
        px, py = ax + t * dx, ay + t * dy
        d = math.hypot(x - px, y - py)
        if best is None or d < best[3]:
            best = (px, py, math.degrees(math.atan2(dy, dx)), d, owner)
    return best


# ---------------------------------------------------------------- kadastr fonini moslash

def bg_map(floor, x: float, y: float) -> tuple[float, float]:
    """Fon rasmidagi nuqta (etaj kengligiga keltirilgan rasm piksellarida) -> chizma koordinatasi.

    Fon etaj markazi atrofida bg_scale marta kattalashtiriladi, bg_rot gradusga buriladi va
    (bg_dx, bg_dy) ga suriladi.
    """
    cx, cy = floor.width / 2, floor.height / 2
    a = math.radians(floor.bg_rot)
    s = floor.bg_scale
    dx, dy = x - cx, y - cy
    return (cx + s * (dx * math.cos(a) - dy * math.sin(a)) + floor.bg_dx,
            cy + s * (dx * math.sin(a) + dy * math.cos(a)) + floor.bg_dy)


def bg_compose(floor, scale: float, angle: float, tx: float, ty: float) -> None:
    """Fonga qo'shimcha o'xshashlik o'zgarishi qo'llaydi: p -> scale*R(angle)*p + (tx, ty) (chizma
    koordinatalarida). Natija yana (siljish, masshtab, burilish) parametrlariga yoziladi."""
    cx, cy = floor.width / 2, floor.height / 2
    mx, my = bg_map(floor, cx, cy)                       # fon markazining hozirgi joyi
    a = math.radians(angle)
    nx = scale * (mx * math.cos(a) - my * math.sin(a)) + tx
    ny = scale * (mx * math.sin(a) + my * math.cos(a)) + ty
    floor.bg_scale *= scale
    floor.bg_rot = ((floor.bg_rot + angle + 180) % 360) - 180
    floor.bg_dx, floor.bg_dy = nx - cx, ny - cy


def similarity_from_pairs(p1, q1, p2, q2) -> tuple[float, float, float, float]:
    """Ikki juft nuqta (p -> q) bo'yicha o'xshashlik: (masshtab, burchak gradusda, tx, ty)."""
    vx, vy = p2[0] - p1[0], p2[1] - p1[1]
    wx, wy = q2[0] - q1[0], q2[1] - q1[1]
    lp, lq = math.hypot(vx, vy), math.hypot(wx, wy)
    if lp < 1e-9 or lq < 1e-9:
        raise ValueError("Nuqtalar bir-biriga juda yaqin")
    s = lq / lp
    ang = math.degrees(math.atan2(wy, wx) - math.atan2(vy, vx))
    a = math.radians(ang)
    tx = q1[0] - s * (p1[0] * math.cos(a) - p1[1] * math.sin(a))
    ty = q1[1] - s * (p1[0] * math.sin(a) + p1[1] * math.cos(a))
    return s, ang, tx, ty


def rotate_points(points, angle: float, center=None) -> list[tuple[float, float]]:
    """Nuqtalarni markaz atrofida aylantiradi (gradus; ekranda musbat - soat yo'nalishida).

    Markaz berilmasa - ko'pburchakning og'irlik markazi (element joyida aylanadi).
    """
    if center is None:
        c = Polygon(points).centroid
        center = (c.x, c.y)
    cx, cy = center
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)
    out = []
    for x, y in points:
        dx, dy = x - cx, y - cy
        # 90° karrali burilishlarda kasr shovqinini yo'qotish (devorlar aniq tik qolsin)
        out.append((round(cx + dx * ca - dy * sa, 6), round(cy + dx * sa + dy * ca, 6)))
    return out
