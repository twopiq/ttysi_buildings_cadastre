"""Gumbazli (doira) o'tish binolari: aniqlash, chizish asbobi, saqlash va eksport."""

import math
import os

import cv2
import numpy as np
import pytest

from tests.synthetic import make_plan
from ttysi_cadastre.detection import DetectParams, detect
from ttysi_cadastre.model import Building, Floor, Room


def make_dome(size=900, r=300, gap_deg=36, wall=10):
    """Kadastrdagidek: qo'sh chiziqli aylana devor, tepada va pastda kirish, atrofida ustunlar, ichida yozuv."""
    img = np.full((size, size, 3), 255, np.uint8)
    c = (size // 2, size // 2)
    for start, end in ((-90 + gap_deg / 2, 90 - gap_deg / 2), (90 + gap_deg / 2, 270 - gap_deg / 2)):
        for rr in (r, r + wall):
            cv2.ellipse(img, c, (rr, rr), 0, start, end, (40, 40, 40), 2)
    for k in range(8):                                   # ustunlar
        a = math.radians(22.5 + 45 * k)
        x, y = int(c[0] + (r + 25) * math.cos(a)), int(c[1] + (r + 25) * math.sin(a))
        cv2.rectangle(img, (x - 12, y - 12), (x + 12, y + 12), (40, 40, 40), 2)
    cv2.putText(img, "1", (c[0] - 10, c[1] - 20), cv2.FONT_HERSHEY_SIMPLEX, 1, (40, 40, 40), 2)
    cv2.putText(img, "66.47", (c[0] - 50, c[1] + 25), cv2.FONT_HERSHEY_SIMPLEX, 1, (40, 40, 40), 2)
    return img, c, r


def test_detect_dome_with_entrances():
    img, c, r = make_dome()
    res = detect(img, DetectParams())
    domes = [rm for rm in res.rooms if rm.shape == "ellipse"]
    assert len(domes) == 1 and domes[0].kind == "dome"
    pts = np.array(domes[0].points)
    assert np.allclose(pts.mean(0), c, atol=6)
    radius = np.hypot(*(pts - pts.mean(0)).T).mean()
    assert radius == pytest.approx(r, rel=0.04)
    # boshqa (bo'lak) xonalar doira ichida qolmagan
    assert all(cv2.pointPolygonTest(pts.astype(np.float32), tuple(np.mean(rm.points, 0)), False) < 0
               for rm in res.rooms if rm.shape != "ellipse")
    assert len(res.doors) == 2
    angles = sorted(round(math.degrees(math.atan2(d.y - c[1], d.x - c[0]))) for d in res.doors)
    assert angles[0] == pytest.approx(-90, abs=4) and angles[1] == pytest.approx(90, abs=4)
    for d in res.doors:
        assert d.width == pytest.approx(2 * r * math.sin(math.radians(18)), rel=0.35)


def test_no_dome_on_rectangular_plan():
    for noisy in (False, True):
        res = detect(make_plan(noisy), DetectParams())
        assert not any(rm.shape == "ellipse" for rm in res.rooms)
        assert not res.doors


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_dome_tool_and_editing(qapp, tmp_path):
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtTest import QTest
    from ttysi_cadastre.ui.canvas import DOME, SELECT, RoomItem
    from ttysi_cadastre.ui.main_window import MainWindow
    b = Building(name="B")
    f = Floor(name="1", width=1000, height=800, scale_m_per_px=0.02)
    b.floors.append(f)
    w = MainWindow()
    w.building = b
    w.refresh_all()
    w.resize(1400, 900)
    w.show()
    w.select_tool(DOME)
    v = w.view
    v.resetTransform()
    v.centerOn(500, 400)
    a = v.mapFromScene(QPointF(300, 200))
    z = v.mapFromScene(QPointF(500, 350))           # torilgan to'rtburchak - doira (kattasi bo'yicha)
    QTest.mousePress(v.viewport(), Qt.LeftButton, Qt.NoModifier, a)
    QTest.mouseMove(v.viewport(), z)
    QTest.mouseRelease(v.viewport(), Qt.LeftButton, Qt.NoModifier, z)
    assert len(f.rooms) == 1
    room = f.rooms[0]
    assert room.kind == "dome" and room.shape == "ellipse" and len(room.points) == 72
    xs, ys = [p[0] for p in room.points], [p[1] for p in room.points]
    assert (max(xs) - min(xs)) == pytest.approx(max(ys) - min(ys), rel=0.02)   # aniq doira
    assert room.area() * 0.02 ** 2 == pytest.approx(math.pi * 2 ** 2, rel=0.03)  # r = 200 px = 4 m

    item = next(i for i in w.scene.items() if isinstance(i, RoomItem))
    w.select_tool(SELECT)
    w.scene.clearSelection()
    item.setSelected(True)
    assert item.handles == [] and len(item.resize_handles) == 8     # burchak nuqtalari yo'q, o'lcham bor
    w.p_room_w.setValue(10)
    w.p_room_h.setValue(6)                                              # ellipsga aylanadi
    x0, y0, x1, y1 = item.bbox()
    assert (x1 - x0, y1 - y0) == (pytest.approx(500), pytest.approx(300))

    # saqlash / ochish va eksport
    p = str(tmp_path / "g.ttysi")
    b.save(p)
    g = Building.load(p).floors[0].rooms[0]
    assert g.shape == "ellipse" and g.kind == "dome"
    from ttysi_cadastre.export import export_dxf, export_image
    from ttysi_cadastre.render import RenderOptions
    export_dxf(str(tmp_path / "g.dxf"), b, f)
    import ezdxf
    layers = {e.dxf.layer for e in ezdxf.readfile(str(tmp_path / "g.dxf")).modelspace()}
    assert "GUMBAZ" in layers and "XONA_DOME" in layers
    export_image(str(tmp_path / "g.png"), b, f, RenderOptions(), 800)
    assert os.path.getsize(tmp_path / "g.png") > 1000
    w.dirty = False
    w.close()


def test_apply_detection_adds_entrance_doors(qapp):
    from ttysi_cadastre.ui.main_window import MainWindow
    img, c, r = make_dome()
    w = MainWindow()
    f = Floor(name="1", width=img.shape[1], height=img.shape[0])
    w.apply_detection(f, img, DetectParams(), keep_eq=False)
    assert sum(rm.shape == "ellipse" for rm in f.rooms) == 1
    assert len(f.doors) == 2
    w.apply_detection(f, img, DetectParams(), keep_eq=False)            # qayta chizishda takrorlanmaydi
    assert len(f.doors) == 2
    w.dirty = False
    w.close()
    assert Room(points=[(0, 0), (1, 0), (0, 1)]).shape == ""
