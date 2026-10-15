"""AT belgilarini aniqlash oynasi (xonalarni chizishdan alohida).

Chapda - kadastr rasmi va topilgan nomzodlar (ko'k ruchka - ko'k, qora ruchka - qizil ramka).
Ramkani bosish - shu nomzodni chiqarib tashlash/qaytarish. O'ngda - siyoh turlari, sezgirlik,
"faqat bino ichida" va natijani qo'shish usuli. Sozlama o'zgarsa natija darhol qayta hisoblanadi.
"""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QDialog, QFrame, QGraphicsRectItem,
                               QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel, QPushButton, QRadioButton,
                               QSlider, QVBoxLayout)

from ..geometry import bg_unmap
from ..marks import Mark, MarkParams, detect_marks
from ..model import Floor
from ..render import meter_px
from . import theme
from .import_dialog import cv_to_qimage

STYLE = f"""
QDialog {{ background: {theme.BG}; }}
QFrame#side {{ background: {theme.SURFACE}; border-left: 1px solid {theme.LINE}; }}
QLabel#h {{ font-size: 18px; font-weight: 700; }}
QLabel#muted {{ color: {theme.INK_2}; font-size: 13px; }}
QLabel#count {{ font-size: 15px; font-weight: 600; }}
"""


class CandidateItem(QGraphicsRectItem):
    def __init__(self, mark: Mark, pad: float):
        super().__init__(QRectF(mark.x - mark.w / 2 - pad, mark.y - mark.h / 2 - pad,
                                mark.w + 2 * pad, mark.h + 2 * pad))
        self.mark = mark
        self.excluded = False
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(("Ko'k ruchka" if mark.color == "blue" else f"Qora ruchka, ishonch {mark.score:.0%}")
                        + ". Bosing - chiqarib tashlash/qaytarish")
        self.restyle()

    def restyle(self):
        col = QColor("#1565c0" if self.mark.color == "blue" else "#d32f2f")
        pen = QPen(QColor("#9e9e9e") if self.excluded else col, 2.5, Qt.DashLine if self.excluded else Qt.SolidLine)
        pen.setCosmetic(True)
        self.setPen(pen)
        fill = QColor(col)
        fill.setAlpha(0 if self.excluded else 28)
        self.setBrush(QBrush(fill))

    def mousePressEvent(self, event):
        self.excluded = not self.excluded
        self.restyle()
        dlg = self.scene().property("dialog") if self.scene() else None
        if dlg is not None:
            dlg.update_count()
        event.accept()


