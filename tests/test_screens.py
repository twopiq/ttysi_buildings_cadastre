"""Yangi dizayndagi ekranlar: bosh sahifa, muharrir paneli, import va eksport."""

import os

import pytest

from tests.synthetic import ROOMS, make_plan
from ttysi_cadastre.model import Building, Equipment, Floor, Room


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _building():
    b = Building(name="Sinov binosi")
    for n in (1, 2):
        f = Floor(name=f"{n}-qavat", width=1000, height=700, scale_m_per_px=0.02)
        f.rooms = [Room(points=[(100, 100), (500, 100), (500, 400), (100, 400)], name=f"{n}01")]
        f.equipment = [Equipment(code="K", x=200, y=200), Equipment(code="T", x=300, y=200, status="planned")]
        b.floors.append(f)
    b.floors[1].equipment.append(Equipment(code="?", x=400, y=300))
    return b


def _window(b=None):
    from ttysi_cadastre.ui.main_window import MainWindow
    w = MainWindow()
    if b is not None:
        w.building = b
        w.refresh_all()
    return w


def _close(w):
    w.dirty = False
    w.close()


def test_home_page_recent_projects(qapp, tmp_path):
    from ttysi_cadastre.ui.home import ProjectCard, forget, recent, remember
    w = _window()
    assert w.pages.currentWidget() is w.home                 # dastur bosh sahifadan boshlanadi
    w.settings.remove("recent/projects")
    b = _building()
    path = str(tmp_path / "bino.ttysi")
    b.save(path)
    w.open_project(path)
    assert w.pages.currentWidget() is w.editor
    items = recent(w.settings)
    assert items[0]["path"] == os.path.abspath(path)
    assert items[0]["floors"] == 2 and items[0]["ready"] == 1 and items[0]["unknown"] == 1
    assert items[0]["counts"] == {"K": 2} and items[0]["planned"] == 2
    remember(w.settings, b, path)                            # takrorlanmaydi
    assert len(recent(w.settings)) == 1
    w.show_home()
    cards = [c for c in w.home.cards if isinstance(c, ProjectCard)]
    assert len(cards) == 1 and cards[0].isEnabled()
    forget(w.settings, path)
    assert recent(w.settings) == []
    _close(w)


def test_editor_tabs_steps_and_tiles(qapp):
    b = _building()
    w = _window(b)
    assert len(w.floor_tabs.buttons) == 2
    assert w.floor_tabs.buttons[0].isChecked()
    assert w.floor_tabs.buttons[1].findChild(type(w.project_name), "badge").text() == "1"
    w.floor_tabs.selected.emit(1)
    assert w.floor is b.floors[1]
    states = [c.property("state") for c in w.steps.chips]
    assert states == ["done", "active", "warn", "todo"]
    assert w.tiles["K"].value.text() == "1"
    assert w.tiles["planned"].value.text() == "+1"
    assert not w.tiles["?"].isHidden()
    assert "tasdiqlash" in w.review_link.text()
    # xona tanlansa - o'ng panelda xona va undagi jihozlar
    room = w.scene.room_items()[0]
    room.setSelected(True)
    assert w.props.currentIndex() == 1
    assert w.props_title.text() == "TANLANGAN XONA"
    texts = [w.room_eq.itemAt(i).widget().text() for i in range(w.room_eq.count()) if w.room_eq.itemAt(i).widget()]
    assert "K. × 1" in texts and "T × 1 kerak" in texts
    _close(w)


def test_export_dialog_and_run(qapp, tmp_path):
    from ttysi_cadastre.ui.export_dialog import ExportDialog
    b = _building()
    w = _window(b)
    d = ExportDialog(w, "svg")
    assert d.kind() == "svg" and d.raster_row.isHidden()
    d.r_all.setChecked(True)
    assert d.floors() == b.floors
    assert not d.warn.isHidden()                             # 2-qavatda "?" bor
    d.c_planned.setChecked(False)
    assert d.options().planned is False
    d.cards["excel"].setChecked(True)
    assert d.scope_box.isHidden() and not d.c_names.isEnabled()
    d.cards["dxf"].setChecked(True)
    assert d.c_planned.isEnabled() and not d.c_names.isEnabled()
    d.reject()

    paths = [str(tmp_path / "1.svg"), str(tmp_path / "2.svg")]
    assert w.run_export("svg", b.floors, d.options(), paths=paths) == paths
    assert all(os.path.getsize(p) > 500 for p in paths)
    pdf = str(tmp_path / "hammasi.pdf")
    w.run_export("pdf", b.floors, d.options(), paths=[pdf])
    assert os.path.getsize(pdf) > 500
    dxf = str(tmp_path / "e.dxf")
    w.run_export("dxf", [b.floors[0]], d.options(), paths=[dxf])
    import ezdxf
    layers = {e.dxf.layer for e in ezdxf.readfile(dxf).modelspace()}
    assert "AT_T_KERAK" not in layers                         # rejadagi jihozlar chiqarilmadi
    _close(w)


