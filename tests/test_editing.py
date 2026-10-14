"""Eshik tomoni va kengligi, zina yo'nalishi, elementlar o'lchamini o'zgartirish."""

import math
import os

import pytest

from ttysi_cadastre.geometry import auto_stair_direction, stair_lines
from ttysi_cadastre.model import Building, Equipment, Floor, Room


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _window():
    from ttysi_cadastre.ui.main_window import MainWindow
    b = Building(name="B")
    f = Floor(name="1", width=1000, height=700, scale_m_per_px=0.02)        # 1 m = 50 px
    f.rooms = [Room(points=[(100, 100), (500, 100), (500, 400), (100, 400)], name="101"),
               Room(points=[(600, 100), (700, 100), (700, 400), (600, 400)], kind="stairs")]
    f.equipment = [Equipment(code="K", x=200, y=200)]
    b.floors.append(f)
    w = MainWindow()
    w.building = b
    w.refresh_all()
    return w, f


def _close(w):
    w.dirty = False
    w.close()


def _item(w, cls, pred=lambda it: True):
    return next(i for i in w.scene.items() if isinstance(i, cls) and pred(i))


def test_door_opens_to_clicked_side(qapp):
    from PySide6.QtCore import QPointF
    w, f = _window()
    # yuqori devor (y=100): ichkaridan (pastdan) va tashqaridan (tepadan) bosish
    inside = w.scene.add_door(QPointF(300, 120))
    outside = w.scene.add_door(QPointF(420, 80))
    assert inside.door.y == pytest.approx(100) and outside.door.y == pytest.approx(100)
    assert inside.door.flip != outside.door.flip

    def opening_y(door):
        from ttysi_cadastre.geometry import door_lines
        leaf = door_lines(door, 10)[2]                 # ochiq tabaqa chizig'i
        return leaf[1][1]
    assert opening_y(inside.door) > 100 and opening_y(outside.door) < 100
    # ikki marta bosish - tomonini almashtirish
    before = inside.door.flip
    inside.mouseDoubleClickEvent(None)
    assert inside.door.flip != before
    _close(w)


def test_door_width_handles_and_panel(qapp):
    from PySide6.QtCore import QPointF
    from ttysi_cadastre.ui.canvas import DoorItem
    w, f = _window()
    d = w.scene.add_door(QPointF(300, 110))
    w.scene.clearSelection()
    d.setSelected(True)
    assert w.props.currentIndex() == 5 and len(d.width_handles) == 2
    assert w.p_door_w.value() == pytest.approx(0.9)
    w.p_door_w.setValue(1.5)
    assert d.door.width == pytest.approx(75)
    d.set_width(10_000)                                 # chegaralangan: 4 m
    assert d.door.width == pytest.approx(200)
    w.p_door_leaves.setCurrentIndex(1)
    w.on_door_props()
    assert d.door.leaves == 2
    w.undo()
    assert _item(w, DoorItem).door.leaves == 1
    _close(w)


def test_stairs_direction(qapp):
    pts = [(0, 0), (100, 0), (100, 300), (0, 300)]
    assert auto_stair_direction(pts) == "up"
    lines = {d: stair_lines(pts, 20, d) for d in ("up", "down", "left", "right")}
    tip = {d: ln[-1][1] for d, ln in lines.items()}               # strelka uchi
    assert tip["up"][1] < tip["down"][1]
    assert tip["left"][0] < tip["right"][0]
    # o'ngga/chapga - pog'onalar vertikal chiziqlar
    step = lines["right"][0]
    assert step[0][0] == pytest.approx(step[-1][0])

    w, f = _window()
    from ttysi_cadastre.ui.canvas import RoomItem
    st = _item(w, RoomItem, lambda i: i.room.kind == "stairs")
    w.scene.clearSelection()
    st.setSelected(True)
    assert not w.p_stairs.parentWidget().isHidden()
    w.turn_stairs()
    assert f.rooms[1].direction == "right"                        # up -> right (soat bo'yicha)
    w.p_stairs_dir.setCurrentIndex(w.p_stairs_dir.findData("down"))
    w.on_stairs_dir()
    assert f.rooms[1].direction == "down"
    # saqlash/ochishda yo'nalish saqlanadi
    d = f.to_dict()
    g = Floor.from_dict(d, None)
    assert g.rooms[1].direction == "down"
    # oddiy xonada zina sozlamasi ko'rinmaydi
    room = _item(w, RoomItem, lambda i: i.room.kind == "room")
    w.scene.clearSelection()
    room.setSelected(True)
    assert w.p_stairs.parentWidget().isHidden()
    _close(w)