class MarksDialog(QDialog):
    """Natija: marks() - tanlangan nomzodlar (fon rasmi piksellarida); replace() - "?" lar almashtirilsinmi."""

    def __init__(self, floor: Floor, image: np.ndarray, parent=None):
        super().__init__(parent)
        self.floor = floor
        self.image = image
        self.setWindowTitle(f"AT belgilarini aniqlash — {floor.name}")
        self.setStyleSheet(STYLE)
        self.resize(1360, 860)
        self.found: list[Mark] = []
        self.items: list[CandidateItem] = []

        self.scene = QGraphicsScene(self)
        self.scene.setProperty("dialog", self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setBackgroundBrush(QColor("#3A4552"))
        self.view.wheelEvent = self._wheel
        self.scene.addPixmap(QPixmap.fromImage(cv_to_qimage(image)))
        self.scene.setSceneRect(QRectF(0, 0, image.shape[1], image.shape[0]))

        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(360)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(20, 20, 20, 20)
        sl.setSpacing(12)
        h = QLabel("AT belgilarini aniqlash")
        h.setObjectName("h")
        sl.addWidget(h)
        info = QLabel("Kadastr rasmidagi qo'lyozma belgilar topiladi. Turi keyin tasdiqlash ekranida beriladi. "
                      "Noto'g'ri ramkani bosib chiqarib tashlang.")
        info.setObjectName("muted")
        info.setWordWrap(True)
        sl.addWidget(info)
        self.c_blue = QCheckBox("Ko'k ruchka")
        self.c_black = QCheckBox("Qora ruchka (qo'lyozma)")
        self.c_blue.setChecked(True)
        self.c_black.setChecked(True)
        hint = QLabel("Qora ruchka bosma chizmadan to'q va qalin bo'lsa ajratiladi. Toza (qora bosma) PDF'da "
                      "qora qo'lyozma qidirilmaydi.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        sl.addWidget(self.c_blue)
        sl.addWidget(self.c_black)
        sl.addWidget(hint)
        sl.addWidget(QLabel("Sezgirlik"))
        srow = QHBoxLayout()
        self.sens = QSlider(Qt.Horizontal)
        self.sens.setRange(0, 100)
        self.sens.setValue(50)
        self.sens_label = QLabel("50%")
        self.sens.valueChanged.connect(lambda v: self.sens_label.setText(f"{v}%"))
        srow.addWidget(QLabel("kamroq"))
        srow.addWidget(self.sens, 1)
        srow.addWidget(QLabel("ko'proq"))
        srow.addWidget(self.sens_label)
        sl.addLayout(srow)
        self.c_inside = QCheckBox("Faqat bino ichida (xonalar va ularning devorlari yonida)")
        self.c_inside.setChecked(bool(floor.rooms))
        self.c_inside.setEnabled(bool(floor.rooms))
        sl.addWidget(self.c_inside)

        sl.addWidget(QLabel("Natija"))
        self.r_replace = QRadioButton("Tasdiqlanmagan (?) belgilar o'rniga")
        self.r_add = QRadioButton("Mavjudlariga qo'shish (yaqinidagi takrorlar tashlanadi)")
        grp = QButtonGroup(self)
        grp.addButton(self.r_replace)
        grp.addButton(self.r_add)
        self.r_replace.setChecked(True)
        sl.addWidget(self.r_replace)
        sl.addWidget(self.r_add)
        self.count = QLabel()
        self.count.setObjectName("count")
        self.count.setWordWrap(True)
        sl.addWidget(self.count)
        sl.addStretch()
        self.ok = QPushButton("Qo'shish va tasdiqlash")
        self.ok.setObjectName("primary")
        self.ok.setMinimumHeight(44)
        self.ok.clicked.connect(self.accept)
        cancel = QPushButton("Bekor qilish")
        cancel.clicked.connect(self.reject)
        sl.addWidget(self.ok)
        sl.addWidget(cancel)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.view, 1)
        lay.addWidget(side)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.run)
        for sig in (self.c_blue.toggled, self.c_black.toggled, self.sens.valueChanged, self.c_inside.toggled):
            sig.connect(lambda *_: self.timer.start())
        self.run()

    def _wheel(self, event):
        f = 1.0015 ** event.angleDelta().y()
        self.view.scale(f, f)

    def showEvent(self, e):
        super().showEvent(e)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def params(self) -> MarkParams:
        return MarkParams(blue=self.c_blue.isChecked(), black=self.c_black.isChecked(),
                          sensitivity=self.sens.value() / 100)

    def _inside_mask(self) -> np.ndarray | None:
        """Xonalar (va devor yonidagi ~1.5 m) maydoni - fon rasmi piksellarida."""
        f = self.floor
        if not (self.c_inside.isChecked() and f.rooms):
            return None
        h, w = self.image.shape[:2]
        k = w / max(1, f.width)                       # chizma -> rasm piksellari
        mask = np.zeros((h, w), np.uint8)
        for r in f.rooms:
            pts = np.array([bg_unmap(f, x, y) for x, y in r.points]) * k
            cv2.fillPoly(mask, [pts.astype(np.int32)], 255)
        pad = max(3, int(meter_px(f) * 1.5 * k)) | 1
        return cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (pad, pad)))

    def run(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            found = detect_marks(self.image, self.params())
            inside = self._inside_mask()
            if inside is not None:
                h, w = inside.shape
                found = [m for m in found if 0 <= int(m.y) < h and 0 <= int(m.x) < w and inside[int(m.y), int(m.x)]]
        finally:
            QApplication.restoreOverrideCursor()
        for it in self.items:
            self.scene.removeItem(it)
        self.found = found
        pad = max(4.0, max(self.image.shape[:2]) * 0.003)
        self.items = [CandidateItem(m, pad) for m in found]
        for it in self.items:
            self.scene.addItem(it)
        self.update_count()

    def update_count(self):
        chosen = [it for it in self.items if not it.excluded]
        blue = sum(1 for it in chosen if it.mark.color == "blue")
        self.count.setText(f"Topildi: {len(chosen)} ta belgi (ko'k {blue}, qora {len(chosen) - blue})"
                           + (f", {len(self.items) - len(chosen)} ta chiqarib tashlandi" if len(chosen) < len(self.items)
                              else ""))
        self.ok.setEnabled(bool(chosen) or self.r_replace.isChecked())

    def marks(self) -> list[Mark]:
        return [it.mark for it in self.items if not it.excluded]

    def replace(self) -> bool:
        return self.r_replace.isChecked()
