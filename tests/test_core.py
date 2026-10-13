import os

import ezdxf
import pytest

from tests.synthetic import MARKS, ROOMS, make_double_line_plan, make_phone_photo, make_plan
from ttysi_cadastre.detection import DetectParams, detect, find_paper_corners, warp_to_rect
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


def test_detect_double_line_walls_with_scale():
    """Kadastr uslubi: qo'sh ingichka chiziqli devorlar, eshik yoylari, masshtab ma'lum."""
    mpp = 0.025
    res = detect(make_double_line_plan(mpp), DetectParams(m_per_px=mpp, wall_m=0.3, door_m=1.2))
    assert len(res.rooms) == len(ROOMS)
    found = sorted(_bbox(r.points) for r in res.rooms)
    for exp, got in zip(sorted(ROOMS), found):
        assert all(abs(a - b) < 10 for a, b in zip(exp, got)), (exp, got)
    assert [r.kind for r in res.rooms].count("corridor") == 1


def test_corridor_with_exterior_entrance_is_kept():
    """Tashqi kirish eshigi bor koridor tashqi maydon deb tushib qolmasligi kerak."""
    mpp = 0.025
    res = detect(make_double_line_plan(mpp, entrance=True), DetectParams(m_per_px=mpp, wall_m=0.3, door_m=1.2))
    corridors = [r for r in res.rooms if r.kind == "corridor"]
    assert len(corridors) == 1
    x0, y0, x1, y1 = _bbox(corridors[0].points)
    assert x1 - x0 > 900 and 100 < y1 - y0 < 140
    assert len(res.rooms) == len(ROOMS)


def test_room_contains_and_room_of():
    f = Floor(name="x")
    big = Room(points=[(0, 0), (100, 0), (100, 100), (0, 100)], name="katta")
    small = Room(points=[(10, 10), (30, 10), (30, 30), (10, 30)], name="kichik")
    f.rooms = [big, small]
    assert f.room_of(Equipment(code="T", x=20, y=20)) is small
    assert f.room_of(Equipment(code="T", x=60, y=60)) is big
    assert f.room_of(Equipment(code="T", x=160, y=60)) is None


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


def test_excel_report(tmp_path):
    import openpyxl
    from ttysi_cadastre.report import export_excel
    b, f = _sample()
    f.equipment += [Equipment(code="T", x=150, y=150), Equipment(code="T", x=160, y=150)]
    p = str(tmp_path / "h.xlsx")
    export_excel(p, [b, b])
    wb = openpyxl.load_workbook(p)
    rows = list(wb["Umumiy"].iter_rows(values_only=True))
    head = rows[0]
    first = dict(zip(head, rows[1]))
    assert first["T"] == 3 and first["W"] == 1 and first["Tasdiqlanmagan"] == 1
    total = dict(zip(head, rows[-1]))
    assert total["Bino"] == "BARCHA BINOLAR" and total["T"] == 6
    rooms = [dict(zip(rows_h, r)) for rows_h in [next(wb["Xonalar"].iter_rows(values_only=True))]
             for r in list(wb["Xonalar"].iter_rows(values_only=True))[1:]]
    r101 = next(r for r in rooms if r["Xona №"] == "101")
    assert r101["T"] == 2 and r101["W"] == 1 and r101["Maydon, m²"] == 48.0
    corridor = next(r for r in rooms if r["Turi"] == "Koridor")
    assert corridor["T"] == 1 and corridor["Tasdiqlanmagan"] == 1
    assert wb["Jihozlar"].max_row == 1 + 2 * 9


