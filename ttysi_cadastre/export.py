"""Tayyor etajni eksport qilish: PNG/JPG, SVG, PDF va DXF (AutoCAD)."""

from __future__ import annotations

import ezdxf
from ezdxf.enums import TextEntityAlignment
from PySide6.QtCore import QMarginsF, QRectF, QSize
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtSvg import QSvgGenerator

from .equipment import EQUIPMENT_TYPES, ROOM_KINDS, UNKNOWN, get_type
from .geometry import door_lines, stair_lines
from .model import Building, Floor
from .render import (RenderOptions, dome_ring, draw_page, is_wide, label_px, meter_px, room_label,
                     symbol_radius, wall_width)


def _page_size(floor: Floor, long_side: int, legend: bool) -> tuple[int, int]:
    """Chizma nisbatiga mos sahifa o'lchami (shartli belgilar ustuni bilan)."""
    ratio = floor.width / floor.height
    if is_wide(floor):
        # uzun etaj: pastda sarlavha va shartli belgilar uchun joy
        return long_side, int(max(long_side / ratio * 1.3, long_side * 0.3))
    if legend:
        ratio += 0.4
    if ratio >= 1:
        return long_side, int(long_side / ratio * 1.08)
    return int(long_side * ratio * 1.08), long_side


def _background(floor: Floor) -> QImage | None:
    if not floor.image:
        return None
    img = QImage()
    img.loadFromData(floor.image)
    return img


