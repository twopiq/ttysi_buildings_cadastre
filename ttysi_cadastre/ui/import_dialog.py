"""Rasm/PDF yuklash oynalari: sahifa tanlash, etajni kesib olish, masshtab va aniqlash sozlamalari."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QRectF, QSettings, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QImage, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QGraphicsEllipseItem, QGraphicsItem, QGraphicsPolygonItem,
                               QGraphicsRectItem, QGraphicsScene, QGraphicsView, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QPushButton, QSlider, QSpinBox, QVBoxLayout, QWidget)

from ..detection import DetectParams, find_paper_corners, warp_to_rect


def cv_to_qimage(img: np.ndarray) -> QImage:
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()


def qimage_to_cv(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format_RGB888)
    w, h = img.width(), img.height()
    arr = np.frombuffer(img.constBits(), np.uint8, count=img.bytesPerLine() * h)
    arr = arr.reshape(h, img.bytesPerLine())[:, :w * 3].reshape(h, w, 3)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def image_paper_mm_per_px(path: str) -> float | None:
    """Skaner rasmining DPI ma'lumotidan qog'oz o'lchamini oladi (72/96 - standart, ishonchsiz)."""
    img = QImage(path)
    dpm = img.dotsPerMeterX()
    dpi = dpm * 0.0254
    if img.isNull() or dpi < 100 or dpi > 1300:
        return None
    return 1000.0 / dpm


# ======================================================================== PDF sahifasini tanlash

class PdfPageDialog(QDialog):
    """PDF sahifasini tanlash (bitta sahifada bir nechta etaj bo'lishi mumkin)."""

    def __init__(self, doc: QPdfDocument, parent=None, current: int = 0):
        super().__init__(parent)
        self.doc = doc
        self.setWindowTitle("PDF sahifasini tanlang")
        self.resize(900, 600)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Etaj joylashgan sahifani tanlang. Keyingi oynada etajni ramka bilan belgilaysiz."))
        self.list = QListWidget()
        self.list.setViewMode(QListView.IconMode)
        self.list.setIconSize(QSize(260, 190))
        self.list.setResizeMode(QListView.Adjust)
        self.list.setSpacing(8)
        for i in range(doc.pageCount()):
            s = doc.pagePointSize(i)
            k = 260 / max(s.width(), s.height())
            thumb = doc.render(i, QSize(int(s.width() * k), int(s.height() * k)))
            self.list.addItem(QListWidgetItem(QIcon(QPixmap.fromImage(thumb)), f"{i + 1}-sahifa"))
        self.list.setCurrentRow(min(current, doc.pageCount() - 1))
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("Aniqlik:"))
        self.dpi = QComboBox()
        for d in (150, 200, 300):
            self.dpi.addItem(f"{d} DPI", d)
        self.dpi.setCurrentIndex(1)
        row.addWidget(self.dpi)
        row.addStretch()
        lay.addLayout(row)
        b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        b.button(QDialogButtonBox.Ok).setText("Tanlash")
        b.button(QDialogButtonBox.Cancel).setText("Tugatish")
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        lay.addWidget(b)

    def page(self) -> int:
        return max(0, self.list.currentRow())

    def render(self) -> tuple[np.ndarray, float]:
        """Tanlangan sahifa rasmi va qog'ozdagi mm/piksel."""
        dpi = self.dpi.currentData()
        s = self.doc.pagePointSize(self.page())
        img = self.doc.render(self.page(), QSize(round(s.width() / 72 * dpi), round(s.height() / 72 * dpi)))
        # shaffof fonni oq qilish
        out = QImage(img.size(), QImage.Format_RGB888)
        out.fill(QColor("white"))
        p = QPainter(out)
        p.drawImage(0, 0, img)
        p.end()
        return qimage_to_cv(out), 25.4 / dpi


# ======================================================================== aniqlash sozlamalari

