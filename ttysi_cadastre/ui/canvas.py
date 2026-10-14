"""Chizma muharriri: xonalar, koridorlar va AT jihozlarini chizish va tahrirlash."""

from __future__ import annotations

import math
from dataclasses import replace

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPainterPathStroker, QPen,
                           QPixmap, QPolygonF)
from PySide6.QtWidgets import (QGraphicsItem, QInputDialog,
                               QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsPolygonItem,
                               QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem,
                               QGraphicsView, QMenu)

from ..equipment import ROOM_KINDS, get_type
from ..geometry import STAIR_DIRECTIONS, auto_stair_direction, nearest_wall, rotate_points
from ..detection import ellipse_points
from ..model import Door, Equipment, Floor, Room, Wall
from ..render import (door_wall_thickness, draw_dome, draw_door, draw_equipment_symbol, draw_stairs, label_px,
                      meter_px, room_label, symbol_radius, wall_width)

# Asboblar
SELECT, ROOM_POLY, ROOM_RECT, EQUIP, SPLIT, SCALE, PAN, DOOR, STAIRS, WALL, DOME = (
    "select", "room_poly", "room_rect", "equip", "split", "scale", "pan", "door", "stairs", "wall", "dome")

SNAP_PX = 10   # ekran piksellarida yopishish masofasi


def add_rotate_menu(menu: QMenu) -> dict:
    """"Aylantirish" ichki menyusi; {amal: burchak yoki "custom"} qaytaradi."""
    sub = menu.addMenu("Aylantirish")
    return {sub.addAction("90° o'ngga   ]"): 90.0, sub.addAction("90° chapga   ["): -90.0,
            sub.addAction("180°"): 180.0, sub.addAction("Burchak kiritish..."): "custom"}


def ask_angle(parent=None) -> float | None:
    a, ok = QInputDialog.getDouble(parent, "Aylantirish",
                                   "Burchak (gradus, + soat yo'nalishida, - teskari):", 90, -360, 360, 1)
    return a if ok else None


class VertexHandle(QGraphicsRectItem):
    """Xona burchagini sudrash uchun tutqich (ekranda doim bir xil o'lchamda)."""

    SIZE = 9

    def __init__(self, room_item: "RoomItem", index: int):
        s = self.SIZE
        super().__init__(-s / 2, -s / 2, s, s, room_item)
        self.room_item = room_item
        self.index = index
        self.setBrush(QColor("#1e88e5"))
        self.setPen(QPen(QColor("white"), 1))
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIgnoresTransformations
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setCursor(Qt.SizeAllCursor)
        self.setZValue(10)
        self.setToolTip("Sudrang. O'ng tugma - burchakni o'chirish")

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            scene: FloorScene = self.scene()
            value = scene.snap_point(self.room_item.mapToScene(value), exclude=self.room_item,
                                     ortho_from=self.room_item.neighbours(self.index))
            value = self.room_item.mapFromScene(value)
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.room_item.move_vertex(self.index, value)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.room_item.commit()

    def contextMenuEvent(self, event):
        menu = QMenu()
        act = menu.addAction("Burchakni o'chirish")
        if menu.exec(event.screenPos()) == act:
            self.room_item.remove_vertex(self.index)


STAIR_NAMES = {"": "Avtomatik", "right": "→  O'ngga", "down": "↓  Pastga", "left": "←  Chapga",
               "up": "↑  Yuqoriga"}


def door_flip_for(door: Door, x: float, y: float) -> bool:
    """Bosilgan nuqta devorning qaysi tomonida: eshik o'sha tomonga ochiladi."""
    a = math.radians(door.angle)
    return ((x - door.x) * -math.sin(a) + (y - door.y) * math.cos(a)) < 0


class ResizeHandle(QGraphicsRectItem):
    """Element chegarasi burchagi/qirrasidagi tutqich: sudrab elementni kattalashtirish/kichiklashtirish.

    Burchak tutqichi ikki tomonga, qirra tutqichi bir tomonga cho'zadi; Shift - nisbatni saqlash.
    Burchak tutqichlari burchak nuqtalari bilan ustma-ust tushmasligi uchun biroz tashqariga chiqarilgan.
    """

    SIZE = 9
    OFFSET = 9
    CURSORS = {(-1, -1): Qt.SizeFDiagCursor, (1, 1): Qt.SizeFDiagCursor, (1, -1): Qt.SizeBDiagCursor,
               (-1, 1): Qt.SizeBDiagCursor, (0, -1): Qt.SizeVerCursor, (0, 1): Qt.SizeVerCursor,
               (-1, 0): Qt.SizeHorCursor, (1, 0): Qt.SizeHorCursor}

    def __init__(self, target, role: tuple[int, int]):
        s, o = self.SIZE, self.OFFSET
        hx, hy = role
        super().__init__(-s / 2 + hx * o, -s / 2 + hy * o, s, s, target)
        self.target = target
        self.role = role
        self.setBrush(QColor("white"))
        pen = QPen(QColor("#1565c0"), 1.5)
        self.setPen(pen)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.setCursor(self.CURSORS[role])
        self.setZValue(11)
        self.setToolTip("Sudrab o'lchamini o'zgartiring (Shift - nisbatni saqlash)")

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        self.target.resize_begin()
        event.accept()

    def mouseMoveEvent(self, event):
        self.target.resize_to(self.role, event.scenePos(), bool(event.modifiers() & Qt.ShiftModifier))

    def mouseReleaseEvent(self, event):
        self.target.resize_end()


