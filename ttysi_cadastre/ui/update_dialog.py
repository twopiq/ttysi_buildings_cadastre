"""Yangilanish: fonda tekshirish va yuklash, oyna tepasidagi xabar paneli, bitta yangilanish oynasi.

Oddiy ish tartibi:
  * dastur ochilganda (va har 6 soatda) fonda tekshiriladi;
  * kichik kod yangilanishi so'ramasdan fonda yuklanadi - tepada "Versiya X tayyor. [Qayta ochish]"
    paneli chiqadi (qayta ochilmasa ham, keyingi ishga tushishda o'zi kuchga kiradi);
  * to'liq paket kerak bo'lsa (kutubxonalar o'zgargan) - panel "Yuklab o'rnatish" tugmasi bilan chiqadi;
  * yangilangandan keyin birinchi ochilishda "Nima yangi" oynasi ko'rsatiladi.
"""

from __future__ import annotations

import sys
import time

from PySide6.QtCore import QObject, QProcess, QSettings, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QProgressBar, QPushButton, QRadioButton, QTextBrowser, QToolButton,
                               QVBoxLayout, QWidget)

from .. import __version__, updater
from . import theme

SETTINGS_KEY = "update"
PERIOD_MS = 6 * 3600 * 1000


def load_settings() -> dict:
    s = QSettings("TTYSI", "BinolarKadastr")
    return {
        "kind": s.value(f"{SETTINGS_KEY}/kind", "github"),
        "folder": s.value(f"{SETTINGS_KEY}/folder", ""),
        "repo": s.value(f"{SETTINGS_KEY}/repo", updater.DEFAULT_REPO),
        "token": s.value(f"{SETTINGS_KEY}/token", ""),
        "auto": s.value(f"{SETTINGS_KEY}/auto", True, type=bool),
    }


def save_settings(d: dict) -> None:
    s = QSettings("TTYSI", "BinolarKadastr")
    for k, v in d.items():
        s.setValue(f"{SETTINGS_KEY}/{k}", v)


