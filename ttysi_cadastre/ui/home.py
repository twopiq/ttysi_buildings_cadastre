"""Bosh sahifa: binolar papkasi, har bir bino va uning etajlari, yangi bino va ish tartibi.

Tuzilma:  Binolar papkasi / 1-bino.ttysi  (ichida 1-qavat, 2-qavat, ...)
                        / 2-bino.ttysi  (ichida 1-qavat, 2-qavat, ...)
Har bir bino - bitta .ttysi fayl, etajlar va kadastr rasmlari shu faylning ichida (bitta faylni
nusxalash yoki yuborish kifoya). Bosh sahifa papkadagi barcha binolarni o'zi ko'rsatadi; boshqa
joydan ochilgan loyihalar ham "oxirgilar" ro'yxatida qoladi.
"""

from __future__ import annotations

import json
import os
import time

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu, QProgressBar, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from .. import __version__
from ..equipment import EQUIPMENT_TYPES, get_type
from . import theme
from .widgets import LayoutButton, chip, svg_icon

RECENT_KEY = "recent/projects"
WORKSPACE_KEY = "workspace/folder"
RECENT_LIMIT = 12
DROP_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")


def summary(building, path: str) -> dict:
    floors = building.floors
    counts: dict[str, int] = {}
    planned = 0
    unknown = 0
    for f in floors:
        for e in f.equipment:
            if e.code == "?":
                unknown += 1
            elif e.planned:
                planned += 1
            else:
                counts[e.code] = counts.get(e.code, 0) + 1
    ready = sum(1 for f in floors if f.rooms and not any(e.code == "?" for e in f.equipment))
    floor_list = [[f.name, sum(1 for e in f.equipment if e.code == "?")] for f in floors]
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        mtime = time.time()
    return {"path": os.path.abspath(path), "name": building.name or os.path.basename(path),
            "address": building.address, "floors": len(floors), "ready": ready, "unknown": unknown,
            "planned": planned, "counts": counts, "time": mtime, "floor_list": floor_list}


def default_workspace() -> str:
    docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or os.path.expanduser("~")
    return os.path.join(docs, "TTYSI Binolar")


def workspace(settings: QSettings) -> str:
    """Binolar papkasi (yangi binolar shu yerda saqlanadi)."""
    return settings.value(WORKSPACE_KEY, "") or default_workspace()


def safe_file_name(name: str) -> str:
    return "".join(c for c in name if c not in '\\/:*?"<>|').strip().rstrip(".") or "Bino"


def new_building_path(settings: QSettings, name: str) -> str:
    """Papkada shu nomli bino uchun bo'sh fayl nomi ("1-bino.ttysi", band bo'lsa "1-bino (2).ttysi")."""
    folder = workspace(settings)
    os.makedirs(folder, exist_ok=True)
    base = safe_file_name(name)
    path = os.path.join(folder, base + ".ttysi")
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base} ({n}).ttysi")
        n += 1
    return path


_cache: dict[str, tuple[float, dict]] = {}


def scan(folder: str) -> list[dict]:
    """Papkadagi barcha binolar (rasmlarsiz tez o'qiladi, o'zgarmagan fayllar keshdan)."""
    from ..model import Building
    out = []
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for name in names:
        if not name.lower().endswith(".ttysi"):
            continue
        path = os.path.abspath(os.path.join(folder, name))
        try:
            mtime = os.path.getmtime(path)
            hit = _cache.get(path)
            if hit is None or hit[0] != mtime:
                _cache[path] = (mtime, summary(Building.load(path, images=False), path))
            out.append(_cache[path][1])
        except Exception:
            continue    # buzilgan yoki boshqa fayl - ro'yxatda ko'rsatilmaydi
    return sorted(out, key=lambda i: natural_key(i["name"]))


def natural_key(text: str):
    """"2-bino" "10-bino" dan oldin keladi."""
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def recent(settings: QSettings) -> list[dict]:
    try:
        items = json.loads(settings.value(RECENT_KEY, "[]") or "[]")
    except (ValueError, TypeError):
        return []
    return [i for i in items if isinstance(i, dict) and i.get("path")]


