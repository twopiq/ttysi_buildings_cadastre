"""Belgilarni tasdiqlash ekrani: qo'lyozma belgining asl rasmi va bir tugma bilan tur berish.

Dizayn maketidagi "Belgilarni tasdiqlash" ekrani asosida. Tugmalar (1-6, Del, N, Q)
klaviatura sozlamalaridan olinadi - foydalanuvchi ularni almashtirishi mumkin.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QRadioButton, QSizePolicy, QStackedWidget,
                               QVBoxLayout, QWidget)

from ..equipment import EQUIPMENT_TYPES
from ..render import draw_equipment_symbol, meter_px
from . import theme
from .shortcuts import display, registry

STYLE = f"""
QDialog {{ background: {theme.BG}; }}
QFrame#header {{ background: {theme.SURFACE}; border-bottom: 1px solid {theme.LINE}; }}
QLabel#title {{ font-size: 16px; font-weight: 600; }}
QLabel#question {{ font-size: 22px; font-weight: 700; }}
QLabel#muted {{ color: {theme.INK_2}; }}
QLabel#photo {{ background: {theme.PAPER}; border: 1px solid {theme.LINE}; border-radius: 12px; }}
QLabel#caption {{ color: white; background: rgba(23, 32, 43, 190); border-radius: 6px; padding: 3px 8px; }}
QPushButton#typeBtn {{
    min-height: 64px; border: 1px solid {theme.LINE}; border-radius: 12px; background: {theme.SURFACE};
    text-align: left; padding: 0 12px;
}}
QPushButton#typeBtn:hover {{ border: 2px solid {theme.PRIMARY}; background: {theme.PRIMARY_SOFT}; }}
QLabel#typeName {{ font-size: 15px; font-weight: 600; background: transparent; }}
QLabel#kbd {{
    font-size: 12px; color: {theme.INK_2}; border: 1px solid {theme.LINE_STRONG}; border-radius: 4px;
    padding: 1px 6px; background: transparent;
}}
QFrame#status {{ background: {theme.SURFACE}; border: 1px solid {theme.LINE}; border-radius: 12px; }}
QFrame#tip {{ background: {theme.PRIMARY_SOFT}; border-radius: 12px; }}
QFrame#tip QLabel {{ color: {theme.PRIMARY_DARK}; }}
QPushButton#danger {{ min-height: 40px; color: {theme.DANGER_FG}; border-color: {theme.DANGER_LINE}; }}
QPushButton#secondary {{ min-height: 40px; }}
QLabel#thumb {{ background: {theme.PAPER}; border: 1px solid {theme.LINE}; border-radius: 8px; }}
QLabel#thumbCurrent {{ background: {theme.PAPER}; border: 2px solid {theme.PRIMARY}; border-radius: 8px; }}
QLabel#done {{ font-size: 24px; font-weight: 700; color: {theme.OK_FG}; }}
"""


class TypeButton(QPushButton):
    """Katta tugma: jihoz belgisi, nomi va klaviatura tugmasi."""

    def __init__(self, code: str, name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("typeBtn")
        self.code = code
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(name)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(12)
        icon = QLabel()
        pm = QPixmap(36, 36)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        draw_equipment_symbol(p, code, QPointF(18, 18), 16)
        p.end()
        icon.setPixmap(pm)
        self.name = QLabel(name)
        self.name.setObjectName("typeName")
        self.kbd = QLabel()
        self.kbd.setObjectName("kbd")
        for w in (icon, self.name, self.kbd):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.name.setWordWrap(True)
        self.kbd.setFixedHeight(22)
        self.kbd.setMinimumWidth(22)
        self.kbd.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon)
        lay.addWidget(self.name, 1)
        lay.addWidget(self.kbd, 0, Qt.AlignVCenter)

    def set_key(self, text: str):
        self.kbd.setText(text)
        self.kbd.setVisible(bool(text))


class ReviewDialog(QDialog):
    """Tasdiqlanmagan ("?") belgilarni birma-bir ko'rib chiqish."""

    finished_all = Signal()

    PHOTO = QSize(600, 400)

    def __init__(self, window, parent=None):
        super().__init__(parent or window)
        self.w = window
        self.floor = window.floor
        self.bg: QImage | None = window.background_for(self.floor)
        self.setWindowTitle("Belgilarni tasdiqlash")
        self.setStyleSheet(STYLE)
        self.resize(1180, 760)
        self.queue = sorted([e for e in self.floor.equipment if e.code == "?"], key=lambda e: (e.y, e.x))
        self.total = len(self.queue)
        self.index = 0
        self.reviewed = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._review_page())
        self.pages.addWidget(self._done_page())
        root.addWidget(self.pages, 1)
        self.refresh_keys()
        registry().listeners.append(self._on_key_changed)
        self.show_current()

    # ------------------------------------------------------------ qurilish
    def _header(self) -> QFrame:
        f = QFrame()
        f.setObjectName("header")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(20, 10, 20, 10)
        back = QPushButton("‹  Chizmaga qaytish")
        back.setObjectName("secondary")
        back.clicked.connect(self.reject)
        title = QLabel(f"Belgilarni tasdiqlash · {self.floor.name}")
        title.setObjectName("title")
        self.progress_label = QLabel()
        self.progress_label.setObjectName("muted")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(220)
        self.progress.setAccessibleName("Tasdiqlangan belgilar")
        lay.addWidget(back)
        lay.addSpacing(12)
        lay.addWidget(title)
        lay.addStretch()
        lay.addWidget(self.progress_label)
        lay.addWidget(self.progress)
        return f

    def _review_page(self) -> QWidget:
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(24)

        left = QVBoxLayout()
        left.setSpacing(10)
        q = QLabel("Bu belgi qaysi jihoz?")
        q.setObjectName("question")
        self.where = QLabel()
        self.where.setObjectName("muted")
        head = QHBoxLayout()
        head.addWidget(q)
        head.addWidget(self.where)
        head.addStretch()
        left.addLayout(head)
        self.photo = QLabel()
        self.photo.setObjectName("photo")
        self.photo.setAlignment(Qt.AlignCenter)
        self.photo.setMinimumSize(self.PHOTO)
        self.photo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left.addWidget(self.photo, 1)
        self.caption = QLabel(self.photo)
        self.caption.setObjectName("caption")
        self.caption.move(12, 12)
        thumbs_row = QHBoxLayout()
        nxt = QLabel("Navbatdagilar:")
        nxt.setObjectName("muted")
        thumbs_row.addWidget(nxt)
        self.thumbs = [QLabel() for _ in range(6)]
        for t in self.thumbs:
            t.setFixedSize(56, 56)
            t.setAlignment(Qt.AlignCenter)
            thumbs_row.addWidget(t)
        thumbs_row.addStretch()
        left.addLayout(thumbs_row)
        lay.addLayout(left, 3)

        right = QVBoxLayout()
        right.setSpacing(12)
        grid = QGridLayout()
        grid.setSpacing(10)
        self.type_buttons: dict[str, TypeButton] = {}
        for i, t in enumerate(EQUIPMENT_TYPES):
            b = TypeButton(t.code, t.name)
            b.clicked.connect(lambda _=False, c=t.code: self.choose(c))
            grid.addWidget(b, i // 2, i % 2)
            self.type_buttons[t.code] = b
        right.addLayout(grid)

        st = QFrame()
        st.setObjectName("status")
        sl = QHBoxLayout(st)
        sl.setContentsMargins(14, 10, 14, 10)
        hl = QLabel("Holati:")
        hl.setObjectName("muted")
        self.r_exist = QRadioButton("Mavjud")
        self.r_plan = QRadioButton("Kerak (o'rnatilishi rejada)")
        self.r_exist.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.r_exist)
        grp.addButton(self.r_plan)
        sl.addWidget(hl)
        sl.addWidget(self.r_exist)
        sl.addWidget(self.r_plan)
        sl.addStretch()
        self.plan_key = QLabel()
        self.plan_key.setObjectName("kbd")
        sl.addWidget(self.plan_key)
        right.addWidget(st)

        row = QHBoxLayout()
        self.b_delete = QPushButton()
        self.b_delete.setObjectName("danger")
        self.b_delete.clicked.connect(self.delete_current)
        self.b_skip = QPushButton()
        self.b_skip.setObjectName("secondary")
        self.b_skip.clicked.connect(self.skip)
        row.addWidget(self.b_delete)
        row.addWidget(self.b_skip)
        right.addLayout(row)

        tip = QFrame()
        tip.setObjectName("tip")
        tl = QVBoxLayout(tip)
        tl.setContentsMargins(14, 10, 14, 10)
        t1 = QLabel("<b>Maslahat</b>")
        self.tip_text = QLabel()
        self.tip_text.setWordWrap(True)
        tl.addWidget(t1)
        tl.addWidget(self.tip_text)
        right.addWidget(tip)
        right.addStretch()
        rw = QWidget()
        rw.setLayout(right)
        rw.setMinimumWidth(400)
        rw.setMaximumWidth(480)
        lay.addWidget(rw, 2)
        return page

    def _done_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setAlignment(Qt.AlignCenter)
        self.done_title = QLabel("✓  Barcha belgilar tasdiqlandi")
        self.done_title.setObjectName("done")
        self.done_title.setAlignment(Qt.AlignCenter)
        self.done_text = QLabel()
        self.done_text.setObjectName("muted")
        self.done_text.setAlignment(Qt.AlignCenter)
        b = QPushButton("Chizmaga qaytish")
        b.setObjectName("primary")
        b.setMinimumHeight(44)
        b.clicked.connect(self.accept)
        lay.addWidget(self.done_title)
        lay.addWidget(self.done_text)
        lay.addSpacing(16)
        lay.addWidget(b, 0, Qt.AlignCenter)
        return page

    # ------------------------------------------------------------ tugmalar
    def refresh_keys(self):
        reg = registry()
        for code, b in self.type_buttons.items():
            b.set_key(display(reg.key(f"equip.{code}")))
        self.b_delete.setText(self._with_key("Belgi emas", "edit.delete"))
        self.b_skip.setText(self._with_key("O'tkazib yuborish", "review.next"))
        pk = display(reg.key("tool.plan_mode"))
        self.plan_key.setText(pk)
        self.plan_key.setVisible(bool(pk))
        self.tip_text.setText("\"Kam\", \"X\" → Kamera · \"A.S\" → Switch · \"t\" → Tochka · "
                              "\"K.S\" — ikkita belgi: birini tasdiqlang, ikkinchisini chizmada qo'shing.")

    @staticmethod
    def _with_key(text: str, sid: str) -> str:
        k = display(registry().key(sid))
        return f"{text}   {k}" if k else text

    def _on_key_changed(self, sid, seq):
        self.refresh_keys()

    def keyPressEvent(self, event):
        reg = registry()
        if self.pages.currentIndex() == 0:
            for t in EQUIPMENT_TYPES:
                if reg.matches(f"equip.{t.code}", event):
                    self.choose(t.code)
                    return
            if reg.matches("edit.delete", event):
                self.delete_current()
                return
            if reg.matches("review.next", event):
                self.skip()
                return
            if reg.matches("tool.plan_mode", event):
                (self.r_exist if self.r_plan.isChecked() else self.r_plan).setChecked(True)
                return
        super().keyPressEvent(event)

    def done_event(self):
        try:
            registry().listeners.remove(self._on_key_changed)
        except ValueError:
            pass

    def accept(self):
        self.done_event()
        super().accept()

    def reject(self):
        self.done_event()
        super().reject()

    # ------------------------------------------------------------ ko'rsatish
    def current(self):
        return self.queue[self.index] if 0 <= self.index < len(self.queue) else None

    def show_current(self):
        self.progress.setMaximum(max(1, self.total))
        self.progress.setValue(self.reviewed)
        self.progress_label.setText(f"{self.reviewed} / {self.total} belgi")
        eq = self.current()
        if eq is None:
            self.done_text.setText(f"{self.total} ta belgi ko'rib chiqildi. Natijani chizmada tekshiring.")
            self.pages.setCurrentIndex(1)
            self.finished_all.emit()
            return
        self.pages.setCurrentIndex(0)
        room = self.floor.room_of(eq)
        if room is None:
            self.where.setText("xonadan tashqarida")
        else:
            self.where.setText(f"{room.name}-xona ichida" if room.name else "xona ichida")
        pm, zoom = self.crop(eq, self.photo.size() if self.photo.width() > 50 else self.PHOTO, ring=True)
        self.photo.setPixmap(pm)
        self.caption.setText(f"Asl rasm · {zoom:.0f}× kattalashtirilgan" if self.bg else "Kadastr rasmi yo'q")
        self.caption.adjustSize()
        upcoming = self.queue[self.index:self.index + len(self.thumbs)]
        for i, t in enumerate(self.thumbs):
            if i < len(upcoming):
                t.setPixmap(self.crop(upcoming[i], QSize(52, 52))[0])
                t.setObjectName("thumbCurrent" if i == 0 else "thumb")
                t.setStyle(t.style())
                t.show()
            else:
                t.hide()

    def crop(self, eq, size: QSize, ring: bool = False) -> tuple[QPixmap, float]:
        """Belgi atrofidagi asl rasm bo'lagi (taxminan 5 m)."""
        pm = QPixmap(size)
        pm.fill(QColor(theme.PAPER))
        if self.bg is None or self.bg.isNull():
            p = QPainter(pm)
            p.setPen(QColor(theme.INK_2))
            p.drawText(pm.rect(), Qt.AlignCenter, "?")
            p.end()
            return pm, 1.0
        k = self.bg.width() / max(1, self.floor.width)          # etaj -> rasm piksellari
        half = max(meter_px(self.floor) * 2.5, 60) * k
        aspect = size.width() / max(1, size.height())
        rect = QRectF(eq.x * k - half * aspect, eq.y * k - half, 2 * half * aspect, 2 * half)
        part = self.bg.copy(rect.toAlignedRect())
        scaled = part.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        zoom = scaled.width() / max(1, part.width())
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        ox, oy = (size.width() - scaled.width()) / 2, (size.height() - scaled.height()) / 2
        p.drawImage(QPointF(ox, oy), scaled)
        if ring:
            r = min(scaled.width(), scaled.height()) * 0.2
            pen = QPen(QColor(theme.DANGER_FG), 3, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(size.width() / 2, size.height() / 2), r, r)
        p.end()
        return pm, max(1.0, zoom)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.pages.currentIndex() == 0 and self.current() is not None:
            pm, _ = self.crop(self.current(), self.photo.size(), ring=True)
            self.photo.setPixmap(pm)

    # ------------------------------------------------------------ amallar
    def _item_for(self, eq):
        for it in self.w.scene.equipment_items():
            if it.eq is eq:
                return it
        return None

    def choose(self, code: str):
        eq = self.current()
        if eq is None:
            return
        status = "planned" if self.r_plan.isChecked() else "existing"
        it = self._item_for(eq)
        if it is not None:
            it.set_code(code)
            it.set_status(status)
        else:
            eq.code, eq.status = code, status
        self.w.scene.changed_model.emit()
        self.queue.pop(self.index)
        self.reviewed += 1
        self._after_change()

    def delete_current(self):
        eq = self.current()
        if eq is None:
            return
        it = self._item_for(eq)
        if eq in self.floor.equipment:
            self.floor.equipment.remove(eq)
        if it is not None:
            self.w.scene.removeItem(it)
        self.w.scene.changed_model.emit()
        self.queue.pop(self.index)
        self.reviewed += 1
        self._after_change()

    def skip(self):
        if self.current() is None:
            return
        if len(self.queue) > 1:
            self.queue.append(self.queue.pop(self.index))   # navbat oxiriga
        self._after_change()

    def _after_change(self):
        if self.index >= len(self.queue):
            self.index = 0
        self.r_exist.setChecked(True)
        self.show_current()