class Resizable:
    """Xona/zina va devor uchun umumiy: chegara bo'yicha o'lchamni o'zgartirish (tutqichlar va aniq qiymat)."""

    resize_handles: list = []

    def points_list(self) -> list[tuple[float, float]]:
        raise NotImplementedError

    def set_points(self, pts: list[tuple[float, float]]) -> None:
        raise NotImplementedError

    def bbox(self) -> tuple[float, float, float, float]:
        pts = self.points_list()
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def show_resize(self, on: bool):
        for h in getattr(self, "resize_handles", []):
            h.setParentItem(None)
            if h.scene():
                h.scene().removeItem(h)
        self.resize_handles = []
        if not on:
            return
        x0, y0, x1, y1 = self.bbox()
        for hx in (-1, 0, 1):
            for hy in (-1, 0, 1):
                if (hx, hy) == (0, 0):
                    continue
                if (hx and x1 - x0 < 1) or (hy and y1 - y0 < 1):
                    continue            # to'g'ri devor: faqat uzunligi bo'yicha
                h = ResizeHandle(self, (hx, hy))
                self.resize_handles.append(h)
        self.place_resize()

    def place_resize(self):
        x0, y0, x1, y1 = self.bbox()
        for h in getattr(self, "resize_handles", []):
            hx, hy = h.role
            h.setPos(QPointF((x0, (x0 + x1) / 2, x1)[hx + 1], (y0, (y0 + y1) / 2, y1)[hy + 1]))

    def resize_begin(self):
        self.commit(emit=False)
        self._orig = self.points_list()
        self._obox = self.bbox()
        for h in self.handles:          # burchak tutqichlari sudrash vaqtida yashiriladi
            h.setParentItem(None)
            if h.scene():
                h.scene().removeItem(h)
        self.handles = []

    def resize_to(self, role, p: QPointF, keep: bool = False):
        if not getattr(self, "_orig", None):
            self.resize_begin()
        x0, y0, x1, y1 = self._obox
        hx, hy = role
        ax = x1 if hx == -1 else x0
        ay = y1 if hy == -1 else y0
        sx = sy = 1.0
        if hx:
            edge = x0 if hx == -1 else x1
            sx = max(0.05, (p.x() - ax) / (edge - ax)) if abs(edge - ax) > 1e-6 else 1.0
        if hy:
            edge = y0 if hy == -1 else y1
            sy = max(0.05, (p.y() - ay) / (edge - ay)) if abs(edge - ay) > 1e-6 else 1.0
        if keep and hx and hy:
            sx = sy = max(sx, sy)
        self.set_points([(ax + (x - ax) * sx, ay + (y - ay) * sy) for x, y in self._orig])
        self.place_resize()

    def resize_end(self):
        self._orig = None
        self.commit()
        self.show_handles(self.isSelected())

    def scale_by(self, sx: float, sy: float | None = None, anchor: str = "center"):
        """Markaz (yoki chap-yuqori burchak) atrofida masshtablash - tugmalar va aniq o'lcham uchun."""
        sy = sx if sy is None else sy
        self.commit(emit=False)
        x0, y0, x1, y1 = self.bbox()
        ax, ay = ((x0 + x1) / 2, (y0 + y1) / 2) if anchor == "center" else (x0, y0)
        self.set_points([(ax + (x - ax) * sx, ay + (y - ay) * sy) for x, y in self.points_list()])
        self.commit(emit=False)
        if self.isSelected():
            self.show_handles(True)


