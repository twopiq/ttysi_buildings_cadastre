"""Chizma muharriri: xonalar, koridorlar va AT jihozlarini chizish va tahrirlash."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen,
                           QPixmap, QPolygonF)
from PySide6.QtWidgets import (QGraphicsItem,
                               QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsPolygonItem,
                               QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem,
                               QGraphicsView, QMenu)

from ..equipment import ROOM_KINDS, get_type
from ..model import Equipment, Floor, Room
from ..render import draw_equipment_symbol, label_px, room_label, symbol_radius, wall_width

# Asboblar
SELECT, ROOM_POLY, ROOM_RECT, EQUIP, SPLIT, SCALE, PAN = (
    "select", "room_poly", "room_rect", "equip", "split", "scale", "pan")

SNAP_PX = 10   # ekran piksellarida yopishish masofasi


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


class RoomItem(QGraphicsPolygonItem):
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

    def show_handles(self, on: bool):
        for h in self.handles:
            h.setParentItem(None)
            if h.scene():
                h.scene().removeItem(h)
        self.handles = []
        if on:
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

    def mouseDoubleClickEvent(self, event):
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
        add_v = menu.addAction("Shu yerga burchak qo'shish")
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
        elif act == add_v:
            self.insert_vertex_at(event.scenePos())
        elif act == merge:
            scene.request_merge.emit()
        elif act == delete:
            scene.delete_selected()


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
        tip = t.name + (f"\n{self.eq.note}" if self.eq.note else "")
        if t.code == "?":
            tip += "\nTurini tanlash: 1-6 tugmalari"
        self.setToolTip(tip)

    def boundingRect(self):
        r = self.r * 1.6
        return QRectF(-r, -r, 2 * r, 2 * r)

    def paint(self, p: QPainter, option, widget=None):
        p.setRenderHint(QPainter.Antialiasing)
        draw_equipment_symbol(p, self.eq.code, QPointF(0, 0), self.r)
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

    def selected_equipment(self) -> list[EquipmentItem]:
        return [i for i in self.selectedItems() if isinstance(i, EquipmentItem)]

    def add_room(self, points, kind="room") -> RoomItem:
        room = Room(points=[(p.x(), p.y()) if isinstance(p, QPointF) else p for p in points], kind=kind)
        self.floor.rooms.append(room)
        item = RoomItem(room, self.floor)
        self.addItem(item)
        self.changed_model.emit()
        return item

    def add_equipment(self, code: str, pos: QPointF) -> EquipmentItem:
        eq = Equipment(code=code, x=pos.x(), y=pos.y())
        self.floor.equipment.append(eq)
        item = EquipmentItem(eq, self.floor)
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
        super().mouseReleaseEvent(event)
        if moved:
            self.changed_model.emit()


class FloorView(QGraphicsView):
    """Kattalashtirish (g'ildirak), surish (o'rta tugma / Probel) va chizish asboblari."""

    status = Signal(str)
    split_requested = Signal(QPointF, QPointF)
    scale_requested = Signal(float)   # piksel masofasi

    def __init__(self, scene: FloorScene):
        super().__init__(scene)
        self.fscene = scene
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setBackgroundBrush(QColor("#eceff1"))
        self.tool = SELECT
        self.equip_code = "K"
        self.points: list[QPointF] = []
        self.preview: QGraphicsPathItem | None = None
        self.rect_start: QPointF | None = None
        self._panning = False
        self._pan_last = None
        self._space = False
        self.digit_pressed = None   # oyna tomonidan beriladi: f(key) -> bool

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
        if self.tool == ROOM_RECT and self.rect_start is not None and cursor is not None:
            path.addRect(QRectF(self.rect_start, cursor).normalized())
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
        self.scale(f, f)
        self.fscene.view_scale = self.transform().m11()

    def zoom_fit(self):
        if self.fscene.floor:
            f = self.fscene.floor
            self.fitInView(QRectF(0, 0, f.width, f.height), Qt.KeepAspectRatio)
            self.fscene.view_scale = self.transform().m11()

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
        elif self.tool == ROOM_RECT:
            self.rect_start = p
        elif self.tool == EQUIP:
            self.fscene.add_equipment(self.equip_code, p)
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
        if self.tool in (ROOM_POLY, SPLIT, SCALE) and self.points:
            p = self._ortho_lock(self._snapped(event.position().toPoint()),
                                 bool(event.modifiers() & Qt.ShiftModifier))
            self._update_preview(p)
        elif self.tool == ROOM_RECT and self.rect_start is not None:
            self._update_preview(self._snapped(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            self.viewport().setCursor(Qt.ArrowCursor if self.tool == SELECT else Qt.CrossCursor)
            return
        if self.tool == ROOM_RECT and self.rect_start is not None and event.button() == Qt.LeftButton:
            r = QRectF(self.rect_start, self._snapped(event.position().toPoint())).normalized()
            self.cancel_drawing()
            if r.width() > 3 and r.height() > 3:
                self.fscene.add_room([r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()])
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.tool == ROOM_POLY:
            self.finish_polygon()
            return
        super().mouseDoubleClickEvent(event)

    def finish_polygon(self):
        pts = self.points
        # ikki marta bosishdagi takror nuqtani olib tashlash
        while len(pts) >= 2 and _dist(pts[-1], pts[-2]) < 1e-6:
            pts.pop()
        self.cancel_drawing()
        if len(pts) >= 3:
            self.fscene.add_room(pts)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space and not event.isAutoRepeat():
            self._space = True
            self.viewport().setCursor(Qt.OpenHandCursor)
            return
        if event.text() and event.text() in "123456" and not event.modifiers() & ~Qt.KeypadModifier:
            if self.digit_pressed and self.digit_pressed(event.text()):
                return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and self.tool == ROOM_POLY:
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
