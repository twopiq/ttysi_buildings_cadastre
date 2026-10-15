"""Eksport jarayoni oynasi: nima yozilayotgani, tugadimi, xato bo'ldimi.

Har bir fayl alohida ish (Job): biri xato bo'lsa qolganlari baribir yoziladi. Oxirida natija:
"tugadi" (yashil), "qisman" (sariq) yoki "bajarilmadi" (qizil) va har bir fayl bo'yicha xabar.
Xato bo'lgan fayllarni "Qayta urinish" bilan qayta yozish, tayyor faylni yoki papkani ochish mumkin.
"""

from __future__ import annotations

import errno
import os
import time
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QProgressBar, QPushButton, QVBoxLayout)

from . import theme


@dataclass
class Job:
    label: str                                   # "1-qavat", "Excel hisobot" ...
    path: str
    run: Callable[[Callable[[str], None]], None]  # run(step) - step("2/5-sahifa") oraliq holat uchun
    error: str = ""
    done: bool = False
    root: str = ""                                # berilsa: shu papka ichidagi yetishmagan papkalar yaratiladi


def friendly_error(e: BaseException) -> str:
    """Foydalanuvchi tushunadigan xato matni."""
    if isinstance(e, PermissionError) or getattr(e, "errno", None) in (errno.EACCES, errno.EPERM):
        return ("Faylga yozib bo'lmadi: u boshqa dasturda ochiq (Excel, PDF ko'ruvchi, AutoCAD) yoki papkaga "
                "yozish huquqi yo'q. Faylni yoping va \"Qayta urinish\"ni bosing.")
    if isinstance(e, FileNotFoundError):
        return "Papka topilmadi (o'chirilgan yoki fleshka uzilgan bo'lishi mumkin)."
    if getattr(e, "errno", None) == errno.ENOSPC:
        return "Diskda joy qolmagan."
    if isinstance(e, MemoryError):
        return "Xotira yetmadi: rasm o'lchamini kichikroq tanlang."
    if type(e) is OSError and e.args and isinstance(e.args[0], str):
        return e.args[0]
    return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__


def check_writable(path: str) -> None:
    """Yozishdan oldin tekshirish: Qt yozuvchilari (PDF, rasm) xatoni jim o'tkazib yuboradi."""
    folder = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(folder):
        raise FileNotFoundError(folder)
    existed = os.path.exists(path)
    with open(path, "ab"):                  # fayl boshqa dasturda ochiq bo'lsa (Windows) - PermissionError
        pass
    if not existed:
        os.remove(path)


