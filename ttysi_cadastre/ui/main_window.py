"""Asosiy oyna."""

from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QSettings, Qt, QTimer
from PySide6.QtPdf import QPdfDocument
from PySide6.QtGui import QAction, QActionGroup, QIcon, QImage, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDockWidget, QFileDialog, QFormLayout, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QPushButton, QSlider, QStackedWidget, QToolBar,
                               QVBoxLayout, QWidget)

from .. import __version__
from ..detection import DetectParams, decode_image, detect, encode_jpg, limit_size, read_image
from ..equipment import BY_KEY, EQUIPMENT_TYPES, ROOM_KINDS, UNKNOWN
from ..export import export_dxf, export_image, export_pdf, export_svg
from ..geometry import merge_rooms, split_room
from ..model import Building, Equipment, Floor, Room
from ..render import RenderOptions, draw_equipment_symbol, equipment_counts, wall_width
from ..report import export_excel
from ..updater import is_frozen
from .canvas import (DOOR, EQUIP, ROOM_POLY, ROOM_RECT, SCALE, SELECT, SPLIT, STAIRS, EquipmentItem,
                     FloorScene, FloorView, RoomItem)
from .import_dialog import ImportDialog, PdfPageDialog, RedetectDialog, image_paper_mm_per_px
from .update_dialog import Updater, UpdateSettingsDialog, load_settings

FILE_FILTER = "TTYSI kadastr loyihasi (*.ttysi)"
IMAGE_FILTER = "Kadastr hujjati (*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff)"


def type_icon(code: str) -> QIcon:
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    draw_equipment_symbol(p, code, QPointF(16, 16), 13)
    p.end()
    return QIcon(pm)


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


