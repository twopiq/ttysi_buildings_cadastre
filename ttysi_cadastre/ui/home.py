"""Bosh sahifa: binolar papkasi, har bir bino va uning etajlari, yangi bino va ish tartibi.

Tuzilma:  Binolar papkasi / 1-bino.ttysi  (ichida 1-qavat, 2-qavat, ...)
                        / 2-bino.ttysi  (ichida 1-qavat, 2-qavat, ...)
                        / Tashkilot nomi / 3-bino.ttysi, 4-bino.ttysi ...
Tashkilot - binolar papkasi ichidagi papka (bir nechta binoni birlashtiradi, umumiy hisobot beradi).
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
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QProgressBar,
                               QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from .. import __version__
from ..workspace import (ORG_MARK, create_org, drop_cache, free_path, is_org, move_file,
                         orgs, safe_file_name, scan, summary)
from ..equipment import EQUIPMENT_TYPES, get_type
from . import theme
from .widgets import LayoutButton, chip, svg_icon

RECENT_KEY = "recent/projects"
WORKSPACE_KEY = "workspace/folder"
RECENT_LIMIT = 12
DROP_EXT = (".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff")


def default_workspace() -> str:
    docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or os.path.expanduser("~")
    return os.path.join(docs, "TTYSI Binolar")


def workspace(settings: QSettings) -> str:
    """Binolar papkasi (yangi binolar shu yerda saqlanadi)."""
    return settings.value(WORKSPACE_KEY, "") or default_workspace()


def new_building_path(settings: QSettings, name: str, org: str | None = None) -> str:
    """Binolar papkasida (yoki tashkilot papkasida) shu nomli bino uchun bo'sh fayl nomi."""
    folder = org or workspace(settings)
    os.makedirs(folder, exist_ok=True)
    return free_path(folder, safe_file_name(name))


# ------------------------------------------------------------------ tashkilotlar
def org_of(settings: QSettings, path: str | None) -> str | None:
    """Bino fayli tashkilot papkasida bo'lsa - shu papka, aks holda None."""
    if not path:
        return None
    d = os.path.dirname(os.path.abspath(path))
    ws = os.path.abspath(workspace(settings))
    if os.path.normcase(os.path.dirname(d)) == os.path.normcase(ws) and is_org(d):
        return d
    return None


def new_org(settings: QSettings, name: str) -> str:
    """Yangi tashkilot papkasi (nomi band bo'lsa raqam qo'shiladi)."""
    return create_org(workspace(settings), name)


def _repath_recent(settings: QSettings, old: str, new: str | None) -> None:
    items = []
    for i in recent(settings):
        p = i["path"]
        if os.path.normcase(p) == os.path.normcase(old) or os.path.normcase(p).startswith(os.path.normcase(old) + os.sep):
            if new is None:
                continue
            i["path"] = os.path.abspath(new + p[len(old):])
        items.append(i)
    settings.setValue(RECENT_KEY, json.dumps(items, ensure_ascii=False))


def move_building(settings: QSettings, path: str, org: str | None) -> str:
    """Bino faylini tashkilotga (org=None - tashkilotsiz, binolar papkasiga) ko'chirish. Natija - yangi yo'l."""
    old = os.path.abspath(path)
    new = move_file(old, org or workspace(settings))
    if new != old:
        _repath_recent(settings, old, new)
    return new


def rename_org(settings: QSettings, org: str, name: str) -> str:
    org = os.path.abspath(org)
    new = os.path.abspath(free_path(os.path.dirname(org), safe_file_name(name) or "Tashkilot", ""))
    os.rename(org, new)
    drop_cache(org)
    _repath_recent(settings, org, new)
    return new


def dissolve_org(settings: QSettings, org: str) -> list[str]:
    """Tashkilotni tarqatish: binolar tashkilotsiz bo'lib qoladi (o'chirilmaydi), papka o'chiriladi."""
    moved = [move_building(settings, b["path"], None) for b in scan(org)]
    mark = os.path.join(org, ORG_MARK)
    if os.path.exists(mark):
        os.remove(mark)
    try:
        os.rmdir(org)                 # boshqa fayllar bo'lsa papka qoladi
    except OSError:
        pass
    return moved


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
QFrame#orgHead {{ background: {theme.PRIMARY_SOFT}; border: 1px solid #C9D8EE; border-radius: 10px; }}
QLabel#orgTitle {{ font-size: 17px; font-weight: 700; color: {theme.PRIMARY_DARK}; }}
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

    menu_builder = None          # HomePage beradi: (menu, path) -> menyuga amallar qo'shadi

    def _menu(self, pos):
        m = QMenu(self)
        if self.menu_builder is not None:
            self.menu_builder(m, self.path)
        else:
            m.addAction("Ro'yxatdan olib tashlash", lambda: self.remove_requested.emit(self.path))
        m.exec(self.mapToGlobal(pos))


