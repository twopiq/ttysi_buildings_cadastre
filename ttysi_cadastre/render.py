"""Etaj chizmasini QPainter bilan chizish (eksport uchun: PNG/JPG, SVG, PDF)."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPolygonF

from .equipment import EQUIPMENT_TYPES, ROOM_KINDS, UNKNOWN, get_type
from .geometry import door_cut, door_lines, nearest_wall, stair_lines
from .model import Building, Floor


@dataclass
class RenderOptions:
    background: bool = False   # kadastr rasmini fon sifatida qo'shish
    room_names: bool = True
    legend: bool = True
    title: bool = True
    planned: bool = True       # "kerak" (rejadagi) jihozlarni ham chizish


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


def draw_equipment_symbol(p: QPainter, code: str, center: QPointF, r: float, planned: bool = False) -> None:
    """AT jihozi belgisi: rangli doira (xonalar uchun - kvadrat) ichida qisqa belgi.

    Rejadagi (kerak) jihoz - oq fon, rangli punktir chegara va rangli yozuv.
    """
    t = get_type(code)
    color = QColor(t.color)
    if planned:
        pen = QPen(color, r * 0.2, Qt.DashLine)
        p.setPen(pen)
        p.setBrush(QBrush(QColor("white")))
    else:
        p.setPen(QPen(color.darker(140), r * 0.14))
        p.setBrush(QBrush(color))
    if code in ("SER", "KX"):
        p.drawRect(QRectF(center.x() - r, center.y() - r, 2 * r, 2 * r))
    else:
        p.drawEllipse(center, r, r)
    f = QFont("Arial")
    f.setBold(True)
    f.setPixelSize(max(1, int(r * (0.95 if len(t.label) <= 2 else 0.7))))
    p.setFont(f)
    p.setPen(color.darker(120) if planned else QColor("white"))
    p.drawText(QRectF(center.x() - r, center.y() - r, 2 * r, 2 * r), Qt.AlignCenter, t.label)


def draw_door(p: QPainter, door, wall: float, cut_color: QColor | None = None) -> None:
    """Eshik: devorda oq o'rin, kesak belgilari, ochiq tabaqa va ochilish yoyi."""
    p.setPen(Qt.NoPen)
    p.setBrush(cut_color or QColor("white"))
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in door_cut(door, wall)]))
    pen = QPen(QColor("#212121"), max(1.0, wall * 0.22))
    pen.setCapStyle(Qt.FlatCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    for ln in door_lines(door, wall):
        p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in ln]))


def draw_wall(p: QPainter, wall, color: QColor | None = None) -> None:
    pen = QPen(color or QColor("#212121"), wall.thickness)
    pen.setJoinStyle(Qt.MiterJoin)
    pen.setCapStyle(Qt.SquareCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in wall.points]))


def draw_walls(p: QPainter, floor: Floor) -> None:
    for wall in floor.walls:
        draw_wall(p, wall)


def door_wall_thickness(floor: Floor, door) -> float:
    """Eshik turgan devor qalinligi: mustaqil devorda - o'sha devorniki, aks holda xona devori."""
    ww = wall_width(floor)
    snap = nearest_wall(floor.rooms, door.x, door.y, floor.walls)
    if snap and snap[4] is not None and snap[3] < 1.0:
        return max(ww, snap[4].thickness)
    return ww


def draw_stairs(p: QPainter, room, floor: Floor) -> None:
    """Zina: pog'onalar (0.3 m) va yo'nalish strelkasi."""
    p.setPen(QPen(QColor("#616161"), max(1.0, wall_width(floor) * 0.18)))
    p.setBrush(Qt.NoBrush)
    for ln in stair_lines(room.points, meter_px(floor) * 0.3, room.direction):
        p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in ln]))


def draw_floor(p: QPainter, floor: Floor, opts: RenderOptions, background: QImage | None = None) -> None:
    """Etajni uning o'z koordinatalarida (piksellarda) chizadi."""
    if opts.background and background is not None and not background.isNull():
        p.setOpacity(0.35)
        p.drawImage(QRectF(0, 0, floor.width, floor.height), background)
        p.setOpacity(1.0)
    ww = wall_width(floor)
    # avval to'ldirish, keyin devorlar - qo'shni xonalar devorlari ustma-ust tushadi
    for room in floor.rooms:
        poly = QPolygonF([QPointF(x, y) for x, y in room.points])
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(ROOM_KINDS.get(room.kind, ROOM_KINDS["room"])[1]))
        p.drawPolygon(poly)
    for room in floor.rooms:
        if room.kind == "stairs":
            draw_stairs(p, room, floor)
    pen = QPen(QColor("#212121"), ww)
    pen.setJoinStyle(Qt.MiterJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    for room in floor.rooms:
        p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in room.points]))
    draw_walls(p, floor)
    for door in floor.doors:
        draw_door(p, door, door_wall_thickness(floor, door))
    if opts.room_names:
        f = QFont("Arial")
        f.setPixelSize(label_px(floor))
        p.setFont(f)
        p.setPen(QColor("#424242"))
        for room in floor.rooms:
            text = room_label(room, floor)
            if text:
                cx, cy = room.centroid()
                p.drawText(QRectF(cx - 300, cy - 100, 600, 200), Qt.AlignCenter, text)
    r = symbol_radius(floor)
    for e in floor.equipment:
        if e.planned and not opts.planned:
            continue
        draw_equipment_symbol(p, e.code, QPointF(e.x, e.y), r, e.planned)


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