class RoomItem(Resizable, QGraphicsPolygonItem):
    def __init__(self, room: Room, floor: Floor):
        super().__init__(QPolygonF([QPointF(x, y) for x, y in room.points]))
        self.room = room
        self.floor = floor
        self.handles: list[VertexHandle] = []
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.label = QGraphicsSimpleTextItem(self)
        f = QFont("Arial")
        f.setPixelSize(label_px(floor))
        self.label.setFont(f)
        self.label.setBrush(QColor("#424242"))
        self.label.setAcceptedMouseButtons(Qt.NoButton)
        self.refresh_style()

    # --- ko'rinish
    def refresh_style(self):
        color = QColor(ROOM_KINDS.get(self.room.kind, ROOM_KINDS["room"])[1])
        color.setAlpha(170)
        self.setBrush(color)
        pen = QPen(QColor("#1565c0") if self.isSelected() else QColor("#212121"), wall_width(self.floor))
        pen.setJoinStyle(Qt.MiterJoin)
        self.setPen(pen)
        self.update_label()

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if self.room.kind == "stairs":
            pts = [(q.x(), q.y()) for q in self.polygon()]
            painter.save()
            draw_stairs(painter, Room(points=pts, kind="stairs", direction=self.room.direction), self.floor)
            painter.restore()
        elif self.room.kind == "dome":
            pts = [(q.x(), q.y()) for q in self.polygon()]
            painter.save()
            draw_dome(painter, Room(points=pts, kind="dome"), self.floor)
            painter.restore()

    def update_label(self):
        self.label.setText(room_label(self.room, self.floor))
        poly = self.polygon()
        pts = [(p.x(), p.y()) for p in poly]
        cx, cy = Room(points=pts).centroid() if len(pts) >= 3 else (0, 0)
        r = self.label.boundingRect()
        self.label.setPos(cx - r.width() / 2, cy - r.height() / 2)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self.refresh_style()
            self.show_handles(bool(value))
        return super().itemChange(change, value)

    def points_list(self):
        off = self.pos()
        return [(q.x() + off.x(), q.y() + off.y()) for q in self.polygon()]

    def set_points(self, pts):
        self.setPos(0, 0)
        self.setPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
        self.update_label()

    def set_direction(self, direction: str):
        self.room.direction = direction
        self.update()

    def cycle_direction(self) -> str:
        """Zina yo'nalishini soat strelkasi bo'yicha 90° buradi."""
        cur = self.room.direction or auto_stair_direction(self.room.points)
        nxt = STAIR_DIRECTIONS[(STAIR_DIRECTIONS.index(cur) + 1) % 4]
        self.set_direction(nxt)
        return nxt

    def show_handles(self, on: bool):
        for h in self.handles:
            h.setParentItem(None)
            if h.scene():
                h.scene().removeItem(h)
        self.handles = []
        self.show_resize(on)
        if on and self.room.shape != "ellipse":      # doira - burchaklari emas, o'lchami tahrirlanadi
            for i, p in enumerate(self.polygon()):
                h = VertexHandle(self, i)
                h.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
                h.setPos(p)
                h.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
                self.handles.append(h)

    def neighbours(self, i: int) -> list[QPointF]:
        poly = self.polygon()
        n = poly.count()
        return [self.mapToScene(poly[(i - 1) % n]), self.mapToScene(poly[(i + 1) % n])]

    # --- tahrirlash
    def move_vertex(self, i: int, pos: QPointF):
        poly = self.polygon()
        poly[i] = pos
        self.setPolygon(poly)
        self.update_label()
        self.place_resize()

    def remove_vertex(self, i: int):
        poly = self.polygon()
        if poly.count() <= 3:
            return
        poly.remove(i)
        self.setPolygon(poly)
        self.commit()
        self.show_handles(True)

    def insert_vertex_at(self, scene_pos: QPointF):
        """Eng yaqin qirraga yangi burchak qo'shadi."""
        p = self.mapFromScene(scene_pos)
        poly = self.polygon()
        best, best_d = 0, float("inf")
        for i in range(poly.count()):
            a, b = poly[i], poly[(i + 1) % poly.count()]
            d = _seg_dist(p, a, b)
            if d < best_d:
                best, best_d = i, d
        poly.insert(best + 1, p)
        self.setPolygon(poly)
        self.commit()
        self.show_handles(True)

    def commit(self, emit: bool = True):
        """Elementdagi holatni modelga yozadi."""
        off = self.pos()
        self.room.points = [(p.x() + off.x(), p.y() + off.y()) for p in self.polygon()]
        if off != QPointF(0, 0):
            self.setPos(0, 0)
            self.setPolygon(QPolygonF([QPointF(x, y) for x, y in self.room.points]))
            if self.isSelected():
                self.show_handles(True)
        self.update_label()
        if emit and self.scene():
            self.scene().changed_model.emit()

    def rotate(self, angle: float):
        """Xonani o'z markazi atrofida aylantiradi."""
        self.commit(emit=False)
        self.room.points = rotate_points(self.room.points, angle)
        self.setPolygon(QPolygonF([QPointF(x, y) for x, y in self.room.points]))
        if self.isSelected():
            self.show_handles(True)
        self.update_label()

    def mouseDoubleClickEvent(self, event):
        if self.room.shape != "ellipse":
            self.insert_vertex_at(event.scenePos())

    def contextMenuEvent(self, event):
        scene: FloorScene = self.scene()
        if not self.isSelected():
            scene.clearSelection()
            self.setSelected(True)
        menu = QMenu()
        kinds = {}
        sub = menu.addMenu("Turi")
        for k, (name, _) in ROOM_KINDS.items():
            a = sub.addAction(name)
            a.setCheckable(True)
            a.setChecked(k == self.room.kind)
            kinds[a] = k
        dirs = {}
        if self.room.kind == "stairs":
            dm = menu.addMenu("Zina yo'nalishi (ko'tarilish)")
            for d, name in STAIR_NAMES.items():
                a = dm.addAction(name)
                a.setCheckable(True)
                a.setChecked(d == self.room.direction)
                dirs[a] = d
        add_v = menu.addAction("Shu yerga burchak qo'shish")
        add_v.setEnabled(self.room.shape != "ellipse")
        rotations = add_rotate_menu(menu)
        menu.addSeparator()
        merge = menu.addAction("Tanlangan xonalarni birlashtirish")
        merge.setEnabled(len(scene.selected_rooms()) >= 2)
        delete = menu.addAction("O'chirish")
        act = menu.exec(event.screenPos())
        if act in kinds:
            for it in scene.selected_rooms():
                it.room.kind = kinds[act]
                it.refresh_style()
            scene.changed_model.emit()
        elif act in dirs:
            for it in scene.selected_rooms():
                if it.room.kind == "stairs":
                    it.set_direction(dirs[act])
            scene.changed_model.emit()
        elif act == add_v:
            self.insert_vertex_at(event.scenePos())
        elif act in rotations:
            scene.rotate_selected(rotations[act])
        elif act == merge:
            scene.request_merge.emit()
        elif act == delete:
            scene.delete_selected()


