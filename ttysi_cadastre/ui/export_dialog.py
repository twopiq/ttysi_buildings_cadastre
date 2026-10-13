"""Eksport oynasi: format, qaysi etajlar va chizma sozlamalari bitta joyda.

Dizayn maketidagi "Eksport" oynasi asosida.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QRadioButton, QVBoxLayout, QWidget)

from ..render import RenderOptions
from . import theme

# kalit, sarlavha, izoh
FORMATS = [
    ("pdf", "PDF", "Chop etish uchun, A3/A4"),
    ("image", "Rasm (PNG / JPG)", "Hujjat va xabarlarga"),
    ("dxf", "AutoCAD (DXF)", "Qatlamlar va bloklar bilan"),
    ("excel", "Excel hisobot", "Jihozlar soni va reja"),
    ("svg", "Vektor rasm (SVG)", "Tahrirlash va veb uchun"),
    ("excel_many", "Excel — bir nechta bino", "Bir nechta loyiha bo'yicha umumiy"),
]

STYLE = f"""
QDialog {{ background: {theme.SURFACE}; }}
QLabel#h2 {{ font-size: 20px; font-weight: 700; }}
QLabel#legend {{ font-size: 13px; color: {theme.INK_2}; }}
QPushButton#fmt {{
    min-height: 60px; text-align: left; border: 1px solid {theme.LINE}; border-radius: 10px;
    background: {theme.SURFACE}; padding: 0;
}}
QPushButton#fmt:hover {{ border-color: {theme.PRIMARY}; }}
QPushButton#fmt:checked {{ border: 2px solid {theme.PRIMARY}; background: {theme.PRIMARY_SOFT}; }}
QPushButton#fmt:disabled {{ background: #F7F8FA; }}
QLabel#fmtTitle {{ font-weight: 600; background: transparent; }}
QLabel#fmtDesc {{ font-size: 12px; color: {theme.INK_2}; background: transparent; }}
QFrame#warn {{ background: {theme.WARN_BG}; border-radius: 10px; }}
QFrame#warn QLabel {{ color: {theme.WARN_FG}; }}
QPushButton#close {{ border: none; background: transparent; min-width: 36px; font-size: 18px; color: {theme.INK_2}; }}
"""


class FormatCard(QPushButton):
    def __init__(self, key: str, title: str, desc: str):
        super().__init__()
        self.setObjectName("fmt")
        self.key = key
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(title)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(0)
        t = QLabel(title)
        t.setObjectName("fmtTitle")
        d = QLabel(desc)
        d.setObjectName("fmtDesc")
        for w in (t, d):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            lay.addWidget(w)


class ExportDialog(QDialog):
    """Natija: kind(), all_floors(), options(), size(), raster_ext(); review_requested - "Tasdiqlash" bosildi."""

    def __init__(self, window, kind: str | None = None):
        super().__init__(window)
        self.w = window
        self.review_requested = False
        self.settings = QSettings("TTYSI", "BinolarKadastr")
        self.setWindowTitle("Eksport")
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 24)
        lay.setSpacing(16)

        head = QHBoxLayout()
        h = QLabel("Eksport")
        h.setObjectName("h2")
        head.addWidget(h)
        head.addStretch()
        close = QPushButton("✕")
        close.setObjectName("close")
        close.setAccessibleName("Yopish")
        close.clicked.connect(self.reject)
        head.addWidget(close)
        lay.addLayout(head)

        lay.addWidget(self._legend("Format"))
        grid = QGridLayout()
        grid.setSpacing(10)
        self.group = QButtonGroup(self)
        self.cards: dict[str, FormatCard] = {}
        for i, (key, title, desc) in enumerate(FORMATS):
            c = FormatCard(key, title, desc)
            self.group.addButton(c)
            grid.addWidget(c, i // 2, i % 2)
            self.cards[key] = c
        lay.addLayout(grid)

        # rasm o'lchami va turi
        self.raster_row = QWidget()
        rr = QHBoxLayout(self.raster_row)
        rr.setContentsMargins(0, 0, 0, 0)
        self.raster_fmt = QComboBox()
        self.raster_fmt.addItem("PNG", ".png")
        self.raster_fmt.addItem("JPG", ".jpg")
        self.size_box = QComboBox()
        for s in (2000, 4000, 6000):
            self.size_box.addItem(f"{s} piksel", s)
        self.size_box.setCurrentIndex(1)
        rr.addWidget(QLabel("Rasm:"))
        rr.addWidget(self.raster_fmt)
        rr.addWidget(self.size_box)
        rr.addStretch()
        lay.addWidget(self.raster_row)

        floors = window.building.floors
        self.scope_box = QWidget()
        sl = QVBoxLayout(self.scope_box)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(self._legend("Qaysi etajlar"))
        row = QHBoxLayout()
        cur = window.floor.name if window.floor else "—"
        self.r_current = QRadioButton(f"Joriy etaj ({cur})")
        self.r_all = QRadioButton(f"Barcha {len(floors)} ta etaj")
        self.r_current.setChecked(True)
        self.r_all.setEnabled(len(floors) > 1)
        for r in (self.r_current, self.r_all):
            r.toggled.connect(self.update_state)
            row.addWidget(r)
        row.addStretch()
        sl.addLayout(row)
        lay.addWidget(self.scope_box)

        og = QGridLayout()
        og.setHorizontalSpacing(16)
        self.c_names = QCheckBox("Xona raqamlari va maydonlari")
        self.c_legend = QCheckBox("Shartli belgilar jadvali")
        self.c_planned = QCheckBox("Rejadagi (\"kerak\") jihozlar")
        self.c_bg = QCheckBox("Kadastr rasmi fonda")
        self.c_title = QCheckBox("Sarlavha (bino va etaj nomi)")
        self.checks = {"names": self.c_names, "legend": self.c_legend, "planned": self.c_planned,
                       "background": self.c_bg, "title": self.c_title}
        defaults = {"names": True, "legend": True, "planned": True, "background": False, "title": True}
        for i, (k, c) in enumerate(self.checks.items()):
            c.setChecked(self.settings.value(f"export/{k}", defaults[k], type=bool))
            og.addWidget(c, i // 2, i % 2)
        lay.addLayout(og)

        self.warn = QFrame()
        self.warn.setObjectName("warn")
        wl = QHBoxLayout(self.warn)
        wl.setContentsMargins(12, 10, 12, 10)
        self.warn_text = QLabel()
        self.warn_text.setWordWrap(True)
        self.warn_text.setTextFormat(Qt.RichText)
        self.warn_text.linkActivated.connect(self._review)
        wl.addWidget(self.warn_text)
        lay.addWidget(self.warn)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Bekor qilish")
        cancel.setMinimumHeight(44)
        cancel.clicked.connect(self.reject)
        self.ok = QPushButton("Saqlash…")
        self.ok.setObjectName("primary")
        self.ok.setMinimumHeight(44)
        self.ok.setDefault(True)
        self.ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(self.ok)
        lay.addLayout(btns)

        kind = kind or self.settings.value("export/format", "pdf")
        if kind == "pdf_all":
            kind = "pdf"
            self.r_all.setChecked(len(floors) > 1)
        (self.cards.get(kind) or self.cards["pdf"]).setChecked(True)
        self.group.buttonToggled.connect(lambda *_: self.update_state())
        self.update_state()

    @staticmethod
    def _legend(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("legend")
        return lab

    # ------------------------------------------------------------ natija
    def kind(self) -> str:
        b = self.group.checkedButton()
        return b.key if b else "pdf"

    def all_floors(self) -> bool:
        return self.r_all.isChecked() and self.kind() not in ("excel", "excel_many")

    def floors(self):
        if self.kind() in ("excel", "excel_many") or self.all_floors():
            return list(self.w.building.floors)
        return [self.w.floor] if self.w.floor else []

    def options(self) -> RenderOptions:
        return RenderOptions(background=self.c_bg.isChecked(), room_names=self.c_names.isChecked(),
                             legend=self.c_legend.isChecked(), title=self.c_title.isChecked(),
                             planned=self.c_planned.isChecked())

    def size(self) -> int:
        return self.size_box.currentData()

    def raster_ext(self) -> str:
        return self.raster_fmt.currentData()

    # ------------------------------------------------------------ holat
    def update_state(self):
        k = self.kind()
        drawing = k in ("pdf", "image", "svg")
        self.raster_row.setVisible(k == "image")
        self.scope_box.setVisible(k not in ("excel", "excel_many"))
        for name, c in self.checks.items():
            c.setEnabled(drawing or (k == "dxf" and name == "planned"))
        unknown_floors = [f for f in self.floors() if any(e.code == "?" for e in f.equipment)]
        n = sum(1 for f in unknown_floors for e in f.equipment if e.code == "?")
        if n and k != "excel_many":
            where = unknown_floors[0].name if len(unknown_floors) == 1 else f"{len(unknown_floors)} ta etajda"
            self.warn_text.setText(
                f"⚠ {where}: {n} ta belgi hali tasdiqlanmagan — ular \"?\" bo'lib chiqadi. "
                f"<a href='review' style='color:{theme.WARN_FG}; font-weight:600'>Tasdiqlash</a>")
            self.warn.show()
        else:
            self.warn.hide()
        self.ok.setText("Fayllarni tanlash…" if k == "excel_many" else "Saqlash…")
        self.adjustSize()

    def _review(self, _link=None):
        self.review_requested = True
        self.reject()

    def accept(self):
        self.settings.setValue("export/format", self.kind())
        for k, c in self.checks.items():
            self.settings.setValue(f"export/{k}", c.isChecked())
        super().accept()
