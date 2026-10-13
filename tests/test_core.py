import os

import ezdxf
import pytest

from tests.synthetic import MARKS, ROOMS, make_phone_photo, make_plan
from ttysi_cadastre.detection import detect, find_paper_corners, warp_to_rect
from ttysi_cadastre.geometry import merge_rooms, split_room
from ttysi_cadastre.model import Building, Equipment, Floor, Room


def _bbox(points):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def test_detect_scanned_plan():
    res = detect(make_plan())
    assert len(res.rooms) == len(ROOMS)
    found = sorted(_bbox(r.points) for r in res.rooms)
    for exp, got in zip(sorted(ROOMS), found):
        assert all(abs(a - b) < 8 for a, b in zip(exp, got)), (exp, got)
    kinds = [r.kind for r in res.rooms]
    assert kinds.count("corridor") == 1
    assert len(res.marks) == len(MARKS)


def test_detect_phone_photo():
    photo = make_phone_photo(make_plan())
    img = warp_to_rect(photo, find_paper_corners(photo))
    res = detect(img)
    assert len(res.rooms) == len(ROOMS)
    assert len(res.marks) == len(MARKS)


def test_split_and_merge():
    sq = [(0, 0), (100, 0), (100, 50), (0, 50)]
    parts = split_room(sq, (50, 10), (50, 40))
    assert len(parts) == 2
    assert merge_rooms(parts, 2) is not None
    assert merge_rooms([sq, [(300, 0), (400, 0), (400, 50), (300, 50)]], 5) is None


def test_project_roundtrip(tmp_path):
    b = Building(name="Bino", address="Manzil")
    f = Floor(name="1-etaj", image=b"\x89PNGfake", width=100, height=80, scale_m_per_px=0.05)
    f.rooms.append(Room(points=[(0, 0), (10, 0), (10, 10)], kind="corridor", name="K"))
    f.equipment.append(Equipment(code="W", x=5, y=5, note="izoh"))
    b.floors.append(f)
    p = tmp_path / "t.ttysi"
    b.save(str(p))
    b2 = Building.load(str(p))
    f2 = b2.floors[0]
    assert (b2.name, b2.address) == ("Bino", "Manzil")
    assert f2.image == f.image and f2.scale_m_per_px == 0.05
    assert f2.rooms[0].kind == "corridor" and f2.equipment[0].note == "izoh"


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _sample():
    b = Building(name="Bino")
    f = Floor(name="1-etaj", width=1000, height=700, scale_m_per_px=0.02)
    f.rooms = [Room(points=[(100, 100), (500, 100), (500, 400), (100, 400)], name="101"),
               Room(points=[(500, 100), (900, 100), (900, 400), (500, 400)], kind="corridor")]
    f.equipment = [Equipment(code=c, x=200 + 80 * i, y=250) for i, c in enumerate(["SER", "KX", "K", "W", "S", "T", "?"])]
    b.floors.append(f)
    return b, f


def test_exports(qapp, tmp_path):
    from ttysi_cadastre.export import export_dxf, export_image, export_pdf, export_svg
    from ttysi_cadastre.render import RenderOptions
    b, f = _sample()
    for name, fn in (("a.png", lambda p: export_image(p, b, f, RenderOptions(), 1000)),
                     ("a.jpg", lambda p: export_image(p, b, f, RenderOptions(), 1000)),
                     ("a.svg", lambda p: export_svg(p, b, f, RenderOptions())),
                     ("a.pdf", lambda p: export_pdf(p, b, [f, f], RenderOptions())),
                     ("a.dxf", lambda p: export_dxf(p, b, f))):
        p = str(tmp_path / name)
        fn(p)
        assert os.path.getsize(p) > 500, name
    doc = ezdxf.readfile(str(tmp_path / "a.dxf"))
    assert not doc.audit().has_errors
    msp = doc.modelspace()
    assert len(msp.query("LWPOLYLINE")) == 2
    assert len(msp.query("INSERT")) == 7
    assert {e.dxf.layer for e in msp.query("INSERT")} >= {"AT_W", "AT_TASDIQLANMAGAN"}


def test_main_window(qapp):
    from ttysi_cadastre.ui.main_window import MainWindow
    b, f = _sample()
    w = MainWindow()
    w.building = b
    w.refresh_all()
    assert w.floor is f
    # '?' belgini tanlab, 4 (Wi-Fi) tugmasi bilan tasdiqlash
    w.select_next_unknown()
    assert w.on_digit("4")
    assert f.equipment[-1].code == "W"
    w.undo()
    assert f.equipment[-1].code == "?"
    w.dirty = False
    w.close()
