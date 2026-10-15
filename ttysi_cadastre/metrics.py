"""Chizma o'lchovlari va belgilar (Qt'siz): muharrir, eksport va sayt bir xil qiymatlardan foydalanadi."""

from __future__ import annotations

from .equipment import ROOM_KINDS
from .geometry import nearest_wall
from .model import Floor


def meter_px(floor: Floor) -> float:
    """Chizmadagi taxminiy "1 metr" piksellarda (masshtab bo'lmasa - rasm o'lchamidan)."""
    if floor.scale_m_per_px:
        return 1.0 / floor.scale_m_per_px
    return (floor.width * floor.height) ** 0.5 / 40


def wall_width(floor: Floor) -> float:
    """Xona devorlarining qalinligi piksellarda (etaj sozlamasi, standart 0.30 m)."""
    return meter_px(floor) * (floor.wall_m or 0.30)


def label_px(floor: Floor) -> int:
    return max(1, int(meter_px(floor) * 0.6))


def symbol_radius(floor: Floor) -> float:
    return meter_px(floor) * 0.55 * (getattr(floor, "symbol_scale", 1.0) or 1.0)


def door_wall_thickness(floor: Floor, door) -> float:
    """Eshik turgan devor qalinligi: mustaqil devorda - o'sha devorniki, aks holda xona devori."""
    ww = wall_width(floor)
    snap = nearest_wall(floor.rooms, door.x, door.y, floor.walls)
    if snap and snap[4] is not None and snap[3] < 1.0:
        return max(ww, snap[4].thickness)
    return ww


def dome_ring(room, floor: Floor) -> list[tuple[float, float]]:
    """Gumbaz belgisi: xona ichidagi punktir halqa (devordan ~0.6 m ichkarida)."""
    cx, cy = room.centroid()
    rad = max(1.0, sum(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 for x, y in room.points) / len(room.points))
    k = max(0.5, 1 - meter_px(floor) * 0.6 / rad)
    return [(cx + (x - cx) * k, cy + (y - cy) * k) for x, y in room.points]


def room_label(room, floor: Floor) -> str:
    parts = []
    if room.name:
        parts.append(room.name)
    elif room.kind != "room":
        parts.append(ROOM_KINDS[room.kind][0])
    if floor.scale_m_per_px:
        parts.append(f"{room.area() * floor.scale_m_per_px ** 2:.1f} m²")
    return "\n".join(parts)


def equipment_counts(floor: Floor, planned: bool = False) -> dict[str, int]:
    """Jihozlar soni turlar bo'yicha (planned=True - faqat rejadagilar, aks holda mavjudlar)."""
    counts: dict[str, int] = {}
    for e in floor.equipment:
        if e.planned == planned:
            counts[e.code] = counts.get(e.code, 0) + 1
    return counts


