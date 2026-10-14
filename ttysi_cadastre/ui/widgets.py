"""Dizayn tizimining umumiy elementlari: ikonkalar, etaj tablari, ish bosqichlari, plitkalar."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea,
                               QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from ..equipment import EQUIPMENT_TYPES, get_type
from ..render import draw_equipment_symbol
from . import theme

# 24x24 chiziqli ikonkalar (dizayn maketidagi bilan bir xil)
ICONS = {
    "select": '<path d="M5 3l14 8-6 2-2 6z"/>',
    "room_poly": '<path d="M4 9l7-5 9 3-2 13H6z"/>',
    "room_rect": '<rect x="4" y="5" width="16" height="14"/>',
    "wall": '<path d="M5 5v14h14" stroke-width="3.5" stroke-linecap="square" stroke-linejoin="miter"/>',
    "door": '<path d="M3 20h18"/><path d="M6 20V8"/><path d="M6 8a12 12 0 0 1 12 12"/>',
    "stairs": '<rect x="5" y="3" width="14" height="18"/><path d="M5 7h14M5 11h14M5 15h14"/>',
    "dome": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4.5" stroke-dasharray="2 2"/>',
    "split": '<rect x="4" y="5" width="16" height="14"/><path d="M12 3v18" stroke-dasharray="3 3"/>',
    "undo": '<path d="M9 14L4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "redo": '<path d="M15 14l5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
    "export": '<path d="M12 3v12"/><path d="M7 10l5 5 5-5"/><path d="M5 21h14"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "fit": '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
    "back": '<path d="M15 18l-6-6 6-6"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1'
                'M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
    "org": '<path d="M4 21V6l8-3 8 3v15"/><path d="M2 21h20M10 21v-4h4v4M8 9h2M14 9h2M8 13h2M14 13h2"/>',
    "folder": '<path d="M3 6h6l2 2h10v11H3z"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
    "warn": '<path d="M12 3l10 18H2z"/><path d="M12 10v4M12 18h.01"/>',
}


def svg_pixmap(name: str, color: str, size: int = 20, stroke: float = 2.0) -> QPixmap:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
           f'{ICONS[name]}</svg>')
    ratio = 2
    pm = QPixmap(size * ratio, size * ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, size * ratio, size * ratio))
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def svg_icon(name: str, color: str = theme.INK_2, active: str | None = None, size: int = 20) -> QIcon:
    icon = QIcon()
    icon.addPixmap(svg_pixmap(name, color, size), QIcon.Normal, QIcon.Off)
    icon.addPixmap(svg_pixmap(name, active or color, size), QIcon.Normal, QIcon.On)
    icon.addPixmap(svg_pixmap(name, "#A8B0BB", size), QIcon.Disabled, QIcon.Off)
    return icon


def type_icon(code: str, size: int = 32) -> QIcon:
    pm = QPixmap(size * 2, size * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    draw_equipment_symbol(p, code, QPointF(size, size), size * 0.8)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


def kbd(text: str) -> str:
    """Matn ichidagi klaviatura tugmasi (QLabel rich text)."""
    if not text:
        return ""
    return (f"<span style=\"font-family:'IBM Plex Mono',monospace; background-color:#EEF1F4; "
            f"color:{theme.INK}\">&nbsp;{text}&nbsp;</span>")


def section_title(text: str) -> QLabel:
    lab = QLabel(text.upper())
    lab.setObjectName("section")
    return lab


def hline() -> QFrame:
    f = QFrame()
    f.setObjectName("hline")
    f.setFixedHeight(1)
    return f


def field(label: str, widget: QWidget) -> QWidget:
    """Yorliq ustida, maydon pastida (dizayndagi forma ko'rinishi)."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    lab = QLabel(label)
    lab.setObjectName("fieldLabel")
    lay.addWidget(lab)
    lay.addWidget(widget)
    return w


def chip(text: str, bg: str, fg: str = "white", dashed: bool = False) -> QLabel:
    lab = QLabel(text)
    border = f"1px dashed {fg}" if dashed else "none"
    lab.setStyleSheet(f"QLabel {{ padding: 3px 8px; border-radius: 11px; background: {bg}; color: {fg};"
                      f" font-size: 12px; font-weight: 600; border: {border}; }}")
    return lab


class LayoutButton(QPushButton):
    """Ichida layout (bir nechta yorliq) bo'lgan tugma: o'lchami layout bo'yicha hisoblanadi."""

    def sizeHint(self) -> QSize:
        s = super().sizeHint()
        if self.layout() is not None:
            ls = self.layout().sizeHint()
            return QSize(max(s.width(), ls.width()), max(s.height(), ls.height()))
        return s

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


# ======================================================================== etaj tablari

class FloorTabs(QScrollArea):
    """Yuqori paneldagi etajlar: bosish - ochish, o'ng tugma - amallar, "+ Etaj" - yangi etaj."""

    selected = Signal(int)
    add_clicked = Signal()

    def __init__(self, menu_factory=None, parent=None):
        super().__init__(parent)
        self.menu_factory = menu_factory     # f(index) -> QMenu
        self.setObjectName("floorTabs")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFixedHeight(48)
        inner = QWidget()
        inner.setObjectName("floorTabsInner")
        self.lay = QHBoxLayout(inner)
        self.lay.setContentsMargins(0, 4, 0, 4)
        self.lay.setSpacing(6)
        self.setWidget(inner)
        self.buttons: list[QPushButton] = []
        self.add_btn = QPushButton("+ Etaj")
        self.add_btn.setObjectName("addFloor")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self.add_clicked)
        self.current = -1

    def set_floors(self, floors, current: int):
        for b in self.buttons:
            b.hide()
            b.deleteLater()
        self.buttons = []
        while self.lay.count():
            self.lay.takeAt(0)
        for i, f in enumerate(floors):
            unknown = sum(1 for e in f.equipment if e.code == "?")
            b = LayoutButton()
            b.setObjectName("floorTab")
            b.setCheckable(True)
            b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            b.setCursor(Qt.PointingHandCursor)
            b.setAccessibleName(f.name)
            b.setContextMenuPolicy(Qt.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda pos, i=i, b=b: self._menu(i, b, pos))
            b.clicked.connect(lambda _=False, i=i: self.selected.emit(i))
            lay = QHBoxLayout(b)
            lay.setContentsMargins(12, 7, 12, 7)
            lay.setSpacing(6)
            name = QLabel(f.name)
            name.setObjectName("floorTabText")
            name.setAttribute(Qt.WA_TransparentForMouseEvents)
            lay.addWidget(name)
            if unknown:
                badge = QLabel(str(unknown))
                badge.setObjectName("badge")
                badge.setAttribute(Qt.WA_TransparentForMouseEvents)
                lay.addWidget(badge)
                b.setToolTip(f"{unknown} ta belgining turi tasdiqlanmagan")
            b.name_label = name
            self.lay.addWidget(b)
            self.buttons.append(b)
        self.lay.addWidget(self.add_btn)
        self.lay.addStretch()
        self.set_current(current)

    def set_current(self, i: int):
        self.current = i
        for j, b in enumerate(self.buttons):
            b.setChecked(j == i)
            b.name_label.setProperty("current", j == i)
            b.name_label.style().unpolish(b.name_label)
            b.name_label.style().polish(b.name_label)
        if 0 <= i < len(self.buttons):
            self.ensureWidgetVisible(self.buttons[i])

    def _menu(self, i, button, pos):
        if self.menu_factory:
            self.selected.emit(i)
            m: QMenu = self.menu_factory(i)
            m.exec(button.mapToGlobal(pos))


