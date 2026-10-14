"""Masshtabni nisbat bo'yicha qayta hisoblash oynasi.

Nisbat (1:300) o'zi yetarli emas: rasmdagi 1 piksel qog'ozda necha mm ekanini ham bilish kerak.
PDF'dan olingan rasmda bu aniqlikdan (DPI) kelib chiqadi; eski versiyada qo'shilgan etajlarda
saqlanmagan bo'lishi mumkin - shu oynada beriladi. Yoki masshtab ma'lum uzunlik (2 nuqta) bilan olinadi.
"""

from __future__ import annotations

from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QHBoxLayout, QLabel, QPushButton, QRadioButton,
                               QSpinBox, QVBoxLayout)

from ..detection import MAX_STORED_SIZE
from ..model import Floor
from . import theme
from .import_dialog import ratio_presets

DPIS = (150, 200, 300, 400, 600)


class ScaleDialog(QDialog):
    """Natija: mode() - "dpi" yoki "points"; ratio(); paper_mm_per_px()."""

    def __init__(self, floor: Floor, parent=None):
        super().__init__(parent)
        self.floor = floor
        self.setWindowTitle(f"Masshtabni qayta hisoblash — {floor.name}")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        h = QLabel("Masshtabni qayta hisoblash")
        h.setStyleSheet("font-size: 18px; font-weight: 700")
        lay.addWidget(h)

        row = QHBoxLayout()
        self.ratio_spin = QSpinBox()
        self.ratio_spin.setRange(1, 100000)
        self.ratio_spin.setPrefix("1 : ")
        self.ratio_spin.setValue(floor.ratio or 300)
        row.addWidget(QLabel("Nisbat (shtampdagi \"Нисбат\"):"))
        row.addWidget(self.ratio_spin, 1)
        row.addWidget(ratio_presets(self.ratio_spin))
        lay.addLayout(row)

        q = QLabel("Kadastr rasmi qanday olingan?")
        q.setStyleSheet("font-weight: 600")
        lay.addWidget(q)
        self.r_dpi = QRadioButton("PDF yoki skaner — aniqligi (DPI):")
        self.r_points = QRadioButton("Telefon rasmi yoki noma'lum — ma'lum uzunlik bo'yicha (2 nuqta bilan)")
        grp = QButtonGroup(self)
        grp.addButton(self.r_dpi)
        grp.addButton(self.r_points)
        drow = QHBoxLayout()
        drow.addWidget(self.r_dpi)
        self.dpi = QComboBox()
        self.dpi.setEditable(True)
        for d in DPIS:
            self.dpi.addItem(str(d))
        self.dpi.setCurrentText(str(self._guess_dpi()))
        self.dpi.setToolTip("PDF'dan etaj qo'shishda standart - 200 DPI")
        drow.addWidget(self.dpi)
        drow.addStretch()
        lay.addLayout(drow)
        lay.addWidget(self.r_points)
        self.r_dpi.setChecked(True)

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        lay.addWidget(self.preview)
        self.warn = QLabel()
        self.warn.setWordWrap(True)
        self.warn.setStyleSheet(f"color: {theme.WARN_FG}")
        lay.addWidget(self.warn)

        btns = QHBoxLayout()
        btns.addStretch()
        cancel = QPushButton("Bekor qilish")
        cancel.clicked.connect(self.reject)
        self.ok = QPushButton("Hisoblash")
        self.ok.setObjectName("primary")
        self.ok.setDefault(True)
        self.ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(self.ok)
        lay.addLayout(btns)

        for sig in (self.ratio_spin.valueChanged, self.dpi.currentTextChanged, self.r_dpi.toggled):
            sig.connect(self.update_preview)
        self.update_preview()

    def _guess_dpi(self) -> int:
        f = self.floor
        if f.paper_mm_per_px:
            return round(25.4 / f.paper_mm_per_px)
        return 200

    # --- natija
    def mode(self) -> str:
        return "dpi" if self.r_dpi.isChecked() else "points"

    def ratio(self) -> int:
        return self.ratio_spin.value()

    def dpi_value(self) -> float | None:
        try:
            v = float(self.dpi.currentText().replace(",", "."))
        except ValueError:
            return None
        return v if 20 <= v <= 4800 else None

    def paper_mm_per_px(self) -> float | None:
        d = self.dpi_value()
        return 25.4 / d if d else None

    def update_preview(self, *_):
        f = self.floor
        if self.mode() == "points":
            self.ok.setText("2 nuqtani belgilash")
            self.preview.setText("Chizmada uzunligi ma'lum chiziqning (devor, o'lcham chizig'i) ikki uchini bosasiz va "
                                 "uzunligini metrda kiritasiz. Shundan keyin nisbat o'zgarsa o'zi qayta hisoblanadi.")
            self.warn.clear()
            self.ok.setEnabled(True)
            return
        self.ok.setText("Hisoblash")
        paper = self.paper_mm_per_px()
        if not paper:
            self.preview.setText("DPI noto'g'ri (masalan 200).")
            self.ok.setEnabled(False)
            return
        self.ok.setEnabled(True)
        mpp = paper * self.ratio() / 1000
        area = sum(r.area() for r in f.rooms) * mpp ** 2
        self.preview.setText(f"1 piksel = {mpp * 100:.2f} sm.  Etaj o'lchami: {f.width * mpp:.1f} × "
                             f"{f.height * mpp:.1f} m,  xonalar umumiy maydoni ≈ <b>{area:.1f} m²</b>.")
        self.warn.setText("Diqqat: rasm saqlashda kichraytirilgan bo'lishi mumkin - natijani kadastrdagi bitta "
                          "xona maydoni bilan solishtiring." if max(f.width, f.height) >= MAX_STORED_SIZE else "")
