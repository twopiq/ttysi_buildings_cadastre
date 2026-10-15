"""Rasm/PDF yuklash oynalari: sahifa tanlash, etajni kesib olish, masshtab va aniqlash sozlamalari."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSettings, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QImage, QPainter, QPen, QPixmap, QPolygonF, QTransform
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QFrame, QGraphicsEllipseItem, QGraphicsItem, QGraphicsPolygonItem,
                               QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QPushButton, QSlider, QSpinBox, QToolButton, QVBoxLayout,
                               QWidget)

from ..detection import DetectParams, find_paper_corners, warp_to_rect
from . import theme


RATIOS = (100, 150, 200, 250, 300, 400, 500, 1000)


def ratio_presets(spin) -> "QComboBox":
    """Nisbat maydoni yonidagi tez tanlash ro'yxati (1:100 ... 1:1000)."""
    box = QComboBox()
    box.addItem("Tanlash", 0)
    for r in RATIOS:
        box.addItem(f"1:{r}", r)
    box.setToolTip("Ko'p uchraydigan nisbatlar")

    def pick(i):
        r = box.itemData(i)
        if r:
            spin.setValue(r)
        box.blockSignals(True)
        box.setCurrentIndex(0)
        box.blockSignals(False)
    box.currentIndexChanged.connect(pick)
    return box


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

        self.blue = QCheckBox("AT belgilari: ko'k ruchka")
        self.blue.setChecked(p.detect_blue)
        form.addRow(self.blue)
        self.sens = self._slider(0, 100, int(p.blue_sensitivity * 100))
        form.addRow("Belgilar sezgirligi:", self._with_value(self.sens, lambda v: f"{v}%"))
        self.black = QCheckBox("AT belgilari: qora ruchka (qo'lyozma)")
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

IMPORT_STYLE = f"""
QDialog {{ background: {theme.BG}; }}
QFrame#importTop {{ background: {theme.SURFACE}; border-bottom: 1px solid {theme.LINE}; }}
QPushButton#back {{ border: none; background: transparent; color: {theme.PRIMARY}; font-weight: 600; padding: 0 4px; }}
QLabel#title {{ font-weight: 600; font-size: 16px; }}
QFrame#pages, QFrame#side {{ background: {theme.SURFACE}; }}
QFrame#pages {{ border-right: 1px solid {theme.LINE}; }}
QFrame#side {{ border-left: 1px solid {theme.LINE}; }}
QLabel#section {{ font-size: 12px; font-weight: 600; color: {theme.INK_3}; }}
QLabel#fieldLabel {{ font-size: 13px; color: {theme.INK_2}; }}
QLabel#muted {{ color: {theme.INK_2}; font-size: 13px; }}
QLabel#ok {{ color: {theme.OK_FG}; font-size: 12px; }}
QListWidget#pageList {{ border: none; background: transparent; }}
QListWidget#pageList::item {{ border: 1px solid {theme.LINE}; border-radius: 6px; padding: 4px; margin: 2px; color: {theme.INK_2}; }}
QListWidget#pageList::item:selected {{ border: 2px solid {theme.PRIMARY}; background: {theme.SURFACE}; color: {theme.PRIMARY_DARK}; }}
QFrame#autoCard, QFrame#advanced {{ border: 1px solid {theme.LINE}; border-radius: 10px; background: {theme.SURFACE}; }}
QToolButton#expander {{ border: none; font-weight: 600; background: transparent; }}
QPushButton#primary {{ min-height: 48px; font-size: 15px; border-radius: 10px; }}
QPushButton#secondary {{ min-height: 44px; border-radius: 10px; }}
QPushButton#tool {{ min-height: 30px; padding: 0 10px; font-weight: 500; }}
QGroupBox {{ border: none; margin-top: 0; padding-top: 0; font-weight: 600; }}
"""

HANDLE_COLOR = QColor(theme.PRIMARY)


class CornerHandle(QGraphicsEllipseItem):
    def __init__(self, dialog: "ImportDialog"):
        super().__init__(-8, -8, 16, 16)
        self.dialog = dialog
        self.setBrush(QBrush(HANDLE_COLOR))
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
        self.setFrameShape(QFrame.NoFrame)

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
        pen = QPen(HANDLE_COLOR, 2, Qt.DashLine)
        pen.setCosmetic(True)
        return pen


def _field(label: str, widget: QWidget) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    lab = QLabel(label)
    lab.setObjectName("fieldLabel")
    lay.addWidget(lab)
    lay.addWidget(widget)
    return w


