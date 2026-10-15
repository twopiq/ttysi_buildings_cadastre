"""Etaj chizmasi brauzer uchun (Qt'siz): sayt (web/) shu ma'lumotdan SVG chizadi.

Geometriya (eshik yoylari, zina pog'onalari, gumbaz halqasi, devor qalinligi) muharrir va eksport bilan
bir xil funksiyalardan hisoblanadi - sayt va dastur chizmasi bir-biridan farq qilmaydi.
"""

from __future__ import annotations

from .equipment import EQUIPMENT_TYPES, ROOM_KINDS, UNKNOWN, get_type
from .geometry import door_cut, door_lines, stair_lines
from .metrics import (door_wall_thickness, dome_ring, equipment_counts, label_px, meter_px, room_label,
                      symbol_radius, wall_width)
from .model import Building, Floor


def _r(v: float) -> float:
    return round(float(v), 2)


def _pts(pts) -> list[list[float]]:
    return [[_r(x), _r(y)] for x, y in pts]


def equipment_types() -> list[dict]:
    return [{"code": t.code, "label": t.label, "name": t.name, "color": t.color, "key": t.key,
             "square": t.code in ("SER", "KX")} for t in EQUIPMENT_TYPES + [UNKNOWN]]


def room_kinds() -> list[dict]:
    return [{"kind": k, "name": v[0], "fill": v[1]} for k, v in ROOM_KINDS.items()]


def floor_scene(floor: Floor) -> dict:
    """Etajning chiziladigan barcha elementlari (etaj piksellarida)."""
    ww = wall_width(floor)
    rooms = []
    for r in floor.rooms:
        cx, cy = r.centroid()
        item = {"id": r.id, "kind": r.kind, "name": r.name, "points": _pts(r.points),
                "fill": ROOM_KINDS.get(r.kind, ROOM_KINDS["room"])[1], "label": room_label(r, floor),
                "cx": _r(cx), "cy": _r(cy),
                "area_m2": round(r.area() * floor.scale_m_per_px ** 2, 1) if floor.scale_m_per_px else None}
        if r.kind == "stairs":
            item["stairs"] = [_pts(ln) for ln in stair_lines(r.points, meter_px(floor) * 0.3, r.direction)]
        if r.shape == "ellipse" or r.kind == "dome":
            item["ring"] = _pts(dome_ring(r, floor))
        rooms.append(item)
    doors = []
    for d in floor.doors:
        t = door_wall_thickness(floor, d)
        doors.append({"id": d.id, "cut": _pts(door_cut(d, t)), "lines": [_pts(ln) for ln in door_lines(d, t)],
                      "stroke": _r(max(1.0, t * 0.22))})
    eq = []
    for e in floor.equipment:
        room = floor.room_of(e)
        eq.append({"id": e.id, "code": e.code, "x": _r(e.x), "y": _r(e.y), "note": e.note, "status": e.status,
                   "room": room.name if room else ""})
    return {
        "id": floor.id, "name": floor.name, "width": floor.width, "height": floor.height,
        "has_image": bool(floor.image or floor.image_ref),
        "bg": {"dx": floor.bg_dx, "dy": floor.bg_dy, "scale": floor.bg_scale, "rot": floor.bg_rot},
        "scale_m_per_px": floor.scale_m_per_px, "ratio": floor.ratio,
        "wall_width": _r(ww), "symbol_r": _r(symbol_radius(floor)), "label_px": label_px(floor),
        "meter_px": _r(meter_px(floor)),
        "rooms": rooms,
        "walls": [{"id": w.id, "points": _pts(w.points), "thickness": _r(w.thickness)} for w in floor.walls],
        "doors": doors,
        "equipment": eq,
        "counts": equipment_counts(floor), "planned": equipment_counts(floor, planned=True),
        "unknown": sum(1 for e in floor.equipment if e.code == "?"),
    }


def building_json(building: Building) -> dict:
    return {"name": building.name, "address": building.address,
            "floors": [floor_scene(f) for f in building.floors]}


def valid_code(code: str) -> bool:
    return get_type(code).code == code