class WallItem(Resizable, QGraphicsPathItem):
    """Mustaqil devor: siniq chiziq, burchaklari tahrirlanadi, qalinligi tanlanadi."""

    THICKNESS_M = (0.12, 0.25, 0.38, 0.51, 0.64)

    def __init__(self, wall: Wall, floor: Floor):
        super().__init__()
        self.wall = wall
        self.floor = floor
        self.pts = [QPointF(x, y) for x, y in wall.points]
        self.handles: list[VertexHandle] = []
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(2)
        self.setToolTip("Devor. Ikki marta bosish - burchak qo'shish. O'ng tugma - qalinligi")
        self.rebuild()

    def rebuild(self):
        path = QPainterPath()
        if self.pts:
            path.moveTo(self.pts[0])
            for q in self.pts[1:]:
                path.lineTo(q)
        self.setPath(path)
        pen = QPen(QColor("#1565c0") if self.isSelected() else QColor("#212121"), self.wall.thickness)
        pen.setJoinStyle(Qt.MiterJoin)
        pen.setCapStyle(Qt.SquareCap)
        self.setPen(pen)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(self.wall.thickness + 8)
        return stroker.createStroke(self.path())

    def points_list(self):
        off = self.pos()
        return [(q.x() + off.x(), q.y() + off.y()) for q in self.pts]

    def set_points(self, pts):
        self.setPos(0, 0)
        self.pts = [QPointF(x, y) for x, y in pts]
        self.rebuild()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self.rebuild()
            self.show_handles(bool(value))
        return super().itemChange(change, value)

    def show_handles(self, on: bool):
        for h in self.handles:
            h.setParentItem(None)
            if h.scene():
                h.scene().removeItem(h)
        self.handles = []
        self.show_resize(on)
        if on:
            for i, q in enumerate(self.pts):
                h = VertexHandle(self, i)
                h.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
                h.setPos(q)
                h.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
                self.handles.append(h)

    # VertexHandle shu usullarni chaqiradi (RoomItem bilan bir xil interfeys)
    def neighbours(self, i: int) -> list[QPointF]:
        return [self.mapToScene(self.pts[j]) for j in (i - 1, i + 1) if 0 <= j < len(self.pts)]

    def move_vertex(self, i: int, pos: QPointF):
        self.pts[i] = QPointF(pos)
        self.rebuild()
        self.place_resize()

    def remove_vertex(self, i: int):
        if len(self.pts) <= 2:
            return
        self.pts.pop(i)
        self.commit()
        self.show_handles(True)

    def insert_vertex_at(self, scene_pos: QPointF):
        p = self.mapFromScene(scene_pos)
        best, best_d = 0, float("inf")
        for i in range(len(self.pts) - 1):
            d = _seg_dist(p, self.pts[i], self.pts[i + 1])
            if d < best_d:
                best, best_d = i, d
        self.pts.insert(best + 1, p)
        self.commit()
        self.show_handles(True)

    def commit(self, emit: bool = True):
        off = self.pos()
        self.wall.points = [(q.x() + off.x(), q.y() + off.y()) for q in self.pts]
        if off != QPointF(0, 0):
            self.setPos(0, 0)
            self.pts = [QPointF(x, y) for x, y in self.wall.points]
            if self.isSelected():
                self.show_handles(True)
        self.rebuild()
        if emit and self.scene():
            self.scene().changed_model.emit()

    def rotate(self, angle: float):
        """Devorni o'z o'rtasi atrofida aylantiradi."""
        self.commit(emit=False)
        n = len(self.wall.points)
        center = (sum(x for x, _ in self.wall.points) / n, sum(y for _, y in self.wall.points) / n)
        self.wall.points = rotate_points(self.wall.points, angle, center)
        self.pts = [QPointF(x, y) for x, y in self.wall.points]
        self.rebuild()
        if self.isSelected():
            self.show_handles(True)

    def mouseDoubleClickEvent(self, event):
        self.insert_vertex_at(event.scenePos())

    def contextMenuEvent(self, event):
        scene: FloorScene = self.scene()
        if not self.isSelected():
            scene.clearSelection()
            self.setSelected(True)
        menu = QMenu()
        sub = menu.addMenu("Qalinligi")
        m = meter_px(self.floor)
        widths = {}
        for tm in self.THICKNESS_M:
            a = sub.addAction(f"{tm:.2f} m")
            a.setCheckable(True)
            a.setChecked(abs(self.wall.thickness - tm * m) < m * 0.02)
            widths[a] = tm * m
        add_v = menu.addAction("Shu yerga burchak qo'shish")
        rotations = add_rotate_menu(menu)
        menu.addSeparator()
        delete = menu.addAction("O'chirish")
        act = menu.exec(event.screenPos())
        if act in widths:
            for it in scene.selected_walls():
                it.prepareGeometryChange()
                it.wall.thickness = widths[act]
                it.rebuild()
            scene.update()
            scene.changed_model.emit()
        elif act == add_v:
            self.insert_vertex_at(event.scenePos())
        elif act in rotations:
            scene.rotate_selected(rotations[act])
        elif act == delete:
            scene.delete_selected()


class DoorWidthHandle(QGraphicsRectItem):
    """Eshik chetidagi tutqich: devor bo'ylab sudrab eshik kengligini o'zgartirish."""

    SIZE = 9

    def __init__(self, door_item: "DoorItem", side: int):
        s = self.SIZE
        super().__init__(-s / 2, -s / 2, s, s, door_item)
        self.door_item = door_item
        self.side = side
        self.setBrush(QColor("white"))
        self.setPen(QPen(QColor("#1565c0"), 1.5))
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.setCursor(Qt.SizeHorCursor)
        self.setZValue(11)
        self.setToolTip("Sudrab eshik kengligini o'zgartiring")

    def mousePressEvent(self, event):
        event.accept()

    def mouseMoveEvent(self, event):
        d = self.door_item.door
        a = math.radians(d.angle)
        p = event.scenePos()
        along = (p.x() - d.x) * math.cos(a) + (p.y() - d.y) * math.sin(a)
        self.door_item.set_width(abs(along) * 2)

    def mouseReleaseEvent(self, event):
        if self.door_item.scene():
            self.door_item.scene().changed_model.emit()


