"""Etajning kadastr rasmini almashtirish."""

import os

import cv2
import numpy as np
import pytest

from tests.synthetic import ROOMS, make_plan
from ttysi_cadastre.detection import encode_jpg
from ttysi_cadastre.model import Building, Door, Equipment, Floor, Room, Wall


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _window(tmp_path):
    from ttysi_cadastre.ui.main_window import MainWindow
    old = np.full((500, 800, 3), 255, np.uint8)
    f = Floor(name="2-qavat", image=encode_jpg(old), width=800, height=500, scale_m_per_px=0.02)
    f.rooms = [Room(points=[(100, 100), (300, 100), (300, 300), (100, 300)], name="201")]
    f.walls = [Wall(points=[(400, 100), (600, 100)], thickness=15)]
    f.doors = [Door(x=200, y=100, width=45)]
    f.equipment = [Equipment(code="K", x=150, y=150), Equipment(code="?", x=250, y=250)]
    b = Building(name="B")
    b.floors.append(f)
    w = MainWindow()
    w.building = b
    w.refresh_all()
    return w, f


def _accept(**opts):
    from PySide6.QtWidgets import QDialog

    def hook(dlg):
        assert not dlg.name.isEnabled() and dlg.b_create.text() == "Rasmni almashtirish"
        dlg.full_corners()
        for k, v in opts.items():
            if k == "auto":
                dlg.auto.setChecked(v)
            elif k == "scale":
                dlg.scale.setValue(v)
        return QDialog.Accepted
    return hook


def test_replace_keeps_drawing_in_place(qapp, tmp_path):
    w, f = _window(tmp_path)
    new = np.full((1000, 1600, 3), 230, np.uint8)            # 2 baravar katta skaner
    p = str(tmp_path / "yangi.png")
    cv2.imwrite(p, new)
    old_image = f.image
    assert w.replace_floor_image(p, dialog_hook=_accept(auto=False))
    assert f.image != old_image and (f.width, f.height) == (1600, 1000)
    assert f.rooms[0].points[0] == pytest.approx((200, 200)) and f.rooms[0].name == "201"
    assert f.walls[0].thickness == pytest.approx(30)
    assert (f.doors[0].x, f.doors[0].width) == (pytest.approx(400), pytest.approx(90))
    assert f.equipment[1].code == "?" and f.equipment[1].x == pytest.approx(500)
    assert f.scale_m_per_px == pytest.approx(0.01)             # masshtab ham moslandi (1 m - o'sha joyda)
    assert w.background_for(f).width() == 1600                  # yangi fon ko'rsatilmoqda
    assert w.dirty
    w.undo()                                                    # tarix yangi rasmdan boshlanadi
    assert f.rooms[0].points[0] == pytest.approx((200, 200))
    w.dirty = False
    w.close()


def test_replace_and_redetect(qapp, tmp_path):
    w, f = _window(tmp_path)
    p = str(tmp_path / "plan.png")
    cv2.imwrite(p, make_plan(False))
    assert w.replace_floor_image(p, dialog_hook=_accept(auto=True))
    assert len(f.rooms) == len(ROOMS)                           # xonalar yangi rasmdan
    codes = [e.code for e in f.equipment]
    assert "K" in codes                                         # tasdiqlangan belgi saqlandi
    assert len(f.walls) == 1 and len(f.doors) == 1              # qo'lda chizilganlar saqlandi
    w.dirty = False
    w.close()


def test_cancel_changes_nothing(qapp, tmp_path):
    from PySide6.QtWidgets import QDialog
    w, f = _window(tmp_path)
    p = str(tmp_path / "x.png")
    cv2.imwrite(p, np.full((100, 100, 3), 255, np.uint8))
    before = f.to_dict(), f.image
    assert not w.replace_floor_image(p, dialog_hook=lambda d: QDialog.Rejected)
    assert (f.to_dict(), f.image) == before and not w.dirty
    w.close()


def test_remove_image(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    w, f = _window(tmp_path)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    w.remove_floor_image()
    assert f.image is None and len(f.rooms) == 1 and w.dirty
    w.dirty = False
    w.close()