# ======================================================================== ish bosqichlari

class StepChip(LayoutButton):
    """Bosqich: holati done (yashil ✓), active (ko'k), warn (to'q sariq), todo (kulrang)."""

    def __init__(self, number: int):
        super().__init__()
        self.setObjectName("step")
        self.number = number
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 12, 0)
        lay.setSpacing(8)
        self.circle = QLabel(str(number))
        self.circle.setObjectName("stepNum")
        self.circle.setFixedSize(22, 22)
        self.circle.setAlignment(Qt.AlignCenter)
        self.text = QLabel()
        self.text.setObjectName("stepText")
        for w in (self.circle, self.text):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(self.circle)
        lay.addWidget(self.text)
        self.setFixedHeight(34)

    def set_state(self, state: str, text: str):
        self.circle.setText("✓" if state == "done" else str(self.number))
        self.text.setText(text)
        for w in (self, self.circle, self.text):
            w.setProperty("state", state)
            w.style().unpolish(w)
            w.style().polish(w)
        self.setMinimumWidth(self.layout().sizeHint().width())
        self.setAccessibleName(text)


class StepsBar(QFrame):
    clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("steps")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 8, 20, 8)
        lay.setSpacing(8)
        self.chips = []
        for i in range(1, 5):
            c = StepChip(i)
            c.clicked.connect(lambda _=False, i=i: self.clicked.emit(i))
            lay.addWidget(c)
            self.chips.append(c)
        lay.addStretch()

    def set_steps(self, states: list[tuple[str, str]]):
        for c, (state, text) in zip(self.chips, states):
            c.set_state(state, text)