class ParamsWidget(QGroupBox):
    """Aniqlash sozlamalari. Masshtab ma'lum bo'lsa - metrlarda, aks holda rasm o'lchamiga nisbatan."""

    def __init__(self, params: DetectParams | None = None, metric: bool = False, parent=None):
        super().__init__("Avtomatik chizish sozlamalari", parent)
        p = params or DetectParams()
        form = QFormLayout(self)
        self.metric_box = QWidget()
        mf = QFormLayout(self.metric_box)
        mf.setContentsMargins(0, 0, 0, 0)
        self.wall_m = self._dspin(0.1, 2.0, p.wall_m, " m")
        self.door_m = self._dspin(0.6, 4.0, p.door_m, " m")
        self.min_m2 = self._dspin(0.5, 50, p.min_room_m2, " m²")
        mf.addRow("Devor qalinligi:", self.wall_m)
        mf.addRow("Eshik kengligi:", self.door_m)
        mf.addRow("Eng kichik xona:", self.min_m2)
        form.addRow(self.metric_box)
        self.frac_box = QWidget()
        ff = QFormLayout(self.frac_box)
        ff.setContentsMargins(0, 0, 0, 0)
        self.door = self._slider(10, 80, int(p.door_gap * 1000))
        ff.addRow("Eshik kengligi:", self._with_value(self.door, lambda v: f"{v / 10:.1f}%"))
        self.min_room = self._slider(2, 50, int(p.min_room * 10000))
        ff.addRow("Eng kichik xona:", self._with_value(self.min_room, lambda v: f"{v / 100:.2f}%"))
        form.addRow(self.frac_box)
        self.set_metric(metric)

        self.blue = QCheckBox("Ko'k ruchka belgilarini topish")
        self.blue.setChecked(p.detect_blue)
        form.addRow(self.blue)
        self.sens = self._slider(0, 100, int(p.blue_sensitivity * 100))
        form.addRow("Ko'k rang sezgirligi:", self._with_value(self.sens, lambda v: f"{v}%"))
        self.black = QCheckBox("Qora yozuvlarni ham belgi nomzodi qilish\n"
                               "(ishonchsiz: bosma raqamlar ham tushadi)")
        self.black.setChecked(p.detect_black)
        form.addRow(self.black)
        self.ortho = QCheckBox("Devorlarni gorizontal/vertikal tekislash")
        self.ortho.setChecked(p.orthogonal)
        form.addRow(self.ortho)
        self.numbering = QCheckBox("Xonalarni avtomatik raqamlash")
        self.numbering.setChecked(True)
        form.addRow(self.numbering)
        hint = QLabel("Xona koridorga qo'shilib ketsa - eshik kengligini oshiring.\n"
                      "Koridor bo'laklanib ketsa - kamaytiring.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #616161")
        form.addRow(hint)

    def set_metric(self, on: bool):
        self.use_metric = on
        self.metric_box.setVisible(on)
        self.frac_box.setVisible(not on)

    @staticmethod
    def _dspin(lo, hi, val, suffix):
        s = QDoubleSpinBox()
        s.setRange(lo, hi)
        s.setDecimals(2)
        s.setSingleStep(0.1)
        s.setValue(val)
        s.setSuffix(suffix)
        return s

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

    def params(self, m_per_px: float | None = None) -> DetectParams:
        return DetectParams(
            m_per_px=m_per_px if self.use_metric else None,
            wall_m=self.wall_m.value(),
            door_m=self.door_m.value(),
            min_room_m2=self.min_m2.value(),
            door_gap=self.door.value() / 1000,
            min_room=self.min_room.value() / 10000,
            detect_blue=self.blue.isChecked(),
            detect_black=self.black.isChecked(),
            blue_sensitivity=self.sens.value() / 100,
            orthogonal=self.ortho.isChecked(),
        )


# ======================================================================== kesib olish va perspektiva

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


class CropView(QGraphicsView):
    """Bo'sh joyda sichqonchani bosib tortish - etajni to'rtburchak ramka bilan belgilash."""

    def __init__(self, scene, dialog: "ImportDialog"):
        super().__init__(scene)
        self.dialog = dialog
        self.start = None
        self.band: QGraphicsRectItem | None = None
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

    def wheelEvent(self, event):
        f = 1.0015 ** event.angleDelta().y()
        self.scale(f, f)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not isinstance(self.itemAt(event.position().toPoint()), CornerHandle):
            self.start = self.mapToScene(event.position().toPoint())
            self.band = self.scene().addRect(QRectF(self.start, self.start), self._pen())
            self.band.setZValue(20)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.band.setRect(QRectF(self.start, self.mapToScene(event.position().toPoint())).normalized())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.start is not None:
            r = self.band.rect()
            self.scene().removeItem(self.band)
            self.band, self.start = None, None
            if r.width() > 10 and r.height() > 10:
                self.dialog.set_rect(r)
            return
        super().mouseReleaseEvent(event)

    @staticmethod
    def _pen():
        pen = QPen(QColor("#1e88e5"), 2, Qt.DashLine)
        pen.setCosmetic(True)
        return pen


