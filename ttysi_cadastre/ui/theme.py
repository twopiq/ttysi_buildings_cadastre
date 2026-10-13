"""Dizayn tizimi: ranglar, shrift (IBM Plex Sans) va umumiy uslub.

Qiymatlar dizayn maketidagi "Dizayn tizimi" artboardi bilan bir xil.
"""

from __future__ import annotations

import os

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

# --- ranglar
PRIMARY = "#1C5BA6"
PRIMARY_DARK = "#123F75"
PRIMARY_SOFT = "#E6EEF8"
INK = "#17202B"
INK_2 = "#4A5563"
INK_3 = "#5B6675"
BG = "#F4F6F8"
SURFACE = "#FFFFFF"
LINE = "#D8DEE5"
LINE_STRONG = "#C9D1DB"
OK_FG, OK_BG = "#1E6B3A", "#E7F4EC"
WARN_FG, WARN_BG = "#8A4300", "#FFF1E0"
DANGER_FG, DANGER_BG, DANGER_LINE = "#B3261E", "#FCEBEA", "#F0C9C6"
PAPER = "#F7F5EF"            # kadastr qog'ozi foni (asl rasm atrofida)

FONT_FAMILY = "IBM Plex Sans"


FONT_FILES = [f"ibm-plex-sans-{subset}-{w}-normal.woff"
              for subset in ("latin", "latin-ext") for w in (400, 500, 600, 700)]


def load_fonts() -> bool:
    """Dastur bilan kelgan shriftlarni yuklaydi (yangilanish zip'i ichidan ham ishlaydi).

    Faqat paket yuklovchisining get_data() ishlatiladi - .exe da qo'shimcha modul shart emas.
    """
    import ttysi_cadastre
    ok = False
    loader = ttysi_cadastre.__spec__.loader
    folder = os.path.join(os.path.dirname(ttysi_cadastre.__file__), "fonts")
    for name in FONT_FILES:
        try:
            data = loader.get_data(os.path.join(folder, name))
        except OSError:
            continue
        if QFontDatabase.addApplicationFontFromData(data) >= 0:
            ok = True
    return ok


def font(size_px: int = 14, weight: QFont.Weight = QFont.Normal) -> QFont:
    f = QFont(FONT_FAMILY)
    f.setPixelSize(size_px)
    f.setWeight(weight)
    return f


STYLESHEET = f"""
QWidget {{ font-family: "{FONT_FAMILY}"; color: {INK}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QPushButton {{
    min-height: 32px; padding: 0 14px; border: 1px solid {LINE_STRONG}; border-radius: 8px;
    background: {SURFACE}; font-weight: 600;
}}
QPushButton:hover {{ border-color: {PRIMARY}; }}
QPushButton:focus {{ border: 2px solid {PRIMARY}; }}
QPushButton#primary {{ background: {PRIMARY}; color: white; border: none; }}
QPushButton#primary:hover {{ background: {PRIMARY_DARK}; }}
QPushButton#danger {{ color: {DANGER_FG}; border-color: {DANGER_LINE}; }}
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QKeySequenceEdit {{
    min-height: 30px; border: 1px solid {LINE_STRONG}; border-radius: 8px; padding: 0 8px; background: {SURFACE};
}}
QComboBox::drop-down {{ border: none; width: 26px; }}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{ border: 2px solid {PRIMARY}; }}
QProgressBar {{ border: none; border-radius: 4px; background: #EEF1F4; max-height: 8px; }}
QProgressBar::chunk {{ border-radius: 4px; background: {PRIMARY}; }}
QToolTip {{ color: {INK}; background: {SURFACE}; border: 1px solid {LINE}; }}
"""


def apply(app: QApplication) -> None:
    """Butun dasturga dizayn tizimini qo'llaydi."""
    load_fonts()
    app.setFont(font(13))
    app.setStyleSheet(STYLESHEET)
