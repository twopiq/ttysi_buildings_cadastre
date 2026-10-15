"""Nisbat (1:200, 1:300 ...) bo'yicha masshtab va kadastr fonini chizmaga moslash."""

import os

import numpy as np
import pytest

from tests.synthetic import make_plan
from ttysi_cadastre.detection import DetectParams, encode_jpg
from ttysi_cadastre.geometry import bg_map
from ttysi_cadastre.model import Building, Floor, Room


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _window(floor):
    from ttysi_cadastre.ui.main_window import MainWindow
    b = Building(name="B")
    b.floors.append(floor)
    w = MainWindow()
    w.building = b
    w.refresh_all()
    w.scene.clearSelection()
    w.on_selection()
    return w


def _close(w):
    w.dirty = False
    w.close()


def test_ratio_from_pdf_paper(qapp):
    f = Floor(name="1", width=1000, height=700, scale_m_per_px=25.4 / 200 * 300 / 1000,
              ratio=300, paper_mm_per_px=25.4 / 200)
    w = _window(f)
    assert w.p_ratio.value() == 300 and "1:300" in w.floor_info.text()
    w.p_ratio.setValue(400)
    assert f.ratio == 400 and f.scale_m_per_px == pytest.approx(25.4 / 200 * 0.4)
    # tez tanlash ro'yxati
    box = w.p_ratio_preset
    box.setCurrentIndex(box.findData(200))
    assert f.ratio == 200 and box.currentIndex() == 0
    w.undo()
    assert f.ratio == 400
    _close(w)