def test_import_screen_with_pdf(qapp, tmp_path):
    from PySide6.QtCore import QMarginsF, QRectF
    from PySide6.QtGui import QPageLayout, QPageSize, QPainter, QPdfWriter
    from PySide6.QtPdf import QPdfDocument
    from ttysi_cadastre.ui.import_dialog import ImportDialog, cv_to_qimage
    p = str(tmp_path / "k.pdf")
    wr = QPdfWriter(p)
    wr.setPageLayout(QPageLayout(QPageSize(QPageSize.A3), QPageLayout.Landscape, QMarginsF(0, 0, 0, 0)))
    painter = QPainter(wr)
    r = wr.pageLayout().paintRectPixels(wr.resolution())
    painter.drawImage(QRectF(0, 0, r.width(), r.height()), cv_to_qimage(make_plan(False)))
    wr.newPage()
    painter.drawImage(QRectF(0, 0, r.width(), r.height()), cv_to_qimage(make_plan(False)))
    painter.end()
    doc = QPdfDocument()
    doc.load(p)

    w = _window(Building(name="PDF"))
    dlg = ImportDialog(None, "1-qavat", w, doc=doc, page=1, file_name="k.pdf")
    assert dlg.page_list.count() == 2 and dlg.page() == 1
    assert dlg.img.shape[1] == pytest.approx(420 / 25.4 * 200, rel=0.01)
    dlg.scale.setValue(100)
    assert dlg.m_per_px() == pytest.approx(25.4 / 200 * 100 / 1000)
    assert "Masshtab hisoblandi" in dlg.scale_hint.text()
    assert "1-qavat" in dlg.size_tag.text() and " m" in dlg.size_tag.text()
    dlg.dpi.setCurrentIndex(0)                                # 150 DPI - sahifa qayta chiziladi
    assert dlg.img.shape[1] == pytest.approx(420 / 25.4 * 150, rel=0.01)

    # "Yaratish va yana etaj": oyna yopilganda etaj qo'shiladi va again=True
    from PySide6.QtCore import QTimer
    QTimer.singleShot(0, dlg.accept_again)
    assert w.create_floor(dlg)
    assert dlg.again
    f = w.building.floors[-1]
    assert f.scale_m_per_px and len(f.rooms) == len(ROOMS)
    assert w.floor is f and w.pages.currentWidget() is w.editor
    _close(w)
    doc.close()


def test_buildings_folder_and_floors(qapp, tmp_path):
    """Binolar papkasi: 1-bino > 1,2-qavat; 2-bino > 1-qavat. Bosh sahifada etaj bosilsa - shu etaj ochiladi."""
    from ttysi_cadastre.ui.home import ProjectCard, WORKSPACE_KEY, forget, scan
    w = _window()
    w.settings.setValue(WORKSPACE_KEY, str(tmp_path / "Binolar"))
    w.settings.remove("recent/projects")
    p1 = w.create_building("1-bino", "Toshkent")
    assert p1 == str(tmp_path / "Binolar" / "1-bino.ttysi") and os.path.exists(p1)
    for n in (1, 2):
        w.building.floors.append(Floor(name=f"{n}-qavat", width=100, height=100))
    w.building.floors[1].equipment.append(Equipment(code="?", x=5, y=5))
    assert w.save_project()
    w.create_building("2-bino")
    w.building.floors.append(Floor(name="1-qavat", width=100, height=100))
    w.save_project()
    assert w.create_building("1-bino").endswith("1-bino (2).ttysi")     # nom band - yangi fayl
    forget(w.settings, w.path)
    os.remove(w.path)

    items = scan(str(tmp_path / "Binolar"))
    assert [i["name"] for i in items] == ["1-bino", "2-bino"]
    assert items[0]["floor_list"] == [["1-qavat", 0], ["2-qavat", 1]]

    w.dirty = False
    w.show_home()
    cards = [c for c in w.home.cards if isinstance(c, ProjectCard)]
    assert len(cards) == 2 and not w.home.other_title.isVisible()
    chips = cards[0].findChildren(type(w.home.cards[-1]).__mro__[1], "floorChip")
    assert [c.text() for c in chips] == ["1-qavat", "2-qavat  ⚠1"]
    chips[1].click()                                                  # 1-bino, 2-qavat
    assert w.pages.currentWidget() is w.editor
    assert w.building.name == "1-bino" and w.floor is w.building.floors[1]

    w.fill_switch_menu()
    names = [a.text() for a in w.switch_menu.actions() if a.text()]
    assert names[0].startswith("1-bino") and w.switch_menu.actions()[0].isChecked()
    assert names[1].startswith("2-bino")
    _close(w)
