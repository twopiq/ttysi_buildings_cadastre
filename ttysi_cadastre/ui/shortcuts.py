"""Klaviatura tugmalari (goryachiy klavishlar): ro'yxat, foydalanuvchi sozlamasi va tahrirlash oynasi.

Har bir amal o'z identifikatori bilan ro'yxatdan o'tadi: register("tool.wall", "Devor", "L").
Foydalanuvchi o'zgartirgan tugma QSettings'da "shortcuts/<id>" kalitida saqlanadi.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QKeySequenceEdit,
                               QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

SETTINGS_PREFIX = "shortcuts/"


@dataclass
class Entry:
    sid: str
    label: str
    default: str
    group: str


class Registry:
    def __init__(self, settings: QSettings | None = None):
        self.settings = settings or QSettings("TTYSI", "BinolarKadastr")
        self.entries: dict[str, Entry] = {}
        self.listeners = []          # f(sid, QKeySequence) - tugma o'zgarganda chaqiriladi

    def register(self, sid: str, label: str, default: str = "", group: str = "Umumiy") -> QKeySequence:
        if sid not in self.entries:
            self.entries[sid] = Entry(sid, label, default, group)
        return self.key(sid)

    def text(self, sid: str) -> str:
        e = self.entries.get(sid)
        stored = self.settings.value(SETTINGS_PREFIX + sid)
        if stored is not None:
            return str(stored)
        return e.default if e else ""

    def key(self, sid: str) -> QKeySequence:
        return QKeySequence(self.text(sid))

    def set(self, sid: str, seq: str) -> None:
        e = self.entries.get(sid)
        if e and seq == e.default:
            self.settings.remove(SETTINGS_PREFIX + sid)
        else:
            self.settings.setValue(SETTINGS_PREFIX + sid, seq)
        for f in self.listeners:
            f(sid, QKeySequence(seq))

    def reset_all(self) -> None:
        for sid in self.entries:
            self.set(sid, self.entries[sid].default)

    def matches(self, sid: str, event) -> bool:
        """Klaviatura hodisasi shu amal tugmasiga mos keladimi (oynalar ichidagi qo'lda ishlov uchun)."""
        seq = self.key(sid)
        if seq.isEmpty():
            return False
        pressed = QKeySequence(event.keyCombination())
        return pressed.toString(QKeySequence.PortableText) == seq.toString(QKeySequence.PortableText)

    def conflicts(self, mapping: dict[str, str] | None = None) -> dict[str, list[str]]:
        """Bir xil tugmaga berilgan amallar: {tugma: [amal, ...]} (faqat 2 va undan ko'p)."""
        mapping = mapping or {sid: self.text(sid) for sid in self.entries}
        seen: dict[str, list[str]] = {}
        for sid, seq in mapping.items():
            norm = QKeySequence(seq).toString(QKeySequence.PortableText)
            if norm:
                seen.setdefault(norm, []).append(sid)
        return {k: v for k, v in seen.items() if len(v) > 1}


_registry: Registry | None = None


def registry() -> Registry:
    global _registry
    if _registry is None:
        _registry = Registry()
    return _registry


def display(seq: QKeySequence | str) -> str:
    """Tugmani foydalanuvchiga ko'rsatish matni (masalan "Ctrl+Shift+R")."""
    if isinstance(seq, str):
        seq = QKeySequence(seq)
    return seq.toString(QKeySequence.NativeText)


class ShortcutsDialog(QDialog):
    """Barcha amallar va tugmalari: o'zgartirish, standartga qaytarish, to'qnashuvlarni ko'rsatish."""

    def __init__(self, reg: Registry, parent=None):
        super().__init__(parent)
        self.reg = reg
        self.setWindowTitle("Klaviatura tugmalari")
        self.resize(640, 640)
        lay = QVBoxLayout(self)
        info = QLabel("Tugmani o'zgartirish uchun maydonni bosing va yangi tugmani bosing. "
                      "Bir xil tugma ikki amalga berilsa, qizil bilan ko'rsatiladi.")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Qidirish: amal nomi yoki tugma")
        self.search.textChanged.connect(self.filter)
        lay.addWidget(self.search)

        entries = sorted(reg.entries.values(), key=lambda e: (e.group, e.label))
        self.table = QTableWidget(len(entries), 3)
        self.table.setHorizontalHeaderLabels(["Amal", "Tugma", ""])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.edits: dict[str, QKeySequenceEdit] = {}
        self.rows: dict[str, int] = {}
        for row, e in enumerate(entries):
            item = QTableWidgetItem(f"{e.group} · {e.label}")
            item.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 0, item)
            ed = QKeySequenceEdit(reg.key(e.sid))
            ed.setMaximumSequenceLength(1)
            ed.setClearButtonEnabled(True)
            ed.keySequenceChanged.connect(self.check)
            self.table.setCellWidget(row, 1, ed)
            b = QPushButton("Standart")
            b.setToolTip(f"Standart: {display(e.default) or 'yo‘q'}")
            b.clicked.connect(lambda _=False, sid=e.sid: self.edits[sid].setKeySequence(
                QKeySequence(self.reg.entries[sid].default)))
            cell = QWidget()
            cl = QHBoxLayout(cell)
            cl.setContentsMargins(4, 2, 4, 2)
            cl.addWidget(b)
            self.table.setCellWidget(row, 2, cell)
            self.edits[e.sid] = ed
            self.rows[e.sid] = row
        lay.addWidget(self.table, 1)

        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #B3261E")
        lay.addWidget(self.warning)
        row = QHBoxLayout()
        reset = QPushButton("Hammasini standartga qaytarish")
        reset.clicked.connect(self.reset_all)
        row.addWidget(reset)
        row.addStretch()
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText("Saqlash")
        self.buttons.button(QDialogButtonBox.Save).setObjectName("primary")
        self.buttons.button(QDialogButtonBox.Cancel).setText("Bekor qilish")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        row.addWidget(self.buttons)
        lay.addLayout(row)
        self.check()

    def mapping(self) -> dict[str, str]:
        return {sid: ed.keySequence().toString(QKeySequence.PortableText) for sid, ed in self.edits.items()}

    def check(self) -> bool:
        conflicts = self.reg.conflicts(self.mapping())
        bad = {sid for sids in conflicts.values() for sid in sids}
        for sid, row in self.rows.items():
            self.table.item(row, 0).setForeground(Qt.red if sid in bad else Qt.black)
        if conflicts:
            lines = [f"{display(k)}: " + ", ".join(self.reg.entries[s].label for s in v) for k, v in conflicts.items()]
            self.warning.setText("Bir xil tugma: " + "; ".join(lines))
        else:
            self.warning.clear()
        self.buttons.button(QDialogButtonBox.Save).setEnabled(not conflicts)
        return not conflicts

    def filter(self, text: str):
        t = text.strip().lower()
        for sid, row in self.rows.items():
            e = self.reg.entries[sid]
            hay = f"{e.group} {e.label} {display(self.edits[sid].keySequence())}".lower()
            self.table.setRowHidden(row, bool(t) and t not in hay)

    def reset_all(self):
        for sid, ed in self.edits.items():
            ed.setKeySequence(QKeySequence(self.reg.entries[sid].default))

    def accept(self):
        if not self.check():
            return
        for sid, seq in self.mapping().items():
            if seq != self.reg.text(sid):
                self.reg.set(sid, seq)
        super().accept()