class OrgDialog(QDialog):
    """Yangi tashkilot (yoki mavjudiga binolar qo'shish): nomi va birlashtiriladigan binolar."""

    def __init__(self, buildings: list[dict], name: str = "", parent=None, title="Yangi tashkilot",
                 checked: set[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        self.name = QLineEdit(name)
        self.name.setPlaceholderText("masalan: Toshkent shahar 5-maktab")
        self.name.selectAll()
        from .widgets import field
        lay.addWidget(field("Tashkilot nomi", self.name))
        cap = QLabel("Birlashtiriladigan binolar" if buildings else
                     "Binolar papkasida boshqa bino yo'q - tashkilot bo'sh yaratiladi.")
        cap.setObjectName("muted")
        lay.addWidget(cap)
        self.list = QListWidget()
        self.list.setMinimumHeight(min(320, 40 + 30 * len(buildings)))
        for b in buildings:
            where = f"   ({b['org']})" if b.get("org") else ""
            it = QListWidgetItem(f"{b['name']} · {b['floors']} etaj{where}")
            it.setData(Qt.UserRole, b["path"])
            it.setCheckState(Qt.Checked if checked and b["path"] in checked else Qt.Unchecked)
            self.list.addItem(it)
        self.list.setVisible(bool(buildings))
        lay.addWidget(self.list, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Saqlash")
        bb.button(QDialogButtonBox.Ok).setObjectName("primary")
        bb.button(QDialogButtonBox.Cancel).setText("Bekor qilish")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.resize(480, self.sizeHint().height())

    def chosen(self) -> list[str]:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]


class HomePage(QWidget):
    open_path = Signal(str)
    open_floor = Signal(str, int)
    open_dialog = Signal()
    new_building = Signal()
    new_from_file = Signal(str)
    new_building_in = Signal(str)        # tashkilot papkasi
    org_report = Signal(str)             # tashkilot bo'yicha Excel hisobot
    org_export = Signal(str)             # tashkilotni to'liq eksport
    moved = Signal(str, str)             # bino fayli ko'chirildi: eski, yangi yo'l

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
        org_b = QPushButton("  Yangi tashkilot")
        org_b.setMinimumHeight(44)
        org_b.setIcon(svg_icon("org", theme.INK_2, size=16))
        org_b.setToolTip("Bir nechta binoni bitta tashkilotga birlashtirish")
        org_b.clicked.connect(lambda: self.create_org())
        nb = QPushButton("  Yangi bino")
        nb.setObjectName("primary")
        nb.setMinimumHeight(44)
        nb.setIcon(svg_icon("plus", "#FFFFFF", size=16))
        nb.clicked.connect(self.new_building)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        for b in (ob, org_b, nb):
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

        self.sections = QVBoxLayout()           # tashkilotlar, tashkilotsiz binolar, boshqa joydagilar
        self.sections.setSpacing(28)
        lay.addLayout(self.sections)
        self.sections_w: QWidget | None = None
        self.other_title = QLabel()

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
        c.menu_builder = self._card_menu
        return c

    def refresh(self):
        if self.sections_w is not None:
            self.sections_w.hide()
            self.sections_w.deleteLater()
        self.sections_w = QWidget()
        sl = QVBoxLayout(self.sections_w)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(28)
        self.sections.addWidget(self.sections_w)
        folder = workspace(self.settings)
        self.folder_label.setText(f"Binolar papkasi: {folder}")
        self.orgs = orgs(folder)
        own = scan(folder)
        in_orgs = [b for o in self.orgs for b in o["buildings"]]
        own_paths = {os.path.normcase(i["path"]) for i in own + in_orgs}
        others = [i for i in recent(self.settings) if os.path.normcase(i["path"]) not in own_paths]
        cols = 3
        self.cards = []

        def grid(cards):
            g = QGridLayout()
            g.setSpacing(16)
            for i, c in enumerate(cards):
                g.addWidget(c, i // cols, i % cols, Qt.AlignTop)
            for c in range(cols):
                g.setColumnStretch(c, 1)
            sl.addLayout(g)

        # --- tashkilotlar
        for o in self.orgs:
            sl.addWidget(self._org_head(o))
            cards = [self._card(it) for it in o["buildings"]]
            if cards:
                grid(cards)
            else:
                e = QLabel("Bo'sh. Binoni kartochkasi menyusidan (o'ng tugma) shu tashkilotga ko'chiring "
                           "yoki \"+ Bino\" bilan yangisini qo'shing.")
                e.setObjectName("muted")
                e.setWordWrap(True)
                sl.addWidget(e)
            self.cards += cards

        # --- tashkilotsiz binolar
        if self.orgs:
            t = QLabel("Tashkilotsiz binolar")
            t.setObjectName("sectionTitle")
            sl.addWidget(t)
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
        new.setFixedHeight(max([c.sizeHint().height() for c in main_cards + self.cards] + [180]))
        main_cards.append(new)
        grid(main_cards)

        # --- boshqa joydagi loyihalar
        self.other_title = QLabel("Boshqa joydagi loyihalar")
        self.other_title.setObjectName("sectionTitle")
        sl.addWidget(self.other_title)
        other_cards = [self._card(it) for it in others]
        grid(other_cards)
        self.other_title.setVisible(bool(other_cards))
        self.cards = self.cards + main_cards + other_cards
        self.buildings = own

    def _org_head(self, o: dict) -> QFrame:
        box = QFrame()
        box.setObjectName("orgHead")
        h = QHBoxLayout(box)
        h.setContentsMargins(14, 10, 8, 10)
        h.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(svg_icon("org", theme.PRIMARY, size=22).pixmap(22, 22))
        h.addWidget(icon)
        col = QVBoxLayout()
        col.setSpacing(0)
        t = QLabel(o["name"])
        t.setObjectName("orgTitle")
        bs = o["buildings"]
        floors = sum(b["floors"] for b in bs)
        unknown = sum(b["unknown"] for b in bs)
        counts: dict[str, int] = {}
        for b in bs:
            for k, v in b["counts"].items():
                counts[k] = counts.get(k, 0) + v
        info = f"Tashkilot · {len(bs)} ta bino · {floors} etaj"
        if counts:
            info += " · " + ", ".join(f"{t.label} {counts[t.code]}" for t in EQUIPMENT_TYPES if counts.get(t.code))
        sub = QLabel(info)
        sub.setObjectName("muted")
        col.addWidget(t)
        col.addWidget(sub)
        h.addLayout(col, 1)
        if unknown:
            h.addWidget(chip(f"{unknown} ta belgi kutmoqda", theme.WARN_BG, theme.WARN_FG))
        for text, slot in (("+ Bino", lambda _=False, p=o["path"]: self.new_building_in.emit(p)),
                           ("Excel hisobot", lambda _=False, p=o["path"]: self.org_report.emit(p)),
                           ("To'liq eksport", lambda _=False, p=o["path"]: self.org_export.emit(p))):
            b = QPushButton(text)
            b.setObjectName("link")
            b.clicked.connect(slot)
            b.setEnabled(text == "+ Bino" or bool(bs))
            h.addWidget(b)
        more = QPushButton("⋯")
        more.setObjectName("link")
        more.setToolTip("Tashkilot amallari")
        m = QMenu(more)
        m.addAction("To'liq eksport (PDF, Excel, DXF, ZIP)...", lambda p=o["path"]: self.org_export.emit(p))
        m.addAction("Binolarni qo'shish...", lambda p=o["path"]: self.add_to_org(p))
        m.addAction("Nomini o'zgartirish...", lambda p=o["path"]: self.rename_org(p))
        m.addAction("Papkani ochish", lambda p=o["path"]: QDesktopServices.openUrl(QUrl.fromLocalFile(p)))
        m.addSeparator()
        m.addAction("Tashkilotni tarqatish (binolar saqlanadi)", lambda p=o["path"]: self.dissolve_org(p))
        more.setMenu(m)
        h.addWidget(more)
        return box

    def _card_menu(self, m: QMenu, path: str):
        ws = os.path.normcase(os.path.abspath(workspace(self.settings)))
        here = os.path.normcase(os.path.dirname(path))
        inside = here == ws or any(os.path.normcase(o["path"]) == here for o in self.orgs)
        if inside:
            sub = m.addMenu("Tashkilotga ko'chirish")
            for o in self.orgs:
                a = sub.addAction(o["name"], lambda p=o["path"]: self.move(path, p))
                a.setEnabled(os.path.normcase(o["path"]) != here)
            if self.orgs:
                sub.addSeparator()
            sub.addAction("Yangi tashkilot...", lambda: self.create_org(checked={path}))
            if here != ws:
                m.addAction("Tashkilotdan chiqarish", lambda: self.move(path, None))
        else:
            m.addAction("Ro'yxatdan olib tashlash", lambda: self._forget(path))

    def _all_buildings(self, exclude_org: str | None = None) -> list[dict]:
        out = [dict(b) for b in scan(workspace(self.settings))]
        for o in orgs(workspace(self.settings)):
            if exclude_org and os.path.normcase(o["path"]) == os.path.normcase(exclude_org):
                continue
            out += [dict(b, org=o["name"]) for b in o["buildings"]]
        return out

    def move(self, path: str, org: str | None, refresh=True) -> str | None:
        try:
            new = move_building(self.settings, path, org)
        except OSError as e:
            QMessageBox.warning(self, "Ko'chirish", f"{os.path.basename(path)}: {e}")
            return None
        if os.path.normcase(new) != os.path.normcase(os.path.abspath(path)):
            self.moved.emit(os.path.abspath(path), new)
        if refresh:
            self.refresh()
        return new

    def create_org(self, name: str | None = None, paths: list[str] | None = None,
                   checked: set[str] | None = None) -> str | None:
        """Yangi tashkilot; name/paths berilsa oyna ko'rsatilmaydi (testlar uchun)."""
        if name is None:
            dlg = OrgDialog(self._all_buildings(), f"{len(orgs(workspace(self.settings))) + 1}-tashkilot",
                            self, checked=checked)
            if dlg.exec() != QDialog.Accepted:
                return None
            name, paths = dlg.name.text().strip(), dlg.chosen()
        try:
            org = new_org(self.settings, name or "Tashkilot")
        except OSError as e:
            QMessageBox.warning(self, "Tashkilot", str(e))
            return None
        for p in paths or []:
            self.move(p, org, refresh=False)
        self.refresh()
        return org

    def add_to_org(self, org: str):
        dlg = OrgDialog(self._all_buildings(exclude_org=org), os.path.basename(org), self,
                        title="Tashkilotga binolar qo'shish")
        dlg.name.setEnabled(False)
        if dlg.exec() != QDialog.Accepted:
            return
        for p in dlg.chosen():
            self.move(p, org, refresh=False)
        self.refresh()

    def rename_org(self, org: str, name: str | None = None) -> str | None:
        if name is None:
            name, ok = QInputDialog.getText(self, "Tashkilot nomi", "Yangi nom:", text=os.path.basename(org))
            if not ok or not name.strip() or name.strip() == os.path.basename(org):
                return None
        old_files = [b["path"] for b in scan(org)]
        try:
            new = rename_org(self.settings, org, name.strip())
        except OSError as e:
            QMessageBox.warning(self, "Tashkilot", f"Nomini o'zgartirib bo'lmadi: {e}")
            return None
        for p in old_files:
            self.moved.emit(p, os.path.join(new, os.path.basename(p)))
        self.refresh()
        return new

    def dissolve_org(self, org: str, confirm=True):
        if confirm and QMessageBox.question(
                self, "Tashkilotni tarqatish",
                f"\"{os.path.basename(org)}\" tashkiloti tarqatilsinmi? Binolar o'chirilmaydi - "
                "tashkilotsiz binolar qatoriga o'tadi.") != QMessageBox.Yes:
            return
        old = [b["path"] for b in scan(org)]
        new = dissolve_org(self.settings, org)
        for a, b in zip(old, new):
            if os.path.normcase(a) != os.path.normcase(b):
                self.moved.emit(a, b)
        self.refresh()

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
