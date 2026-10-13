"""Asosiy oyna."""

from __future__ import annotations

import math
import os
from datetime import datetime

from PySide6.QtCore import QPointF, QSettings, QSize, Qt, QTimer
from PySide6.QtPdf import QPdfDocument
from PySide6.QtGui import QAction, QActionGroup, QImage, QKeySequence
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSlider,
                               QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from .. import __version__
from ..detection import DetectParams, decode_image, detect, encode_jpg, limit_size, read_image
from ..equipment import BY_KEY, EQUIPMENT_TYPES, ROOM_KINDS, UNKNOWN, get_type
from ..export import export_dxf, export_image, export_pdf, export_svg
from ..geometry import merge_rooms, split_room
from ..model import Building, Equipment, Floor, Room
from ..render import RenderOptions, equipment_counts, meter_px, wall_width
from ..report import export_excel
from ..updater import is_frozen
from .export_dialog import ExportDialog
from .home import HomePage, remember
from .canvas import (DOOR, EQUIP, ROOM_POLY, ROOM_RECT, SCALE, SELECT, SPLIT, STAIRS, WALL, EquipmentItem,
                     FloorScene, FloorView, RoomItem, WallItem)
from .import_dialog import ImportDialog, RedetectDialog, image_paper_mm_per_px
from .review_dialog import ReviewDialog
from .shortcuts import ShortcutsDialog, display, registry
from .update_dialog import Updater, UpdateSettingsDialog, load_settings
from . import theme
from .widgets import (EDITOR_STYLE, FloorTabs, StepsBar, Tile, chip, equip_grid, field, hline, kbd, section_title,
                      svg_icon, type_icon)

FILE_FILTER = "TTYSI kadastr loyihasi (*.ttysi)"
IMAGE_FILTER = "Kadastr hujjati (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff)"


