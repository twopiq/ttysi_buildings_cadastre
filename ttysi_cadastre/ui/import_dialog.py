"""Rasm yuklash oynasi: perspektivani to'g'rilash va aniqlash sozlamalari."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QGraphicsItem,
                               QGraphicsEllipseItem, QGraphicsPolygonItem, QGraphicsScene,
                               QGraphicsView, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSlider, QVBoxLayout, QWidget)

from ..detection import DetectParams, find_paper_corners, warp_to_rect


def cv_to_qimage(img: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class ParamsWidget(QGroupBox):
    """Aniqlash sozlamalari (yangi etaj va qayta aniqlash uchun umumiy)."""

    def __init__(self, params: DetectParams | None = None, parent=None):
        super().__init__("Avtomatik chizish sozlamalari", parent)
        p = params or DetectParams()
        form = QFormLayout(self)
        self.door = self._slider(10, 80, int(p.door_gap * 1000))
        form.addRow("Eshik kengligi:", self._with_value(self.door, lambda v: f"{v / 10:.1f}%"))
        self.min_room = self._slider(2, 50, int(p.min_room * 10000))
        form.addRow("Eng kichik xona:", self._with_value(self.min_room, lambda v: f"{v / 100:.2f}%"))
        self.blue = QCheckBox("Ko'k ruchka belgilarini topish")
        self.blue.setChecked(p.detect_blue)
        form.addRow(self.blue)
        self.sens = self._slider(0, 100, int(p.blue_sensitivity * 100))
        form.addRow("Ko'k rang sezgirligi:", self._with_value(self.sens, lambda v: f"{v}%"))
        self.black = QCheckBox("Qora yozuvlarni ham belgi nomzodi qilish (ishonchsiz:\n"
                               "bosma raqamlar ham tushadi, keraksizlarini o'chirasiz)")
        self.black.setChecked(p.detect_black)
        form.addRow(self.black)
        self.ortho = QCheckBox("Devorlarni gorizontal/vertikal tekislash")
        self.ortho.setChecked(p.orthogonal)
        form.addRow(self.ortho)
        hint = QLabel("Xonalar qo'shilib ketsa - eshik kengligini oshiring.\n"
                      "Ortiqcha mayda xonalar chiqsa - eng kichik xonani oshiring.")
        hint.setStyleSheet("color: #616161")
        form.addRow(hint)

    @staticmethod
    def _slider(lo, hi, val):
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(max(lo, min(hi, val)))
        return s

    @staticmethod
    def _with_value(slider, fmt):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lab = QLabel(fmt(slider.value()))
        lab.setMinimumWidth(50)
        slider.valueChanged.connect(lambda v: lab.setText(fmt(v)))
        lay.addWidget(slider)
        lay.addWidget(lab)
        return w

    def params(self) -> DetectParams:
        return DetectParams(
            door_gap=self.door.value() / 1000,
            min_room=self.min_room.value() / 10000,
            detect_blue=self.blue.isChecked(),
            detect_black=self.black.isChecked(),
            blue_sensitivity=self.sens.value() / 100,
            orthogonal=self.ortho.isChecked(),
        )


class CornerHandle(QGraphicsEllipseItem):
    def __init__(self, dialog: "ImportDialog"):
        super().__init__(-8, -8, 16, 16)
        self.dialog = dialog
        self.setBrush(QBrush(QColor(229, 57, 53, 200)))
        self.setPen(QPen(QColor("white"), 2))
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIgnoresTransformations
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setCursor(Qt.SizeAllCursor)
        self.setZValue(10)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.dialog.update_outline()
        return super().itemChange(change, value)


class ImportDialog(QDialog):
    def __init__(self, img: np.ndarray, floor_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kadastr rasmini yuklash")
        self.resize(1150, 780)
        self.img = img

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.view.setBackgroundBrush(QColor("#37474f"))
        self.pix = self.scene.addPixmap(QPixmap())
        self.outline = QGraphicsPolygonItem()
        pen = QPen(QColor("#e53935"), 2)
        pen.setCosmetic(True)
        self.outline.setPen(pen)
        self.outline.setBrush(QColor(229, 57, 53, 25))
        self.scene.addItem(self.outline)
        self.handles = [CornerHandle(self) for _ in range(4)]
        for h in self.handles:
            self.scene.addItem(h)

        side = QVBoxLayout()
        form = QFormLayout()
        self.name = QLineEdit(floor_name)
        form.addRow("Etaj nomi:", self.name)
        side.addLayout(form)

        persp = QGroupBox("Qog'oz chegarasi (telefon rasmi uchun)")
        pl = QVBoxLayout(persp)
        lab = QLabel("Qizil nuqtalarni qog'oz burchaklariga sudrang.\n"
                     "Skaner rasmi bo'lsa - \"Butun rasm\" ni tanlang.")
        lab.setWordWrap(True)
        pl.addWidget(lab)
        row = QHBoxLayout()
        b_auto = QPushButton("Avto topish")
        b_auto.clicked.connect(self.auto_corners)
        b_full = QPushButton("Butun rasm")
        b_full.clicked.connect(self.full_corners)
        row.addWidget(b_auto)
        row.addWidget(b_full)
        pl.addLayout(row)
        row = QHBoxLayout()
        b_l = QPushButton("⟲ 90°")
        b_l.clicked.connect(lambda: self.rotate(cv2.ROTATE_90_COUNTERCLOCKWISE))
        b_r = QPushButton("⟳ 90°")
        b_r.clicked.connect(lambda: self.rotate(cv2.ROTATE_90_CLOCKWISE))
        row.addWidget(b_l)
        row.addWidget(b_r)
        pl.addLayout(row)
        side.addWidget(persp)

        self.auto = QCheckBox("Chizmani avtomatik chizish")
        self.auto.setChecked(True)
        side.addWidget(self.auto)
        self.params_w = ParamsWidget()
        self.auto.toggled.connect(self.params_w.setEnabled)
        side.addWidget(self.params_w)
        side.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Davom etish")
        buttons.button(QDialogButtonBox.Cancel).setText("Bekor qilish")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        side.addWidget(buttons)

        lay = QHBoxLayout(self)
        lay.addWidget(self.view, 1)
        sw = QWidget()
        sw.setLayout(side)
        sw.setFixedWidth(360)
        lay.addWidget(sw)

        self.set_image(img)
        self.auto_corners()

    def set_image(self, img):
        self.img = img
        self.pix.setPixmap(QPixmap.fromImage(cv_to_qimage(img)))
        h, w = img.shape[:2]
        self.scene.setSceneRect(-w * 0.05, -h * 0.05, w * 1.1, h * 1.1)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def showEvent(self, e):
        super().showEvent(e)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def set_corners(self, pts):
        for h, (x, y) in zip(self.handles, pts):
            h.setPos(float(x), float(y))
        self.update_outline()

    def auto_corners(self):
        self.set_corners(find_paper_corners(self.img))

    def full_corners(self):
        h, w = self.img.shape[:2]
        self.set_corners([(0, 0), (w - 1, 0), (w - 1, h - 1), (0, h - 1)])

    def rotate(self, code):
        self.set_image(cv2.rotate(self.img, code))
        self.auto_corners()

    def update_outline(self):
        self.outline.setPolygon(QPolygonF([h.pos() for h in self.handles]))

    def corners(self):
        return [(h.pos().x(), h.pos().y()) for h in self.handles]

    def result_image(self) -> np.ndarray:
        h, w = self.img.shape[:2]
        c = self.corners()
        full = [(0, 0), (w - 1, 0), (w - 1, h - 1), (0, h - 1)]
        if all(abs(a[0] - b[0]) < 2 and abs(a[1] - b[1]) < 2 for a, b in zip(c, full)):
            return self.img
        return warp_to_rect(self.img, c)


class RedetectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Qayta avtomatik chizish")
        lay = QVBoxLayout(self)
        self.params_w = ParamsWidget()
        lay.addWidget(self.params_w)
        self.keep_eq = QCheckBox("Turi tasdiqlangan AT jihozlarini saqlab qolish")
        self.keep_eq.setChecked(True)
        lay.addWidget(self.keep_eq)
        warn = QLabel("Diqqat: joriy xonalar o'chirilib, yangidan chiziladi (Ctrl+Z bilan qaytarish mumkin).")
        warn.setWordWrap(True)
        warn.setStyleSheet("color: #c62828")
        lay.addWidget(warn)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Chizish")
        buttons.button(QDialogButtonBox.Cancel).setText("Bekor qilish")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