def notes_html(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return "<p>Xatolar tuzatildi va ish barqarorligi yaxshilandi.</p>"
    out, items = [], []
    for ln in lines:
        if ln.startswith(("-", "*", "•")):
            items.append(f"<li>{ln.lstrip('-*• ').strip()}</li>")
        else:
            if items:
                out.append("<ul>" + "".join(items) + "</ul>")
                items = []
            out.append(f"<p>{ln}</p>")
    if items:
        out.append("<ul>" + "".join(items) + "</ul>")
    return "".join(out)


# ======================================================================== fon oqimi

class _Worker(QObject):
    """Tarmoq ishlarini fonda bajaradi (oyna qotib qolmasligi uchun)."""

    finished = Signal(object, object)   # natija, xato
    progress = Signal(int, int)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    def run(self):
        try:
            res = self.fn(lambda done, total: self.progress.emit(done, total))
            self.finished.emit(res, None)
        except Exception as e:  # tarmoq/fayl xatolari foydalanuvchiga ko'rsatiladi
            self.finished.emit(None, e)


class _Relay(QObject):
    """Asosiy oqimda yashaydi: fon oqimidagi signallar navbat orqali shu yerga keladi."""

    def __init__(self, on_done, on_progress, parent=None):
        super().__init__(parent)
        self.on_done = on_done
        self.on_progress = on_progress

    @Slot(object, object)
    def done(self, res, err):
        self.on_done(res, err)

    @Slot(int, int)
    def progress(self, done, total):
        if self.on_progress:
            self.on_progress(done, total)


def run_in_thread(owner, fn, on_done, on_progress=None):
    """fn(progress) ni fon oqimida bajaradi; on_done/on_progress asosiy (GUI) oqimida chaqiriladi."""
    thread = QThread(owner)
    worker = _Worker(fn)
    relay = _Relay(on_done, on_progress, owner)
    worker.moveToThread(thread)
    thread._keep = (worker, relay)   # Python havolalari - ish tugaguncha o'chib ketmasin
    thread.started.connect(worker.run)
    worker.finished.connect(relay.done)
    worker.progress.connect(relay.progress)
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.finished.connect(relay.deleteLater)
    if hasattr(owner, "threads"):
        owner.threads.append(thread)
        thread.finished.connect(lambda: owner.threads.remove(thread) if thread in owner.threads else None)
    thread.start()
    return thread


# ======================================================================== holat mashinasi

class Updater(QObject):
    """Yangilanish holati: idle, checking, latest, available, downloading, ready, error.

    available - yangi versiya bor, foydalanuvchi tasdig'i kerak (to'liq paket yoki manba koddan ishlash);
    ready     - kod yangilanishi yuklangan, qayta ochilganda kuchga kiradi.
    """

    changed = Signal()

    def __init__(self, window):
        super().__init__(window)
        self.w = window
        self.state = "idle"
        self.info: updater.UpdateInfo | None = None
        self.full = False
        self.error = ""
        self.done_bytes = 0
        self.total_bytes = 0
        self.threads: list[QThread] = []
        self.timer = QTimer(self)
        self.timer.setInterval(PERIOD_MS)
        self.timer.timeout.connect(lambda: self.check(silent=True))

    def start_auto(self):
        """Dastur ochilgandan keyin (va har 6 soatda) fonda tekshirish."""
        if load_settings()["auto"]:
            QTimer.singleShot(4000, lambda: self.check(silent=True))
            self.timer.start()

    def shutdown(self, timeout_ms: int = 3000):
        """Oyna yopilayotganda fon oqimlari tugashini kutadi."""
        self.timer.stop()
        for t in list(self.threads):
            try:
                t.quit()
                t.wait(timeout_ms)
            except RuntimeError:   # Qt obyekti allaqachon o'chirilgan
                pass

    def _set(self, state: str, error: str = ""):
        self.state = state
        self.error = error
        self.changed.emit()

    @property
    def busy(self) -> bool:
        return self.state in ("checking", "downloading")

    @property
    def version(self) -> str:
        return self.info.version if self.info else ""

    # --- tekshirish
    def check(self, silent: bool = False):
        """silent=True - fonda (xato bo'lsa jim); False - "Yangilanish" oynasi ochiladi."""
        if not silent:
            UpdateDialog(self, self.w).show()
        if self.busy or self.state == "ready":
            self.changed.emit()
            return
        try:
            src = updater.make_source(load_settings())
        except Exception as e:
            self._set("error", updater.friendly_error(e))
            return
        self.silent = silent
        self._set("checking")
        run_in_thread(self, lambda _p: updater.check(src), self._checked)

    def _checked(self, info, err):
        QSettings("TTYSI", "BinolarKadastr").setValue(f"{SETTINGS_KEY}/last_check", time.time())
        if err is not None:
            self._set("error", updater.friendly_error(err))
            return
        if info is None:
            self._set("latest")
            return
        self.info = info
        man = updater.bundled_manifest()
        # yuklangan kod ishga tushmagan bo'lsa (BROKEN) - to'liq paket bilan yangilanadi
        self.full = info.needs_full(man["libs"] if man else None) or updater.is_broken(info.version)
        if not updater.is_frozen():
            self._set("available")           # manba koddan ishlayapti: git pull
        elif not self.full and updater.downloaded(info.version):
            self._set("ready")
        elif not self.full:
            self.download()                  # kichik kod yangilanishi - so'ramasdan fonda
        else:
            self._set("available")

    # --- yuklash
    def download(self):
        if self.info is None or self.state == "downloading":
            return
        info, full = self.info, self.full
        self.done_bytes = self.total_bytes = 0
        self._set("downloading")

        def progress(done, total):
            self.done_bytes, self.total_bytes = done, total
            self.changed.emit()

        def job(p):
            return updater.prepare_full_update(info, p) if full else updater.install_code_update(info, p)

        def done(res, err):
            if err is not None:
                self._set("error", updater.friendly_error(err))
                return
            if full:
                self.full_script = res
                self._set("ready")
                self.restart()
            else:
                self._set("ready")

        run_in_thread(self, job, done, progress)

    def restart(self) -> bool:
        """Saqlashni so'rab, dasturni qayta ochadi (ochiq loyiha ham qayta ochiladi)."""
        if not self.w.maybe_save():
            return False
        self.w.dirty = False
        if self.full and getattr(self, "full_script", None):
            updater.launch_full_update(self.full_script)
        else:
            args = [self.w.path] if getattr(self.w, "path", None) else []
            QProcess.startDetached(sys.executable, args)
        self.w.close()
        return True

    # --- matnlar
    def message(self) -> str:
        v = self.version
        if self.state == "checking":
            return "Yangilanish tekshirilmoqda..."
        if self.state == "latest":
            return f"Sizda eng so'nggi versiya: {__version__}"
        if self.state == "error":
            return f"Yangilab bo'lmadi: {self.error}"
        if self.state == "downloading":
            mb = f"{self.done_bytes / 1048576:.1f}" + (f" / {self.total_bytes / 1048576:.1f}" if self.total_bytes else "")
            return f"Versiya {v} yuklanmoqda... {mb} MB"
        if self.state == "ready":
            return f"Versiya {v} tayyor. Dastur qayta ochilganda kuchga kiradi."
        if self.state == "available":
            if not updater.is_frozen():
                return f"Yangi versiya {v} mavjud. Dastur manba koddan ishlamoqda — yangilash: git pull"
            return f"Yangi versiya {v} mavjud (to'liq paket, ~110 MB)."
        return ""

    def action(self) -> str:
        """Asosiy tugma matni (bo'sh - tugma yo'q)."""
        if self.state == "ready":
            return "Qayta ochish"
        if self.state == "available" and updater.is_frozen():
            return "Yuklab o'rnatish"
        if self.state == "error":
            return "Qayta urinish"
        return ""

    def do_action(self):
        if self.state == "ready":
            self.restart()
        elif self.state == "available":
            self.download()
        elif self.state == "error":
            self.check(silent=True)


# ======================================================================== tepadagi panel

class UpdateBanner(QFrame):
    """Oyna tepasidagi ingichka panel: yangi versiya bor / tayyor / yuklanmoqda."""

    SHOW = ("available", "downloading", "ready")

    def __init__(self, upd: Updater, parent=None):
        super().__init__(parent)
        self.upd = upd
        self.setObjectName("updateBanner")
        self.setStyleSheet(f"""
            QFrame#updateBanner {{ background: {theme.PRIMARY_SOFT}; border-bottom: 1px solid #C9D8EC; }}
            QFrame#updateBanner QLabel {{ color: {theme.PRIMARY_DARK}; }}
            QPushButton#bannerLink {{ border: none; background: transparent; color: {theme.PRIMARY};
                font-weight: 600; min-height: 28px; padding: 0 6px; }}
            QToolButton#bannerClose {{ border: none; background: transparent; color: {theme.INK_2}; }}
        """)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 6, 12, 6)
        lay.setSpacing(10)
        self.text = QLabel()
        lay.addWidget(self.text, 1)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedWidth(160)
        lay.addWidget(self.bar)
        self.notes_btn = QPushButton("Nima yangi?")
        self.notes_btn.setObjectName("bannerLink")
        self.notes_btn.clicked.connect(self.show_notes)
        lay.addWidget(self.notes_btn)
        self.act = QPushButton()
        self.act.setObjectName("primary")
        self.act.setMinimumHeight(30)
        self.act.clicked.connect(upd.do_action)
        lay.addWidget(self.act)
        close = QToolButton()
        close.setObjectName("bannerClose")
        close.setText("✕")
        close.setToolTip("Yopish")
        close.clicked.connect(self.dismiss)
        lay.addWidget(close)
        self.dismissed_for = None
        upd.changed.connect(self.refresh)
        self.refresh()

    def dismiss(self):
        self.dismissed_for = (self.upd.state, self.upd.version)
        self.hide()

    def refresh(self):
        u = self.upd
        visible = u.state in self.SHOW and (u.state, u.version) != self.dismissed_for
        self.setVisible(visible)
        if not visible:
            return
        self.text.setText(u.message())
        self.bar.setVisible(u.state == "downloading")
        if u.state == "downloading":
            self.bar.setMaximum(u.total_bytes or 0)
            self.bar.setValue(u.done_bytes)
        a = u.action()
        self.act.setText(a)
        self.act.setVisible(bool(a))
        self.notes_btn.setVisible(bool(u.info))

    def show_notes(self):
        if self.upd.info:
            NotesDialog(f"Versiya {self.upd.version}: nima yangi", self.upd.info.notes, self.window()).exec()