class History:
    """Etaj uchun bekor qilish/qaytarish tarixi (holat nusxalari)."""

    LIMIT = 100

    def __init__(self, floor: Floor):
        self.stack = [floor.content_dict()]
        self.index = 0

    def push(self, floor: Floor):
        self.stack = self.stack[: self.index + 1]
        self.stack.append(floor.content_dict())
        if len(self.stack) > self.LIMIT:
            self.stack.pop(0)
        self.index = len(self.stack) - 1

    def undo(self):
        if self.index > 0:
            self.index -= 1
            return self.stack[self.index]

    def redo(self):
        if self.index < len(self.stack) - 1:
            self.index += 1
            return self.stack[self.index]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.building = Building()
        self.path: str | None = None
        self.dirty = False
        self.floor: Floor | None = None
        self.histories: dict[str, History] = {}
        self.bg_cache: dict[str, QImage] = {}
        self.settings = QSettings("TTYSI", "BinolarKadastr")

        self.scene = FloorScene(self)
        self.view = FloorView(self.scene)
        self.view.setFrameShape(QFrame.NoFrame)
        self.scene.changed_model.connect(self.on_model_changed)
        self.scene.selectionChanged.connect(self.on_selection)
        self.scene.request_merge.connect(self.merge_selected)
        self.view.status.connect(self.show_hint)
        self.view.zoomed.connect(lambda z: self.zoom_label.setText(f"{z * 100:.0f}%"))
        self.view.split_requested.connect(self.split_room)
        self.view.scale_requested.connect(self.set_scale)

        self.updater = Updater(self)
        self.sc_actions: dict[str, QAction] = {}
        self.saved_at = None
        self._tabs_sig = None
        self.build_actions()
        self.pages = QStackedWidget()
        self.home = HomePage(self.settings, self.build_settings_menu())
        self.home.open_path.connect(self.open_project)
        self.home.open_dialog.connect(lambda: self.open_project())
        self.home.new_building.connect(self.new_building)
        self.home.new_from_file.connect(self.new_building)
        self.pages.addWidget(self.home)
        self.editor = self.build_editor()
        self.pages.addWidget(self.editor)
        self.setCentralWidget(self.pages)
        self.setStyleSheet(EDITOR_STYLE)
        self.resize(1440, 900)
        self.refresh_all()
        self.select_tool(SELECT)
        self.pages.setCurrentWidget(self.home)
        # o'rnatilgan dasturda: ochilgandan keyin fonda yangilanishni tekshirish
        if is_frozen() and load_settings()["auto"]:
            QTimer.singleShot(4000, lambda: self.updater.check(silent=True))

    # ================================================================ UI qurish
    def build_actions(self):
        mb = self.menuBar()
        A = self._act
        m = mb.addMenu("&Fayl")
        A(m, "Bosh sahifa", self.show_home, "Ctrl+H", "file.home")
        A(m, "Yangi loyiha", self.new_project, QKeySequence.New, "file.new")
        A(m, "Ochish...", self.open_project, QKeySequence.Open, "file.open")
        A(m, "Saqlash", self.save_project, QKeySequence.Save, "file.save")
        A(m, "Boshqa nom bilan saqlash...", self.save_project_as, "Ctrl+Shift+S", "file.save_as")
        A(m, "Bino ma'lumotlari...", self.edit_building_info, None, "file.info")
        m.addSeparator()
        A(m, "Eksport...", lambda: self.export(), "Ctrl+E", "export.dialog")
        ex = m.addMenu("Eksport (to'g'ridan-to'g'ri)")
        A(ex, "Rasm (PNG / JPG)...", lambda: self.export("image"), None, "export.image")
        A(ex, "Vektor rasm (SVG)...", lambda: self.export("svg"), None, "export.svg")
        A(ex, "PDF - joriy etaj...", lambda: self.export("pdf"), None, "export.pdf")
        A(ex, "PDF - barcha etajlar...", lambda: self.export("pdf_all"), None, "export.pdf_all")
        A(ex, "AutoCAD chizma (DXF)...", lambda: self.export("dxf"), None, "export.dxf")
        ex.addSeparator()
        A(ex, "Excel hisobot - joriy bino...", self.export_excel_current, "Ctrl+R", "export.excel")
        A(ex, "Excel hisobot - bir nechta bino...", self.export_excel_many, None, "export.excel_many")
        m.addSeparator()
        A(m, "Chiqish", self.close, QKeySequence.Quit, "file.quit")

        m = mb.addMenu("&Tahrir")
        self.a_undo = A(m, "Bekor qilish", self.undo, QKeySequence.Undo, "edit.undo")
        self.a_redo = A(m, "Qaytarish", self.redo, "Ctrl+Y", "edit.redo")
        A(m, "Qaytarish (2)", self.redo, "Ctrl+Shift+Z", "edit.redo2").setVisible(False)
        m.addSeparator()
        A(m, "O'chirish", self.scene.delete_selected, QKeySequence.Delete, "edit.delete")
        A(m, "Hammasini tanlash", self.select_all, QKeySequence.SelectAll, "edit.select_all")
        A(m, "Jihoz holatini almashtirish (mavjud / kerak)", self.toggle_status, "Ctrl+K", "edit.toggle_status")
        A(m, "Tanlangan xonalarni birlashtirish", self.merge_selected, "Ctrl+M", "edit.merge")
        tm = m.addMenu("Devor qalinligi")
        A(tm, "Qalinlashtirish (+5 sm)", lambda: self.change_wall_thickness(0.05), "Alt+Up", "wall.thicker")
        A(tm, "Yupqalashtirish (-5 sm)", lambda: self.change_wall_thickness(-0.05), "Alt+Down", "wall.thinner")
        rm = m.addMenu("Aylantirish (joyida)")
        A(rm, "90° o'ngga", lambda: self.rotate_selected(90.0), "]", "rotate.cw")
        A(rm, "90° chapga", lambda: self.rotate_selected(-90.0), "[", "rotate.ccw")
        A(rm, "180°", lambda: self.rotate_selected(180.0), None, "rotate.180")
        A(rm, "Burchak kiritish...", lambda: self.rotate_selected("custom"), "Ctrl+Shift+R", "rotate.custom")
        m.addSeparator()
        A(m, "Belgilarni tasdiqlash...", self.open_review, "Ctrl+T", "review.open")
        A(m, "Keyingi tasdiqlanmagan belgi", self.select_next_unknown, "N", "review.next")
        m.addSeparator()
        A(m, "Klaviatura tugmalari...", self.edit_shortcuts, "Ctrl+,", "app.shortcuts")

        m = mb.addMenu("&Etaj")
        A(m, "PDF / rasmdan yangi etaj qo'shish...", self.add_floor_from_image, "Ctrl+I", "floor.import")
        A(m, "Bo'sh etaj qo'shish", self.add_empty_floor, None, "floor.empty")
        A(m, "Qayta avtomatik chizish...", self.redetect, None, "floor.redetect")
        A(m, "Masshtabni belgilash", lambda: self.select_tool(SCALE), None, "floor.scale")
        A(m, "Xonalarni qayta raqamlash...", self.renumber_rooms, None, "floor.renumber")
        A(m, "Etaj nomini o'zgartirish...", self.rename_floor, "F2", "floor.rename")
        A(m, "Etajni o'chirish", self.delete_floor, None, "floor.delete")

        m = mb.addMenu("&Ko'rinish")
        A(m, "Butun chizmani ko'rsatish", self.view.zoom_fit, "Ctrl+0", "view.fit")
        self.a_ortho = A(m, "Orto rejim (faqat gorizontal/vertikal)", self.toggle_ortho, "F8", "view.ortho")
        self.a_ortho.setCheckable(True)
        self.a_ortho.setChecked(True)

        m = mb.addMenu("&Yordam")
        A(m, "Qo'llanma", self.show_help, QKeySequence.HelpContents, "help.manual")
        m.addSeparator()
        A(m, "Yangilanishni tekshirish...", lambda: self.updater.check(silent=False), None, "help.update")
        A(m, "Yangilanish sozlamalari...", lambda: UpdateSettingsDialog(self).exec(), None, "help.update_settings")
        A(m, "Dastur haqida", lambda: QMessageBox.about(
            self, "Dastur haqida",
            f"TTYSI Binolar kadastri — AT jihozlari xaritasi\nVersiya {__version__}"), None, "help.about")

        self.tool_group = QActionGroup(self)
        self.tool_actions = {}
        self.tool_order: list[QAction] = []
        reg = registry()

        def tool(text, key, tool_id, code=None, tip=""):
            sid = f"tool.{tool_id}" + (f".{code}" if code else "")
            a = QAction(text, self)
            a.setCheckable(True)
            if code:
                a.setIcon(type_icon(code))
            else:
                a.setIcon(svg_icon(tool_id, theme.INK_2, theme.PRIMARY_DARK))
            a.triggered.connect(lambda: self.select_tool(tool_id, code))
            a.setProperty("tip", tip or text.replace("\n", " "))
            self.tool_group.addAction(a)
            self.tool_actions[(tool_id, code)] = a
            if not code:
                self.tool_order.append(a)
            if key is not None:
                reg.register(sid, a.property("tip"), key, "Asboblar")
                self.sc_actions[sid] = a
            self._refresh_tip(a, sid)
            return a

        tool("Tanlash", "V", SELECT)
        tool("Xona", "P", ROOM_POLY, tip="Xona/koridorni burchaklari bo'yicha chizish")
        tool("To'rtburchak", "R", ROOM_RECT, tip="To'rtburchak xona")
        tool("Devor", "L", WALL, tip="Devor chizish (Enter - tugatish)")
        tool("Eshik", "D", DOOR, tip="Eshik qo'yish")
        tool("Zina", "Z", STAIRS, tip="Zinapoya chizish")
        tool("Bo'lish", "B", SPLIT, tip="Xonani bo'lish")
        for t in EQUIPMENT_TYPES:
            tool(t.label, None, EQUIP, t.code, tip=f"{t.name} qo'yish")
        self.a_plan_mode = QAction("Kerak (reja)", self)
        self.a_plan_mode.setCheckable(True)
        self.a_plan_mode.setProperty("tip", "Yangi qo'yilgan jihozlar \"kerak (rejada)\" bo'ladi")
        self.a_plan_mode.toggled.connect(lambda on: setattr(self.view, "place_planned", on))
        self.addAction(self.a_plan_mode)
        reg.register("tool.plan_mode", "Kerak (reja) rejimi", "Q", "Asboblar")
        self.sc_actions["tool.plan_mode"] = self.a_plan_mode

        # AT jihozlari: tanlangan belgining turi yoki shu turdagi belgini qo'yish (standart 1-6)
        for t in EQUIPMENT_TYPES:
            a = QAction(t.name, self)
            a.triggered.connect(lambda _=False, code=t.code: self.on_equip_key(code))
            self.addAction(a)
            sid = f"equip.{t.code}"
            reg.register(sid, f"{t.name} ({t.label})", t.key, "AT jihozlari")
            self.sc_actions[sid] = a

        for sid, a in self.sc_actions.items():
            a.setShortcut(reg.key(sid))
            self._refresh_tip(a, sid)
        reg.listeners.append(self._on_shortcut_changed)

    def _act(self, menu, text, slot, shortcut=None, sid=None):
        a = QAction(text, self)
        a.triggered.connect(slot)
        menu.addAction(a)
        self.addAction(a)
        if sid:
            default = shortcut
            if isinstance(default, QKeySequence.StandardKey):
                default = QKeySequence(default).toString(QKeySequence.PortableText)
            elif isinstance(default, QKeySequence):
                default = default.toString(QKeySequence.PortableText)
            group = menu.title().replace("&", "") if hasattr(menu, "title") else "Umumiy"
            registry().register(sid, text.replace("...", ""), default or "", group)
            self.sc_actions[sid] = a
            a.setShortcut(registry().key(sid))
        elif shortcut:
            a.setShortcut(shortcut)
        return a

    def _refresh_tip(self, a: QAction, sid: str):
        tip = a.property("tip")
        if tip:
            key = display(registry().key(sid)) if sid in registry().entries else ""
            a.setToolTip(f"{tip} ({key})" if key else tip)

    def _on_shortcut_changed(self, sid: str, seq: QKeySequence):
        a = self.sc_actions.get(sid)
        if a is not None:
            a.setShortcut(seq)
            self._refresh_tip(a, sid)

    def edit_shortcuts(self):
        ShortcutsDialog(registry(), self).exec()

    def build_editor(self) -> QWidget:
        """Muharrir: yuqori panel, ish bosqichlari, asboblar, chizma va xususiyatlar."""
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar())
        self.steps = StepsBar()
        self.steps.clicked.connect(self.on_step)
        root.addWidget(self.steps)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_tool_panel())
        body.addLayout(self._build_center(), 1)
        body.addWidget(self._build_right_panel())
        root.addLayout(body, 1)
        return page

    def _build_topbar(self) -> QFrame:
        top = QFrame()
        top.setObjectName("topbar")
        lay = QHBoxLayout(top)
        lay.setContentsMargins(20, 8, 20, 8)
        lay.setSpacing(16)
        logo = QPushButton("AT")
        logo.setObjectName("logo")
        logo.setFixedSize(32, 32)
        logo.setCursor(Qt.PointingHandCursor)
        logo.setToolTip("Bosh sahifa — barcha binolar")
        logo.clicked.connect(self.show_home)
        lay.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.project_name = QLabel()
        self.project_name.setObjectName("projectName")
        self.project_state = QLabel()
        self.project_state.setObjectName("projectState")
        col.addWidget(self.project_name)
        col.addWidget(self.project_state)
        lay.addLayout(col)
        info = QToolButton()
        info.setObjectName("zoomBtn")
        info.setIcon(svg_icon("edit", theme.INK_3, size=16))
        info.setToolTip("Bino nomi va manzili")
        info.clicked.connect(self.edit_building_info)
        lay.addWidget(info)
        self.floor_tabs = FloorTabs(self.floor_menu)
        self.floor_tabs.selected.connect(self.select_floor)
        self.floor_tabs.add_clicked.connect(self.add_floor_from_image)
        lay.addWidget(self.floor_tabs, 1)
        for icon, tip, slot in (("undo", "Bekor qilish", self.undo), ("redo", "Qaytarish", self.redo)):
            b = QPushButton()
            b.setObjectName("iconBtn")
            b.setIcon(svg_icon(icon, theme.INK_2, size=18))
            b.setIconSize(QSize(18, 18))
            b.setToolTip(tip)
            b.setAccessibleName(tip)
            b.clicked.connect(slot)
            lay.addWidget(b)
        exp = QPushButton("  Eksport")
        exp.setObjectName("primary")
        exp.setIcon(svg_icon("export", "#FFFFFF", size=16))
        exp.clicked.connect(lambda: self.export())
        lay.addWidget(exp)
        return top

    def _build_tool_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("toolPanel")
        panel.setFixedWidth(92)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(8, 12, 8, 12)
        lay.setSpacing(4)
        for a in self.tool_order:
            b = QToolButton()
            b.setObjectName("tool")
            b.setDefaultAction(a)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIconSize(QSize(20, 20))
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            lay.addWidget(b)
        lay.addSpacing(4)
        lay.addWidget(hline())
        lay.addSpacing(4)
        g = QLabel("AT jihoz")
        g.setObjectName("toolGroup")
        g.setAlignment(Qt.AlignCenter)
        lay.addWidget(g)
        lay.addWidget(equip_grid({t.code: self.tool_actions[(EQUIP, t.code)] for t in EQUIPMENT_TYPES}))
        plan = QCheckBox("Kerak\n(reja)")
        plan.setObjectName("planMode")
        plan.setToolTip(self.a_plan_mode.toolTip())
        plan.toggled.connect(self.a_plan_mode.setChecked)
        self.a_plan_mode.toggled.connect(plan.setChecked)
        lay.addWidget(plan, 0, Qt.AlignHCenter)
        lay.addStretch()
        return panel

    def _build_center(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setContentsMargins(16, 16, 16, 12)
        col.setSpacing(12)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.floor_title = QLabel()
        self.floor_title.setObjectName("floorTitle")
        self.floor_info = QLabel()
        self.floor_info.setObjectName("muted")
        row.addWidget(self.floor_title)
        row.addWidget(self.floor_info)
        row.addStretch()
        lab = QLabel("Kadastr foni")
        lab.setObjectName("hint")
        row.addWidget(lab)
        self.bg_slider = QSlider(Qt.Horizontal)
        self.bg_slider.setRange(0, 100)
        self.bg_slider.setValue(60)
        self.bg_slider.setFixedWidth(120)
        self.bg_slider.setAccessibleName("Kadastr fonining shaffofligi")
        self.bg_slider.valueChanged.connect(lambda v: self.scene.set_bg_opacity(v / 100))
        row.addWidget(self.bg_slider)
        zoom = QFrame()
        zoom.setObjectName("zoomBox")
        zl = QHBoxLayout(zoom)
        zl.setContentsMargins(0, 0, 0, 0)
        zl.setSpacing(0)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("zoomLabel")
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setMinimumWidth(48)
        for icon, tip, slot in (("minus", "Kichiklashtirish", lambda: self.view.zoom_by(1 / 1.25)),
                                (None, None, None),
                                ("plus", "Kattalashtirish", lambda: self.view.zoom_by(1.25)),
                                ("fit", "Butun chizma", self.view.zoom_fit)):
            if icon is None:
                zl.addWidget(self.zoom_label)
                continue
            b = QToolButton()
            b.setObjectName("zoomBtn")
            b.setIcon(svg_icon(icon, theme.INK_2, size=16))
            b.setToolTip(tip)
            b.setAccessibleName(tip)
            b.clicked.connect(slot)
            zl.addWidget(b)
        row.addWidget(zoom)
        col.addLayout(row)

        card = QFrame()
        card.setObjectName("canvasCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(1, 1, 1, 1)
        cl.addWidget(self.view)
        col.addWidget(card, 1)

        row = QHBoxLayout()
        self.hint = QLabel()
        self.hint.setObjectName("hint")
        self.hint.setTextFormat(Qt.RichText)
        self.hint.setWordWrap(True)
        row.addWidget(self.hint, 1)
        self.review_link = QLabel()
        self.review_link.setTextFormat(Qt.RichText)
        self.review_link.linkActivated.connect(lambda _: self.open_review())
        row.addWidget(self.review_link)
        col.addLayout(row)
        return col

    def _build_right_panel(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("rightScroll")
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(330)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        w = QWidget()
        w.setObjectName("rightPanel")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)
        self.props_title = section_title("Etaj sozlamalari")
        lay.addWidget(self.props_title)

        self.props = QStackedWidget()
        self.props.currentChanged.connect(self._on_props_page)
        # 0 - hech narsa tanlanmagan: etaj sozlamalari
        nw = QWidget()
        nl = QVBoxLayout(nw)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setSpacing(12)
        hint = QLabel("Element tanlanmagan. Xona, devor yoki belgini bosing.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        nl.addWidget(hint)
        self.p_room_wall = self._thickness_spin()
        self.p_room_wall.setToolTip("Barcha xonalar chegarasidagi devorlar qalinligi (shu etaj uchun)")
        self.p_room_wall.valueChanged.connect(self.on_room_wall_thickness)
        self.p_new_wall = self._thickness_spin()
        self.p_new_wall.setToolTip("Devor asbobi bilan chiziladigan yangi devorlar qalinligi")
        self.p_new_wall.setValue(float(self.settings.value("new_wall_m", 0.25)))
        self.p_new_wall.valueChanged.connect(self.on_new_wall_thickness)
        self.scene.new_wall_m = self.p_new_wall.value()
        nl.addWidget(field("Xona devorlari qalinligi", self.p_room_wall))
        nl.addWidget(field("Yangi devorlar qalinligi", self.p_new_wall))
        nl.addStretch()
        self.props.addWidget(nw)
        # 1 - xona
        rw = QWidget()
        rl = QVBoxLayout(rw)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(12)
        self.p_room_name = QLineEdit()
        self.p_room_name.setPlaceholderText("masalan: 105 yoki Kabinet")
        self.p_room_name.editingFinished.connect(self.on_room_props)
        self.p_room_kind = QComboBox()
        for k, (name, _) in ROOM_KINDS.items():
            self.p_room_kind.addItem(name, k)
        self.p_room_kind.activated.connect(self.on_room_props)
        self.p_room_area = QLabel()
        self.p_room_area.setStyleSheet("font-weight: 600")
        rl.addWidget(field("Raqami / nomi", self.p_room_name))
        rl.addWidget(field("Turi", self.p_room_kind))
        ar = QHBoxLayout()
        al = QLabel("Maydoni")
        al.setObjectName("fieldLabel")
        ar.addWidget(al)
        ar.addStretch()
        ar.addWidget(self.p_room_area)
        rl.addLayout(ar)
        br = QHBoxLayout()
        br.setSpacing(6)
        for text, name, slot in (("Aylantirish", "small", lambda: self.rotate_selected(90.0)),
                                 ("Bo'lish", "small", lambda: self.select_tool(SPLIT)),
                                 ("O'chirish", "smallDanger", self.scene.delete_selected)):
            b = QPushButton(text)
            b.setObjectName(name)
            b.clicked.connect(slot)
            br.addWidget(b)
        br.addStretch()
        rl.addLayout(br)
        box = QFrame()
        box.setObjectName("roomEq")
        box.setMinimumHeight(66)
        bl = QVBoxLayout(box)
        bl.setContentsMargins(10, 10, 10, 10)
        bl.setSpacing(6)
        lab = QLabel("Xonadagi jihozlar")
        lab.setObjectName("muted")
        bl.addWidget(lab)
        self.room_eq = QHBoxLayout()
        self.room_eq.setSpacing(6)
        bl.addLayout(self.room_eq)
        rl.addWidget(box)
        rl.addStretch()
        self.props.addWidget(rw)
        # 2 - AT jihozi
        ew = QWidget()
        el = QVBoxLayout(ew)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(12)
        self.p_eq_type = QComboBox()
        for t in EQUIPMENT_TYPES + [UNKNOWN]:
            self.p_eq_type.addItem(type_icon(t.code, 16), t.name, t.code)
        self.p_eq_type.activated.connect(self.on_eq_props)
        self.p_eq_note = QLineEdit()
        self.p_eq_note.setPlaceholderText("masalan: Hikvision, 2-port")
        self.p_eq_note.editingFinished.connect(self.on_eq_props)
        self.p_eq_status = QComboBox()
        self.p_eq_status.addItem("Mavjud", "existing")
        self.p_eq_status.addItem("Kerak (o'rnatilishi rejada)", "planned")
        self.p_eq_status.activated.connect(self.on_eq_props)
        self.p_eq_room = QLabel()
        self.p_eq_room.setObjectName("muted")
        el.addWidget(self.p_eq_room)
        el.addWidget(field("Turi", self.p_eq_type))
        el.addWidget(field("Holati", self.p_eq_status))
        el.addWidget(field("Izoh", self.p_eq_note))
        el.addStretch()
        self.props.addWidget(ew)
        # 3 - bir nechta
        self.p_multi = QLabel()
        self.p_multi.setAlignment(Qt.AlignTop)
        self.p_multi.setWordWrap(True)
        self.p_multi.setTextFormat(Qt.RichText)
        self.props.addWidget(self.p_multi)
        # 4 - devor(lar)
        ww = QWidget()
        wl = QVBoxLayout(ww)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(12)
        self.p_wall_thick = self._thickness_spin()
        self.p_wall_thick.valueChanged.connect(self.on_wall_thickness)
        self.p_wall_len = QLabel()
        self.p_wall_len.setStyleSheet("font-weight: 600")
        self.p_wall_count = QLabel()
        self.p_wall_count.setObjectName("muted")
        self.p_wall_count.setWordWrap(True)
        wl.addWidget(field("Qalinligi", self.p_wall_thick))
        lr = QHBoxLayout()
        ll = QLabel("Uzunligi")
        ll.setObjectName("fieldLabel")
        lr.addWidget(ll)
        lr.addStretch()
        lr.addWidget(self.p_wall_len)
        wl.addLayout(lr)
        wl.addWidget(self.p_wall_count)
        wl.addStretch()
        self.props.addWidget(ww)
        lay.addWidget(self.props)

        lay.addWidget(hline())
        lay.addWidget(section_title("Etaj bo'yicha"))
        grid = QGridLayout()
        grid.setSpacing(8)
        self.tiles: dict[str, Tile] = {}
        for i, key in enumerate([t.code for t in EQUIPMENT_TYPES] + ["planned", "?"]):
            t = Tile()
            if key == "?":
                t.clicked.connect(self.open_review)
            elif key != "planned":
                t.clicked.connect(lambda _=False, c=key: self.on_equip_key(c))
            grid.addWidget(t, i // 3, i % 3)
            self.tiles[key] = t
        lay.addLayout(grid)
        self.stats = QLabel()
        self.stats.setObjectName("muted")
        self.stats.setWordWrap(True)
        self.stats.setTextFormat(Qt.RichText)
        self.stats.linkActivated.connect(lambda _: self.open_review())
        lay.addWidget(self.stats)
        lay.addStretch()
        scroll.setWidget(w)
        return scroll

    PROPS_TITLES = ["Etaj sozlamalari", "Tanlangan xona", "Tanlangan jihoz", "Tanlangan elementlar",
                    "Tanlangan devor"]

    def _on_props_page(self, i: int):
        self.props_title.setText(self.PROPS_TITLES[i].upper())
        self.update_hint()

    def floor_menu(self, i: int) -> QMenu:
        m = QMenu(self)
        m.addAction("Nomini o'zgartirish...", self.rename_floor)
        m.addAction("Chapga surish", lambda: self.move_floor(-1)).setEnabled(i > 0)
        m.addAction("O'ngga surish", lambda: self.move_floor(1)).setEnabled(i < len(self.building.floors) - 1)
        m.addSeparator()
        m.addAction("Qayta avtomatik chizish...", self.redetect)
        m.addAction("Xonalarni qayta raqamlash...", self.renumber_rooms)
        m.addSeparator()
        m.addAction("Etajni o'chirish", self.delete_floor)
        return m

    def on_step(self, i: int):
        if i == 1:
            self.add_floor_from_image()
        elif i == 2:
            self.select_tool(SELECT)
            self.view.zoom_fit()
        elif i == 3:
            self.open_review()
        elif i == 4:
            self.export()

    def refresh_steps(self):
        f = self.floor
        if f is None:
            self.steps.set_steps([("active", "Kadastr rasmini yuklang"), ("todo", "Xonalarni tekshirish"),
                                  ("todo", "Belgilarni tasdiqlash"), ("todo", "Eksport")])
            return
        rooms = len(f.rooms)
        unknown = sum(1 for e in f.equipment if e.code == "?")
        known = len(f.equipment) - unknown
        s1 = ("done", "Rasm yuklandi" if f.image else "Etaj qo'shildi")
        if not rooms:
            s2 = ("active", "Xonalarni chizing")
        else:
            s2 = ("done" if known and not unknown else "active", f"Xonalarni tekshirish · {rooms} ta")
        if unknown:
            s3 = ("warn", f"Belgilar · {unknown} ta tasdiqlanmagan")
        elif known:
            s3 = ("done", f"Belgilar · {known} ta")
        else:
            s3 = ("todo", "Belgilarni qo'ying")
        s4 = ("active" if rooms and not unknown else "todo", "Eksport")
        self.steps.set_steps([s1, s2, s3, s4])

    def show_hint(self, text: str):
        """Asbob maslahati (chizma ostida)."""
        self.hint.setText(text)

    def update_hint(self):
        reg = registry()

        def k(sid):
            return kbd(display(reg.key(sid)))

        i = self.props.currentIndex()
        if i == 1:
            text = (f"Xona tanlandi. Burchaklarni sudrang · {k('rotate.cw')} aylantirish · "
                    f"{k('edit.delete')} o'chirish")
        elif i == 2:
            text = (f"Jihoz tanlandi. Sudrab ko'chiring · jihoz tugmasi bilan turini o'zgartiring · "
                    f"{k('edit.toggle_status')} mavjud/kerak · {k('edit.delete')} o'chirish")
        elif i == 3:
            text = f"{k('edit.merge')} xonalarni birlashtirish · {k('edit.delete')} o'chirish"
        elif i == 4:
            text = f"Devor tanlandi. {k('wall.thicker')} / {k('wall.thinner')} qalinlik · {k('edit.delete')} o'chirish"
        elif self.floor is None:
            text = "Yuqoridagi \"+ Etaj\" tugmasi bilan kadastr PDF yoki rasmini yuklang."
        else:
            text = (f"{k('tool.select')} tanlash · {k('tool.room_poly')} xona · {k('tool.wall')} devor · "
                    f"{k('tool.door')} eshik · g'ildirak - kattalashtirish")
        self.hint.setText(text)

    # ================================================================ holat
    def set_dirty(self, d=True):
        self.dirty = d
        name = os.path.basename(self.path) if self.path else "Nomsiz"
        self.setWindowTitle(f"{'*' if d else ''}{name} — TTYSI Binolar kadastri")
        self.project_name.setText(self.building.name or "Nomsiz bino")
        if d:
            state = "Saqlanmagan o'zgarishlar bor"
        elif not self.path:
            state = "Hali saqlanmagan"
        else:
            state = "Saqlandi" + (f" · {self.saved_at}" if self.saved_at else "")
        self.project_state.setText(state)

    def refresh_all(self):
        self.floor = None
        self._tabs_sig = None
        self.refresh_floor_list()
        if self.building.floors:
            self.select_floor(0)
        else:
            self.show_floor(None)
        self.set_dirty(False)
        self.pages.setCurrentWidget(self.editor)

    def refresh_floor_list(self, select: int | None = None):
        floors = self.building.floors
        sig = tuple((f.id, f.name, sum(1 for e in f.equipment if e.code == "?")) for f in floors)
        cur = floors.index(self.floor) if self.floor in floors else -1
        if sig != self._tabs_sig:
            self._tabs_sig = sig
            self.floor_tabs.set_floors(floors, cur)
        if select is not None:
            self.select_floor(select)
        else:
            self.floor_tabs.set_current(cur)

    def select_floor(self, i: int):
        if 0 <= i < len(self.building.floors):
            self.view.cancel_drawing()
            if self.building.floors[i] is not self.floor:
                self.show_floor(self.building.floors[i])
            self.floor_tabs.set_current(i)

    def background_for(self, floor: Floor) -> QImage | None:
        if not floor.image:
            return None
        if floor.id not in self.bg_cache:
            img = QImage()
            img.loadFromData(floor.image)
            self.bg_cache[floor.id] = img
        return self.bg_cache[floor.id]

    def show_floor(self, floor: Floor | None, keep_view=False):
        self.floor = floor
        tr = self.view.transform()
        h, v = self.view.horizontalScrollBar().value(), self.view.verticalScrollBar().value()
        self.scene.load(floor, self.background_for(floor) if floor else None)
        if floor is not None and floor.id not in self.histories:
            self.histories[floor.id] = History(floor)
        if keep_view:
            self.view.setTransform(tr)
            self.view.horizontalScrollBar().setValue(h)
            self.view.verticalScrollBar().setValue(v)
        else:
            QTimer.singleShot(0, self.view.zoom_fit)
        self.on_selection()
        self.refresh_stats()

    def refresh_stats(self):
        f = self.floor
        self.refresh_steps()
        if f is None:
            self.floor_title.setText("Etaj yo'q")
            self.floor_info.setText("")
            for t in self.tiles.values():
                t.hide()
            self.stats.setText("Yuqoridagi \"+ Etaj\" tugmasi bilan kadastr PDF yoki rasmini yuklang.")
            self.review_link.setText("")
            self.update_hint()
            return
        counts = equipment_counts(f)
        need = equipment_counts(f, planned=True)
        for t in EQUIPMENT_TYPES:
            short = {"SER": "Serverxona", "KX": "K.x.", "T": "Tochka", "S": "Switch"}.get(t.code, t.name)
            self.tiles[t.code].set(str(counts.get(t.code, 0)), short)
            self.tiles[t.code].setToolTip(f"{t.name}: mavjud {counts.get(t.code, 0)} ta"
                                          + (f", kerak {need[t.code]} ta" if need.get(t.code) else ""))
            self.tiles[t.code].show()
        n_need = sum(need.values())
        self.tiles["planned"].set(f"+{n_need}", "kerak", "warn" if n_need else "")
        self.tiles["planned"].setVisible(bool(n_need))
        unknown = counts.get("?", 0)
        self.tiles["?"].set(str(unknown), "noma'lum (?)", "warn")
        self.tiles["?"].setVisible(bool(unknown))
        self.tiles["?"].setToolTip("Tasdiqlash ekranini ochish")
        if unknown:
            key = display(registry().key("review.open"))
            self.review_link.setText(f"<a href='review' style='color:{theme.PRIMARY}; font-weight:600; "
                                     f"text-decoration:none'>{unknown} ta belgini tasdiqlash →</a>"
                                     + (f" <span style='color:{theme.INK_3}'>({key})</span>" if key else ""))
        else:
            self.review_link.setText("")

        lines = []
        rooms = {}
        for r in f.rooms:
            rooms[r.kind] = rooms.get(r.kind, 0) + 1
        lines += [f"{ROOM_KINDS[k][0]}: <b>{n}</b>" for k, n in rooms.items()]
        if f.walls:
            lines.append(f"Alohida devorlar: <b>{len(f.walls)}</b>")
        if f.doors:
            lines.append(f"Eshiklar: <b>{len(f.doors)}</b>")
        total = None
        if f.scale_m_per_px:
            total = sum(r.area() for r in f.rooms) * f.scale_m_per_px ** 2
            lines.append(f"Umumiy maydon: <b>{total:.1f} m²</b>")
        else:
            lines.append("<i>Masshtab belgilanmagan (Etaj → Masshtabni belgilash)</i>")
        self.stats.setText("<br>".join(lines))
        self.floor_title.setText(f.name)
        info = [f"{len(f.rooms)} ta xona"]
        info.append(f"{total:.0f} m²" if total is not None else "masshtab yo'q")
        self.floor_info.setText("· " + " · ".join(info))
        self.update_hint()

    def on_model_changed(self):
        if self.floor is None:
            return
        self.histories[self.floor.id].push(self.floor)
        self.set_dirty()
        self.refresh_stats()
        self.refresh_floor_list()
        self.on_selection()

    def restore(self, snapshot):
        if snapshot is None or self.floor is None:
            return
        self.floor.load_content(snapshot)
        self.show_floor(self.floor, keep_view=True)
        self.refresh_floor_list()
        self.set_dirty()

    def undo(self):
        if self.floor:
            self.view.cancel_drawing()
            self.restore(self.histories[self.floor.id].undo())

    def redo(self):
        if self.floor:
            self.restore(self.histories[self.floor.id].redo())

    # ================================================================ tanlash va xususiyatlar
    def select_tool(self, tool, code=None):
        self.view.set_tool(tool, code)
        a = self.tool_actions.get((tool, code)) or self.tool_actions.get((tool, None))
        if a:
            a.setChecked(True)
        elif self.tool_group.checkedAction():
            self.tool_group.checkedAction().setChecked(False)
        if tool != SELECT:
            self.scene.clearSelection()

    def select_all(self):
        for it in self.scene.room_items() + self.scene.equipment_items():
            it.setSelected(True)

    def on_selection(self):
        try:
            sel = self.scene.selectedItems()
        except RuntimeError:
            return
        rooms = [i for i in sel if isinstance(i, RoomItem)]
        eqs = [i for i in sel if isinstance(i, EquipmentItem)]
        walls = [i for i in sel if isinstance(i, WallItem)]
        if walls and len(walls) == len(sel):
            m = meter_px(self.floor)
            self._set_quiet(self.p_wall_thick, walls[0].wall.thickness / m)
            length = sum(math.dist(a, b) for it in walls for a, b in zip(it.wall.points, it.wall.points[1:])) / m
            self.p_wall_len.setText(f"{length:.2f} m" + ("" if self.floor.scale_m_per_px else " (masshtab yo'q)"))
            self.p_wall_count.setText(f"{len(walls)} ta devor tanlangan - qalinlik hammasiga qo'llanadi."
                                      if len(walls) > 1 else "Alt+↑ / Alt+↓ - 5 sm ga o'zgartirish.")
            self.props.setCurrentIndex(4)
        elif len(sel) == 1 and rooms:
            r = rooms[0].room
            self.p_room_name.setText(r.name)
            self.p_room_kind.setCurrentIndex(self.p_room_kind.findData(r.kind))
            if self.floor and self.floor.scale_m_per_px:
                self.p_room_area.setText(f"{r.area() * self.floor.scale_m_per_px ** 2:.1f} m²")
            else:
                self.p_room_area.setText("masshtab yo'q")
            self.fill_room_equipment(r)
            self.props.setCurrentIndex(1)
        elif len(sel) == 1 and eqs:
            e = eqs[0].eq
            room = self.floor.room_of(e) if self.floor else None
            self.p_eq_room.setText(("xonadan tashqarida" if room is None else
                                    f"{room.name}-xona ichida" if room.name else "xona ichida"))
            self.p_eq_type.setCurrentIndex(self.p_eq_type.findData(e.code))
            self.p_eq_note.setText(e.note)
            self.p_eq_status.setCurrentIndex(self.p_eq_status.findData(e.status))
            self.props.setCurrentIndex(2)
        elif sel:
            k = lambda sid: kbd(display(registry().key(sid)))  # noqa: E731
            self.p_multi.setText(f"<b>{len(rooms)}</b> ta xona, <b>{len(eqs)}</b> ta belgi tanlangan.<br><br>"
                                 "Jihoz tugmasi — belgilar turini o'zgartirish<br>"
                                 f"{k('edit.merge')} — xonalarni birlashtirish<br>"
                                 f"{k('edit.delete')} — o'chirish")
            self.props.setCurrentIndex(3)
        else:
            if self.floor is not None:
                self._set_quiet(self.p_room_wall, self.floor.wall_m)
            self.props.setCurrentIndex(0)

    def fill_room_equipment(self, room):
        while self.room_eq.count():
            it = self.room_eq.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        counts: dict[tuple[str, bool], int] = {}
        for e in self.floor.equipment:
            if self.floor.room_of(e) is room:
                counts[(e.code, e.planned)] = counts.get((e.code, e.planned), 0) + 1
        if not counts:
            lab = QLabel("yo'q")
            lab.setObjectName("muted")
            self.room_eq.addWidget(lab)
        for (code, planned), n in sorted(counts.items()):
            t = get_type(code)
            if planned:
                self.room_eq.addWidget(chip(f"{t.label} × {n} kerak", theme.SURFACE, t.color, dashed=True))
            else:
                self.room_eq.addWidget(chip(f"{t.label} × {n}", t.color))
        self.room_eq.addStretch()
        self.props.currentWidget().updateGeometry()
        self.props.updateGeometry()

    @staticmethod
    def _thickness_spin() -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(0.05, 1.50)
        sp.setDecimals(2)
        sp.setSingleStep(0.01)
        sp.setSuffix(" m")
        sp.setKeyboardTracking(False)   # yozib bo'lgach (Enter) qo'llanadi, har harfda emas
        return sp

    @staticmethod
    def _set_quiet(spin: QDoubleSpinBox, value: float) -> None:
        spin.blockSignals(True)
        spin.setValue(value)
        spin.blockSignals(False)

    def on_room_wall_thickness(self, value: float):
        if self.floor is None or abs(self.floor.wall_m - value) < 1e-9:
            return
        self.floor.wall_m = value
        self.histories[self.floor.id].push(self.floor)
        self.show_floor(self.floor, keep_view=True)
        self.set_dirty()

    def on_new_wall_thickness(self, value: float):
        self.scene.new_wall_m = value
        self.settings.setValue("new_wall_m", value)

    def on_wall_thickness(self, value: float):
        walls = self.scene.selected_walls()
        if walls:
            self.scene.set_wall_thickness(walls, value)

    def change_wall_thickness(self, delta_m: float):
        """Alt+↑ / Alt+↓: tanlangan devorlarni 5 sm ga qalinlashtirish / yupqalashtirish."""
        walls = self.scene.selected_walls()
        if not walls:
            self.statusBar().showMessage("Avval devorni tanlang.", 4000)
            return
        m = meter_px(self.floor)
        value = min(1.5, max(0.05, round(walls[0].wall.thickness / m + delta_m, 2)))
        self.scene.set_wall_thickness(walls, value)
        self.statusBar().showMessage(f"Devor qalinligi: {value:.2f} m", 3000)

    def on_room_props(self):
        rooms = self.scene.selected_rooms()
        if len(rooms) != 1:
            return
        it = rooms[0]
        name, kind = self.p_room_name.text().strip(), self.p_room_kind.currentData()
        if (name, kind) == (it.room.name, it.room.kind):
            return
        it.room.name, it.room.kind = name, kind
        it.refresh_style()
        self.scene.changed_model.emit()

    def on_eq_props(self):
        eqs = self.scene.selected_equipment()
        if len(eqs) != 1:
            return
        it = eqs[0]
        code, note, status = self.p_eq_type.currentData(), self.p_eq_note.text().strip(), self.p_eq_status.currentData()
        if (code, note, status) == (it.eq.code, it.eq.note, it.eq.status):
            return
        it.set_code(code)
        it.set_status(status)
        it.eq.note = note
        it.refresh_tooltip()
        self.scene.changed_model.emit()

    def rotate_selected(self, angle):
        if not self.scene.rotate_selected(angle):
            self.statusBar().showMessage("Aylantirish uchun xona, devor, zina yoki eshikni tanlang.", 4000)

    def toggle_status(self):
        eqs = self.scene.selected_equipment()
        if not eqs:
            self.statusBar().showMessage("Avval jihozni tanlang.", 4000)
            return
        new = "existing" if all(it.eq.planned for it in eqs) else "planned"
        for it in eqs:
            it.set_status(new)
        self.scene.changed_model.emit()

    def on_digit(self, key: str) -> bool:
        """Standart tugma bo'yicha (1-6) - eski usul, testlar va moslik uchun."""
        t = BY_KEY.get(key)
        if t is None:
            return False
        self.on_equip_key(t.code)
        return True

    def on_equip_key(self, code: str) -> None:
        """Jihoz tugmasi: tanlangan belgilar turini o'rnatish yoki shu turdagi belgini qo'yish asbobi."""
        eqs = self.scene.selected_equipment()
        if eqs:
            was_unknown = len(eqs) == 1 and eqs[0].eq.code == "?"
            for it in eqs:
                it.set_code(code)
            self.scene.changed_model.emit()
            if was_unknown:
                self.select_next_unknown()
        else:
            self.select_tool(EQUIP, code)

    def open_review(self):
        """Tasdiqlash ekrani: har bir \"?\" belgini rasmdagi joyi bilan ko'rsatib, turini so'raydi."""
        if self.floor is None or not any(e.code == "?" for e in self.floor.equipment):
            self.statusBar().showMessage("Tasdiqlanmagan belgi yo'q ✓", 4000)
            return
        ReviewDialog(self).exec()
        self.refresh_stats()
        self.refresh_floor_list()

    def select_next_unknown(self):
        items = [i for i in self.scene.equipment_items() if i.eq.code == "?"]
        if not items:
            self.statusBar().showMessage("Barcha belgilar tasdiqlangan ✓", 4000)
            return
        items.sort(key=lambda i: (i.pos().y(), i.pos().x()))
        if self.view.tool != SELECT:
            self.select_tool(SELECT)
        self.scene.clearSelection()
        items[0].setSelected(True)
        self.view.centerOn(items[0])
        self.statusBar().showMessage(f"Tasdiqlanmagan belgi ({len(items)} ta qoldi): turini jihoz tugmasi bilan tanlang, "
                                     "noto'g'ri bo'lsa Del.")

    def toggle_ortho(self):
        self.scene.ortho = self.a_ortho.isChecked()

    # ================================================================ xonalar ustida amallar
    def split_room(self, a: QPointF, b: QPointF):
        if self.floor is None:
            return
        target = self.scene.selected_rooms()
        mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
        candidates = [i for i in target] or [i for i in self.scene.room_items() if i.contains(i.mapFromScene(mid))]
        for it in candidates:
            parts = split_room(it.room.points, (a.x(), a.y()), (b.x(), b.y()))
            if parts:
                idx = self.floor.rooms.index(it.room)
                new = [Room(points=parts[0], kind=it.room.kind, name=it.room.name)]
                new += [Room(points=p, kind=it.room.kind) for p in parts[1:]]
                self.floor.rooms[idx:idx + 1] = new
                self.histories[self.floor.id].push(self.floor)
                self.show_floor(self.floor, keep_view=True)
                self.set_dirty()
                self.refresh_stats()
                return
        self.statusBar().showMessage("Chiziq birorta xonani kesib o'tmadi.", 5000)

    def merge_selected(self):
        rooms = self.scene.selected_rooms()
        if len(rooms) < 2:
            self.statusBar().showMessage("Birlashtirish uchun kamida 2 ta xonani tanlang (Ctrl + bosish).", 5000)
            return
        merged = merge_rooms([it.room.points for it in rooms], wall_width(self.floor) * 1.5)
        if merged is None:
            QMessageBox.warning(self, "Birlashtirish", "Tanlangan xonalar bir-biriga tegib turmaydi.")
            return
        first = rooms[0].room
        idx = min(self.floor.rooms.index(it.room) for it in rooms)
        for it in rooms:
            self.floor.rooms.remove(it.room)
        self.floor.rooms.insert(idx, Room(points=merged, kind=first.kind, name=first.name))
        self.histories[self.floor.id].push(self.floor)
        self.show_floor(self.floor, keep_view=True)
        self.set_dirty()
        self.refresh_stats()

    def set_scale(self, px: float):
        self.select_tool(SELECT)
        if self.floor is None or px < 1:
            return
        m, ok = QInputDialog.getDouble(self, "Masshtab", "Belgilangan chiziq uzunligi (metr):",
                                       5.0, 0.01, 10000, 2)
        if not ok:
            return
        self.floor.scale_m_per_px = m / px
        self.histories[self.floor.id].push(self.floor)
        self.show_floor(self.floor, keep_view=True)
        self.set_dirty()

    # ================================================================ etajlar
    def edit_building_info(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Bino ma'lumotlari")
        lay = QVBoxLayout(dlg)
        name = QLineEdit(self.building.name)
        addr = QLineEdit(self.building.address)
        lay.addWidget(field("Bino nomi", name))
        lay.addWidget(field("Manzil", addr))
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("Saqlash")
        bb.button(QDialogButtonBox.Save).setObjectName("primary")
        bb.button(QDialogButtonBox.Cancel).setText("Bekor qilish")
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.resize(420, dlg.sizeHint().height())
        if dlg.exec() != QDialog.Accepted:
            return
        n, a = name.text().strip(), addr.text().strip()
        if (n, a) != (self.building.name, self.building.address):
            self.building.name, self.building.address = n, a
            self.set_dirty()

    def next_floor_name(self):
        return f"{len(self.building.floors) + 1}-etaj"

    def add_floor_from_image(self, path: str | None = None):
        if not path:
            last = self.settings.value("last_dir", "")
            path, _ = QFileDialog.getOpenFileName(self, "Kadastr hujjatini tanlang", last, IMAGE_FILTER)
        if not path:
            return
        self.settings.setValue("last_dir", os.path.dirname(path))
        if path.lower().endswith(".pdf"):
            self.add_floors_from_pdf(path)
            return
        try:
            img = read_image(path)
        except Exception as e:
            QMessageBox.critical(self, "Xato", str(e))
            return
        self.import_floor(img, image_paper_mm_per_px(path), from_pdf=False, file_name=os.path.basename(path))

    def add_floors_from_pdf(self, path: str):
        """PDF: sahifa tanlanadi, undan etaj kesib olinadi; bir nechta etajni ketma-ket qo'shish mumkin."""
        doc = QPdfDocument(self)
        if doc.load(path) != QPdfDocument.Error.None_ or doc.pageCount() == 0:
            QMessageBox.critical(self, "Xato", "PDF faylni ochib bo'lmadi.")
            return
        page = 0
        try:
            while True:
                dlg = ImportDialog(None, self.next_floor_name(), self, doc=doc, page=page,
                                   file_name=os.path.basename(path))
                if not self.create_floor(dlg) or not dlg.again:
                    break
                page = dlg.page()
        finally:
            doc.close()

    def import_floor(self, img, paper_mm_per_px, from_pdf: bool, file_name: str = "") -> bool:
        dlg = ImportDialog(img, self.next_floor_name(), self, paper_mm_per_px=paper_mm_per_px,
                           from_pdf=from_pdf, file_name=file_name)
        return self.create_floor(dlg)

    def create_floor(self, dlg: ImportDialog) -> bool:
        """Import oynasini ko'rsatadi va natijadan etaj yaratadi."""
        if dlg.exec() != QDialog.Accepted:
            return False
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            cropped = dlg.result_image()
            mpp = dlg.m_per_px()
            corrected = limit_size(cropped)
            if mpp:
                mpp *= cropped.shape[1] / corrected.shape[1]
            h, w = corrected.shape[:2]
            floor = Floor(name=dlg.name.text().strip() or self.next_floor_name(),
                          image=encode_jpg(corrected), width=w, height=h, scale_m_per_px=mpp)
            msg = "Etaj qo'shildi."
            if dlg.auto.isChecked():
                msg = self.apply_detection(floor, corrected, dlg.params_w.params(mpp), keep_eq=False,
                                           numbering=dlg.params_w.numbering.isChecked())
        finally:
            QApplication.restoreOverrideCursor()
        self.building.floors.append(floor)
        self.refresh_floor_list(select=len(self.building.floors) - 1)
        self.set_dirty()
        self.pages.setCurrentWidget(self.editor)
        self.statusBar().showMessage(msg, 10000)
        if any(e.code == "?" for e in floor.equipment) and not dlg.again:
            QTimer.singleShot(300, self.open_review)
        return True

    def apply_detection(self, floor: Floor, img, params: DetectParams, keep_eq: bool,
                        numbering: bool = True) -> str:
        res = detect(img, params)
        floor.rooms = [Room(points=r.points, kind=r.kind, name=str(i) if numbering else "")
                       for i, r in enumerate(res.rooms, 1)]
        kept = [e for e in floor.equipment if e.code != "?"] if keep_eq else []
        floor.equipment = kept + [Equipment(code="?", x=x, y=y) for x, y in res.marks]
        return (f"Topildi: {len(res.rooms)} ta xona/koridor, {len(res.marks)} ta belgi nomzodi. "
                "Chizmani tekshirib, tuzating.")

    def redetect(self):
        if self.floor is None or not self.floor.image:
            QMessageBox.information(self, "Qayta chizish", "Bu etajda kadastr rasmi yo'q.")
            return
        mpp = self.floor.scale_m_per_px
        dlg = RedetectDialog(self, metric=mpp is not None)
        if dlg.exec() != QDialog.Accepted:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            img = decode_image(self.floor.image)
            if img.shape[1] != self.floor.width and mpp:
                mpp *= self.floor.width / img.shape[1]
            msg = self.apply_detection(self.floor, img, dlg.params_w.params(mpp), dlg.keep_eq.isChecked(),
                                       numbering=dlg.params_w.numbering.isChecked())
        finally:
            QApplication.restoreOverrideCursor()
        self.histories[self.floor.id].push(self.floor)
        self.show_floor(self.floor, keep_view=True)
        self.refresh_floor_list()
        self.set_dirty()
        self.statusBar().showMessage(msg, 10000)

    def renumber_rooms(self):
        """Xonalarni chapdan o'ngga, yuqoridan pastga qayta raqamlash."""
        if self.floor is None or not self.floor.rooms:
            return
        start, ok = QInputDialog.getInt(self, "Xonalarni raqamlash", "Birinchi raqam:", 1, 0, 100000)
        if not ok:
            return
        row_h = max(self.floor.width, self.floor.height) * 0.05
        order = sorted(self.floor.rooms, key=lambda r: (round(min(q[1] for q in r.points) / row_h),
                                                         min(q[0] for q in r.points)))
        for i, r in enumerate(order, start):
            r.name = str(i)
        self.histories[self.floor.id].push(self.floor)
        self.show_floor(self.floor, keep_view=True)
        self.set_dirty()

    def export_excel_current(self):
        if not self.building.floors:
            QMessageBox.information(self, "Hisobot", "Avval etaj qo'shing.")
            return
        base = "".join(c for c in self.building.name if c not in '\\/:*?"<>|')
        default = os.path.join(self.settings.value("export_dir", self.settings.value("last_dir", "")),
                               f"{base} - hisobot.xlsx")
        path, _ = QFileDialog.getSaveFileName(self, "Excel hisobot", default, "Excel (*.xlsx)")
        if path:
            self._write_excel(path, [self.building])

    def export_excel_many(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Hisobotga kiradigan loyihalarni tanlang (bir nechta)", self.settings.value("last_dir", ""),
            FILE_FILTER)
        if not paths:
            return
        buildings = []
        for p in paths:
            if self.path and os.path.abspath(p) == os.path.abspath(self.path):
                buildings.append(self.building)  # saqlanmagan o'zgarishlar ham kirsin
                continue
            try:
                buildings.append(Building.load(p))
            except Exception as e:
                QMessageBox.warning(self, "Xato", f"{os.path.basename(p)}: {e}")
        if not buildings:
            return
        default = os.path.join(self.settings.value("export_dir", ""), "Binolar - umumiy hisobot.xlsx")
        path, _ = QFileDialog.getSaveFileName(self, "Excel hisobot", default, "Excel (*.xlsx)")
        if path:
            self._write_excel(path, buildings)

    def _write_excel(self, path: str, buildings):
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            export_excel(path, buildings)
        except Exception as e:
            QMessageBox.critical(self, "Hisobot xatosi", str(e))
            return
        self.settings.setValue("export_dir", os.path.dirname(path))
        self.statusBar().showMessage(f"Hisobot saqlandi: {path}", 10000)

    def add_empty_floor(self):
        self.building.floors.append(Floor(name=self.next_floor_name()))
        self.refresh_floor_list(select=len(self.building.floors) - 1)
        self.set_dirty()

    def rename_floor(self):
        if self.floor is None:
            return
        name, ok = QInputDialog.getText(self, "Etaj nomi", "Yangi nom:", text=self.floor.name)
        if ok and name.strip():
            self.floor.name = name.strip()
            self.histories[self.floor.id].push(self.floor)
            self.refresh_floor_list()
            self.set_dirty()

    def delete_floor(self):
        if self.floor is None:
            return
        if QMessageBox.question(self, "Etajni o'chirish",
                                f"\"{self.floor.name}\" o'chirilsinmi? Buni qaytarib bo'lmaydi.") != QMessageBox.Yes:
            return
        i = self.building.floors.index(self.floor)
        self.building.floors.pop(i)
        self.floor = None
        self.refresh_floor_list()
        if self.building.floors:
            self.select_floor(min(i, len(self.building.floors) - 1))
        else:
            self.show_floor(None)
        self.set_dirty()

    def move_floor(self, d):
        if self.floor is None:
            return
        fl = self.building.floors
        i = fl.index(self.floor)
        j = i + d
        if 0 <= j < len(fl):
            fl[i], fl[j] = fl[j], fl[i]
            self.refresh_floor_list()
            self.set_dirty()

    # ================================================================ fayllar
    def maybe_save(self) -> bool:
        if not self.dirty:
            return True
        r = QMessageBox.question(self, "Saqlanmagan o'zgarishlar", "O'zgarishlar saqlansinmi?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if r == QMessageBox.Save:
            return self.save_project()
        return r == QMessageBox.Discard

    def build_settings_menu(self) -> QMenu:
        m = QMenu(self)
        m.addAction("Klaviatura tugmalari...", self.edit_shortcuts)
        m.addAction("Qo'llanma", self.show_help)
        m.addSeparator()
        m.addAction("Yangilanishni tekshirish...", lambda: self.updater.check(silent=False))
        m.addAction("Yangilanish sozlamalari...", lambda: UpdateSettingsDialog(self).exec())
        return m

    def show_home(self):
        if self.pages.currentWidget() is self.home or not self.maybe_save():
            return
        self.home.refresh()
        self.pages.setCurrentWidget(self.home)

    def new_building(self, path: str | None = None):
        """Bosh sahifadan: yangi loyiha va darhol etaj yuklash."""
        if self.pages.currentWidget() is not self.home and not self.maybe_save():
            return
        self.dirty = False
        self.new_project()
        self.add_floor_from_image(path)

    def new_project(self):
        if not self.maybe_save():
            return
        self.building = Building()
        self.path = None
        self.histories.clear()
        self.bg_cache.clear()
        self.refresh_all()

    def open_project(self, path: str | None = None):
        if not self.maybe_save():
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Loyihani ochish", self.settings.value("last_dir", ""),
                                                  FILE_FILTER)
        if not path:
            return
        try:
            b = Building.load(path)
        except Exception as e:
            QMessageBox.critical(self, "Ochib bo'lmadi", str(e))
            return
        self.settings.setValue("last_dir", os.path.dirname(path))
        self.building = b
        self.path = path
        remember(self.settings, b, path)
        self.histories.clear()
        self.bg_cache.clear()
        self.refresh_all()

    def save_project(self) -> bool:
        if not self.path:
            return self.save_project_as()
        try:
            self.building.save(self.path)
        except Exception as e:
            QMessageBox.critical(self, "Saqlab bo'lmadi", str(e))
            return False
        self.saved_at = datetime.now().strftime("%H:%M")
        remember(self.settings, self.building, self.path)
        self.set_dirty(False)
        self.statusBar().showMessage(f"Saqlandi: {self.path}", 5000)
        return True

    def save_project_as(self) -> bool:
        default = os.path.join(self.settings.value("last_dir", ""), f"{self.building.name}.ttysi")
        path, _ = QFileDialog.getSaveFileName(self, "Loyihani saqlash", default, FILE_FILTER)
        if not path:
            return False
        if not path.lower().endswith(".ttysi"):
            path += ".ttysi"
        self.path = path
        self.settings.setValue("last_dir", os.path.dirname(path))
        return self.save_project()

    @staticmethod
    def _safe_name(name: str) -> str:
        return "".join(c for c in name if c not in '\\/:*?"<>|').strip() or "chizma"

    def export(self, kind: str | None = None):
        """Eksport oynasi (format, etajlar, sozlamalar), keyin fayl tanlash."""
        if not self.building.floors and kind != "excel_many":
            QMessageBox.information(self, "Eksport", "Avval etaj qo'shing.")
            return
        dlg = ExportDialog(self, kind)
        result = dlg.exec()
        if dlg.review_requested:
            target = next((f for f in dlg.floors() if any(e.code == "?" for e in f.equipment)), None)
            if target is not None and target is not self.floor:
                self.select_floor(self.building.floors.index(target))
            self.open_review()
            return
        if result != QDialog.Accepted:
            return
        k = dlg.kind()
        if k == "excel":
            self.export_excel_current()
        elif k == "excel_many":
            self.export_excel_many()
        else:
            self.run_export(k, dlg.floors(), dlg.options(), dlg.size(), dlg.raster_ext())

    def run_export(self, kind: str, floors, opts: RenderOptions, size: int = 4000,
                   raster_ext: str = ".png", paths: list[str] | None = None) -> list[str]:
        """Chizmani faylga yozadi. PDF - barcha etajlar bitta faylda; boshqalar - har etaj alohida fayl."""
        if not floors:
            return []
        ext = {"image": raster_ext, "svg": ".svg", "pdf": ".pdf", "dxf": ".dxf"}[kind]
        start = self.settings.value("export_dir", self.settings.value("last_dir", ""))
        b = self.building.name
        if paths is None:
            if len(floors) > 1 and kind != "pdf":
                folder = QFileDialog.getExistingDirectory(self, "Fayllar saqlanadigan papka", start)
                if not folder:
                    return []
                paths = [os.path.join(folder, self._safe_name(f"{b} - {f.name}") + ext) for f in floors]
            else:
                base = self._safe_name(b if len(floors) > 1 else f"{b} - {floors[0].name}")
                filters = {".png": "PNG rasm (*.png)", ".jpg": "JPG rasm (*.jpg)", ".svg": "SVG (*.svg)",
                           ".pdf": "PDF (*.pdf)", ".dxf": "AutoCAD DXF (*.dxf)"}
                path, _ = QFileDialog.getSaveFileName(self, "Eksport", os.path.join(start, base + ext), filters[ext])
                if not path:
                    return []
                if not os.path.splitext(path)[1]:
                    path += ext
                paths = [path]
        self.settings.setValue("export_dir", os.path.dirname(paths[0]))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if kind == "pdf":
                export_pdf(paths[0], self.building, list(floors), opts)
            else:
                for f, path in zip(floors, paths):
                    if kind == "image":
                        export_image(path, self.building, f, opts, size)
                    elif kind == "svg":
                        export_svg(path, self.building, f, opts)
                    elif kind == "dxf":
                        export_dxf(path, self.building, f, planned=opts.planned)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Eksport xatosi", str(e))
            return []
        QApplication.restoreOverrideCursor()
        msg = f"Eksport qilindi: {paths[0]}" if len(paths) == 1 else \
            f"Eksport qilindi: {len(paths)} ta fayl — {os.path.dirname(paths[0])}"
        if kind == "dxf" and any(not f.scale_m_per_px for f in floors):
            msg += "  (masshtab belgilanmagan etaj DXF'da piksellarda)"
        self.statusBar().showMessage(msg, 10000)
        return paths

    def show_help(self):
        reg = registry()

        def k(sid):
            return f"<b>{display(reg.key(sid)) or '—'}</b>"

        keys = "<br>".join(f"{k('equip.' + t.code)} — {t.label} {t.name}" for t in EQUIPMENT_TYPES)
        eq = {t.code: display(reg.key("equip." + t.code)) for t in EQUIPMENT_TYPES}
        QMessageBox.information(self, "Qo'llanma", f"""
<h3>Ish tartibi</h3>
<ol>
<li>{k('floor.import')} — kadastr rasmini yuklang (skaner yoki telefon rasmi).
Telefon rasmi bo'lsa, ko'k nuqtalarni qog'oz burchaklariga moslang.</li>
<li>Dastur xonalar, koridorlar va <b>ko'k ruchka</b> belgilarini taxminiy topadi.
Topilgan belgilar <b>?</b> bo'lib turadi va <b>tasdiqlash ekrani</b> ochiladi ({k('review.open')}):
har bir belgining asl rasmi ko'rsatiladi, turini bitta tugma bilan bering, {k('edit.delete')} — belgi emas,
{k('review.next')} — keyinroq.
Qora ruchkadagi belgilarni asboblar panelidan qo'lda qo'ying.</li>
<li>Xonalarni tuzating: burchaklarni sudrang, qirrani ikki marta bosib burchak qo'shing,
{k('tool.split')} — xonani bo'lish, {k('edit.merge')} — birlashtirish, o'ng tugma — turi (koridor, zinapoya...).</li>
<li><b>Etaj → Masshtabni belgilash</b> — uzunligi ma'lum devorni belgilang (maydonlar m² da chiqadi).</li>
<li><b>Fayl → Eksport</b> — PNG/JPG, SVG, PDF yoki DXF.</li>
</ol>
<h3>Tugmalar</h3>
<i>Barcha tugmalarni o'zgartirish: Yordam → Klaviatura tugmalari ({k('app.shortcuts')})</i><br>
{keys}<br>
<i>Qog'ozda: Kam / X → {eq['K']} (Kamera), A.S → {eq['S']} (Switch), t → {eq['T']} (Tochka),
K.S → ikkita belgi ({eq['K']} va {eq['S']})</i><br>
{k('tool.select')} — tanlash, {k('tool.room_poly')} — xona (burchaklar), {k('tool.room_rect')} — to'rtburchak xona,
{k('tool.split')} — bo'lish<br>
{k('tool.wall')} — devor (burchaklarni bosing, Enter — tugatish). Qalinlik: o'ngdagi panelda yoki
{k('wall.thicker')} / {k('wall.thinner')},
{k('tool.door')} — eshik (devorga bosing; o'ng tugma: bir/ikki tabaqali, ochilish tomoni, kengligi),
{k('tool.stairs')} — zina (maydonini torting)<br>
{k('rotate.cw')} / {k('rotate.ccw')} — tanlanganni joyida 90° o'ngga / chapga aylantirish,
{k('rotate.custom')} — istalgan burchak<br>
{k('view.ortho')} — orto rejim, <b>Shift</b> — orto rejimni vaqtincha teskarisiga<br>
<b>G'ildirak</b> — kattalashtirish, <b>o'rta tugma / Probel+sudrash</b> — surish, {k('view.fit')} — butun chizma<br>
{k('edit.undo')} / {k('edit.redo')} — bekor qilish / qaytarish, <b>Esc</b> — chizishni bekor qilish
""")

    def closeEvent(self, event):
        if self.maybe_save():
            self.updater.shutdown()
            try:
                registry().listeners.remove(self._on_shortcut_changed)
            except ValueError:
                pass
            event.accept()
        else:
            event.ignore()