# ======================================================================== plitkalar

class Tile(LayoutButton):
    """Etaj xulosasidagi son + yorliq plitkasi."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tile")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(0)
        self.value = QLabel()
        self.value.setObjectName("tileValue")
        self.label = QLabel()
        self.label.setObjectName("tileLabel")
        for w in (self.value, self.label):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            w.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            lay.addWidget(w)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def minimumSizeHint(self) -> QSize:
        return QSize(60, self.sizeHint().height())

    def set(self, value: str, label: str, state: str = ""):
        self.value.setText(value)
        self.label.setText(label)
        for w in (self, self.value, self.label):
            w.setProperty("state", state)
            w.style().unpolish(w)
            w.style().polish(w)


class EquipButton(QToolButton):
    """Chap paneldagi rangli AT jihozi tugmasi."""

    def __init__(self, code: str, action: QAction):
        super().__init__()
        t = get_type(code)
        self.setDefaultAction(action)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.setText(t.label)
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        radius = 6 if code in ("SER", "KX") else 16   # xonalar - kvadrat, jihozlar - doira
        color = QColor(t.color)
        self.setStyleSheet(
            f"QToolButton {{ border: none; border-radius: {radius}px; background: {t.color}; color: white;"
            f" font-size: 11px; font-weight: 600; }}"
            f"QToolButton:hover {{ background: {color.darker(115).name()}; }}"
            f"QToolButton:checked {{ border: 3px solid {theme.INK}; }}")


def equip_grid(actions: dict[str, QAction]) -> QWidget:
    w = QWidget()
    g = QGridLayout(w)
    g.setContentsMargins(2, 4, 2, 4)
    g.setSpacing(6)
    for i, t in enumerate(EQUIPMENT_TYPES):
        g.addWidget(EquipButton(t.code, actions[t.code]), i // 2, i % 2)
    return w


EDITOR_STYLE = f"""
QMainWindow {{ background: {theme.BG}; }}
QMenuBar {{ background: {theme.SURFACE}; border-bottom: 1px solid {theme.LINE}; }}
QMenuBar::item {{ padding: 4px 10px; }}
QMenuBar::item:selected {{ background: {theme.PRIMARY_SOFT}; color: {theme.PRIMARY_DARK}; border-radius: 4px; }}
QStatusBar {{ background: {theme.SURFACE}; border-top: 1px solid {theme.LINE}; color: {theme.INK_2}; }}
QFrame#topbar, QFrame#steps {{ background: {theme.SURFACE}; border-bottom: 1px solid {theme.LINE}; }}
QLabel#logo, QPushButton#logo {{ background: {theme.PRIMARY}; color: white; border: none; border-radius: 8px;
    font-weight: 700; font-size: 13px; min-height: 0; padding: 0; }}