def test_ratio_for_photo_after_two_point_scale(qapp, monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    f = Floor(name="1", width=1000, height=700)
    w = _window(f)
    assert "2 nuqta" in w.p_ratio_hint.text()
    w.p_ratio.setValue(200)                                   # faqat nisbat saqlanadi
    assert f.ratio == 200 and f.scale_m_per_px is None
    monkeypatch.setattr(QInputDialog, "getDouble", lambda *a, **k: (10.0, True))
    w.set_scale(500.0)                                         # 500 px = 10 m
    assert f.scale_m_per_px == pytest.approx(0.02)
    w.p_ratio.setValue(400)                                    # endi nisbat masshtabni o'zgartiradi
    assert f.scale_m_per_px == pytest.approx(0.04)
    _close(w)


def test_background_move_and_align(qapp):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest
    from ttysi_cadastre.ui.canvas import BG_ALIGN, BG_MOVE
    img = np.full((350, 500, 3), 255, np.uint8)
    f = Floor(name="1", image=encode_jpg(img), width=1000, height=700)
    f.rooms = [Room(points=[(100, 100), (400, 100), (400, 300), (100, 300)])]
    w = _window(f)
    w.resize(1400, 900)
    w.show()
    v = w.view
    v.resetTransform()
    v.centerOn(500, 350)
    # surish
    w.select_tool(BG_MOVE)
    a, b = v.mapFromScene(QPointF(500, 350)), v.mapFromScene(QPointF(530, 340))
    QTest.mousePress(v.viewport(), Qt.LeftButton, Qt.NoModifier, a)
    QTest.mouseMove(v.viewport(), b)
    QTest.mouseRelease(v.viewport(), Qt.LeftButton, Qt.NoModifier, b)
    assert (f.bg_dx, f.bg_dy) == (pytest.approx(30, abs=1.5), pytest.approx(-10, abs=1.5))
    assert len(f.rooms[0].points) == 4 and f.rooms[0].points[0] == (100, 100)      # chizma joyida
    item = w.scene.bg_item
    p = item.sceneTransform().map(QPointF(0, 0))                                   # rasm burchagi surildi
    assert (p.x(), p.y()) == (pytest.approx(f.bg_dx), pytest.approx(f.bg_dy))
    w.undo()
    assert (f.bg_dx, f.bg_dy) == (0, 0)

    # 2 nuqta: fondagi (200,200)->(250,150), (800,200)->(850,150): faqat surish
    w.select_tool(BG_ALIGN)
    for x, y in ((200, 200), (250, 150), (800, 200), (850, 150)):
        pt = v.mapFromScene(QPointF(x, y))
        QTest.mouseClick(v.viewport(), Qt.LeftButton, Qt.NoModifier, pt)
    assert f.bg_scale == pytest.approx(1, abs=0.01) and f.bg_rot == pytest.approx(0, abs=0.3)
    assert bg_map(f, 200, 200) == (pytest.approx(250, abs=2), pytest.approx(150, abs=2))
    # panel: burilish va o'lcham, keyin asl holiga
    w.select_tool("select")
    w.scene.clearSelection()
    w.on_selection()
    w.p_bg_rot.setValue(1.5)
    w.p_bg_scale.setValue(102)
    assert f.bg_rot == pytest.approx(1.5) and f.bg_scale == pytest.approx(1.02)
    w.reset_bg()
    assert f.bg_identity()
    # saqlash va eksport
    d = Floor.from_dict(f.to_dict(), None)
    assert d.bg_identity()
    f.bg_dx = 40
    g = Floor.from_dict(f.to_dict(), None)
    assert g.bg_dx == 40
    _close(w)


def test_detection_follows_background(qapp):
    img = make_plan(False)
    h, wd = img.shape[:2]
    from ttysi_cadastre.ui.main_window import MainWindow
    w = MainWindow()
    f1 = Floor(name="a", width=wd, height=h)
    w.apply_detection(f1, img, DetectParams(), keep_eq=False)
    f2 = Floor(name="b", width=wd, height=h, bg_dx=100, bg_dy=-20)
    w.apply_detection(f2, img, DetectParams(), keep_eq=False)
    p1 = np.array(f1.rooms[0].points)
    p2 = np.array(f2.rooms[0].points)
    assert np.allclose(p2 - p1, (100, -20))
    _close(w)


def test_import_stores_paper_and_ratio(qapp):
    from ttysi_cadastre.ui.import_dialog import ImportDialog
    from ttysi_cadastre.ui.main_window import MainWindow
    img = np.full((400, 600, 3), 255, np.uint8)
    w = MainWindow()
    dlg = ImportDialog(img, "1", w, paper_mm_per_px=0.2)
    dlg.full_corners()
    dlg.scale_presets.setCurrentIndex(dlg.scale_presets.findData(250))
    assert dlg.scale.value() == 250
    f = Floor(name="1", width=600, height=400)
    w._store_paper(f, dlg, img, img)
    assert f.ratio == 250 and f.paper_mm_per_px == pytest.approx(0.2)
    # telefon rasmi: nisbat ham kiritiladi
    dlg2 = ImportDialog(img, "2", w, paper_mm_per_px=None)
    assert dlg2.scale.isEnabled()
    _close(w)


def test_recalc_scale_for_old_floor(qapp):
    """Eski versiyada qo'shilgan etaj: nisbat bor, qog'oz o'lchami yo'q - "Qayta hisoblash" (DPI bo'yicha)."""
    from PySide6.QtWidgets import QDialog
    f = Floor(name="1-etaj", width=3000, height=1000, ratio=400)
    f.rooms = [Room(points=[(0, 0), (1000, 0), (1000, 500), (0, 500)])]
    w = _window(f)
    assert "Qayta hisoblash" in w.p_ratio_hint.text() and f.scale_m_per_px is None

    def hook(dlg):
        assert dlg.ratio() == 400 and dlg.dpi.currentText() == "200"
        assert "m²" in dlg.preview.text()
        return QDialog.Accepted
    assert w.recalc_scale(dialog_hook=hook)
    assert f.scale_m_per_px == pytest.approx(25.4 / 200 * 400 / 1000)
    assert f.paper_mm_per_px == pytest.approx(25.4 / 200)
    assert "m²" in w.floor_info.text() and "masshtab yo'q" not in w.floor_info.text()
    w.p_ratio.setValue(300)                                    # endi nisbat o'zgarsa darhol hisoblanadi
    assert f.scale_m_per_px == pytest.approx(25.4 / 200 * 0.3)
    w.undo()
    assert f.ratio == 400

    # boshqa DPI va 2 nuqta usuli
    def hook2(dlg):
        dlg.dpi.setCurrentText("300")
        return QDialog.Accepted
    assert w.recalc_scale(dialog_hook=hook2)
    assert f.scale_m_per_px == pytest.approx(25.4 / 300 * 0.4)

    def hook3(dlg):
        dlg.r_points.setChecked(True)
        return QDialog.Accepted
    assert not w.recalc_scale(dialog_hook=hook3)
    assert w.view.tool == "scale"
    _close(w)