class ExportOptionsDialog(QDialog):
    def __init__(self, parent, raster: bool):
        super().__init__(parent)
        self.setWindowTitle("Eksport sozlamalari")
        lay = QVBoxLayout(self)
        self.bg = QCheckBox("Kadastr rasmini fon sifatida qo'shish")
        self.names = QCheckBox("Xona nomlari va maydonlari")
        self.names.setChecked(True)
        self.legend = QCheckBox("Shartli belgilar jadvali")
        self.legend.setChecked(True)
        self.title = QCheckBox("Sarlavha (bino va etaj nomi)")
        self.title.setChecked(True)
        for w in (self.bg, self.names, self.legend, self.title):
            lay.addWidget(w)
        self.size = QComboBox()
        if raster:
            for s in (2000, 4000, 6000):
                self.size.addItem(f"{s} piksel", s)
            self.size.setCurrentIndex(1)
            row = QFormLayout()
            row.addRow("O'lcham:", self.size)
            lay.addLayout(row)
        b = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        b.accepted.connect(self.accept)
        b.rejected.connect(self.reject)
        lay.addWidget(b)

    def options(self) -> RenderOptions:
        return RenderOptions(background=self.bg.isChecked(), room_names=self.names.isChecked(),
                             legend=self.legend.isChecked(), title=self.title.isChecked())


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
        self.setCentralWidget(self.view)
        self.scene.changed_model.connect(self.on_model_changed)
        self.scene.selectionChanged.connect(self.on_selection)
        self.scene.request_merge.connect(self.merge_selected)
        self.view.status.connect(lambda t: self.statusBar().showMessage(t))
        self.view.split_requested.connect(self.split_room)
        self.view.scale_requested.connect(self.set_scale)
        self.view.digit_pressed = self.on_digit

        self.updater = Updater(self)
        self.build_actions()
        self.build_floor_dock()
        self.build_props_dock()
        self.resize(1400, 900)
        self.refresh_all()
        self.select_tool(SELECT)
        # o'rnatilgan dasturda: ochilgandan keyin fonda yangilanishni tekshirish
        if is_frozen() and load_settings()["auto"]:
            QTimer.singleShot(4000, lambda: self.updater.check(silent=True))

    # ================================================================ UI qurish
    def build_actions(self):
        mb = self.menuBar()
        m = mb.addMenu("&Fayl")
        self._act(m, "Yangi loyiha", self.new_project, QKeySequence.New)
        self._act(m, "Ochish...", self.open_project, QKeySequence.Open)
        self._act(m, "Saqlash", self.save_project, QKeySequence.Save)
        self._act(m, "Boshqa nom bilan saqlash...", self.save_project_as, QKeySequence("Ctrl+Shift+S"))
        m.addSeparator()
        ex = m.addMenu("Eksport")
        self._act(ex, "Rasm (PNG / JPG)...", lambda: self.export("image"), QKeySequence("Ctrl+E"))
        self._act(ex, "Vektor rasm (SVG)...", lambda: self.export("svg"))
        self._act(ex, "PDF - joriy etaj...", lambda: self.export("pdf"))
        self._act(ex, "PDF - barcha etajlar...", lambda: self.export("pdf_all"))
        self._act(ex, "AutoCAD chizma (DXF)...", lambda: self.export("dxf"))
        ex.addSeparator()
        self._act(ex, "Excel hisobot - joriy bino...", self.export_excel_current, QKeySequence("Ctrl+R"))
        self._act(ex, "Excel hisobot - bir nechta bino...", self.export_excel_many)
        m.addSeparator()
        self._act(m, "Chiqish", self.close, QKeySequence.Quit)

        m = mb.addMenu("&Tahrir")
        self.a_undo = self._act(m, "Bekor qilish", self.undo, QKeySequence.Undo)
        self.a_redo = self._act(m, "Qaytarish", self.redo, QKeySequence("Ctrl+Y"))
        self._act(m, "", self.redo, QKeySequence("Ctrl+Shift+Z")).setVisible(False)
        m.addSeparator()
        self._act(m, "O'chirish", self.scene.delete_selected, QKeySequence.Delete)
        self._act(m, "Hammasini tanlash", self.select_all, QKeySequence.SelectAll)
        self._act(m, "Jihoz holatini almashtirish (mavjud / kerak)", self.toggle_status, QKeySequence("Ctrl+K"))
        self._act(m, "Tanlangan xonalarni birlashtirish", self.merge_selected, QKeySequence("Ctrl+M"))
        self._act(m, "Keyingi tasdiqlanmagan belgi", self.select_next_unknown, QKeySequence("N"))

        m = mb.addMenu("&Etaj")
        self._act(m, "PDF / rasmdan yangi etaj qo'shish...", self.add_floor_from_image, QKeySequence("Ctrl+I"))
        self._act(m, "Bo'sh etaj qo'shish", self.add_empty_floor)
        self._act(m, "Qayta avtomatik chizish...", self.redetect)
        self._act(m, "Masshtabni belgilash", lambda: self.select_tool(SCALE))
        self._act(m, "Xonalarni qayta raqamlash...", self.renumber_rooms)
        self._act(m, "Etaj nomini o'zgartirish...", self.rename_floor, QKeySequence("F2"))
        self._act(m, "Etajni o'chirish", self.delete_floor)

        m = mb.addMenu("&Ko'rinish")
        self._act(m, "Butun chizmani ko'rsatish", self.view.zoom_fit, QKeySequence("Ctrl+0"))
        self.a_ortho = self._act(m, "Orto rejim (faqat gorizontal/vertikal)", self.toggle_ortho, QKeySequence("F8"))
        self.a_ortho.setCheckable(True)
        self.a_ortho.setChecked(True)

        m = mb.addMenu("&Yordam")
        self._act(m, "Qo'llanma", self.show_help, QKeySequence.HelpContents)
        m.addSeparator()
        self._act(m, "Yangilanishni tekshirish...", lambda: self.updater.check(silent=False))
        self._act(m, "Yangilanish sozlamalari...", lambda: UpdateSettingsDialog(self).exec())
        self._act(m, "Dastur haqida", lambda: QMessageBox.about(
            self, "Dastur haqida",
            f"TTYSI Binolar kadastri — AT jihozlari xaritasi\nVersiya {__version__}"))

        tb = QToolBar("Asboblar")
        tb.setObjectName("tools")
        tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.addToolBar(Qt.LeftToolBarArea, tb)
        self.tool_group = QActionGroup(self)
        self.tool_actions = {}

        def tool(text, key, tool_id, code=None, tip=""):
            a = QAction(text, self)
            a.setCheckable(True)
            if key:
                a.setShortcut(QKeySequence(key))
            a.setToolTip(f"{tip or text} ({key})" if key else (tip or text))
            if code:
                a.setIcon(type_icon(code))
            a.triggered.connect(lambda: self.select_tool(tool_id, code))
            self.tool_group.addAction(a)
            tb.addAction(a)
            self.tool_actions[(tool_id, code)] = a
            return a

        tool("Tanlash", "V", SELECT)
        tool("Xona\n(burchak)", "P", ROOM_POLY, tip="Xona/koridorni burchaklari bo'yicha chizish")
        tool("Xona\n(to'rtburchak)", "R", ROOM_RECT)
        tool("Xonani\nbo'lish", "B", SPLIT)
        tool("Eshik", "D", DOOR, tip="Eshik qo'yish: devorga bosing")
        tool("Zina", "Z", STAIRS, tip="Zinapoya chizish: maydonini torting")
        tb.addSeparator()
        for t in EQUIPMENT_TYPES:
            tool(t.label, None, EQUIP, t.code, tip=f"{t.name} qo'yish (tanlangan belgining turi: {t.key})")
        tb.addSeparator()
        self.a_plan_mode = QAction("Kerak\n(reja)", self)
        self.a_plan_mode.setCheckable(True)
        self.a_plan_mode.setShortcut(QKeySequence("Q"))
        self.a_plan_mode.setToolTip("Yoqilsa, yangi qo'yilgan jihozlar \"kerak (o'rnatilishi rejada)\" bo'ladi (Q)")
        self.a_plan_mode.toggled.connect(lambda on: setattr(self.view, "place_planned", on))
        tb.addAction(self.a_plan_mode)

    def _act(self, menu, text, slot, shortcut=None):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(shortcut)
        a.triggered.connect(slot)
        menu.addAction(a)
        self.addAction(a)
        return a

    def build_floor_dock(self):
        dock = QDockWidget("Bino va etajlar", self)
        dock.setObjectName("floors")
        w = QWidget()
        lay = QVBoxLayout(w)
        form = QFormLayout()
        self.e_name = QLineEdit()
        self.e_name.editingFinished.connect(self.on_building_info)
        self.e_addr = QLineEdit()
        self.e_addr.editingFinished.connect(self.on_building_info)
        form.addRow("Bino:", self.e_name)
        form.addRow("Manzil:", self.e_addr)
        lay.addLayout(form)
        lay.addWidget(QLabel("Etajlar:"))
        self.floor_list = QListWidget()
        self.floor_list.currentRowChanged.connect(self.on_floor_selected)
        lay.addWidget(self.floor_list, 1)
        b = QPushButton("+ PDF / rasmdan etaj qo'shish")
        b.clicked.connect(self.add_floor_from_image)
        lay.addWidget(b)
        row = QHBoxLayout()
        for text, slot in (("▲", lambda: self.move_floor(-1)), ("▼", lambda: self.move_floor(1)),
                           ("Nomi", self.rename_floor), ("O'chirish", self.delete_floor)):
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        lay.addLayout(row)
        dock.setWidget(w)
        dock.setMaximumWidth(300)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def build_props_dock(self):
        dock = QDockWidget("Xususiyatlar", self)
        dock.setObjectName("props")
        w = QWidget()
        lay = QVBoxLayout(w)

        self.props = QStackedWidget()
        # 0 - hech narsa
        none = QLabel("Element tanlanmagan.\n\nXona yoki belgini bosing.")
        none.setAlignment(Qt.AlignTop)
        none.setWordWrap(True)
        self.props.addWidget(none)
        # 1 - xona
        rw = QWidget()
        rf = QFormLayout(rw)
        self.p_room_name = QLineEdit()
        self.p_room_name.setPlaceholderText("masalan: 105 yoki Kabinet")
        self.p_room_name.editingFinished.connect(self.on_room_props)
        self.p_room_kind = QComboBox()
        for k, (name, _) in ROOM_KINDS.items():
            self.p_room_kind.addItem(name, k)
        self.p_room_kind.activated.connect(self.on_room_props)
        self.p_room_area = QLabel()
        rf.addRow("Nomi / raqami:", self.p_room_name)
        rf.addRow("Turi:", self.p_room_kind)
        rf.addRow("Maydoni:", self.p_room_area)
        self.props.addWidget(rw)
        # 2 - AT jihozi
        ew = QWidget()
        ef = QFormLayout(ew)
        self.p_eq_type = QComboBox()
        for t in EQUIPMENT_TYPES + [UNKNOWN]:
            self.p_eq_type.addItem(type_icon(t.code), f"{t.name} ({t.key})" if t.code != "?" else t.name, t.code)
        self.p_eq_type.activated.connect(self.on_eq_props)
        self.p_eq_note = QLineEdit()
        self.p_eq_note.setPlaceholderText("masalan: Hikvision, 2-port")
        self.p_eq_note.editingFinished.connect(self.on_eq_props)
        self.p_eq_status = QComboBox()
        self.p_eq_status.addItem("Mavjud", "existing")
        self.p_eq_status.addItem("Kerak (o'rnatilishi rejada)", "planned")
        self.p_eq_status.activated.connect(self.on_eq_props)
        ef.addRow("Turi:", self.p_eq_type)
        ef.addRow("Holati:", self.p_eq_status)
        ef.addRow("Izoh:", self.p_eq_note)
        self.props.addWidget(ew)
        # 3 - bir nechta
        self.p_multi = QLabel()
        self.p_multi.setAlignment(Qt.AlignTop)
        self.p_multi.setWordWrap(True)
        self.props.addWidget(self.p_multi)
        lay.addWidget(self.props)

        lay.addWidget(QLabel("<b>Fon (kadastr rasmi)</b>"))
        self.bg_slider = QSlider(Qt.Horizontal)
        self.bg_slider.setRange(0, 100)
        self.bg_slider.setValue(60)
        self.bg_slider.valueChanged.connect(lambda v: self.scene.set_bg_opacity(v / 100))
        lay.addWidget(self.bg_slider)

        lay.addWidget(QLabel("<b>Etaj statistikasi</b>"))
        self.stats = QLabel()
        self.stats.setWordWrap(True)
        self.stats.setTextFormat(Qt.RichText)
        lay.addWidget(self.stats)
        lay.addStretch()
        dock.setWidget(w)
        dock.setMinimumWidth(270)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    # ================================================================ holat
    def set_dirty(self, d=True):
        self.dirty = d
        name = os.path.basename(self.path) if self.path else "Nomsiz"
        self.setWindowTitle(f"{'*' if d else ''}{name} — TTYSI Binolar kadastri")

    def refresh_all(self):
        self.e_name.setText(self.building.name)
        self.e_addr.setText(self.building.address)
        self.refresh_floor_list()
        if self.building.floors:
            self.floor_list.setCurrentRow(0)
        else:
            self.show_floor(None)
        self.set_dirty(False)

    def refresh_floor_list(self, select: int | None = None):
        self.floor_list.blockSignals(True)
        self.floor_list.clear()
        for f in self.building.floors:
            unknown = sum(1 for e in f.equipment if e.code == "?")
            text = f.name + (f"   ⚠ {unknown}" if unknown else "")
            item = QListWidgetItem(text)
            if unknown:
                item.setToolTip(f"{unknown} ta belgining turi tasdiqlanmagan")
            self.floor_list.addItem(item)
        self.floor_list.blockSignals(False)
        if select is not None:
            self.floor_list.setCurrentRow(select)
        elif self.floor in self.building.floors:
            self.floor_list.blockSignals(True)
            self.floor_list.setCurrentRow(self.building.floors.index(self.floor))
            self.floor_list.blockSignals(False)

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
        if f is None:
            self.stats.setText("Etaj yo'q. Chapdagi \"+ PDF / rasmdan etaj qo'shish\" tugmasini bosing.")
            return
        counts = equipment_counts(f)
        need = equipment_counts(f, planned=True)
        lines = []
        for t in EQUIPMENT_TYPES:
            extra = f" <span style='color:#c62828'>(+{need[t.code]} kerak)</span>" if need.get(t.code) else ""
            lines.append(f"<span style='color:{t.color}'>■</span> {t.name}: <b>{counts.get(t.code, 0)}</b>{extra}")
        if counts.get("?"):
            lines.append(f"<span style='color:#c62828'>⚠ Tasdiqlanmagan: <b>{counts['?']}</b> "
                         f"(N - keyingisi, 1-6 - turi)</span>")
        rooms = {}
        for r in f.rooms:
            rooms[r.kind] = rooms.get(r.kind, 0) + 1
        lines.append("")
        lines += [f"{ROOM_KINDS[k][0]}: <b>{n}</b>" for k, n in rooms.items()]
        if f.doors:
            lines.append(f"Eshiklar: <b>{len(f.doors)}</b>")
        if f.scale_m_per_px:
            total = sum(r.area() for r in f.rooms) * f.scale_m_per_px ** 2
            lines.append(f"Umumiy maydon: <b>{total:.1f} m²</b>")
        else:
            lines.append("<i>Masshtab belgilanmagan</i>")
        self.stats.setText("<br>".join(lines))

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
        if len(sel) == 1 and rooms:
            r = rooms[0].room
            self.p_room_name.setText(r.name)
            self.p_room_kind.setCurrentIndex(self.p_room_kind.findData(r.kind))
            if self.floor and self.floor.scale_m_per_px:
                self.p_room_area.setText(f"{r.area() * self.floor.scale_m_per_px ** 2:.1f} m²")
            else:
                self.p_room_area.setText("masshtab yo'q")
            self.props.setCurrentIndex(1)
        elif len(sel) == 1 and eqs:
            e = eqs[0].eq
            self.p_eq_type.setCurrentIndex(self.p_eq_type.findData(e.code))
            self.p_eq_note.setText(e.note)
            self.p_eq_status.setCurrentIndex(self.p_eq_status.findData(e.status))
            self.props.setCurrentIndex(2)
        elif sel:
            self.p_multi.setText(f"Tanlangan: {len(rooms)} ta xona, {len(eqs)} ta belgi.\n\n"
                                 "1-6 tugmalari - belgilar turini o'zgartirish.\n"
                                 "Ctrl+M - xonalarni birlashtirish.\nDel - o'chirish.")
            self.props.setCurrentIndex(3)
        else:
            self.props.setCurrentIndex(0)

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
        """1-6: tanlangan belgilar turini o'rnatish yoki shu turdagi belgini qo'yish asbobi."""
        t = BY_KEY.get(key)
        if t is None:
            return False
        eqs = self.scene.selected_equipment()
        if eqs:
            was_unknown = len(eqs) == 1 and eqs[0].eq.code == "?"
            for it in eqs:
                it.set_code(t.code)
            self.scene.changed_model.emit()
            if was_unknown:
                self.select_next_unknown()
        else:
            self.select_tool(EQUIP, t.code)
        return True

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
        self.statusBar().showMessage(f"Tasdiqlanmagan belgi ({len(items)} ta qoldi): turini 1-6 bilan tanlang, "
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
    def on_building_info(self):
        name, addr = self.e_name.text().strip(), self.e_addr.text().strip()
        if (name, addr) != (self.building.name, self.building.address):
            self.building.name, self.building.address = name, addr
            self.set_dirty()

    def on_floor_selected(self, row):
        if 0 <= row < len(self.building.floors):
            self.view.cancel_drawing()
            self.show_floor(self.building.floors[row])

    def next_floor_name(self):
        return f"{len(self.building.floors) + 1}-etaj"

    def add_floor_from_image(self):
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
        self.import_floor(img, image_paper_mm_per_px(path), from_pdf=False)

    def add_floors_from_pdf(self, path: str):
        """PDF: sahifa tanlanadi, undan etaj kesib olinadi; bir nechta etajni ketma-ket qo'shish mumkin."""
        doc = QPdfDocument(self)
        if doc.load(path) != QPdfDocument.Error.None_ or doc.pageCount() == 0:
            QMessageBox.critical(self, "Xato", "PDF faylni ochib bo'lmadi.")
            return
        page = 0
        while True:
            pd = PdfPageDialog(doc, self, current=page)
            if pd.exec() != QDialog.Accepted:
                break
            page = pd.page()
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                img, mm_per_px = pd.render()
            finally:
                QApplication.restoreOverrideCursor()
            self.import_floor(img, mm_per_px, from_pdf=True)
        doc.close()

    def import_floor(self, img, paper_mm_per_px, from_pdf: bool) -> bool:
        dlg = ImportDialog(img, self.next_floor_name(), self, paper_mm_per_px=paper_mm_per_px, from_pdf=from_pdf)
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
        self.statusBar().showMessage(msg, 10000)
        if any(e.code == "?" for e in floor.equipment):
            QTimer.singleShot(300, self.select_next_unknown)
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
            self.floor_list.setCurrentRow(min(i, len(self.building.floors) - 1))
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

    def export(self, kind: str):
        if self.floor is None:
            QMessageBox.information(self, "Eksport", "Avval etaj qo'shing.")
            return
        unknown = sum(1 for f in self.building.floors for e in f.equipment if e.code == "?")
        if unknown and QMessageBox.question(
                self, "Tasdiqlanmagan belgilar",
                f"{unknown} ta belgining turi hali tasdiqlanmagan ('?' bo'lib chiqadi). Davom etilsinmi?"
        ) != QMessageBox.Yes:
            return
        opts = RenderOptions()
        size = 4000
        if kind != "dxf":
            dlg = ExportOptionsDialog(self, raster=(kind == "image"))
            if dlg.exec() != QDialog.Accepted:
                return
            opts = dlg.options()
            size = dlg.size.currentData() or 4000
        base = f"{self.building.name} - {self.floor.name}" if kind != "pdf_all" else self.building.name
        base = "".join(c for c in base if c not in '\\/:*?"<>|')
        filters = {
            "image": "PNG rasm (*.png);;JPG rasm (*.jpg)",
            "svg": "SVG (*.svg)",
            "pdf": "PDF (*.pdf)",
            "pdf_all": "PDF (*.pdf)",
            "dxf": "AutoCAD DXF (*.dxf)",
        }
        ext = {"image": ".png", "svg": ".svg", "pdf": ".pdf", "pdf_all": ".pdf", "dxf": ".dxf"}[kind]
        default = os.path.join(self.settings.value("export_dir", self.settings.value("last_dir", "")), base + ext)
        path, flt = QFileDialog.getSaveFileName(self, "Eksport", default, filters[kind])
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".jpg" if "jpg" in flt else ext
        self.settings.setValue("export_dir", os.path.dirname(path))
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if kind == "image":
                export_image(path, self.building, self.floor, opts, size)
            elif kind == "svg":
                export_svg(path, self.building, self.floor, opts)
            elif kind == "pdf":
                export_pdf(path, self.building, [self.floor], opts)
            elif kind == "pdf_all":
                export_pdf(path, self.building, self.building.floors, opts)
            elif kind == "dxf":
                export_dxf(path, self.building, self.floor)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Eksport xatosi", str(e))
            return
        QApplication.restoreOverrideCursor()
        msg = f"Eksport qilindi: {path}"
        if kind == "dxf" and not self.floor.scale_m_per_px:
            msg += "  (masshtab belgilanmagan - DXF piksellarda)"
        self.statusBar().showMessage(msg, 10000)

    def show_help(self):
        keys = "<br>".join(f"<b>{t.key}</b> — {t.label} {t.name}" for t in EQUIPMENT_TYPES)
        QMessageBox.information(self, "Qo'llanma", f"""
<h3>Ish tartibi</h3>
<ol>
<li><b>Ctrl+I</b> — kadastr rasmini yuklang (skaner yoki telefon rasmi).
Telefon rasmi bo'lsa, qizil nuqtalarni qog'oz burchaklariga moslang.</li>
<li>Dastur xonalar, koridorlar va <b>ko'k ruchka</b> belgilarini taxminiy topadi.
Topilgan belgilar <b>?</b> bo'lib turadi.</li>
<li><b>N</b> — keyingi '?' belgiga o'tish, <b>1-6</b> — turini berish, <b>Del</b> — noto'g'ri bo'lsa o'chirish.
Qora ruchkadagi belgilarni asboblar panelidan qo'lda qo'ying.</li>
<li>Xonalarni tuzating: burchaklarni sudrang, qirrani ikki marta bosib burchak qo'shing,
<b>B</b> — xonani bo'lish, <b>Ctrl+M</b> — birlashtirish, o'ng tugma — turi (koridor, zinapoya...).</li>
<li><b>Etaj → Masshtabni belgilash</b> — uzunligi ma'lum devorni belgilang (maydonlar m² da chiqadi).</li>
<li><b>Fayl → Eksport</b> — PNG/JPG, SVG, PDF yoki DXF.</li>
</ol>
<h3>Tugmalar</h3>
{keys}<br>
<i>Qog'ozda: Kam / X → 3 (Kamera), A.S → 5 (Switch), t → 6 (Tochka), K.S → ikkita belgi (3 va 5)</i><br>
<b>V</b> — tanlash, <b>P</b> — xona (burchaklar), <b>R</b> — to'rtburchak xona, <b>B</b> — bo'lish<br>
<b>D</b> — eshik (devorga bosing; o'ng tugma: bir/ikki tabaqali, ochilish tomoni, kengligi),
<b>Z</b> — zina (maydonini torting)<br>
<b>F8</b> — orto rejim, <b>Shift</b> — orto rejimni vaqtincha teskarisiga<br>
<b>G'ildirak</b> — kattalashtirish, <b>o'rta tugma / Probel+sudrash</b> — surish, <b>Ctrl+0</b> — butun chizma<br>
<b>Ctrl+Z / Ctrl+Y</b> — bekor qilish / qaytarish, <b>Esc</b> — chizishni bekor qilish
""")

    def closeEvent(self, event):
        if self.maybe_save():
            self.updater.shutdown()
            event.accept()
        else:
            event.ignore()
