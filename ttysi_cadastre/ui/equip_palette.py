"""Suzuvchi AT jihoz paneli: chizma ustida kichik oyna, sarlavhasidan ushlab istalgan joyga suriladi.

Chap paneldagi tugmalar bilan bir xil amallar (QAction) ishlatiladi - tanlangan jihoz ikkalasida ham
belgilanadi. Joyi, yo'nalishi (tik / yotiq) va rejimi sozlamalarda saqlanadi.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QSettings, Qt, Signal
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (QCheckBox, QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QToolButton, QVBoxLayout, QWidget)

from ..equipment import EQUIPMENT_TYPES
from . import theme
from .widgets import EquipButton

KEY = "equip_palette/"
MARGIN = 8

STYLE = f"""
QFrame#equipPalette {{ background: {theme.SURFACE}; border: 1px solid {theme.LINE_STRONG}; border-radius: 12px; }}
QFrame#paletteHead {{ background: #EEF1F4; border-top-left-radius: 12px; border-top-right-radius: 12px; }}
QLabel#paletteTitle {{ color: {theme.INK_2}; font-size: 12px; font-weight: 600; }}
QToolButton#paletteBtn {{ border: none; border-radius: 6px; min-width: 24px; min-height: 22px; padding: 0;
    color: {theme.INK_2}; font-size: 13px; background: transparent; }}
QToolButton#paletteBtn:hover {{ background: {theme.PRIMARY_SOFT}; color: {theme.PRIMARY_DARK}; }}
QPushButton#nextUnknown {{ min-height: 28px; padding: 0 8px; font-size: 12px; color: {theme.WARN_FG};
    border: 1px solid #E9C79F; background: {theme.WARN_BG}; border-radius: 8px; }}