def remember(settings: QSettings, building, path: str) -> None:
    item = summary(building, path)
    items = [i for i in recent(settings) if os.path.normcase(i["path"]) != os.path.normcase(item["path"])]
    settings.setValue(RECENT_KEY, json.dumps([item] + items[:RECENT_LIMIT - 1], ensure_ascii=False))


def forget(settings: QSettings, path: str) -> None:
    items = [i for i in recent(settings) if os.path.normcase(i["path"]) != os.path.normcase(path)]
    settings.setValue(RECENT_KEY, json.dumps(items, ensure_ascii=False))


def when(ts: float) -> str:
    days = int(time.time() // 86400 - ts // 86400) if ts else 999
    if days <= 0:
        return "bugun tahrirlandi"
    if days == 1:
        return "kecha tahrirlandi"
    return time.strftime("%d.%m.%Y", time.localtime(ts))


STYLE = f"""
QWidget#home {{ background: {theme.BG}; }}
QFrame#homeTop {{ background: {theme.SURFACE}; border-bottom: 1px solid {theme.LINE}; }}
QLabel#appTitle {{ font-weight: 600; font-size: 16px; }}
QLabel#h1 {{ font-size: 28px; font-weight: 700; }}
QLabel#lead {{ color: {theme.INK_2}; font-size: 14px; }}
QPushButton#card {{
    background: {theme.SURFACE}; border: 1px solid {theme.LINE}; border-radius: 12px; text-align: left; padding: 0;
}}
QPushButton#card:hover {{ border: 2px solid {theme.PRIMARY}; }}
QPushButton#card:disabled {{ background: #F7F8FA; }}
QLabel#cardTitle {{ font-weight: 600; font-size: 16px; }}
QPushButton#floorChip {{
    min-height: 26px; padding: 0 10px; border: 1px solid {theme.LINE_STRONG}; border-radius: 13px;
    background: {theme.SURFACE}; font-size: 12px; font-weight: 500; color: {theme.INK_2};
}}
QPushButton#floorChip:hover {{ border-color: {theme.PRIMARY}; color: {theme.PRIMARY_DARK}; background: {theme.PRIMARY_SOFT}; }}
QPushButton#floorChip[warn="true"] {{ color: {theme.WARN_FG}; border-color: #E9C79F; }}
QFrame#folderBar {{ background: {theme.SURFACE}; border: 1px solid {theme.LINE}; border-radius: 10px; }}
QLabel#sectionTitle {{ font-size: 16px; font-weight: 600; }}
QPushButton#link {{ border: none; background: transparent; color: {theme.PRIMARY}; font-weight: 600;
    min-height: 28px; padding: 0 6px; }}
QPushButton#newCard {{
    border: 2px dashed #A9C0DE; border-radius: 12px; background: transparent; color: {theme.PRIMARY};
    font-weight: 600; min-height: 180px;
}}
QPushButton#newCard:hover {{ background: {theme.PRIMARY_SOFT}; }}
QFrame#stepsCard {{ background: {theme.SURFACE}; border: 1px solid {theme.LINE}; border-radius: 12px; }}
QLabel#stepNo {{
    background: {theme.PRIMARY_SOFT}; color: {theme.PRIMARY_DARK}; font-weight: 700; border-radius: 14px;
}}
"""


class ProjectCard(LayoutButton):
    remove_requested = Signal(str)
    floor_clicked = Signal(str, int)

    def __init__(self, item: dict):
        super().__init__()
        self.setObjectName("card")
        self.path = item["path"]
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(self.path)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        exists = os.path.exists(self.path)
        self.setEnabled(exists)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(14)

        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(item.get("name") or os.path.basename(self.path))
        title.setObjectName("cardTitle")
        floors = item.get("floors", 0)
        sub = QLabel(f"{floors} etaj · {when(item.get('time', 0))}" if exists else "Fayl topilmadi")
        sub.setObjectName("muted")
        col.addWidget(title)
        col.addWidget(sub)
        head.addLayout(col, 1)
        unknown = item.get("unknown", 0)
        ready = item.get("ready", 0)
        if unknown:
            badge = chip(f"{unknown} ta belgi kutmoqda", theme.WARN_BG, theme.WARN_FG)
        elif floors and ready == floors:
            badge = chip("Tayyor", theme.OK_BG, theme.OK_FG)
        else:
            badge = None
        if badge is not None:
            head.addWidget(badge, 0, Qt.AlignTop)
        lay.addLayout(head)

        prog = QVBoxLayout()
        prog.setSpacing(6)
        pr = QHBoxLayout()
        a = QLabel("Tayyor etajlar")
        a.setObjectName("muted")
        b = QLabel(f"{ready} / {floors}")
        b.setObjectName("muted")
        pr.addWidget(a)
        pr.addStretch()
        pr.addWidget(b)
        prog.addLayout(pr)
        bar = QProgressBar()
        bar.setTextVisible(False)
        bar.setMaximum(max(1, floors))
        bar.setValue(ready)
        if floors and ready == floors:
            bar.setStyleSheet(f"QProgressBar::chunk {{ background: {theme.OK_FG}; border-radius: 4px; }}")
        prog.addWidget(bar)
        lay.addLayout(prog)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        counts = item.get("counts", {})
        for t in EQUIPMENT_TYPES:
            if counts.get(t.code):
                chips.addWidget(chip(f"{t.label} {counts[t.code]}", get_type(t.code).color))
        if item.get("planned"):
            chips.addWidget(chip(f"+{item['planned']} kerak", theme.SURFACE, theme.WARN_FG, dashed=True))
        if not counts and not item.get("planned"):
            e = QLabel("AT jihozlari hali belgilanmagan")
            e.setObjectName("muted")
            chips.addWidget(e)
        chips.addStretch()
        lay.addLayout(chips)
        for w in self.findChildren(QWidget):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)

        # etajlar: bosilsa - bino shu etajda ochiladi
        floor_list = item.get("floor_list") or []
        if floor_list and exists:
            fl = QGridLayout()
            fl.setHorizontalSpacing(6)
            fl.setVerticalSpacing(6)
            cap = QLabel("Etajlar:")
            cap.setObjectName("muted")
            cap.setAttribute(Qt.WA_TransparentForMouseEvents)
            fl.addWidget(cap, 0, 0)
            cols = 4
            for i, (name, unk) in enumerate(floor_list):
                b = QPushButton(name + (f"  ⚠{unk}" if unk else ""))
                b.setObjectName("floorChip")
                b.setProperty("warn", bool(unk))
                b.setCursor(Qt.PointingHandCursor)
                b.setToolTip(f"{name} — ochish" + (f" ({unk} ta belgi tasdiqlanmagan)" if unk else ""))
                b.clicked.connect(lambda _=False, i=i: self.floor_clicked.emit(self.path, i))
                fl.addWidget(b, i // cols, 1 + i % cols)
            fl.setColumnStretch(cols + 1, 1)
            lay.addLayout(fl)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _menu(self, pos):
        m = QMenu(self)
        m.addAction("Ro'yxatdan olib tashlash", lambda: self.remove_requested.emit(self.path))
        m.exec(self.mapToGlobal(pos))


class HomePage(QWidget):
    open_path = Signal(str)
    open_floor = Signal(str, int)
    open_dialog = Signal()
    new_building = Signal()
    new_from_file = Signal(str)

    def __init__(self, settings: QSettings, settings_menu: QMenu | None = None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setObjectName("home")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(STYLE)
        self.setAcceptDrops(True)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top = QFrame()
        top.setObjectName("homeTop")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(24, 12, 24, 12)
        tl.setSpacing(12)
        logo = QLabel("AT")
        logo.setObjectName("logo")
        logo.setFixedSize(32, 32)
        logo.setAlignment(Qt.AlignCenter)
        tl.addWidget(logo)
        t = QLabel("TTYSI Binolar kadastri")
        t.setObjectName("appTitle")
        tl.addWidget(t)
        tl.addStretch()
        v = QLabel(f"Versiya {__version__}")
        v.setObjectName("muted")
        tl.addWidget(v)
        if settings_menu is not None:
            sb = QPushButton()
            sb.setObjectName("iconBtn")
            sb.setIcon(svg_icon("settings", theme.INK_2, size=18))
            sb.setToolTip("Sozlamalar")
            sb.setAccessibleName("Sozlamalar")
            sb.setMenu(settings_menu)
            tl.addWidget(sb)
        root.addWidget(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setObjectName("home")
        outer = QHBoxLayout(body)
        outer.setContentsMargins(24, 32, 24, 32)
        content = QWidget()
        content.setMaximumWidth(1200)
        outer.addWidget(content)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(28)

        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(6)
        h1 = QLabel("Binolar")
        h1.setObjectName("h1")
        lead = QLabel("Har bir bino — bitta loyiha. Kadastr PDF yoki rasmini yuklang, dastur etaj chizmasini "
                      "taxminiy chizib beradi, siz tekshirib, AT jihozlarini belgilaysiz.")
        lead.setObjectName("lead")
        lead.setWordWrap(True)
        lead.setMinimumWidth(560)
        lead.setMaximumWidth(640)
        col.addWidget(h1)
        col.addWidget(lead)
        head.addLayout(col)
        head.addStretch(1)
        ob = QPushButton("Loyihani ochish")
        ob.setMinimumHeight(44)
        ob.clicked.connect(self.open_dialog)
        nb = QPushButton("  Yangi bino")
        nb.setObjectName("primary")
        nb.setMinimumHeight(44)
        nb.setIcon(svg_icon("plus", "#FFFFFF", size=16))
        nb.clicked.connect(self.new_building)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        for b in (ob, nb):
            b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            btns.addWidget(b)
        head.addLayout(btns)
        head.setAlignment(btns, Qt.AlignBottom)
        lay.addLayout(head)

        bar = QFrame()
        bar.setObjectName("folderBar")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 8, 8, 8)
        bl.setSpacing(8)
        icon = QLabel()
        icon.setPixmap(svg_icon("folder", theme.INK_2, size=18).pixmap(18, 18))
        bl.addWidget(icon)
        self.folder_label = QLabel()
        self.folder_label.setObjectName("muted")
        self.folder_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bl.addWidget(self.folder_label, 1)
        for text, slot in (("Papkani ochish", self.open_folder), ("O'zgartirish...", self.change_folder)):
            b = QPushButton(text)
            b.setObjectName("link")
            b.clicked.connect(slot)
            bl.addWidget(b)
        lay.addWidget(bar)

        self.grid = QGridLayout()
        self.grid.setSpacing(16)
        lay.addLayout(self.grid)
        self.other_title = QLabel("Boshqa joydagi loyihalar")
        self.other_title.setObjectName("sectionTitle")
        lay.addWidget(self.other_title)
        self.grid2 = QGridLayout()
        self.grid2.setSpacing(16)
        lay.addLayout(self.grid2)

        steps = QFrame()
        steps.setObjectName("stepsCard")
        sl = QVBoxLayout(steps)
        sl.setContentsMargins(20, 20, 20, 20)
        sl.setSpacing(14)
        st = QLabel("4 qadamda tayyor etaj")
        st.setStyleSheet("font-size: 16px; font-weight: 600")
        sl.addWidget(st)
        row = QHBoxLayout()
        row.setSpacing(12)
        for i, (name, desc) in enumerate([
                ("Yuklash", "PDF sahifasidan etajni ramkaga oling, nisbatni kiriting."),
                ("Xonalarni tekshirish", "Taxminiy chizmani tuzating: birlashtirish, bo'lish, eshik va zina."),
                ("Belgilarni tasdiqlash", "Qo'lyozma belgilarga bitta tugma bilan tur bering."),
                ("Eksport", "PDF, rasm, AutoCAD yoki Excel hisobot.")], 1):
            cell = QHBoxLayout()
            cell.setSpacing(10)
            n = QLabel(str(i))
            n.setObjectName("stepNo")
            n.setFixedSize(28, 28)
            n.setAlignment(Qt.AlignCenter)
            cell.addWidget(n, 0, Qt.AlignTop)
            tc = QVBoxLayout()
            tc.setSpacing(2)
            a = QLabel(name)
            a.setStyleSheet("font-weight: 600")
            b = QLabel(desc)
            b.setObjectName("muted")
            b.setWordWrap(True)
            tc.addWidget(a)
            tc.addWidget(b)
            cell.addLayout(tc, 1)
            row.addLayout(cell, 1)
        sl.addLayout(row)
        lay.addWidget(steps)
        lay.addStretch()
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        self.cards: list[QWidget] = []
        self.refresh()

    def _card(self, it: dict) -> ProjectCard:
        c = ProjectCard(it)
        c.clicked.connect(lambda _=False, p=it["path"]: self.open_path.emit(p))
        c.floor_clicked.connect(self.open_floor)
        c.remove_requested.connect(self._forget)
        return c

    def refresh(self):
        for w in self.cards:
            w.hide()
            w.deleteLater()
        self.cards = []
        folder = workspace(self.settings)
        self.folder_label.setText(f"Binolar papkasi: {folder}")
        own = scan(folder)
        own_paths = {os.path.normcase(i["path"]) for i in own}
        others = [i for i in recent(self.settings) if os.path.normcase(i["path"]) not in own_paths]
        main_cards = [self._card(it) for it in own]
        new = LayoutButton()
        new.setObjectName("newCard")
        nl = QVBoxLayout(new)
        nl.setContentsMargins(18, 18, 18, 18)
        nl.setSpacing(8)
        nl.addStretch()
        for w in (QLabel(), QLabel("Yangi bino qo'shish"), QLabel("PDF yoki rasmni shu yerga tashlang")):
            w.setAlignment(Qt.AlignCenter)
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
            nl.addWidget(w)
        icon, title, hint = (nl.itemAt(i).widget() for i in (1, 2, 3))
        icon.setPixmap(svg_icon("plus", theme.PRIMARY, size=28).pixmap(28, 28))
        title.setStyleSheet(f"color: {theme.PRIMARY}; font-weight: 600")
        hint.setObjectName("muted")
        nl.addStretch()
        new.setCursor(Qt.PointingHandCursor)
        new.clicked.connect(self.new_building)
        new.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        new.setFixedHeight(max([c.sizeHint().height() for c in main_cards] + [180]))
        main_cards.append(new)
        other_cards = [self._card(it) for it in others]
        cols = 3
        for grid, cards in ((self.grid, main_cards), (self.grid2, other_cards)):
            for i, c in enumerate(cards):
                grid.addWidget(c, i // cols, i % cols, Qt.AlignTop)
            for c in range(cols):
                grid.setColumnStretch(c, 1)
        self.other_title.setVisible(bool(other_cards))
        self.cards = main_cards + other_cards
        self.buildings = own

    def open_folder(self):
        folder = workspace(self.settings)
        os.makedirs(folder, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def change_folder(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, "Binolar papkasi", workspace(self.settings))
        if d:
            self.settings.setValue(WORKSPACE_KEY, d)
            self.refresh()

    def _forget(self, path: str):
        forget(self.settings, path)
        self.refresh()

    # --- fayl tashlash
    def _dropped(self, event) -> str | None:
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        for u in urls:
            p = u.toLocalFile()
            if p.lower().endswith(DROP_EXT + (".ttysi",)):
                return p
        return None

    def dragEnterEvent(self, event):
        if self._dropped(event):
            event.acceptProposedAction()

    def dropEvent(self, event):
        p = self._dropped(event)
        if not p:
            return
        event.acceptProposedAction()
        if p.lower().endswith(".ttysi"):
            self.open_path.emit(p)
        else:
            self.new_from_file.emit(p)