class NotesDialog(QDialog):
    def __init__(self, title: str, notes: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nima yangi")
        self.resize(520, 420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        h = QLabel(title)
        h.setStyleSheet("font-size: 18px; font-weight: 700")
        lay.addWidget(h)
        tb = QTextBrowser()
        tb.setHtml(notes_html(notes))
        tb.setStyleSheet(f"QTextBrowser {{ border: none; background: {theme.SURFACE}; }}")
        lay.addWidget(tb, 1)
        ok = QPushButton("Yaxshi")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(ok)
        lay.addLayout(row)


def show_whats_new(window) -> bool:
    """Dastur yangi versiyada birinchi marta ochilganda "Nima yangi" oynasini ko'rsatadi."""
    s = QSettings("TTYSI", "BinolarKadastr")
    last = s.value("app/last_version", "")
    s.setValue("app/last_version", __version__)
    if not last or updater.version_tuple(last) >= updater.version_tuple(__version__):
        return False
    NotesDialog(f"Dastur yangilandi: {last} → {__version__}", updater.installed_notes(__version__),
                window).exec()
    return True


# ======================================================================== oynalar

class UpdateDialog(QDialog):
    """Qo'lda tekshirish: holat, "nima yangi", yuklash jarayoni va bitta asosiy tugma."""

    def __init__(self, upd: Updater, parent=None):
        super().__init__(parent)
        self.upd = upd
        self.setWindowTitle("Yangilanish")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        h = QLabel("Dasturni yangilash")
        h.setStyleSheet("font-size: 18px; font-weight: 700")
        lay.addWidget(h)
        cur = QLabel(f"Joriy versiya: {__version__}")
        cur.setObjectName("muted")
        lay.addWidget(cur)
        self.status = QLabel()
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        lay.addWidget(self.bar)
        self.notes = QTextBrowser()
        self.notes.setStyleSheet(f"QTextBrowser {{ border: 1px solid {theme.LINE}; border-radius: 8px; }}")
        lay.addWidget(self.notes, 1)
        row = QHBoxLayout()
        sb = QPushButton("Sozlamalar...")
        sb.clicked.connect(self.open_settings)
        row.addWidget(sb)
        row.addStretch()
        close = QPushButton("Yopish")
        close.clicked.connect(self.accept)
        self.act = QPushButton()
        self.act.setObjectName("primary")
        self.act.clicked.connect(upd.do_action)
        row.addWidget(close)
        row.addWidget(self.act)
        lay.addLayout(row)
        upd.changed.connect(self.refresh)
        self.finished.connect(lambda _: self._disconnect())
        self.refresh()

    def open_settings(self):
        if UpdateSettingsDialog(self).exec() == QDialog.Accepted and not self.upd.busy:
            self.upd.state = "idle"
            self.upd.check(silent=True)          # yangi sozlamalar bilan qayta tekshirish

    def _disconnect(self):
        try:
            self.upd.changed.disconnect(self.refresh)
        except (RuntimeError, TypeError):
            pass

    def refresh(self):
        u = self.upd
        self.status.setText(u.message())
        color = theme.DANGER_FG if u.state == "error" else theme.OK_FG if u.state in ("latest", "ready") \
            else theme.INK
        self.status.setStyleSheet(f"color: {color}; font-weight: 600")
        self.bar.setVisible(u.busy)
        if u.state == "checking":
            self.bar.setMaximum(0)
        elif u.state == "downloading":
            self.bar.setMaximum(u.total_bytes or 0)
            self.bar.setValue(u.done_bytes)
        self.notes.setVisible(bool(u.info) and u.state not in ("latest", "error"))
        if not self.notes.isVisible():
            self.adjustSize()
        if u.info:
            self.notes.setHtml(f"<b>Versiya {u.version}: nima yangi</b>" + notes_html(u.info.notes))
        a = u.action()
        self.act.setText(a)
        self.act.setVisible(bool(a))


class UpdateSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Yangilanish sozlamalari")
        self.resize(540, 0)
        cur = load_settings()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        h = QLabel("Yangilanishlar qayerdan olinsin?")
        h.setStyleSheet("font-weight: 600")
        lay.addWidget(h)
        self.r_github = QRadioButton("Internet orqali (GitHub) — tavsiya etiladi")
        self.r_folder = QRadioButton("Institut tarmog'idagi papkadan (internet kerak emas)")
        grp = QButtonGroup(self)
        grp.addButton(self.r_github)
        grp.addButton(self.r_folder)
        (self.r_folder if cur["kind"] == "folder" else self.r_github).setChecked(True)
        lay.addWidget(self.r_github)
        lay.addWidget(self.r_folder)
        row = QHBoxLayout()
        row.setContentsMargins(24, 0, 0, 0)
        self.folder = QLineEdit(cur["folder"])
        self.folder.setPlaceholderText("masalan: \\\\server\\TTYSI\\yangilanish")
        b = QPushButton("Tanlash...")
        b.clicked.connect(self.pick_folder)
        row.addWidget(self.folder, 1)
        row.addWidget(b)
        lay.addLayout(row)
        hint = QLabel("Papkaga relizdagi update.json va ttysi_app-*.zip (kerak bo'lsa TTYSI_Kadastr_Windows.zip) "
                      "fayllarini qo'yish kifoya.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        hint.setContentsMargins(24, 0, 0, 0)
        lay.addWidget(hint)

        self.more = QToolButton()
        self.more.setText("Qo'shimcha (yopiq repozitoriy)")
        self.more.setCheckable(True)
        self.more.setStyleSheet("QToolButton { border: none; color: %s; font-weight: 600; }" % theme.PRIMARY)
        lay.addWidget(self.more)
        self.more_box = QWidget()
        ml = QVBoxLayout(self.more_box)
        ml.setContentsMargins(0, 0, 0, 0)
        self.repo = QLineEdit(cur["repo"])
        self.token = QLineEdit(cur["token"])
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("faqat yopiq repo uchun: faqat o'qish huquqli token")
        for label, w in (("Repozitoriy", self.repo), ("Token", self.token)):
            lab = QLabel(label)
            lab.setObjectName("fieldLabel")
            ml.addWidget(lab)
            ml.addWidget(w)
        self.more_box.setVisible(bool(cur["token"]) or cur["repo"] != updater.DEFAULT_REPO)
        self.more.setChecked(self.more_box.isVisible())
        self.more.toggled.connect(self.more_box.setVisible)
        lay.addWidget(self.more_box)

        self.auto = QCheckBox("Yangilanishlarni avtomatik tekshirish va yuklab qo'yish")
        self.auto.setChecked(cur["auto"])
        lay.addWidget(self.auto)
        last = QSettings("TTYSI", "BinolarKadastr").value(f"{SETTINGS_KEY}/last_check")
        when = time.strftime("%d.%m.%Y %H:%M", time.localtime(float(last))) if last else "hali tekshirilmagan"
        info = QLabel(f"Joriy versiya: {__version__} · oxirgi tekshirish: {when}")
        info.setObjectName("muted")
        lay.addWidget(info)
        self.test_result = QLabel()
        self.test_result.setWordWrap(True)
        self.test_result.hide()
        lay.addWidget(self.test_result)
        row = QHBoxLayout()
        self.test_btn = QPushButton("Ulanishni tekshirish")
        self.test_btn.clicked.connect(self.test_connection)
        row.addWidget(self.test_btn)
        row.addStretch()
        cancel = QPushButton("Bekor qilish")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Saqlash")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)

    def current(self) -> dict:
        return {"kind": "folder" if self.r_folder.isChecked() else "github",
                "folder": self.folder.text().strip(), "repo": self.repo.text().strip() or updater.DEFAULT_REPO,
                "token": self.token.text().strip(), "auto": self.auto.isChecked()}

    def test_connection(self):
        """Kiritilgan sozlamalar bilan update.json ni o'qib ko'radi (saqlamasdan)."""
        self.test_btn.setEnabled(False)
        self.test_result.setStyleSheet(f"color: {theme.INK_2}")
        self.test_result.setText("Tekshirilmoqda...")
        self.test_result.show()
        st = self.current()

        def job(_p):
            return updater.make_source(st).manifest()

        def done(man, err):
            self.test_btn.setEnabled(True)
            if err is not None:
                self.test_result.setStyleSheet(f"color: {theme.DANGER_FG}; font-weight: 600")
                self.test_result.setText("✗ " + updater.friendly_error(err))
            else:
                self.test_result.setStyleSheet(f"color: {theme.OK_FG}; font-weight: 600")
                self.test_result.setText(f"✓ Ulanish ishlayapti. Oxirgi versiya: {man.get('version', '?')}")

        self.threads = getattr(self, "threads", [])
        run_in_thread(self, job, done)

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Yangilanishlar papkasi", self.folder.text())
        if d:
            self.folder.setText(d)
            self.r_folder.setChecked(True)

    def accept(self):
        save_settings(self.current())
        super().accept()

    def done(self, r):
        for t in getattr(self, "threads", []):      # tekshirish tugashini kutish (oqim yopilmasdan)
            try:
                t.quit()
                t.wait(5000)
            except RuntimeError:
                pass
        super().done(r)
