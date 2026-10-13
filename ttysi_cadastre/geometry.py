"""Xonalar ustida geometrik amallar: bo'lish va birlashtirish."""

from __future__ import annotations

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