class ExportProgress(QDialog):
    def __init__(self, title: str, jobs: list[Job], parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowModality(Qt.WindowModal)
        self.jobs = jobs
        self.cancelled = False
        self.running = False
        self.state = ""                        # "ok" / "partial" / "failed" / "cancelled"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        self.head = QLabel(title)
        self.head.setStyleSheet("font-size: 17px; font-weight: 700")
        self.head.setWordWrap(True)
        lay.addWidget(self.head)
        self.status = QLabel()
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setTextVisible(True)
        lay.addWidget(self.bar)
        self.list = QListWidget()
        self.list.setMinimumHeight(min(260, 60 + 28 * len(jobs)))
        self.list.setWordWrap(True)
        self.list.itemDoubleClicked.connect(lambda it: self._open(it.data(Qt.UserRole)))
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.b_open = QPushButton("Faylni ochish")
        self.b_folder = QPushButton("Papkani ochish")
        self.b_retry = QPushButton("Qayta urinish")
        self.b_close = QPushButton("Bekor qilish")
        self.b_open.clicked.connect(lambda: self._open(self.saved()[0]))
        self.b_folder.clicked.connect(lambda: self._open(os.path.dirname((self.saved() or [j.path for j in jobs])[0])))
        self.b_retry.clicked.connect(self.retry)
        self.b_close.clicked.connect(self._close_or_cancel)
        row.addWidget(self.b_open)
        row.addWidget(self.b_folder)
        row.addStretch()
        row.addWidget(self.b_retry)
        row.addWidget(self.b_close)
        lay.addLayout(row)
        self.resize(560, self.sizeHint().height())

    # ------------------------------------------------------------ ishlash
    def run(self) -> list[str]:
        """Ishlarni bajaradi (oyna ochiq turadi), natija - muvaffaqiyatli yozilgan fayllar."""
        todo = [j for j in self.jobs if not j.done]
        self.running = True
        self.cancelled = False
        self.state = ""
        self._buttons()
        self.show()
        self.bar.setRange(0, len(todo))
        self.bar.setValue(0)
        t0 = time.monotonic()
        for i, job in enumerate(todo):
            if self.cancelled:
                break
            self._step(f"{i + 1}/{len(todo)}: {job.label} — {os.path.basename(job.path)}")
            job.error = ""
            try:
                if job.root and os.path.isdir(os.path.dirname(job.root)):
                    os.makedirs(os.path.dirname(job.path), exist_ok=True)
                check_writable(job.path)
                job.run(lambda text, i=i, job=job: self._step(f"{i + 1}/{len(todo)}: {job.label} — {text}"))
                if not os.path.exists(job.path) or os.path.getsize(job.path) == 0:
                    raise OSError("Fayl yozilmadi (bo'sh chiqdi). Boshqa papka yoki nom bilan urinib ko'ring.")
                job.done = True
            except Exception as e:                  # noqa: BLE001 - har qanday xato foydalanuvchiga ko'rsatiladi
                job.error = friendly_error(e)
            self.bar.setValue(i + 1)
        self.running = False
        self._finish(time.monotonic() - t0)
        return self.saved()

    def _step(self, text: str):
        self.status.setText(f"Yozilmoqda… {text}")
        QApplication.processEvents()

    def saved(self) -> list[str]:
        return [j.path for j in self.jobs if j.done]

    def failed(self) -> list[Job]:
        return [j for j in self.jobs if j.error]

    def _finish(self, secs: float):
        ok, bad = self.saved(), self.failed()
        left = len(self.jobs) - len(ok) - len(bad)
        if self.cancelled and left:
            self.state = "cancelled"
            text, fg, bg = f"Bekor qilindi. {len(ok)} ta fayl saqlandi, {left} tasi yozilmadi.", theme.WARN_FG, theme.WARN_BG
        elif not bad:
            self.state = "ok"
            text = (f"Eksport tugadi ✓  {len(ok)} ta fayl saqlandi" if len(ok) > 1 else "Eksport tugadi ✓  Fayl saqlandi")
            text += f" ({secs:.1f} s)."
            fg, bg = theme.OK_FG, theme.OK_BG
        elif ok:
            self.state = "partial"
            text, fg, bg = f"Qisman bajarildi: {len(ok)} ta fayl saqlandi, {len(bad)} tasida xato.", theme.WARN_FG, theme.WARN_BG
        else:
            self.state = "failed"
            text, fg, bg = "Eksport bajarilmadi — xato yuz berdi.", theme.DANGER_FG, theme.DANGER_BG
        self.status.setText(text)
        self.status.setStyleSheet(f"QLabel {{ color: {fg}; background: {bg}; border-radius: 8px; padding: 8px 10px;"
                                  " font-weight: 600; }")
        self.list.clear()
        for j in self.jobs:
            if j.done:
                it = QListWidgetItem(f"✓  {j.label} — {j.path}")
                it.setForeground(Qt.darkGreen)
                it.setToolTip("Ikki marta bosing - ochish")
            elif j.error:
                it = QListWidgetItem(f"✗  {j.label} — {os.path.basename(j.path)}\n     {j.error}")
                it.setForeground(Qt.red)
            else:
                it = QListWidgetItem(f"–  {j.label} — yozilmadi")
            it.setData(Qt.UserRole, j.path if j.done else "")
            self.list.addItem(it)
        self._buttons()

    def _buttons(self):
        ok = self.saved()
        self.b_open.setVisible(not self.running and len(ok) == 1)
        self.b_folder.setVisible(not self.running and bool(ok))
        self.b_retry.setVisible(not self.running and any(not j.done for j in self.jobs) and bool(self.state))
        self.b_close.setText("Bekor qilish" if self.running else "Yopish")
        if not self.running:
            self.b_close.setObjectName("primary" if self.state == "ok" else "")
            self.b_close.style().unpolish(self.b_close)
            self.b_close.style().polish(self.b_close)
            self.b_close.setDefault(True)

    def retry(self):
        self.run()

    def _close_or_cancel(self):
        if self.running:
            self.cancelled = True
            self.status.setText("To'xtatilmoqda… (joriy fayl tugashi kutiladi)")
        else:
            self.accept()

    def closeEvent(self, e):
        if self.running:                      # yozish paytida yopilmaydi - avval to'xtatiladi
            self.cancelled = True
            e.ignore()
            return
        super().closeEvent(e)

    def reject(self):
        if self.running:
            self.cancelled = True
            return
        super().reject()

    @staticmethod
    def _open(path: str):
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