QPushButton#logo:hover {{ background: {theme.PRIMARY_DARK}; }}
QLabel#projectName {{ font-weight: 600; font-size: 15px; }}
QLabel#projectState, QLabel#muted, QLabel#fieldLabel {{ color: {theme.INK_3}; font-size: 12px; }}
QLabel#fieldLabel {{ font-size: 13px; color: {theme.INK_2}; }}
QScrollArea#floorTabs, QWidget#floorTabsInner {{ background: transparent; }}
QPushButton#floorTab {{ border: none; border-radius: 8px; padding: 0; min-height: 0; background: transparent; }}
QPushButton#floorTab:hover {{ background: #EEF1F4; }}
QPushButton#floorTab:checked {{ background: {theme.PRIMARY_SOFT}; }}
QLabel#floorTabText {{ color: {theme.INK_2}; font-weight: 500; }}
QLabel#floorTabText[current="true"] {{ color: {theme.PRIMARY_DARK}; font-weight: 600; }}
QLabel#badge {{
    background: {theme.WARN_BG}; color: {theme.WARN_FG}; border-radius: 9px; padding: 0 6px;
    font-size: 12px; font-weight: 600; min-height: 18px;
}}
QPushButton#addFloor {{
    border: 1px dashed #A9C0DE; border-radius: 8px; padding: 0 12px; min-height: 32px; background: transparent;
    color: {theme.PRIMARY}; font-weight: 600;
}}
QPushButton#iconBtn {{ min-width: 40px; max-width: 40px; min-height: 40px; padding: 0; }}
QPushButton#primary {{ min-height: 40px; }}
QPushButton#step {{ border: none; border-radius: 17px; padding: 0; min-height: 0; }}
QPushButton#step[state="done"] {{ background: {theme.OK_BG}; }}
QPushButton#step[state="active"] {{ background: {theme.PRIMARY_SOFT}; }}
QPushButton#step[state="warn"] {{ background: {theme.WARN_BG}; }}
QPushButton#step[state="todo"] {{ background: #EEF1F4; }}
QLabel#stepNum {{ border-radius: 11px; color: white; font-size: 12px; font-weight: 600; }}
QLabel#stepNum[state="done"] {{ background: {theme.OK_FG}; }}
QLabel#stepNum[state="active"] {{ background: {theme.PRIMARY}; }}
QLabel#stepNum[state="warn"] {{ background: #B34E00; }}
QLabel#stepNum[state="todo"] {{ background: #8A94A3; }}
QLabel#stepText {{ font-weight: 500; }}
QLabel#stepText[state="done"] {{ color: {theme.OK_FG}; }}
QLabel#stepText[state="active"] {{ color: {theme.PRIMARY_DARK}; font-weight: 600; }}
QLabel#stepText[state="warn"] {{ color: {theme.WARN_FG}; }}
QLabel#stepText[state="todo"] {{ color: {theme.INK_2}; }}
QFrame#toolPanel, QWidget#rightPanel {{ background: {theme.SURFACE}; }}
QFrame#toolPanel {{ border-right: 1px solid {theme.LINE}; }}
QScrollArea#rightScroll {{ border: none; border-left: 1px solid {theme.LINE}; background: {theme.SURFACE}; }}
QToolButton#tool {{
    border: none; border-radius: 10px; min-height: 56px; max-height: 56px; background: transparent;
    color: {theme.INK_2}; font-size: 11px; font-weight: 500;
}}
QToolButton#tool:hover {{ background: #EEF1F4; }}
QToolButton#tool:checked {{ background: {theme.PRIMARY_SOFT}; color: {theme.PRIMARY_DARK}; }}
QLabel#toolGroup {{ font-size: 11px; font-weight: 600; color: {theme.INK_3}; }}
QToolButton#floatBtn {{ border: none; border-radius: 6px; min-width: 20px; min-height: 20px; padding: 0;
    color: {theme.INK_3}; background: transparent; }}
QToolButton#floatBtn:hover {{ background: {theme.PRIMARY_SOFT}; color: {theme.PRIMARY_DARK}; }}
QCheckBox#planMode {{ font-size: 11px; color: {theme.INK_2}; }}
QLabel#floorTitle {{ font-weight: 600; font-size: 16px; }}
QFrame#zoomBox {{ border: 1px solid {theme.LINE}; border-radius: 8px; background: {theme.SURFACE}; }}
QToolButton#zoomBtn {{ border: none; min-width: 34px; min-height: 34px; background: transparent; }}
QToolButton#zoomBtn:hover {{ background: #EEF1F4; }}
QLabel#zoomLabel {{ font-family: 'IBM Plex Mono', monospace; font-size: 12px; color: {theme.INK_2}; }}
QFrame#canvasCard {{ background: {theme.SURFACE}; border: 1px solid {theme.LINE}; border-radius: 12px; }}
QLabel#hint {{ color: {theme.INK_2}; font-size: 13px; }}
QLabel#section {{ font-size: 13px; font-weight: 600; color: {theme.INK_3}; letter-spacing: 0.5px; }}
QFrame#hline {{ background: {theme.LINE}; }}
QFrame#roomEq {{ background: {theme.BG}; border-radius: 8px; }}
QPushButton#tile {{ border: none; border-radius: 8px; background: {theme.BG}; text-align: left; padding: 0;
    min-height: 0; }}
QPushButton#tile[state="warn"] {{ background: {theme.WARN_BG}; }}
QLabel#tileValue {{ font-size: 20px; font-weight: 700; }}
QLabel#tileLabel {{ font-size: 12px; color: {theme.INK_2}; }}
QLabel#tileValue[state="warn"], QLabel#tileLabel[state="warn"] {{ color: {theme.WARN_FG}; }}
QPushButton#small {{ min-height: 34px; padding: 0 12px; font-weight: 500; }}
QPushButton#smallDanger {{ min-height: 34px; padding: 0 12px; font-weight: 500; color: {theme.DANGER_FG};
    border-color: {theme.DANGER_LINE}; }}
"""