def test_pdf_page_render(qapp, tmp_path):
    """PDF sahifasini rasm va qog'oz o'lchami (mm/piksel) bilan olish."""
    from PySide6.QtCore import QMarginsF, QRectF
    from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
    from PySide6.QtPdf import QPdfDocument
    from ttysi_cadastre.ui.import_dialog import PdfPageDialog, cv_to_qimage
    p = str(tmp_path / "k.pdf")
    w = QPdfWriter(p)
    w.setPageLayout(QPageLayout(QPageSize(QPageSize.A3), QPageLayout.Landscape, QMarginsF(0, 0, 0, 0)))
    painter = QPainter(w)
    r = w.pageLayout().paintRectPixels(w.resolution())
    painter.drawImage(QRectF(0, 0, r.width(), r.height()), cv_to_qimage(make_plan(False)))
    painter.end()
    doc = QPdfDocument()
    doc.load(p)
    dlg = PdfPageDialog(doc)
    img, mm_per_px = dlg.render()
    assert img.shape[1] == pytest.approx(420 / 25.4 * 200, rel=0.01)
    assert mm_per_px == pytest.approx(25.4 / 200)
    assert len(detect(img).rooms) == len(ROOMS)


def test_planned_equipment(qapp, tmp_path):
    """Rejadagi (kerak) jihozlar: saqlash, Excel, DXF va oynadagi almashtirish."""
    import openpyxl
    from ttysi_cadastre.export import export_dxf, export_image
    from ttysi_cadastre.render import RenderOptions
    from ttysi_cadastre.report import export_excel
    b, f = _sample()
    f.rooms[0].kind = "computer"
    f.equipment += [Equipment(code="S", x=150, y=150, status="planned", note="kompyuter xona uchun"),
                    Equipment(code="T", x=160, y=150, status="planned")]

    # fayl
    p = str(tmp_path / "r.ttysi")
    b.save(p)
    f2 = Building.load(p).floors[0]
    assert [e.status for e in f2.equipment].count("planned") == 2

    # Excel: umumiy varaqda faqat mavjudlar, "Kerak (reja)" varag'ida rejadagilar
    x = str(tmp_path / "r.xlsx")
    export_excel(x, [b])
    wb = openpyxl.load_workbook(x)
    rows = list(wb["Umumiy"].iter_rows(values_only=True))
    first = dict(zip(rows[0], rows[1]))
    assert first["S"] == 1 and first["T"] == 1 and first["Kerak (rejada)"] == 2
    plan = list(wb["Kerak (reja)"].iter_rows(values_only=True))
    floor_row = dict(zip(plan[0], plan[1]))
    assert floor_row["S"] == 1 and floor_row["T"] == 1 and floor_row["Jami"] == 2
    assert any(r and r[2] == "101" and r[3] == "S" for r in plan)
    rooms = list(wb["Xonalar"].iter_rows(values_only=True))
    r101 = dict(zip(rooms[0], next(r for r in rooms if r[2] == "101")))
    assert r101["Turi"] == "Kompyuter xona" and r101["Kerak (rejada)"] == "S×1, T×1"
    jih = list(wb["Jihozlar"].iter_rows(values_only=True))
    assert [r[6] for r in jih[1:]].count("Kerak") == 2

    # DXF: alohida punktir qatlam
    d = str(tmp_path / "r.dxf")
    export_dxf(d, b, f)
    doc = ezdxf.readfile(d)
    assert doc.layers.get("AT_S_KERAK").dxf.linetype == "DASHED"
    assert {e.dxf.layer for e in doc.modelspace().query("INSERT")} >= {"AT_S_KERAK", "AT_T_KERAK", "AT_S"}
    export_image(str(tmp_path / "r.png"), b, f, RenderOptions(), 1000)

    # oyna: Ctrl+K bilan holatni almashtirish va bekor qilish
    from ttysi_cadastre.ui.main_window import MainWindow
    w = MainWindow()
    w.building = b
    w.refresh_all()
    item = next(i for i in w.scene.equipment_items() if i.eq.code == "W")
    item.setSelected(True)
    w.toggle_status()
    assert item.eq.planned
    w.undo()
    assert not next(e for e in f.equipment if e.code == "W").planned
    w.dirty = False
    w.close()