"""


class _Head(QFrame):
    """Sarlavha: ushlab surish."""

    def __init__(self, palette: "EquipPalette"):
        super().__init__()
        self.palette = palette
        self.setObjectName("paletteHead")
        self.setCursor(Qt.SizeAllCursor)
        self._grab: QPoint | None = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._grab = e.globalPosition().toPoint() - self.palette.pos()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._grab is not None:
            self.palette.move_to(e.globalPosition().toPoint() - self._grab)
            e.accept()

    def mouseReleaseEvent(self, e):
        if self._grab is not None:
            self._grab = None
            self.palette.save_pos()
            e.accept()

    def mouseDoubleClickEvent(self, e):
        self.palette.toggle_orientation()


class EquipPalette(QFrame):
    dock_requested = Signal()
    next_unknown = Signal()

    def __init__(self, host: QWidget, actions: dict[str, QAction], plan_action: QAction, settings: QSettings):
        super().__init__(host)
        self.host = host
        self.actions = actions
        self.plan_action = plan_action
        self.settings = settings
        self.setObjectName("equipPalette")
        self.setStyleSheet(STYLE)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 60))
        self.setGraphicsEffect(shadow)
        self.horizontal = settings.value(KEY + "horizontal", False, type=bool)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 8)
        lay.setSpacing(6)
        self.head = _Head(self)
        hl = QHBoxLayout(self.head)
        hl.setContentsMargins(8, 3, 4, 3)
        hl.setSpacing(2)
        t = QLabel("⠿  AT jihoz")
        t.setObjectName("paletteTitle")
        t.setAttribute(Qt.WA_TransparentForMouseEvents)
        hl.addWidget(t, 1)
        self.b_orient = self._btn("⇄", "Tik / yotiq ko'rinish (sarlavhani ikki marta bosish ham)",
                                  self.toggle_orientation)
        self.b_dock = self._btn("⇤", "Chap panelga qaytarish", self.dock_requested.emit)
        hl.addWidget(self.b_orient)
        hl.addWidget(self.b_dock)
        lay.addWidget(self.head)

        self.body = None
        self.buttons = []
        for t in EQUIPMENT_TYPES:
            b = EquipButton(t.code, actions[t.code])
            b.setFocusPolicy(Qt.NoFocus)
            b.setMinimumWidth(52)
            self.buttons.append(b)
        self.plan = QCheckBox("Kerak (reja)")
        self.plan.setFocusPolicy(Qt.NoFocus)
        self.plan.setToolTip(plan_action.toolTip())
        self.plan.setChecked(plan_action.isChecked())
        self.plan.toggled.connect(plan_action.setChecked)
        plan_action.toggled.connect(self.plan.setChecked)
        self.b_next = QPushButton()
        self.b_next.setObjectName("nextUnknown")
        self.b_next.setFocusPolicy(Qt.NoFocus)
        self.b_next.setToolTip("Keyingi tasdiqlanmagan (?) belgini tanlash")
        self.b_next.clicked.connect(self.next_unknown.emit)
        self.b_next.hide()
        self.body = QWidget()
        lay.addWidget(self.body)
        self._layout_body()
        self.hide()
        host.installEventFilter(self)

    def _btn(self, text, tip, slot) -> QToolButton:
        b = QToolButton()
        b.setObjectName("paletteBtn")
        b.setText(text)
        b.setToolTip(tip)
        b.setFocusPolicy(Qt.NoFocus)
        b.clicked.connect(slot)
        return b

    def _layout_body(self):
        """Tugmalarni tik (2 ustun) yoki yotiq (bitta qator) joylash - har safar yangi to'r."""
        old = self.body
        self.body = QWidget()
        self.grid = QGridLayout(self.body)
        self.grid.setContentsMargins(8, 0, 8, 0)
        self.grid.setSpacing(6)
        n = len(self.buttons)
        if self.horizontal:
            for i, b in enumerate(self.buttons):
                self.grid.addWidget(b, 0, i)
            self.grid.addWidget(self.plan, 0, n)
            self.grid.addWidget(self.b_next, 0, n + 1)
        else:
            for i, b in enumerate(self.buttons):
                self.grid.addWidget(b, i // 2, i % 2)
            rows = (n + 1) // 2
            self.grid.addWidget(self.plan, rows, 0, 1, 2)
            self.grid.addWidget(self.b_next, rows + 1, 0, 1, 2)
        if old is not None:
            self.layout().replaceWidget(old, self.body)
            old.hide()
            old.deleteLater()
            self.body.show()                   # ko'rinib turgan oynaga keyin qo'shilgan bola o'zi ko'rinmaydi
        self._fit()

    def _fit(self):
        self.body.layout().activate()
        self.layout().activate()
        self.resize(self.sizeHint())

    def set_unknown(self, n: int):
        self.b_next.setText(f"Keyingi ?  ({n})")
        self.b_next.setVisible(n > 0)
        self._fit()
        self.clamp()

    def toggle_orientation(self):
        self.horizontal = not self.horizontal
        self.settings.setValue(KEY + "horizontal", self.horizontal)
        self._layout_body()
        self.clamp()
        self.save_pos()

    # ------------------------------------------------------------ joylashuv
    def area(self):
        """Surish mumkin bo'lgan joy - chizma maydoni (aylantirish chiziqlarini to'smaydi)."""
        vp = getattr(self.host, "viewport", None)
        return vp().geometry() if vp else self.host.rect()

    def move_to(self, p: QPoint):
        r = self.area()
        x = max(r.left() + MARGIN, min(p.x(), r.right() + 1 - self.width() - MARGIN))
        y = max(r.top() + MARGIN, min(p.y(), r.bottom() + 1 - self.height() - MARGIN))
        self.move(x, y)
        self.raise_()

    def clamp(self):
        self.move_to(self.pos())

    def save_pos(self):
        """Joyi oyna o'lchamiga nisbatan saqlanadi (oyna kattalashsa ham shu burchakda qoladi)."""
        r = self.area()
        fx = (self.x() - r.left()) / max(1, r.width() - self.width())
        fy = (self.y() - r.top()) / max(1, r.height() - self.height())
        self.settings.setValue(KEY + "pos", f"{fx:.4f},{fy:.4f}")

    def restore_pos(self):
        r = self.area()
        try:
            fx, fy = (float(v) for v in str(self.settings.value(KEY + "pos", "")).split(","))
        except ValueError:
            fx, fy = 0.0, 0.0                          # birinchi marta - chap yuqori burchak
        self.move_to(QPoint(r.left() + round(fx * (r.width() - self.width())),
                            r.top() + round(fy * (r.height() - self.height()))))

    def place_near(self, p: QPoint):
        """Ko'rsatilgan nuqta (host koordinatalari) yoniga - sichqonchadan biroz o'ngga va pastga."""
        self.move_to(p + QPoint(24, 16))
        self.save_pos()

    def eventFilter(self, obj, e):
        if obj is self.host and e.type() == QEvent.Resize and self.isVisible():
            self.restore_pos()
        return False