class ImportDialog(QDialog):
    def __init__(self, img: np.ndarray, floor_name: str, parent=None,
                 paper_mm_per_px: float | None = None, from_pdf: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Etajni yuklash")
        self.resize(1250, 820)
        self.img = img
        self.paper_mm_per_px = paper_mm_per_px
        self.settings = QSettings("TTYSI", "BinolarKadastr")

        self.scene = QGraphicsScene(self)
        self.view = CropView(self.scene, self)
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
        self.scale = QSpinBox()
        self.scale.setRange(0, 10000)
        self.scale.setPrefix("1 : ")
        self.scale.setSpecialValueText("noma'lum")
        self.scale.setValue(int(self.settings.value("last_scale", 300)) if paper_mm_per_px else 0)
        self.scale.setEnabled(paper_mm_per_px is not None)
        self.scale.setToolTip("Kadastr shtampidagi \"Нисбат\" (masalan 1:300 yoki 1:400)")
        form.addRow("Nisbat:", self.scale)
        side.addLayout(form)
        if paper_mm_per_px is None:
            lab = QLabel("Rasmda qog'oz o'lchami yo'q - masshtabni keyin \"Etaj → Masshtabni belgilash\" "
                         "orqali bering.")
            lab.setWordWrap(True)
            lab.setStyleSheet("color: #616161")
            side.addWidget(lab)

        crop = QGroupBox("Etaj chegarasi")
        pl = QVBoxLayout(crop)
        lab = QLabel("Etajni sichqoncha bilan <b>ramkaga oling</b> (bitta sahifada bir nechta etaj "
                     "bo'lsa, faqat keraklisini). Telefon rasmida qizil nuqtalarni qog'oz "
                     "burchaklariga sudrang. G'ildirak - kattalashtirish.")
        lab.setWordWrap(True)
        pl.addWidget(lab)
        row = QHBoxLayout()
        b_auto = QPushButton("Qog'ozni topish")
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
        side.addWidget(crop)

        self.auto = QCheckBox("Chizmani avtomatik chizish")
        self.auto.setChecked(True)
        side.addWidget(self.auto)
        self.params_w = ParamsWidget(metric=self.m_per_px() is not None)
        self.scale.valueChanged.connect(lambda _: self.params_w.set_metric(self.m_per_px() is not None))
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
        sw.setFixedWidth(380)
        lay.addWidget(sw)

        self.set_image(img)
        if from_pdf:
            self.full_corners()
        else:
            self.auto_corners()

    # --- masshtab
    def m_per_px(self) -> float | None:
        """Kesib olingan rasmdagi 1 piksel necha metr (PDF/DPI + nisbat ma'lum bo'lsa)."""
        if self.paper_mm_per_px is None or self.scale.value() <= 0:
            return None
        return self.paper_mm_per_px * self.scale.value() / 1000.0

    def accept(self):
        if self.scale.value() > 0:
            self.settings.setValue("last_scale", self.scale.value())
        super().accept()

    # --- rasm va burchaklar
    def set_image(self, img):
        self.img = img
        self.pix.setPixmap(QPixmap.fromImage(cv_to_qimage(img)))
        h, w = img.shape[:2]
        self.scene.setSceneRect(-w * 0.03, -h * 0.03, w * 1.06, h * 1.06)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def showEvent(self, e):
        super().showEvent(e)
        self.view.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def set_corners(self, pts):
        for h, (x, y) in zip(self.handles, pts):
            h.setPos(float(x), float(y))
        self.update_outline()

    def set_rect(self, r: QRectF):
        h, w = self.img.shape[:2]
        r = r.intersected(QRectF(0, 0, w - 1, h - 1))
        self.set_corners([(r.left(), r.top()), (r.right(), r.top()),
                          (r.right(), r.bottom()), (r.left(), r.bottom())])

    def auto_corners(self):
        self.set_corners(find_paper_corners(self.img))

    def full_corners(self):
        h, w = self.img.shape[:2]
        self.set_corners([(0, 0), (w - 1, 0), (w - 1, h - 1), (0, h - 1)])

    def rotate(self, code):
        self.set_image(cv2.rotate(self.img, code))
        self.full_corners()

    def update_outline(self):
        self.outline.setPolygon(QPolygonF([h.pos() for h in self.handles]))

    def corners(self):
        return [(h.pos().x(), h.pos().y()) for h in self.handles]

    def result_image(self) -> np.ndarray:
        c = np.array(self.corners())
        xs, ys = c[:, 0], c[:, 1]
        # to'g'ri to'rtburchak bo'lsa - oddiy kesish (piksel o'lchami saqlanadi)
        if np.ptp(np.sort(xs)[:2]) < 2 and np.ptp(np.sort(xs)[2:]) < 2 \
                and np.ptp(np.sort(ys)[:2]) < 2 and np.ptp(np.sort(ys)[2:]) < 2:
            x0, x1 = int(round(xs.min())), int(round(xs.max())) + 1
            y0, y1 = int(round(ys.min())), int(round(ys.max())) + 1
            return self.img[max(0, y0):y1, max(0, x0):x1].copy()
        return warp_to_rect(self.img, c)


class RedetectDialog(QDialog):
    def __init__(self, parent=None, metric: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Qayta avtomatik chizish")
        lay = QVBoxLayout(self)
        self.params_w = ParamsWidget(metric=metric)
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
