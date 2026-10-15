"""Dastur va sayt bitta binoni o'zgartirganda: o'zgarishlar birlashtiriladi, ustidan yozilmaydi."""

import os
import time

import pytest

from ttysi_cadastre.merge import merge_equipment, snapshot
from ttysi_cadastre.model import Building, Equipment, Floor


def _b():
    b = Building(name="B")
    f = Floor(name="1", width=500, height=400)
    f.equipment = [Equipment(code="K", x=10, y=10, id="a"), Equipment(code="?", x=20, y=20, id="b"),
                   Equipment(code="T", x=30, y=30, id="c"), Equipment(code="W", x=40, y=40, id="d")]
    b.floors.append(f)
    return b


def _copy(b):
    import copy
    return copy.deepcopy(b)


def test_merge_three_way():
    base = _b()
    snap = snapshot(base)
    mine, theirs = _copy(base), _copy(base)
    fm, ft = mine.floors[0], theirs.floors[0]
    ft.equipment[1].code = "S"                                    # saytda: ? -> S
    ft.equipment.append(Equipment(code="SER", x=50, y=50, id="e"))   # saytda qo'shildi
    ft.equipment = [e for e in ft.equipment if e.id != "c"]       # saytda o'chirildi
    ft.equipment[0].note = "sayt"                                 # a - ikkala joyda o'zgardi
    fm.equipment[0].note = "dastur"
    fm.equipment.append(Equipment(code="T", x=60, y=60, id="f"))  # dasturda qo'shildi
    fm.equipment = [e for e in fm.equipment if e.id != "d"]       # dasturda o'chirildi
    r = merge_equipment(snap, mine, theirs)
    got = {e.id: (e.code, e.note) for e in mine.floors[0].equipment}
    assert got == {"a": ("K", "dastur"), "b": ("S", ""), "e": ("SER", ""), "f": ("T", "")}
    assert (r.added, r.changed, r.deleted, r.conflicts) == (1, 1, 1, 1)
    assert "+1 belgi" in r.text() and "dasturdagisi" in r.text()


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _external(path, fn):
    """Saytdagi o'zgarishga o'xshatish: faylni o'qib, o'zgartirib, saqlash (vaqt belgisi farq qilsin)."""
    b = Building.load(path)
    fn(b.floors[0])
    time.sleep(0.02)
    b.save(path)
    os.utime(path, None)


def test_desktop_picks_up_web_changes(qapp, tmp_path):
    from ttysi_cadastre.ui.main_window import MainWindow
    path = str(tmp_path / "b.ttysi")
    _b().save(path)
    w = MainWindow()
    w.open_project(path)
    assert w.sync_from_disk(force=True) is None                   # o'zgarish yo'q

    # 1) dasturda o'zgarish yo'q: saytdagisi darhol ko'rinadi
    _external(path, lambda f: setattr(f.equipment[1], "code", "S"))
    r = w.sync_from_disk(force=True)
    assert r.changed == 1 and w.building.floors[0].equipment[1].code == "S" and not w.dirty

    # 2) dasturda saqlanmagan o'zgarish + saytda boshqa belgi: saqlaganda ikkalasi ham qoladi
    w.building.floors[0].equipment.append(Equipment(code="SER", x=70, y=70, id="z"))
    w.set_dirty()
    _external(path, lambda f: f.equipment.append(Equipment(code="W", x=80, y=80, id="y")))
    assert w.save_project()
    ids = {e.id for e in Building.load(path).floors[0].equipment}
    assert {"z", "y"} <= ids
    assert w.sync_from_disk(force=True) is None                   # o'zi saqlagani - o'zgarish emas
    w.dirty = False
    w.close()