class DoorItem(QGraphicsItem):
    """Eshik: sudralganda eng yaqin devorga yopishadi va uning yo'nalishini oladi.

    Ochilish tomoni - devorning qaysi tarafiga bosilgan/sudralgan bo'lsa, o'sha taraf.
    """

    WIDTHS = (0.8, 0.9, 1.0, 1.2, 1.5, 1.8)
    MIN_M, MAX_M = 0.5, 4.0

    def __init__(self, door: Door, floor: Floor):
        super().__init__()
        self.door = door
        self.floor = floor
        self.wall = wall_width(floor)
        self.setPos(door.x, door.y)
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(3)
        self.setToolTip("Eshik. Devorning qaysi tomoniga sudrasangiz, o'sha tomonga ochiladi. "
                        "Chetlaridagi tutqichlar - kengligi. O'ng tugma - turi, sharnir tomoni")
        self.width_handles: list[DoorWidthHandle] = []

    def set_width(self, width_px: float):
        m = meter_px(self.floor)
        self.prepareGeometryChange()
        self.door.width = min(self.MAX_M * m, max(self.MIN_M * m, width_px))
        self.place_width_handles()
        self.update()

    def set_flip(self, flip: bool):
        if flip != self.door.flip:
            self.prepareGeometryChange()
            self.door.flip = flip
            self.update()

    def show_width_handles(self, on: bool):
        for h in self.width_handles:
            h.setParentItem(None)
            if h.scene():
                h.scene().removeItem(h)
        self.width_handles = [DoorWidthHandle(self, s) for s in (-1, 1)] if on else []
        self.place_width_handles()

    def place_width_handles(self):
        a = math.radians(self.door.angle)
        for h in self.width_handles:
            r = self.door.width / 2 * h.side
            h.setPos(r * math.cos(a), r * math.sin(a))

    def boundingRect(self):
        r = self.door.width * 1.15 + self.wall
        return QRectF(-r, -r, 2 * r, 2 * r)

    def shape(self):
        # tanlash uchun: eshik o'rni va ochilish maydoni
        path = QPainterPath()
        r = self.door.width * 0.6 + self.wall
        path.addEllipse(QPointF(0, 0), r, r)
        return path

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        draw_door(p, replace(self.door, x=0.0, y=0.0), door_wall_thickness(self.floor, self.door))
        if self.isSelected():
            pen = QPen(QColor("#1565c0"), 2, Qt.DashLine)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            r = self.door.width * 0.6 + self.wall
            p.drawEllipse(QPointF(0, 0), r, r)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            snap = nearest_wall(self.floor.rooms, value.x(), value.y(), self.floor.walls)
            if snap and snap[3] < self.door.width:
                self.prepareGeometryChange()
                old_angle = self.door.angle
                self.door.angle = snap[2]
                # devor o'qi yo'nalishi teskari bo'lsa (180°), tomon saqlanadi; kursor devorning
                # boshqa tarafiga o'tsa (yetarlicha uzoq) - eshik o'sha tarafga ochiladi
                if abs(((snap[2] - old_angle + 180) % 360) - 180) > 90:
                    self.door.flip = not self.door.flip
                if snap[3] > self.wall * 0.6:
                    probe = replace(self.door, x=snap[0], y=snap[1])
                    self.door.flip = door_flip_for(probe, value.x(), value.y())
                self.place_width_handles()
                self.update()
                return QPointF(snap[0], snap[1])
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self.show_width_handles(bool(value))
        return super().itemChange(change, value)

    def commit(self):
        self.door.x, self.door.y = self.pos().x(), self.pos().y()
        self.update()

    def rotate(self, angle: float):
        """Eshikni o'z markazi atrofida aylantiradi (masalan devor burchagida yoki qiya devorda)."""
        self.prepareGeometryChange()
        self.door.angle = (self.door.angle + angle) % 360
        self.place_width_handles()
        self.update()

    def mouseDoubleClickEvent(self, event):
        """Ikki marta bosish - ochilish tomonini almashtirish."""
        self.set_flip(not self.door.flip)
        if self.scene():
            self.scene().changed_model.emit()

    def contextMenuEvent(self, event):
        scene: FloorScene = self.scene()
        if not self.isSelected():
            scene.clearSelection()
            self.setSelected(True)
        menu = QMenu()
        single = menu.addAction("Bir tabaqali")
        double = menu.addAction("Ikki tabaqali")
        single.setCheckable(True)
        double.setCheckable(True)
        single.setChecked(self.door.leaves == 1)
        double.setChecked(self.door.leaves == 2)
        flip = menu.addAction("Ochilish tomonini almashtirish (ichkariga/tashqariga)")
        mirror = menu.addAction("Sharnir tomonini almashtirish")
        mirror.setEnabled(self.door.leaves == 1)
        rotations = add_rotate_menu(menu)
        sub = menu.addMenu("Kengligi")
        widths = {}
        m = meter_px(self.floor)
        for wm in self.WIDTHS:
            a = sub.addAction(f"{wm:.1f} m")
            a.setCheckable(True)
            a.setChecked(abs(self.door.width - wm * m) < m * 0.05)
            widths[a] = wm * m
        menu.addSeparator()
        delete = menu.addAction("O'chirish")
        act = menu.exec(event.screenPos())
        if act is None:
            return
        if act == delete:
            scene.delete_selected()
            return
        if act in rotations:
            scene.rotate_selected(rotations[act])
            return
        self.prepareGeometryChange()
        if act == single:
            self.door.leaves = 1
        elif act == double:
            self.door.leaves = 2
        elif act == flip:
            self.door.flip = not self.door.flip
        elif act == mirror:
            self.door.mirror = not self.door.mirror
        elif act in widths:
            self.door.width = widths[act]
        self.place_width_handles()
        self.update()
        scene.changed_model.emit()


