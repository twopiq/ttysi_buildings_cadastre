"""AT belgilarini alohida aniqlash (qo'lyozma) va uning oynasi."""

import os

import cv2
import numpy as np
import pytest

from ttysi_cadastre.detection import encode_jpg
from ttysi_cadastre.marks import MarkParams, detect_marks
from ttysi_cadastre.model import Building, Equipment, Floor, Room

PEN = [(300, 300), (900, 260), (500, 700), (1300, 800)]      # qo'lyozma belgilar markazlari


def _plan(print_gray: int, pen=True, blue=False) -> np.ndarray:
    img = np.full((1100, 1600, 3), 250, np.uint8)
    g = (print_gray,) * 3
    for x0, y0, x1, y1 in ((100, 100, 1500, 1000), (100, 100, 800, 550), (800, 100, 1500, 550),
                           (100, 550, 800, 1000)):
        cv2.rectangle(img, (x0, y0), (x1, y1), g, 6)
    cv2.putText(img, "101", (400, 450), cv2.FONT_HERSHEY_SIMPLEX, 1.0, g, 2)
    cv2.rectangle(img, (1100, 600), (1130, 630), g, -1)               # ustun (shtrixlangan kvadrat)
    if pen:
        for x, y in PEN:                                              # "X" va "S" ga o'xshash
            cv2.line(img, (x - 18, y - 22), (x + 18, y + 22), (15, 15, 15), 5)
            cv2.line(img, (x + 18, y - 22), (x - 18, y + 22), (15, 15, 15), 5)
            cv2.ellipse(img, (x + 40, y), (12, 18), 30, 0, 300, (20, 20, 20), 4)
    if blue:
        cv2.circle(img, (1200, 300), 20, (200, 60, 20), 5)
    return img


def _near(marks, pts, tol=60):
    return all(any(abs(m.x - x) < tol and abs(m.y - y) < tol for m in marks) for x, y in pts)


def test_black_handwriting_on_gray_print():
    marks = detect_marks(_plan(140))
    assert _near(marks, PEN)
    assert len(marks) <= len(PEN) + 1                    # bosma chiziqlar, ustun, raqamlar belgi emas
    assert all(m.color == "black" for m in marks)


def test_black_print_gives_nothing():
    assert detect_marks(_plan(0, pen=False)) == []


def test_blue_pen():
    marks = detect_marks(_plan(140, pen=False, blue=True), MarkParams(black=False))
    assert len(marks) == 1 and marks[0].color == "blue" and abs(marks[0].x - 1200) < 30


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _window(img):
    from ttysi_cadastre.ui.main_window import MainWindow
    h, w = img.shape[:2]
    f = Floor(name="1-qavat", image=encode_jpg(img), width=w // 2, height=h // 2, scale_m_per_px=0.04)
    f.rooms = [Room(points=[(50, 50), (750, 50), (750, 500), (50, 500)], name="1")]
    f.equipment = [Equipment(code="K", x=150, y=150), Equipment(code="?", x=700, y=450)]
    b = Building(name="B")
    b.floors.append(f)
    w = MainWindow()
    w.building = b
    w.refresh_all()
    return w, f


def test_dialog_replace_and_add(qapp):
    from PySide6.QtWidgets import QDialog
    w, f = _window(_plan(140))

    def hook(dlg):
        assert len(dlg.marks()) >= len(PEN)
        dlg.items[0].excluded = True                     # bittasini chiqarib tashlash
        return QDialog.Accepted
    n = w.detect_marks(dialog_hook=hook, review=False)
    unknown = [e for e in f.equipment if e.code == "?"]
    # 4 ta nomzod: 1 tasi chiqarib tashlandi, 1 tasi tasdiqlangan K ustida - takror; eski "?" almashtirildi
    assert n == len(unknown) == 2
    assert all(abs(e.x - 700) > 5 for e in unknown)
    assert any(e.code == "K" for e in f.equipment)     # tasdiqlanganlar saqlanadi
    assert all(e.x < 800 and e.y < 550 for e in unknown)  # chizma koordinatalarida (rasm / 2)

    def add(dlg):
        dlg.r_add.setChecked(True)
        return QDialog.Accepted
    before = len(f.equipment)
    assert w.detect_marks(dialog_hook=add, review=False) <= 1   # takrorlar qo'shilmaydi
    assert len(f.equipment) - before <= 1
    w.undo()
    w.dirty = False
    w.close()


def test_dialog_inside_filter(qapp):
    from PySide6.QtWidgets import QDialog
    img = _plan(140)
    w, f = _window(img)
    f.rooms = [Room(points=[(50, 50), (400, 50), (400, 275), (50, 275)], name="1")]  # faqat chap yuqori xona

    def hook(dlg):
        assert dlg.c_inside.isChecked()
        inside = dlg.marks()
        dlg.c_inside.setChecked(False)
        dlg.run()
        assert len(dlg.marks()) > len(inside) >= 1
        return QDialog.Rejected
    assert w.detect_marks(dialog_hook=hook) == 0
    w.dirty = False
    w.close()
