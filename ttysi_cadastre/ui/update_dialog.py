"""Yangilanish: sozlamalar oynasi, fonda tekshirish, yuklash va qayta ishga tushirish."""

from __future__ import annotations

import sys

from PySide6.QtCore import QObject, QProcess, QSettings, QThread, Signal, Slot
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QProgressDialog, QPushButton, QRadioButton, QVBoxLayout, QWidget)

from .. import updater

SETTINGS_KEY = "update"


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


class UpdateSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Yangilanish sozlamalari")
        self.resize(520, 300)
        cur = load_settings()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Yangilanishlar qayerdan olinsin?"))
        self.r_folder = QRadioButton("Tarmoq yoki mahalliy papka (masalan \\\\server\\TTYSI\\yangilanish)")
        self.r_github = QRadioButton("GitHub Releases (internet orqali)")
        grp = QButtonGroup(self)
        grp.addButton(self.r_folder)
        grp.addButton(self.r_github)
        (self.r_folder if cur["kind"] == "folder" else self.r_github).setChecked(True)

        lay.addWidget(self.r_folder)
        row = QHBoxLayout()
        self.folder = QLineEdit(cur["folder"])
        b = QPushButton("Tanlash...")
        b.clicked.connect(self.pick_folder)
        row.addWidget(self.folder)
        row.addWidget(b)
        w = QWidget()
        w.setLayout(row)
        lay.addWidget(w)

        lay.addWidget(self.r_github)
        form = QFormLayout()
        self.repo = QLineEdit(cur["repo"])
        self.token = QLineEdit(cur["token"])
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("faqat yopiq (private) repo uchun - o'qish huquqli token")
        form.addRow("Repozitoriy:", self.repo)
        form.addRow("Token:", self.token)
        lay.addLayout(form)

        self.auto = QCheckBox("Dastur ochilganda yangilanishni avtomatik tekshirish")
        self.auto.setChecked(cur["auto"])
        lay.addWidget(self.auto)
        lay.addWidget(QLabel(f"Joriy versiya: {updater.current_version()}"))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Yangilanishlar papkasi", self.folder.text())
        if d:
            self.folder.setText(d)
            self.r_folder.setChecked(True)

    def accept(self):
        save_settings({"kind": "folder" if self.r_folder.isChecked() else "github",
                       "folder": self.folder.text().strip(), "repo": self.repo.text().strip(),
                       "token": self.token.text().strip(), "auto": self.auto.isChecked()})
        super().accept()


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


class Updater(QObject):
    """Asosiy oyna uchun yangilanish jarayoni."""

    def __init__(self, window):
        super().__init__(window)
        self.w = window
        self.busy = False
        self.threads: list[QThread] = []

    def shutdown(self, timeout_ms: int = 3000):
        """Oyna yopilayotganda fon oqimlari tugashini kutadi."""
        for t in list(self.threads):
            try:
                t.quit()
                t.wait(timeout_ms)
            except RuntimeError:   # Qt obyekti allaqachon o'chirilgan
                pass

    def source(self):
        st = load_settings()
        if st["kind"] == "folder" and not st["folder"]:
            raise RuntimeError("Yangilanishlar papkasi ko'rsatilmagan (Yordam → Yangilanish sozlamalari)")
        return updater.make_source(st)

    # --- tekshirish
    def check(self, silent: bool = False):
        if self.busy:
            return
        try:
            src = self.source()
        except RuntimeError as e:
            if not silent:
                QMessageBox.information(self.w, "Yangilanish", str(e))
            return
        self.busy = True
        if not silent:
            self.w.statusBar().showMessage("Yangilanish tekshirilmoqda...")
        run_in_thread(self, lambda _p: updater.check(src),
                      lambda res, err: self._checked(res, err, silent))

    def _checked(self, info, err, silent):
        self.busy = False
        if err is not None:
            if not silent:
                QMessageBox.warning(self.w, "Yangilanish", f"Tekshirib bo'lmadi:\n{err}")
            return
        if info is None:
            if not silent:
                QMessageBox.information(self.w, "Yangilanish",
                                        f"Sizda eng so'nggi versiya: {updater.current_version()}")
            self.w.statusBar().clearMessage()
            return
        self.offer(info)

    def offer(self, info: updater.UpdateInfo):
        man = updater.bundled_manifest()
        full = info.needs_full(man["libs"] if man else None)
        size = "to'liq paket (~100 MB)" if full else "kichik kod yangilanishi"
        text = (f"Yangi versiya mavjud: <b>{info.version}</b> (sizda {updater.current_version()}).<br>"
                f"Hajmi: {size}.<br><br>{info.notes.replace(chr(10), '<br>')}<br><br>Hozir yangilansinmi?")
        if not updater.is_frozen():
            QMessageBox.information(self.w, "Yangilanish",
                                    f"Yangi versiya {info.version} mavjud.\nDastur manba koddan ishlamoqda - "
                                    "yangilash uchun: git pull")
            return
        if QMessageBox.question(self.w, "Yangilanish", text) != QMessageBox.Yes:
            return
        self.install(info, full)

    # --- o'rnatish
    def install(self, info, full: bool):
        dlg = QProgressDialog("Yuklanmoqda...", None, 0, 100, self.w)
        dlg.setWindowTitle("Yangilanish")
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.show()

        def progress(done, total):
            dlg.setMaximum(total or 0)
            dlg.setValue(done if total else 0)
            dlg.setLabelText(f"Yuklanmoqda... {done / 1048576:.1f} MB"
                             + (f" / {total / 1048576:.1f} MB" if total else ""))

        def job(p):
            if full:
                return updater.prepare_full_update(info, p)
            return updater.install_code_update(info, p)

        def done(res, err):
            dlg.close()
            if err is not None:
                QMessageBox.critical(self.w, "Yangilanish", f"Yangilab bo'lmadi:\n{err}")
                return
            if full:
                QMessageBox.information(self.w, "Yangilanish",
                                        "Dastur yopiladi, yangilanadi va qayta ochiladi.")
                if self.w.maybe_save():
                    self.w.dirty = False
                    updater.launch_full_update(res)
                    self.w.close()
                return
            if QMessageBox.question(self.w, "Yangilanish",
                                    f"Versiya {info.version} o'rnatildi. Dastur hozir qayta ochilsinmi?") \
                    == QMessageBox.Yes and self.w.maybe_save():
                self.w.dirty = False
                QProcess.startDetached(sys.executable, sys.argv[1:])
                self.w.close()

        run_in_thread(self, job, done, progress)