class EquipmentItem(QGraphicsItem):
    def __init__(self, eq: Equipment, floor: Floor):
        super().__init__()
        self.eq = eq
        self.r = symbol_radius(floor)
        self.setPos(eq.x, eq.y)
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable)
        self.setZValue(5)
        self.refresh_tooltip()

    def refresh_tooltip(self):
        t = get_type(self.eq.code)
        tip = t.name + (" — kerak (rejada)" if self.eq.planned else "") + (f"\n{self.eq.note}" if self.eq.note else "")
        if t.code == "?":
            tip += "\nTurini tanlash: 1-6 tugmalari"
        self.setToolTip(tip)

    def boundingRect(self):
        r = self.r * 1.6
        return QRectF(-r, -r, 2 * r, 2 * r)

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        draw_equipment_symbol(p, self.eq.code, QPointF(0, 0), self.r, self.eq.planned)
        if self.eq.code == "?":
            pen = QPen(QColor("#ff1744"), self.r * 0.15, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(0, 0), self.r * 1.35, self.r * 1.35)
        if self.isSelected():
            p.setPen(QPen(QColor("#1565c0"), self.r * 0.2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(0, 0), self.r * 1.5, self.r * 1.5)

    def commit(self):
        self.eq.x, self.eq.y = self.pos().x(), self.pos().y()

    def set_code(self, code: str):
        self.eq.code = code
        self.refresh_tooltip()
        self.update()

    def set_status(self, status: str):
        self.eq.status = status
        self.refresh_tooltip()
        self.update()

    def contextMenuEvent(self, event):
        scene: FloorScene = self.scene()
        if not self.isSelected():
            scene.clearSelection()
            self.setSelected(True)
        menu = QMenu()
        exist = menu.addAction("Mavjud")
        plan = menu.addAction("Kerak (o'rnatilishi rejada)")
        for a, st in ((exist, "existing"), (plan, "planned")):
            a.setCheckable(True)
            a.setChecked(self.eq.status == st)
        menu.addSeparator()
        delete = menu.addAction("O'chirish")
        act = menu.exec(event.screenPos())
        if act in (exist, plan):
            for it in scene.selected_equipment():
                it.set_status("existing" if act == exist else "planned")
            scene.changed_model.emit()
        elif act == delete:
            scene.delete_selected()


class FloorScene(QGraphicsScene):
    changed_model = Signal()      # model o'zgardi (bekor qilish tarixiga yoziladi)
    request_merge = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.floor: Floor | None = None
        self.bg_item: QGraphicsPixmapItem | None = None
        self.bg_opacity = 0.6
        self.ortho = True
        self.view_scale = 1.0
        self.new_wall_m = 0.25      # yangi chiziladigan devorlar qalinligi (metr)

    def load(self, floor: Floor | None, bg: QImage | None):
        self.clear()
        self.bg_item = None
        self.floor = floor
        if floor is None:
            return
        self.setSceneRect(QRectF(-floor.width * 0.1, -floor.height * 0.1,
                                 floor.width * 1.2, floor.height * 1.2))
        paper = self.addRect(QRectF(0, 0, floor.width, floor.height), QPen(QColor("#bdbdbd"), 0),
                             QBrush(QColor("white")))
        paper.setZValue(-20)
        if bg is not None and not bg.isNull():
            self.bg_item = self.addPixmap(QPixmap.fromImage(bg))
            self.bg_item.setScale(floor.width / bg.width())
            self.bg_item.setZValue(-10)
            self.bg_item.setOpacity(self.bg_opacity)
            self.bg_item.setTransformationMode(Qt.SmoothTransformation)
        for room in floor.rooms:
            self.addItem(RoomItem(room, floor))
        for wall in floor.walls:
            self.addItem(WallItem(wall, floor))
        for door in floor.doors:
            self.addItem(DoorItem(door, floor))
        for eq in floor.equipment:
            self.addItem(EquipmentItem(eq, floor))

    def set_bg_opacity(self, v: float):
        self.bg_opacity = v
        if self.bg_item:
            self.bg_item.setOpacity(v)

    def room_items(self) -> list[RoomItem]:
        return [i for i in self.items() if isinstance(i, RoomItem)]

    def equipment_items(self) -> list[EquipmentItem]:
        return [i for i in self.items() if isinstance(i, EquipmentItem)]

    def selected_rooms(self) -> list[RoomItem]:
        return [i for i in self.selectedItems() if isinstance(i, RoomItem)]

    def selected_walls(self) -> list["WallItem"]:
        return [i for i in self.selectedItems() if isinstance(i, WallItem)]

    def selected_equipment(self) -> list[EquipmentItem]:
        return [i for i in self.selectedItems() if isinstance(i, EquipmentItem)]

    def add_room(self, points, kind="room", shape="") -> RoomItem:
        room = Room(points=[(p.x(), p.y()) if isinstance(p, QPointF) else p for p in points], kind=kind,
                    shape=shape)
        self.floor.rooms.append(room)
        item = RoomItem(room, self.floor)
        self.addItem(item)
        self.changed_model.emit()
        return item

    def add_equipment(self, code: str, pos: QPointF, planned: bool = False) -> EquipmentItem:
        eq = Equipment(code=code, x=pos.x(), y=pos.y(), status="planned" if planned else "existing")
        self.floor.equipment.append(eq)
        item = EquipmentItem(eq, self.floor)
        self.addItem(item)
        self.changed_model.emit()
        return item

    def add_wall(self, points, thickness_m: float | None = None) -> "WallItem":
        pts = [(q.x(), q.y()) if isinstance(q, QPointF) else tuple(q) for q in points]
        wall = Wall(points=pts, thickness=meter_px(self.floor) * (thickness_m or self.new_wall_m))
        self.floor.walls.append(wall)
        item = WallItem(wall, self.floor)
        self.addItem(item)
        self.changed_model.emit()
        return item

    def set_wall_thickness(self, walls, thickness_m: float) -> None:
        """Tanlangan devorlar qalinligi (metr). Eshiklar ham yangi qalinlikda qayta chiziladi."""
        px = meter_px(self.floor) * thickness_m
        for it in walls:
            it.prepareGeometryChange()
            it.wall.thickness = px
            it.rebuild()
        self.update()
        self.changed_model.emit()

    def rotate_selected(self, angle) -> bool:
        """Tanlangan xona, zina va eshiklarni har birini o'z markazi atrofida aylantiradi."""
        items = [i for i in self.selectedItems() if isinstance(i, (RoomItem, DoorItem, WallItem))]
        if not items:
            return False
        if angle == "custom":
            angle = ask_angle(self.views()[0] if self.views() else None)
            if angle is None or angle == 0:
                return False
        for it in items:
            it.rotate(angle)
        self.changed_model.emit()
        return True

    def add_door(self, pos: QPointF) -> "DoorItem":
        """Eshikni eng yaqin devorga qo'yadi (standart kenglik 0.9 m)."""
        width = meter_px(self.floor) * 0.9
        door = Door(x=pos.x(), y=pos.y(), width=width)
        snap = nearest_wall(self.floor.rooms, pos.x(), pos.y(), self.floor.walls)
        if snap and snap[3] < width * 1.5:
            door.x, door.y, door.angle = snap[0], snap[1], snap[2]
            # devorning qaysi tarafiga bosilgan bo'lsa - eshik o'sha tarafga ochiladi
            door.flip = door_flip_for(door, pos.x(), pos.y())
        self.floor.doors.append(door)
        item = DoorItem(door, self.floor)
        self.addItem(item)
        self.changed_model.emit()
        return item

    def delete_selected(self):
        items = self.selectedItems()
        if not items:
            return
        for it in items:
            if isinstance(it, RoomItem):
                self.floor.rooms.remove(it.room)
            elif isinstance(it, EquipmentItem):
                self.floor.equipment.remove(it.eq)
            elif isinstance(it, DoorItem):
                self.floor.doors.remove(it.door)
            elif isinstance(it, WallItem):
                self.floor.walls.remove(it.wall)
            else:
                continue
            self.removeItem(it)
        self.changed_model.emit()

    def snap_point(self, p: QPointF, exclude=None, ortho_from: list[QPointF] | None = None) -> QPointF:
        """Boshqa xonalar burchaklariga va gorizontal/vertikal yo'nalishga yopishtiradi."""
        tol = SNAP_PX / max(self.view_scale, 1e-6)
        best, best_d = None, tol
        for it in self.room_items():
            if it is exclude:
                continue
            for v in it.polygon():
                v = it.mapToScene(v)
                d = math.hypot(v.x() - p.x(), v.y() - p.y())
                if d < best_d:
                    best, best_d = v, d
        if best is not None:
            return QPointF(best)
        x, y = p.x(), p.y()
        if self.ortho and ortho_from:
            for q in ortho_from:
                if abs(q.x() - x) < tol:
                    x = q.x()
                if abs(q.y() - y) < tol:
                    y = q.y()
        return QPointF(x, y)

    def mouseReleaseEvent(self, event):
        moved = False
        for it in self.selectedItems():
            if isinstance(it, RoomItem) and it.pos() != QPointF(0, 0):
                it.commit(emit=False)
                moved = True
            elif isinstance(it, EquipmentItem) and (it.pos().x(), it.pos().y()) != (it.eq.x, it.eq.y):
                it.commit()
                moved = True
            elif isinstance(it, DoorItem) and (it.pos().x(), it.pos().y()) != (it.door.x, it.door.y):
                it.commit()
                moved = True
            elif isinstance(it, WallItem) and it.pos() != QPointF(0, 0):
                it.commit(emit=False)
                moved = True
        super().mouseReleaseEvent(event)
        if moved:
            self.changed_model.emit()


class FloorView(QGraphicsView):
    """Kattalashtirish (g'ildirak), surish (o'rta tugma / Probel) va chizish asboblari."""

    status = Signal(str)
    split_requested = Signal(QPointF, QPointF)
    scale_requested = Signal(float)   # piksel masofasi
    zoomed = Signal(float)            # joriy kattalashtirish (1.0 = rasmning haqiqiy o'lchami)

    def __init__(self, scene: FloorScene):
        super().__init__(scene)
        self.fscene = scene
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setBackgroundBrush(QColor("#F7F8FA"))
        self.tool = SELECT
        self.equip_code = "K"
        self.points: list[QPointF] = []
        self.preview: QGraphicsPathItem | None = None
        self.rect_start: QPointF | None = None
        self._panning = False
        self._pan_last = None
        self._space = False
        self.place_planned = False  # yangi qo'yiladigan jihozlar "kerak" holatida bo'lsinmi

    # --- asbob
    def set_tool(self, tool: str, code: str | None = None):
        self.cancel_drawing()
        self.tool = tool
        if code:
            self.equip_code = code
        self.setDragMode(QGraphicsView.RubberBandDrag if tool == SELECT else QGraphicsView.NoDrag)
        self.viewport().setCursor(Qt.ArrowCursor if tool == SELECT else Qt.CrossCursor)
        hints = {
            SELECT: "Tanlash: bosing yoki ramka torting. Ikki marta bosish - burchak qo'shish. Del - o'chirish.",
            ROOM_POLY: "Xona chizish: burchaklarni ketma-ket bosing. Enter / ikki marta bosish / birinchi nuqta - tugatish. Esc - bekor.",
            ROOM_RECT: "To'rtburchak xona: sichqonchani bosib, torting.",
            WALL: "Devor: burchaklarni ketma-ket bosing. Enter / ikki marta bosish - tugatish. Esc - bekor.",
            DOOR: "Eshik: devorning ochilishi kerak bo'lgan tarafiga bosing. Kengligi - chetidagi tutqichlar; "
                  "ikki marta bosish - tomonini almashtirish.",
            STAIRS: "Zina: sichqonchani bosib, zina maydonini torting.",
            DOME: "Gumbaz (doira bino): sichqonchani bosib torting - doira; Shift - ellips.",
            EQUIP: f"{get_type(self.equip_code).name}: joyini bosing.",
            SPLIT: "Xonani bo'lish: bo'lish chizig'ining ikki nuqtasini bosing.",
            SCALE: "Masshtab: uzunligi ma'lum bo'lgan devorning ikki uchini bosing.",
        }
        self.status.emit(hints.get(tool, ""))

    def cancel_drawing(self):
        self.points = []
        self.rect_start = None
        if self.preview is not None:
            self.fscene.removeItem(self.preview)
            self.preview = None

    def _update_preview(self, cursor: QPointF | None = None):
        if self.preview is None:
            self.preview = QGraphicsPathItem()
            pen = QPen(QColor("#e53935"), 2)
            pen.setCosmetic(True)
            pen.setStyle(Qt.DashLine)
            self.preview.setPen(pen)
            self.preview.setZValue(100)
            self.fscene.addItem(self.preview)
        path = QPainterPath()
        if self.tool in (ROOM_RECT, STAIRS) and self.rect_start is not None and cursor is not None:
            path.addRect(QRectF(self.rect_start, cursor).normalized())
        elif self.tool == DOME and self.rect_start is not None and cursor is not None:
            path.addEllipse(self._dome_rect(cursor))
        elif self.points:
            path.moveTo(self.points[0])
            for q in self.points[1:]:
                path.lineTo(q)
            if cursor is not None:
                path.lineTo(cursor)
        self.preview.setPath(path)

    def _snapped(self, pos) -> QPointF:
        p = self.mapToScene(pos)
        ref = [self.points[-1]] if self.points else []
        if self.tool == ROOM_POLY and self.points and len(self.points) >= 2:
            ref.append(self.points[0])
        return self.fscene.snap_point(p, ortho_from=ref) if self.tool != EQUIP else p

    def _ortho_lock(self, p: QPointF, shift: bool) -> QPointF:
        """Orto rejim: oxirgi nuqtadan faqat gorizontal/vertikal (Shift - vaqtincha o'chiradi)."""
        if not self.points or not (self.fscene.ortho ^ shift):
            return p
        last = self.points[-1]
        if abs(p.x() - last.x()) >= abs(p.y() - last.y()):
            return QPointF(p.x(), last.y())
        return QPointF(last.x(), p.y())

    # --- sichqoncha
    def wheelEvent(self, event):
        f = 1.0015 ** event.angleDelta().y()
        self.zoom_by(f)

    def zoom_by(self, f: float):
        m = self.transform().m11()
        f = max(0.02, min(16.0, m * f)) / max(m, 1e-9)
        self.scale(f, f)
        self.fscene.view_scale = self.transform().m11()
        self.zoomed.emit(self.transform().m11())

    def zoom_fit(self):
        if self.fscene.floor:
            f = self.fscene.floor
            self.fitInView(QRectF(0, 0, f.width, f.height), Qt.KeepAspectRatio)
            self.fscene.view_scale = self.transform().m11()
            self.zoomed.emit(self.transform().m11())

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton or (self._space and event.button() == Qt.LeftButton):
            self._panning = True
            self._pan_last = event.position()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            return
        if self.fscene.floor is None or event.button() != Qt.LeftButton or self.tool == SELECT:
            if event.button() == Qt.RightButton and self.tool != SELECT and self.points:
                self.points.pop()
                self._update_preview(self.mapToScene(event.position().toPoint()))
                return
            super().mousePressEvent(event)
            return
        shift = bool(event.modifiers() & Qt.ShiftModifier)
        p = self._snapped(event.position().toPoint())
        if self.tool == ROOM_POLY:
            p = self._ortho_lock(p, shift)
            if len(self.points) >= 3 and _dist(p, self.points[0]) < SNAP_PX * 1.5 / self.fscene.view_scale:
                self.finish_polygon()
                return
            self.points.append(p)
            self._update_preview(p)
        elif self.tool == WALL:
            p = self._ortho_lock(p, shift)
            if self.points and _dist(p, self.points[-1]) < 1e-6:
                return
            self.points.append(p)
            self._update_preview(p)
        elif self.tool in (ROOM_RECT, STAIRS, DOME):
            self.rect_start = p
        elif self.tool == DOOR:
            self.fscene.add_door(self.mapToScene(event.position().toPoint()))
        elif self.tool == EQUIP:
            self.fscene.add_equipment(self.equip_code, p, planned=self.place_planned)
        elif self.tool in (SPLIT, SCALE):
            p = self._ortho_lock(p, shift)
            self.points.append(p)
            self._update_preview(p)
            if len(self.points) == 2:
                a, b = self.points
                self.cancel_drawing()
                if self.tool == SPLIT:
                    self.split_requested.emit(a, b)
                else:
                    self.scale_requested.emit(_dist(a, b))

    def mouseMoveEvent(self, event):
        if self._panning:
            d = event.position() - self._pan_last
            self._pan_last = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        if self.tool in (ROOM_POLY, WALL, SPLIT, SCALE) and self.points:
            p = self._ortho_lock(self._snapped(event.position().toPoint()),
                                 bool(event.modifiers() & Qt.ShiftModifier))
            self._update_preview(p)
        elif self.tool in (ROOM_RECT, STAIRS, DOME) and self.rect_start is not None:
            self._dome_shift = bool(event.modifiers() & Qt.ShiftModifier)
            self._update_preview(self._snapped(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            self.viewport().setCursor(Qt.ArrowCursor if self.tool == SELECT else Qt.CrossCursor)
            return
        if self.tool in (ROOM_RECT, STAIRS) and self.rect_start is not None and event.button() == Qt.LeftButton:
            r = QRectF(self.rect_start, self._snapped(event.position().toPoint())).normalized()
            self.cancel_drawing()
            if r.width() > 3 and r.height() > 3:
                self.fscene.add_room([r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()],
                                     kind="stairs" if self.tool == STAIRS else "room")
            return
        if self.tool == DOME and self.rect_start is not None and event.button() == Qt.LeftButton:
            self._dome_shift = bool(event.modifiers() & Qt.ShiftModifier)
            r = self._dome_rect(self._snapped(event.position().toPoint()))
            self.cancel_drawing()
            if r.width() > 3 and r.height() > 3:
                c = r.center()
                self.fscene.add_room(ellipse_points(c.x(), c.y(), r.width() / 2, r.height() / 2),
                                     kind="dome", shape="ellipse")
            return
        super().mouseReleaseEvent(event)

    def _dome_rect(self, cursor: QPointF) -> QRectF:
        """Gumbaz: torilgan to'rtburchakka sig'adigan doira (Shift - erkin ellips)."""
        r = QRectF(self.rect_start, cursor).normalized()
        if not getattr(self, "_dome_shift", False):
            side = max(r.width(), r.height())
            sx = 1 if cursor.x() >= self.rect_start.x() else -1
            sy = 1 if cursor.y() >= self.rect_start.y() else -1
            r = QRectF(self.rect_start, QPointF(self.rect_start.x() + sx * side,
                                                self.rect_start.y() + sy * side)).normalized()
        return r

    def mouseDoubleClickEvent(self, event):
        if self.tool in (ROOM_POLY, WALL):
            self.finish_polygon()
            return
        super().mouseDoubleClickEvent(event)

    def finish_polygon(self):
        pts = self.points
        # ikki marta bosishdagi takror nuqtani olib tashlash
        while len(pts) >= 2 and _dist(pts[-1], pts[-2]) < 1e-6:
            pts.pop()
        self.cancel_drawing()
        if self.tool == WALL:
            if len(pts) >= 2:
                self.fscene.add_wall(pts)
        elif len(pts) >= 3:
            self.fscene.add_room(pts)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space = True
            self.viewport().setCursor(Qt.OpenHandCursor)
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.tool in (ROOM_POLY, WALL):
            self.finish_polygon()
            return
        if event.key() == Qt.Key_Escape:
            if self.points or self.rect_start:
                self.cancel_drawing()
            else:
                self.parent_window_select()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space = False
            self.viewport().setCursor(Qt.ArrowCursor if self.tool == SELECT else Qt.CrossCursor)
            return
        super().keyReleaseEvent(event)

    def parent_window_select(self):
        w = self.window()
        if hasattr(w, "select_tool"):
            w.select_tool(SELECT)
        else:
            self.set_tool(SELECT)


def _dist(a: QPointF, b: QPointF) -> float:
    return math.hypot(a.x() - b.x(), a.y() - b.y())


def _seg_dist(p: QPointF, a: QPointF, b: QPointF) -> float:
    dx, dy = b.x() - a.x(), b.y() - a.y()
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / L))
    return math.hypot(p.x() - a.x() - t * dx, p.y() - a.y() - t * dy)