class ImportDialog(QDialog):
    """Etaj qo'shish ekrani: (PDF bo'lsa) sahifalar, etajni ramkaga olish, nisbat va avtomatik chizish.

    PDF uchun doc berilsa, sahifalar chap tomonda ko'rinadi va ular orasida o'tish mumkin.
    again - "Yaratish va shu PDF'dan yana etaj" bosilgan.
    """

    def __init__(self, img: np.ndarray | None, floor_name: str, parent=None,
                 paper_mm_per_px: float | None = None, from_pdf: bool = False,
                 doc: QPdfDocument | None = None, page: int = 0, file_name: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Etaj qo'shish")
        self.setStyleSheet(IMPORT_STYLE)
        self.resize(1360, 860)
        self.doc = doc
        self.again = False
        self.paper_mm_per_px = paper_mm_per_px
        self.settings = QSettings("TTYSI", "BinolarKadastr")
        from_pdf = from_pdf or doc is not None

        self.scene = QGraphicsScene(self)
        self.view = CropView(self.scene, self)
        self.view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.view.setBackgroundBrush(QColor("#3A4552"))
        self.pix = self.scene.addPixmap(QPixmap())
        self.outline = QGraphicsPolygonItem()
        pen = QPen(HANDLE_COLOR, 2)
        pen.setCosmetic(True)
        self.outline.setPen(pen)
        self.outline.setBrush(QColor(28, 91, 166, 26))
        self.scene.addItem(self.outline)
        self.size_tag = QGraphicsSimpleTextItem()
        self.size_tag.setBrush(QColor("white"))
        self.size_tag.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.size_tag.setZValue(11)
        f = theme.font(12, QFont.DemiBold)
        self.size_tag.setFont(f)
        self.size_bg = self.scene.addRect(QRectF(), QPen(Qt.NoPen), QBrush(HANDLE_COLOR))
        self.size_bg.setFlag(QGraphicsItem.ItemIgnoresTransformations)
        self.size_bg.setZValue(10.5)
        self.scene.addItem(self.size_tag)
        self.handles = [CornerHandle(self) for _ in range(4)]
        for h in self.handles:
            self.scene.addItem(h)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        top = QFrame()
        top.setObjectName("importTop")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(24, 12, 24, 12)
        tl.setSpacing(20)
        back = QPushButton("‹  Bekor qilish")
        back.setObjectName("back")
        back.clicked.connect(self.reject)
        tl.addWidget(back)
        title = QLabel("Etaj qo'shish" + (f" · {file_name}" if file_name else ""))
        title.setObjectName("title")
        tl.addWidget(title)
        tl.addStretch()
        root.addWidget(top)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root.addLayout(body, 1)

        # --- PDF sahifalari
        self.page_list = None
        if doc is not None:
            nav = QFrame()
            nav.setObjectName("pages")
            nav.setFixedWidth(176)
            nl = QVBoxLayout(nav)
            nl.setContentsMargins(12, 16, 12, 16)
            nl.setSpacing(12)
            lab = QLabel("SAHIFALAR")
            lab.setObjectName("section")
            nl.addWidget(lab)
            self.page_list = QListWidget()
            self.page_list.setObjectName("pageList")
            self.page_list.setIconSize(QSize(126, 96))
            self.page_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.page_list.setViewMode(QListView.IconMode)
            self.page_list.setFlow(QListView.TopToBottom)
            self.page_list.setMovement(QListView.Static)
            self.page_list.setWrapping(False)
            self.page_list.setSpacing(4)
            for i in range(doc.pageCount()):
                s = doc.pagePointSize(i)
                k = 126 / max(s.width(), s.height())
                thumb = doc.render(i, QSize(int(s.width() * k), int(s.height() * k)))
                self.page_list.addItem(QListWidgetItem(QIcon(QPixmap.fromImage(thumb)), f"{i + 1}-sahifa"))
            nl.addWidget(self.page_list, 1)
            body.addWidget(nav)

        # --- rasm va ramka
        center = QVBoxLayout()
        center.setContentsMargins(20, 20, 20, 20)
        center.setSpacing(12)
        row = QHBoxLayout()
        row.setSpacing(8)
        t1 = QLabel("<b>Etajni sichqoncha bilan ramkaga oling</b>")
        t2 = QLabel("— bitta sahifada bir nechta etaj bo'lsa, faqat keraklisini. "
                    "Telefon rasmida nuqtalarni qog'oz burchaklariga sudrang.")
        t2.setObjectName("muted")
        t2.setWordWrap(True)
        row.addWidget(t1)
        row.addWidget(t2, 1)
        center.addLayout(row)
        tools = QHBoxLayout()
        tools.setSpacing(6)
        for text, slot in (("Qog'ozni topish", self.auto_corners), ("Butun sahifa", self.full_corners),
                           ("⟲ 90°", lambda: self.rotate(cv2.ROTATE_90_COUNTERCLOCKWISE)),
                           ("⟳ 90°", lambda: self.rotate(cv2.ROTATE_90_CLOCKWISE))):
            b = QPushButton(text)
            b.setObjectName("tool")
            b.clicked.connect(slot)
            tools.addWidget(b)
        tools.addStretch()
        hint = QLabel("G'ildirak — kattalashtirish")
        hint.setObjectName("muted")
        tools.addWidget(hint)
        center.addLayout(tools)
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #3A4552; border-radius: 12px; }")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(8, 8, 8, 8)
        fl.addWidget(self.view)
        center.addWidget(frame, 1)
        body.addLayout(center, 1)

        # --- sozlamalar
        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(360)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(20, 20, 20, 20)
        sl.setSpacing(16)
        self.name = QLineEdit(floor_name)
        sl.addWidget(_field("Etaj nomi", self.name))
        self.scale = QSpinBox()
        self.scale.setRange(0, 10000)
        self.scale.setPrefix("1 : ")
        self.scale.setSpecialValueText("noma'lum")
        self.scale.setButtonSymbols(QSpinBox.NoButtons)
        self.scale.setValue(int(self.settings.value("last_scale", 300)) if paper_mm_per_px or from_pdf else 0)
        self.scale.setToolTip("Kadastr shtampidagi \"Нисбат\" (masalan 1:300 yoki 1:400)")
        srow = QWidget()
        sr = QHBoxLayout(srow)
        sr.setContentsMargins(0, 0, 0, 0)
        sr.setSpacing(6)
        sr.addWidget(self.scale, 1)
        self.scale_presets = ratio_presets(self.scale)
        sr.addWidget(self.scale_presets)
        sw = _field("Nisbat (shtampdagi \"Нисбат\")", srow)
        self.scale_hint = QLabel()
        self.scale_hint.setWordWrap(True)
        sw.layout().addWidget(self.scale_hint)
        sl.addWidget(sw)

        card = QFrame()
        card.setObjectName("autoCard")
        cl = QHBoxLayout(card)
        cl.setContentsMargins(12, 12, 12, 12)
        cl.setSpacing(10)
        self.auto = QCheckBox()
        self.auto_title_text = "<b>Chizmani avtomatik chizish</b>"
        self.auto.setChecked(True)
        cl.addWidget(self.auto, 0, Qt.AlignTop)
        tc = QVBoxLayout()
        tc.setSpacing(2)
        at = QLabel(self.auto_title_text)
        ad = QLabel("Xonalar, koridorlar va ko'k ruchkadagi belgilar topiladi va raqamlanadi.")
        self.auto_title, self.auto_desc = at, ad
        ad.setObjectName("muted")
        ad.setWordWrap(True)
        for w in (at, ad):
            w.mousePressEvent = lambda e: self.auto.toggle()
            tc.addWidget(w)
        cl.addLayout(tc, 1)
        sl.addWidget(card)

        adv = QFrame()
        adv.setObjectName("advanced")
        al = QVBoxLayout(adv)
        al.setContentsMargins(12, 8, 12, 8)
        self.expander = QToolButton()
        self.expander.setObjectName("expander")
        self.expander.setText("Kengaytirilgan sozlamalar")
        self.expander.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.expander.setArrowType(Qt.RightArrow)
        self.expander.setCheckable(True)
        al.addWidget(self.expander)
        self.adv_body = QWidget()
        bl = QVBoxLayout(self.adv_body)
        bl.setContentsMargins(0, 4, 0, 4)
        self.params_w = ParamsWidget(metric=False)
        self.params_w.setTitle("")
        bl.addWidget(self.params_w)
        self.dpi = QComboBox()
        for d in (150, 200, 300):
            self.dpi.addItem(f"{d} DPI", d)
        self.dpi.setCurrentIndex(1)
        if doc is not None:
            bl.addWidget(_field("PDF aniqligi", self.dpi))
        self.adv_body.hide()
        al.addWidget(self.adv_body)
        self.expander.toggled.connect(self._toggle_advanced)
        self.auto.toggled.connect(self.params_w.setEnabled)
        sl.addWidget(adv)
        sl.addStretch()

        self.b_create = QPushButton("Chizmani yaratish")
        self.b_create.setObjectName("primary")
        self.b_create.setDefault(True)
        self.b_create.clicked.connect(self.accept)
        sl.addWidget(self.b_create)
        self.b_again = None
        if doc is not None:
            b = QPushButton("Yaratish va shu PDF'dan yana etaj")
            b.setObjectName("secondary")
            b.clicked.connect(self.accept_again)
            sl.addWidget(b)
            self.b_again = b
        body.addWidget(side)

        self.scale.valueChanged.connect(self.update_scale)
        self.name.textChanged.connect(lambda _: self.update_outline())
        self.img = None
        if doc is not None:
            self.page_list.currentRowChanged.connect(self.load_page)
            self.dpi.currentIndexChanged.connect(lambda _: self.load_page(self.page()))
            self.page_list.setCurrentRow(min(max(page, 0), doc.pageCount() - 1))
        else:
            self.set_image(img)
            if from_pdf:
                self.full_corners()
            else:
                self.auto_corners()
        self.update_scale()

    def set_replace_mode(self, floor_name: str, has_drawing: bool):
        """Mavjud etajning kadastr rasmini almashtirish: etaj nomi o'zgarmaydi, chizma odatda saqlanadi."""
        self.setWindowTitle(f"Kadastr rasmini almashtirish — {floor_name}")
        self.name.setText(floor_name)
        self.name.setEnabled(False)
        self.b_create.setText("Rasmni almashtirish")
        if self.b_again is not None:
            self.b_again.hide()
        self.auto_title.setText("<b>Xonalarni yangi rasmdan qayta chizish</b>")
        self.auto_desc.setText("Joriy xonalar o'rniga yangi rasmdan chiziladi. Turi tasdiqlangan AT belgilari, "
                               "eshiklar va devorlar saqlanadi. Belgilanmasa - chizma o'zgarmaydi, faqat fon "
                               "rasmi almashadi.")
        self.auto.setChecked(not has_drawing)

    # --- PDF sahifalari
    def page(self) -> int:
        return max(0, self.page_list.currentRow()) if self.page_list is not None else 0

    def load_page(self, i: int):
        if self.doc is None or i < 0:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            dpi = self.dpi.currentData()
            s = self.doc.pagePointSize(i)
            img = self.doc.render(i, QSize(round(s.width() / 72 * dpi), round(s.height() / 72 * dpi)))
            out = QImage(img.size(), QImage.Format_RGB888)
            out.fill(QColor("white"))
            p = QPainter(out)
            p.drawImage(0, 0, img)
            p.end()
            self.paper_mm_per_px = 25.4 / dpi
            self.set_image(qimage_to_cv(out))
            self.full_corners()
        finally:
            QApplication.restoreOverrideCursor()
        self.update_scale()

    def _toggle_advanced(self, on: bool):
        self.expander.setArrowType(Qt.DownArrow if on else Qt.RightArrow)
        self.adv_body.setVisible(on)

    # --- masshtab
    def m_per_px(self) -> float | None:
        """Kesib olingan rasmdagi 1 piksel necha metr (PDF/DPI + nisbat ma'lum bo'lsa)."""
        if self.paper_mm_per_px is None or self.scale.value() <= 0:
            return None
        return self.paper_mm_per_px * self.scale.value() / 1000.0

    def update_scale(self, *_):
        mpp = self.m_per_px()
        self.params_w.set_metric(mpp is not None)
        if mpp:
            self.scale_hint.setObjectName("ok")
            self.scale_hint.setText(f"✓ Masshtab hisoblandi: 1 px = {mpp * 100:.1f} sm")
        elif self.paper_mm_per_px is None:
            self.scale_hint.setObjectName("muted")
            self.scale_hint.setText("Rasmda qog'oz o'lchami yo'q (telefon rasmi): nisbat saqlanadi, masshtabni "
                                    "keyin 2 nuqta bilan belgilang - shundan so'ng nisbat o'zgarsa o'zi "
                                    "qayta hisoblanadi.")
        else:
            self.scale_hint.setObjectName("muted")
            self.scale_hint.setText("Nisbatni kiriting — maydonlar m² da hisoblanadi.")
        self.scale_hint.style().unpolish(self.scale_hint)
        self.scale_hint.style().polish(self.scale_hint)
        self.update_outline()

    def accept(self):
        if self.scale.value() > 0:
            self.settings.setValue("last_scale", self.scale.value())
        super().accept()

    def accept_again(self):
        self.again = True
        self.accept()

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
        poly = QPolygonF([h.pos() for h in self.handles])
        self.outline.setPolygon(poly)
        mpp = self.m_per_px() if hasattr(self, "scale") else None
        name = self.name.text().strip() if hasattr(self, "name") else ""
        r = poly.boundingRect()
        text = name
        if mpp and r.width() > 0:
            text += f" · {r.width() * mpp:.0f} × {r.height() * mpp:.0f} m"
        self.size_tag.setText(text)
        br = self.size_tag.boundingRect()
        anchor = QPointF(r.left(), r.bottom())
        self.size_tag.setPos(anchor)
        self.size_tag.setTransform(QTransform.fromTranslate(8, 11))
        self.size_bg.setPos(anchor)
        self.size_bg.setRect(QRectF(0, 8, br.width() + 16, br.height() + 6))
        self.size_bg.setVisible(bool(text))
        self.size_tag.setVisible(bool(text))

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
