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


def stair_lines(points, step: float) -> list[list[tuple[float, float]]]:
    """Zina pog'onalari (xonaning uzun tomoni bo'ylab) va yo'nalish strelkasi."""
    poly = Polygon(points).buffer(0)
    if poly.is_empty or step <= 0:
        return []
    x0, y0, x1, y1 = poly.bounds
    horizontal = (x1 - x0) >= (y1 - y0)   # pog'onalar uzun tomonga tik
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
    # strelka: markaz chizig'i bo'ylab
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if horizontal:
        a, b = (x0 + step, cy), (x1 - step, cy)
        head = [(b[0] - step, cy - step * 0.6), b, (b[0] - step, cy + step * 0.6)]
    else:
        a, b = (cx, y1 - step), (cx, y0 + step)
        head = [(cx - step * 0.6, b[1] + step), b, (cx + step * 0.6, b[1] + step)]
    out += [[a, b], head]
    return out


def nearest_wall(rooms, x: float, y: float):
    """Nuqtaga eng yaqin devor (xona qirrasi): (nuqta x, nuqta y, burchak gradusda, masofa)."""
    best = None
    for room in rooms:
        pts = room.points
        for i in range(len(pts)):
            (ax, ay), (bx, by) = pts[i], pts[(i + 1) % len(pts)]
            dx, dy = bx - ax, by - ay
            L2 = dx * dx + dy * dy
            if L2 < 1e-9:
                continue
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
            px, py = ax + t * dx, ay + t * dy
            d = math.hypot(x - px, y - py)
            if best is None or d < best[3]:
                best = (px, py, math.degrees(math.atan2(dy, dx)), d)
    return best