def export_image(path: str, building: Building, floor: Floor, opts: RenderOptions,
                 long_side: int = 4000) -> None:
    w, h = _page_size(floor, long_side, opts.legend)
    img = QImage(w, h, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    draw_page(p, QRectF(0, 0, w, h), building, floor, opts, _background(floor))
    p.end()
    fmt = "JPG" if path.lower().endswith((".jpg", ".jpeg")) else "PNG"
    if not img.save(path, fmt, 95 if fmt == "JPG" else -1):
        raise OSError(f"Faylni saqlab bo'lmadi: {path}")


def export_svg(path: str, building: Building, floor: Floor, opts: RenderOptions) -> None:
    w, h = _page_size(floor, 2000, opts.legend)
    gen = QSvgGenerator()
    gen.setFileName(path)
    gen.setSize(QSize(w, h))
    gen.setViewBox(QRectF(0, 0, w, h))
    gen.setTitle(f"{building.name} — {floor.name}")
    p = QPainter(gen)
    p.setRenderHint(QPainter.Antialiasing)
    draw_page(p, QRectF(0, 0, w, h), building, floor, opts, _background(floor))
    p.end()


def export_pdf(path: str, building: Building, floors: list[Floor], opts: RenderOptions,
               page: str = "A3") -> None:
    """PDF - har bir etaj alohida sahifada (bitta yoki bir nechta etaj)."""
    writer = QPdfWriter(path)
    writer.setResolution(200)
    size = QPageSize(QPageSize.A3 if page == "A3" else QPageSize.A4)
    writer.setTitle(building.name)
    p = None
    for i, floor in enumerate(floors):
        orient = QPageLayout.Landscape if floor.width >= floor.height else QPageLayout.Portrait
        writer.setPageLayout(QPageLayout(size, orient, QMarginsF(0, 0, 0, 0)))
        if p is None:
            p = QPainter(writer)
            p.setRenderHint(QPainter.Antialiasing)
        else:
            writer.newPage()
        r = writer.pageLayout().paintRectPixels(writer.resolution())
        draw_page(p, QRectF(0, 0, r.width(), r.height()), building, floor, opts, _background(floor))
    if p is not None:
        p.end()


# ---------------------------------------------------------------- DXF

_ACI = {"SER": 1, "KX": 6, "K": 3, "W": 5, "S": 30, "T": 34, "?": 8}


def export_dxf(path: str, building: Building, floor: Floor, planned: bool = True) -> None:
    """AutoCAD DXF. Masshtab berilgan bo'lsa - metrlarda, aks holda piksellarda.

    Qatlamlar: XONA_<tur>, XONA_NOMLARI, AT_<kod>. Y o'qi CAD uchun teskari aylantiriladi.
    """
    k = floor.scale_m_per_px or 1.0
    H = floor.height

    def pt(x, y):
        return (x * k, (H - y) * k)

    doc = ezdxf.new("R2010", setup=True)
    doc.units = ezdxf.units.M if floor.scale_m_per_px else ezdxf.units.unitless
    msp = doc.modelspace()
    for kind, (name, _) in ROOM_KINDS.items():
        doc.layers.add(f"XONA_{kind.upper()}", color=7, linetype="Continuous").description = name
    doc.layers.add("XONA_NOMLARI", color=8)
    for t in EQUIPMENT_TYPES + [UNKNOWN]:
        lname = f"AT_{t.code if t.code != '?' else 'TASDIQLANMAGAN'}"
        doc.layers.add(lname, color=_ACI[t.code]).description = t.name
        if t.code != "?":
            # o'rnatilishi kerak (rejadagi) jihozlar - alohida qatlam, punktir chiziq
            doc.layers.add(lname + "_KERAK", color=_ACI[t.code], linetype="DASHED").description = \
                f"{t.name} — kerak (rejada)"

    text_h = label_px(floor) * 0.8 * k
    for room in floor.rooms:
        layer = f"XONA_{room.kind.upper()}"
        msp.add_lwpolyline([pt(x, y) for x, y in room.points], close=True,
                           dxfattribs={"layer": layer, "const_width": 0})
        label = room_label(room, floor).replace("\n", " / ")
        if label:
            cx, cy = room.centroid()
            msp.add_text(label, height=text_h, dxfattribs={"layer": "XONA_NOMLARI"}) \
               .set_placement(pt(cx, cy), align=TextEntityAlignment.MIDDLE_CENTER)

    # Eshiklar va zina pog'onalari
    doc.layers.add("ESHIKLAR", color=30)
    doc.layers.add("ZINALAR", color=8)
    doc.layers.add("GUMBAZ", color=8, linetype="DASHED")
    ww = wall_width(floor)
    doc.layers.add("DEVORLAR", color=7)
    for wall in floor.walls:
        msp.add_lwpolyline([pt(x, y) for x, y in wall.points],
                           dxfattribs={"layer": "DEVORLAR", "const_width": wall.thickness * k})
    for door in floor.doors:
        for ln in door_lines(door, ww):
            msp.add_lwpolyline([pt(x, y) for x, y in ln], dxfattribs={"layer": "ESHIKLAR"})
    for room in floor.rooms:
        if room.kind == "stairs":
            for ln in stair_lines(room.points, meter_px(floor) * 0.3, room.direction):
                msp.add_lwpolyline([pt(x, y) for x, y in ln], dxfattribs={"layer": "ZINALAR"})
        elif room.kind == "dome":
            msp.add_lwpolyline([pt(x, y) for x, y in dome_ring(room, floor)], close=True,
                               dxfattribs={"layer": "GUMBAZ"})

    # AT jihozlari - bloklar sifatida (CAD'da sanash va almashtirish oson)
    r = symbol_radius(floor) * k
    for t in EQUIPMENT_TYPES + [UNKNOWN]:
        bname = f"AT_{t.code if t.code != '?' else 'Q'}"
        blk = doc.blocks.new(name=bname)
        # BYBLOCK/BYLAYER: rang va chiziq turi blok qo'yilgan qatlamdan olinadi (punktir - rejadagi)
        attrs = {"color": 0, "linetype": "BYLAYER"}
        if t.code in ("SER", "KX"):
            blk.add_lwpolyline([(-r, -r), (r, -r), (r, r), (-r, r)], close=True, dxfattribs=attrs)
        else:
            blk.add_circle((0, 0), r, dxfattribs=attrs)
        blk.add_text(t.label, height=r * 0.8, dxfattribs={"color": 0}).set_placement(
            (0, 0), align=TextEntityAlignment.MIDDLE_CENTER)
    for e in floor.equipment:
        if e.planned and not planned:
            continue
        t = get_type(e.code)
        layer = f"AT_{t.code if t.code != '?' else 'TASDIQLANMAGAN'}"
        if e.planned and t.code != "?":
            layer += "_KERAK"
        bname = f"AT_{t.code if t.code != '?' else 'Q'}"
        ref = msp.add_blockref(bname, pt(e.x, e.y), dxfattribs={"layer": layer, "color": _ACI[t.code]})
        if e.note:
            ref.add_attrib("IZOH", e.note, insert=pt(e.x + 1.3 * r / k, e.y))

    # Sarlavha
    msp.add_text(f"{building.name} — {floor.name}", height=text_h * 1.6,
                 dxfattribs={"layer": "XONA_NOMLARI"}).set_placement(pt(0, -text_h * 3 / k))
    doc.saveas(path)
