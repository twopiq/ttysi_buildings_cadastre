"""Tasdiqlash ekrani va klaviatura tugmalarini almashtirish."""

import os

import numpy as np
import pytest

from ttysi_cadastre.detection import encode_jpg
from ttysi_cadastre.model import Building, Equipment, Floor, Room


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def reg(qapp):
    from ttysi_cadastre.ui.shortcuts import registry
    r = registry()
    yield r
    r.reset_all()


def _window(n_unknown=4):
    from ttysi_cadastre.ui.main_window import MainWindow
    img = np.full((700, 1000, 3), 255, np.uint8)
    b = Building(name="Bino")
    f = Floor(name="1-etaj", image=encode_jpg(img), width=1000, height=700, scale_m_per_px=0.02)
    f.rooms = [Room(points=[(100, 100), (500, 100), (500, 400), (100, 400)], name="101")]
    f.equipment = [Equipment(code="K", x=150, y=150)]
    f.equipment += [Equipment(code="?", x=200 + 60 * i, y=250) for i in range(n_unknown)]
    b.floors.append(f)
    w = MainWindow()
    w.building = b
    w.refresh_all()
    return w, f


def _close(w):
    w.dirty = False
    w.close()


def _key(widget, key, mod=None):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    QTest.keyClick(widget, key, mod or Qt.NoModifier)


def test_review_dialog_flow(qapp, reg):
    from PySide6.QtCore import Qt
    from ttysi_cadastre.ui.review_dialog import ReviewDialog
    w, f = _window(4)
    dlg = ReviewDialog(w)
    assert dlg.total == 4 and dlg.pages.currentIndex() == 0
    assert dlg.where.text() == "101-xona ichida"
    first, second, third, fourth = [e for e in f.equipment if e.code == "?"]

    _key(dlg, Qt.Key_4)                       # Wi-Fi
    assert first.code == "W" and first.status == "existing"
    _key(dlg, Qt.Key_N)                       # o'tkazib yuborish -> navbat oxiriga
    assert dlg.current() is third
    _key(dlg, Qt.Key_Q)                       # "kerak" holati
    _key(dlg, Qt.Key_6)
    assert third.code == "T" and third.planned
    _key(dlg, Qt.Key_Delete)                  # belgi emas
    assert fourth not in f.equipment
    assert dlg.current() is second
    _key(dlg, Qt.Key_3)
    assert second.code == "K"
    assert dlg.pages.currentIndex() == 1 and dlg.reviewed == 4
    assert not any(e.code == "?" for e in f.equipment)
    # chizmadagi elementlar ham yangilangan, bekor qilish ishlaydi
    codes = sorted(i.eq.code for i in w.scene.equipment_items())
    assert codes == sorted(e.code for e in f.equipment)
    w.undo()
    assert any(e.code == "?" for e in f.equipment)
    dlg.accept()
    _close(w)


def test_remapped_keys_work_everywhere(qapp, reg):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeySequence
    from ttysi_cadastre.ui.review_dialog import ReviewDialog
    w, f = _window(2)
    reg.set("equip.K", "F")
    reg.set("review.next", "Space")
    # menyudagi amal ham yangi tugmani oldi
    assert w.sc_actions["equip.K"].shortcut() == QKeySequence("F")
    dlg = ReviewDialog(w)
    assert "F" in dlg.type_buttons["K"].kbd.text()
    first = dlg.current()
    _key(dlg, Qt.Key_3)                       # eski tugma endi ishlamaydi
    assert first.code == "?"
    _key(dlg, Qt.Key_Space)
    assert dlg.current() is not first
    _key(dlg, Qt.Key_F)
    assert sum(e.code == "K" for e in f.equipment) == 2
    # oyna ochiq turganda tugma o'zgarsa, yozuvlar yangilanadi
    reg.set("equip.W", "Ctrl+W")
    assert dlg.type_buttons["W"].kbd.text() == QKeySequence("Ctrl+W").toString(QKeySequence.NativeText)
    dlg.reject()
    # tahrirlagichda ham yangi tugma ishlaydi: tanlangan belgining turi o'zgaradi
    eq = next(i for i in w.scene.equipment_items() if i.eq.code == "?")
    w.scene.clearSelection()
    eq.setSelected(True)
    w.sc_actions["equip.K"].trigger()
    assert eq.eq.code == "K"
    _close(w)


def test_shortcut_registry_persist_and_conflicts(qapp, reg):
    from ttysi_cadastre.ui.shortcuts import Registry, ShortcutsDialog
    w, _ = _window(1)
    assert reg.text("tool.wall") == "L"
    reg.set("tool.wall", "V")
    assert Registry(reg.settings).text("tool.wall") == "V"         # QSettings'da saqlandi
    assert set(reg.conflicts()["V"]) == {"tool.wall", "tool.select"}  # tanlash asbobi bilan to'qnashuv
    reg.set("tool.wall", "L")
    assert reg.settings.value("shortcuts/tool.wall") is None          # standart qiymat saqlanmaydi
    assert not reg.conflicts()

    dlg = ShortcutsDialog(reg, w)
    from PySide6.QtGui import QKeySequence
    from PySide6.QtWidgets import QDialogButtonBox
    dlg.edits["tool.door"].setKeySequence(QKeySequence("V"))           # tanlash asbobi bilan bir xil
    assert not dlg.check()
    assert not dlg.buttons.button(QDialogButtonBox.Save).isEnabled()
    dlg.edits["tool.door"].setKeySequence(QKeySequence("Shift+D"))
    assert dlg.check()
    dlg.accept()
    assert reg.text("tool.door") == "Shift+D"
    assert w.sc_actions["tool.door"].shortcut() == QKeySequence("Shift+D")
    reg.reset_all()
    assert reg.text("tool.door") == "D"
    _close(w)


def test_open_review_without_unknowns(qapp, reg):
    w, _ = _window(0)
    w.open_review()                                                    # modal oyna ochilmaydi
    assert "yo'q" in w.statusBar().currentMessage()
    _close(w)