def draw_page(p: QPainter, page: QRectF, building: Building, floor: Floor,
              opts: RenderOptions, background: QImage | None = None) -> None:
    """Sahifa: sarlavha, chizma va shartli belgilar jadvali."""
    p.fillRect(page, QColor("white"))
    unit = min(page.width(), page.height()) / 60
    margin = unit * 1.5
    area = page.adjusted(margin, margin, -margin, -margin)

    if opts.title:
        f = QFont("Arial")
        f.setBold(True)
        f.setPixelSize(int(unit * 1.6))
        p.setFont(f)
        p.setPen(QColor("black"))
        title = f"{building.name} — {floor.name}"
        h = unit * 2.4
        p.drawText(QRectF(area.left(), area.top(), area.width(), h), Qt.AlignLeft | Qt.AlignVCenter, title)
        if building.address:
            f.setBold(False)
            f.setPixelSize(int(unit * 1.0))
            p.setFont(f)
            p.drawText(QRectF(area.left(), area.top() + h, area.width(), unit * 1.5),
                       Qt.AlignLeft | Qt.AlignVCenter, building.address)
            h += unit * 1.5
        area.setTop(area.top() + h + unit)

    if opts.legend:
        if is_wide(floor):
            # uzun etaj - shartli belgilar pastda, gorizontal
            lh = unit * 7
            draw_legend(p, QRectF(area.left(), area.bottom() - lh, area.width(), lh), floor, unit, columns=6,
                        planned=opts.planned)
            area.setBottom(area.bottom() - lh - unit)
        else:
            lw = unit * 19
            draw_legend(p, QRectF(area.right() - lw, area.top(), lw, area.height()), floor, unit,
                        planned=opts.planned)
            area.setRight(area.right() - lw - unit)

    # chizmani maydonga sig'dirish
    s = min(area.width() / floor.width, area.height() / floor.height)
    p.save()
    p.translate(area.left() + (area.width() - floor.width * s) / 2,
                area.top() + (area.height() - floor.height * s) / 2)
    p.scale(s, s)
    draw_floor(p, floor, opts, background)
    p.restore()


def is_wide(floor: Floor) -> bool:
    return floor.width / max(1, floor.height) > 2.2


def draw_legend(p: QPainter, rect: QRectF, floor: Floor, unit: float, columns: int = 1,
                planned: bool = True) -> None:
    counts = equipment_counts(floor)
    need = equipment_counts(floor, planned=True) if planned else {}
    f = QFont("Arial")
    f.setBold(True)
    f.setPixelSize(int(unit * 1.1))
    p.setFont(f)
    p.setPen(QColor("black"))
    p.drawText(QRectF(rect.left(), rect.top(), rect.width(), unit * 2), Qt.AlignLeft | Qt.AlignVCenter,
               "Shartli belgilar")
    f.setBold(False)
    f.setPixelSize(int(unit * 0.9))

    items = []  # (chizish funksiyasi, matn)
    types = list(EQUIPMENT_TYPES) + ([UNKNOWN] if counts.get(UNKNOWN.code) else [])
    for t in types:
        text = f"{t.name} — {counts.get(t.code, 0)} ta"
        if need.get(t.code):
            text += f" (+{need[t.code]} kerak)"
        items.append((("eq", t.code), text))
    if need:
        items.append((("plan", "S"), "Punktir — o'rnatilishi kerak"))
    for kind, (name, color) in ROOM_KINDS.items():
        n = sum(1 for r in floor.rooms if r.kind == kind)
        if n:
            items.append((("room", color), f"{name} — {n} ta"))

    col_w = rect.width() / columns
    row_h = unit * 2
    rows = -(-len(items) // columns)
    for i, ((what, arg), text) in enumerate(items):
        col, row = (i // rows, i % rows) if columns > 1 else (0, i)
        x = rect.left() + col * col_w
        y = rect.top() + unit * 2.4 + row * row_h + (unit if columns == 1 and what == "room" else 0)
        if what in ("eq", "plan"):
            r = unit * 0.7
            draw_equipment_symbol(p, arg, QPointF(x + r, y + unit * 0.8), r, planned=(what == "plan"))
        else:
            p.setPen(QPen(QColor("#212121"), unit * 0.12))
            p.setBrush(QColor(arg))
            p.drawRect(QRectF(x, y + unit * 0.2, unit * 1.4, unit * 1.2))
        p.setFont(f)
        p.setPen(QColor("black"))
        p.drawText(QRectF(x + unit * 1.9, y, col_w - unit * 2, unit * 1.6),
                   Qt.AlignLeft | Qt.AlignVCenter, text)