def test_resize_handles_and_size_fields(qapp):
    from PySide6.QtCore import QPointF
    from ttysi_cadastre.ui.canvas import RoomItem
    w, f = _window()
    room = _item(w, RoomItem, lambda i: i.room.kind == "room")
    w.scene.clearSelection()
    room.setSelected(True)
    assert len(room.resize_handles) == 8
    assert w.p_room_w.value() == pytest.approx(8.0) and w.p_room_h.value() == pytest.approx(6.0)
    # o'ng-pastki burchakni sudrash: chap-yuqori joyida qoladi
    room.resize_begin()
    room.resize_to((1, 1), QPointF(700, 500))
    room.resize_end()
    assert f.rooms[0].points == [(100, 100), (700, 100), (700, 500), (100, 500)]
    # chap qirra: faqat eni o'zgaradi
    room.resize_begin()
    room.resize_to((-1, 0), QPointF(400, 9999))
    room.resize_end()
    xs = sorted({p[0] for p in f.rooms[0].points})
    ys = sorted({p[1] for p in f.rooms[0].points})
    assert xs == [400, 700] and ys == [100, 500]
    # Shift - nisbat saqlanadi
    room.resize_begin()
    room.resize_to((1, 1), QPointF(1000, 520), keep=True)
    room.resize_end()
    x0, y0, x1, y1 = room.bbox()
    assert (x1 - x0, y1 - y0) == (pytest.approx(600), pytest.approx(800))      # 300x400 -> 2 baravar
    # aniq o'lcham (metr)
    room.setSelected(False)
    room.setSelected(True)
    w.p_room_w.setValue(10)
    w.p_room_h.setValue(4)
    x0, y0, x1, y1 = room.bbox()
    assert (x1 - x0, y1 - y0) == (pytest.approx(500), pytest.approx(200))
    w.undo()
    x0, y0, x1, y1 = _item(w, RoomItem, lambda i: i.room.kind == "room").bbox()
    assert (x1 - x0) == pytest.approx(500)
    _close(w)


def test_grow_shrink(qapp):
    from PySide6.QtCore import QPointF
    from ttysi_cadastre.ui.canvas import RoomItem
    w, f = _window()
    room = _item(w, RoomItem, lambda i: i.room.kind == "room")
    w.scene.clearSelection()
    room.setSelected(True)
    w.scale_selected(1.1)
    x0, y0, x1, y1 = room.bbox()
    assert (x1 - x0) == pytest.approx(440) and (x0 + x1) / 2 == pytest.approx(300)   # markaz joyida
    d = w.scene.add_door(QPointF(300, 110))
    w.scene.clearSelection()
    d.setSelected(True)
    w.scale_selected(2)
    assert d.door.width == pytest.approx(90)
    # faqat AT belgisi tanlansa - etajdagi belgilar o'lchami
    w.scene.clearSelection()
    w.scene.equipment_items()[0].setSelected(True)
    w.scale_selected(1.5)
    assert f.symbol_scale == pytest.approx(1.5)
    from ttysi_cadastre.render import symbol_radius
    assert symbol_radius(f) == pytest.approx(50 * 0.55 * 1.5)
    assert math.isclose(Floor.from_dict(f.to_dict(), None).symbol_scale, 1.5)
    _close(w)
