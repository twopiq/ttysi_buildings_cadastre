"""Tashkilotni to'liq eksport qilish: barcha binolar va etajlar bitta papkada (xohlansa ZIP).

Natija:
    <Tashkilot> - eksport 2026-10-15/
        <Tashkilot> - hisobot.xlsx             barcha binolar bo'yicha Excel
        <Tashkilot> - barcha binolar.pdf       har etaj alohida sahifa
        1-bino/1-bino.pdf                      har bino alohida PDF
        1-bino/1-bino - 1-qavat.png / .dxf     (tanlansa) har etaj rasmi / AutoCAD
        Loyiha fayllari/1-bino.ttysi           zaxira nusxa (dasturda qayta ochish uchun)
        Tarkib.txt                             nima eksport qilingani
    <Tashkilot> - eksport 2026-10-15.zip       (tanlansa) shu papka bitta faylda
"""

from __future__ import annotations

import os
import shutil
import time
import zipfile
from dataclasses import dataclass

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout)

from ..equipment import EQUIPMENT_TYPES
from ..model import Building
from ..render import RenderOptions
from .export_progress import Job
from .home import safe_file_name, scan


@dataclass
class OrgExportOptions:
    excel: bool = True
    pdf_all: bool = True          # bitta umumiy PDF
    pdf_each: bool = True         # har bino alohida PDF
    png: bool = False
    dxf: bool = False
    projects: bool = True         # .ttysi zaxira nusxalari
    zip: bool = False
    planned: bool = True
    background: bool = False
    png_size: int = 4000


class OrgExportDialog(QDialog):
    def __init__(self, org: str, settings: QSettings, parent=None):
        super().__init__(parent)
        self.org = org
        self.settings = settings
        name = os.path.basename(org)
        items = scan(org)
        self.setWindowTitle(f"{name} — to'liq eksport")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(10)
        h = QLabel(f"«{name}» tashkilotini to'liq eksport qilish")
        h.setStyleSheet("font-size: 17px; font-weight: 700")
        lay.addWidget(h)
        floors = sum(i["floors"] for i in items)
        unknown = sum(i["unknown"] for i in items)
        info = QLabel(f"{len(items)} ta bino, {floors} ta etaj. Hammasi bitta papkaga yoziladi.")
        info.setObjectName("muted")
        lay.addWidget(info)
        if unknown:
            w = QLabel(f"⚠ {unknown} ta belgi hali tasdiqlanmagan — chizmada «?» bo'lib chiqadi.")
            w.setStyleSheet("color: #8A4300")
            lay.addWidget(w)
        o = OrgExportOptions()
        self.c = {}
        for key, text in (("excel", "Excel hisobot (barcha binolar, tashkilot bo'yicha jami)"),
                          ("pdf_all", "Umumiy PDF — barcha binolar va etajlar bitta faylda"),
                          ("pdf_each", "Har bir bino uchun alohida PDF"),
                          ("png", "Etaj rasmlari (PNG)"),
                          ("dxf", "AutoCAD chizmalari (DXF)"),
                          ("projects", "Loyiha fayllari (.ttysi) — zaxira nusxa"),
                          ("planned", "Rejadagi (kerak) jihozlarni ham chizish"),
                          ("background", "Kadastr rasmini fon sifatida qo'shish"),
                          ("zip", "ZIP arxiv ham yaratish (yuborish uchun bitta fayl)")):
            cb = QCheckBox(text)
            cb.setChecked(getattr(o, key))
            self.c[key] = cb
            lay.addWidget(cb)
        lay.addWidget(QLabel("Qayerga saqlash:"))
        row = QHBoxLayout()
        self.dest = QLineEdit(settings.value("export_dir", "") or os.path.expanduser("~"))
        b = QPushButton("Tanlash...")
        b.clicked.connect(self._choose)
        row.addWidget(self.dest, 1)
        row.addWidget(b)
        lay.addLayout(row)
        self.where = QLabel()
        self.where.setObjectName("muted")
        self.where.setWordWrap(True)
        lay.addWidget(self.where)
        self.dest.textChanged.connect(self._update)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok = bb.button(QDialogButtonBox.Ok)
        self.ok.setText("Eksport qilish")
        self.ok.setObjectName("primary")
        bb.button(QDialogButtonBox.Cancel).setText("Bekor qilish")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        for cb in self.c.values():
            cb.toggled.connect(self._update)
        self.ok.setEnabled(bool(items))
        self._update()

    def _choose(self):
        d = QFileDialog.getExistingDirectory(self, "Eksport papkasi", self.dest.text())
        if d:
            self.dest.setText(d)

    def _update(self):
        any_out = any(self.c[k].isChecked() for k in ("excel", "pdf_all", "pdf_each", "png", "dxf", "projects"))
        self.ok.setEnabled(any_out and bool(self.dest.text().strip()))
        self.where.setText(f"Natija: {export_folder(self.dest.text().strip(), os.path.basename(self.org))}")

    def options(self) -> OrgExportOptions:
        return OrgExportOptions(**{k: cb.isChecked() for k, cb in self.c.items()})


def export_folder(dest: str, org_name: str) -> str:
    return os.path.join(dest, f"{safe_file_name(org_name)} - eksport {time.strftime('%Y-%m-%d')}")


def org_export_jobs(org: str, dest: str, o: OrgExportOptions, open_building: tuple[str, Building] | None = None
                    ) -> tuple[str, list[Job]]:
    """Eksport ishlari ro'yxati. open_building - (yo'l, bino): muharrirda ochiq bino (saqlanmagan o'zgarishlari
    bilan) fayldan o'qilmaydi."""
    from ..export import export_dxf, export_image, export_pdf, export_pdf_pages
    from ..report import export_excel

    name = os.path.basename(org)
    base = safe_file_name(name)
    folder = export_folder(dest, name)
    items = scan(org)
    opts = RenderOptions(background=o.background, planned=o.planned)
    cache: dict[str, Building] = {}

    def load(path: str) -> Building:
        if open_building and os.path.normcase(open_building[0]) == os.path.normcase(path):
            return open_building[1]
        if path not in cache:
            cache[path] = Building.load(path)
        return cache[path]

    jobs: list[Job] = []

    def add(label, path, fn):
        jobs.append(Job(label, path, lambda step, path=path, fn=fn: fn(step, path), root=folder))

    if o.excel:
        add("Excel hisobot", os.path.join(folder, f"{base} - hisobot.xlsx"),
            lambda step, p: export_excel(p, [load(i["path"]) for i in items], title=name))
    if o.pdf_all:
        def pdf_all(step, p):
            pages = [(b, f) for b in (load(i["path"]) for i in items) for f in b.floors]
            if not pages:
                raise OSError("Tashkilot binolarida etaj yo'q.")
            export_pdf_pages(p, pages, opts, title=name,
                             progress=lambda k, b, f: step(f"{k + 1}/{len(pages)}-sahifa: {b.name}, {f.name}"))
        add("Umumiy PDF", os.path.join(folder, f"{base} - barcha binolar.pdf"), pdf_all)
    for it in items:
        bname = safe_file_name(it["name"])
        bdir = os.path.join(folder, bname)
        if o.pdf_each and it["floors"]:
            add(f"{it['name']} — PDF", os.path.join(bdir, f"{bname}.pdf"),
                lambda step, p, path=it["path"]: export_pdf(p, load(path), load(path).floors, opts,
                                                           progress=lambda k, f: step(f"{f.name}")))
        for k, fname in enumerate(n for n, _ in it.get("floor_list") or []):
            stem = os.path.join(bdir, safe_file_name(f"{it['name']} - {fname}"))
            if o.png:
                add(f"{it['name']}, {fname} — PNG", stem + ".png",
                    lambda step, p, path=it["path"], k=k: export_image(p, load(path), load(path).floors[k], opts,
                                                                      o.png_size))
            if o.dxf:
                add(f"{it['name']}, {fname} — DXF", stem + ".dxf",
                    lambda step, p, path=it["path"], k=k: export_dxf(p, load(path), load(path).floors[k],
                                                                    planned=o.planned))
        if o.projects:
            def copy(step, p, path=it["path"]):
                if open_building and os.path.normcase(open_building[0]) == os.path.normcase(path):
                    open_building[1].save(p)          # saqlanmagan o'zgarishlar ham
                else:
                    shutil.copy2(path, p)
            add(f"{it['name']} — loyiha fayli", os.path.join(folder, "Loyiha fayllari", os.path.basename(it["path"])),
                copy)

    def contents(step, p):
        lines = [f"{name} — to'liq eksport", time.strftime("Sana: %Y-%m-%d %H:%M"), ""]
        total: dict[str, int] = {}
        for it in items:
            c = it.get("counts", {})
            for k, v in c.items():
                total[k] = total.get(k, 0) + v
            eq = ", ".join(f"{t.label} {c[t.code]}" for t in EQUIPMENT_TYPES if c.get(t.code)) or "jihoz yo'q"
            lines.append(f"{it['name']}: {it['floors']} etaj — {eq}"
                         + (f"; {it['unknown']} ta belgi tasdiqlanmagan" if it.get("unknown") else ""))
        lines += ["", "Jami: " + (", ".join(f"{t.label} {total[t.code]}" for t in EQUIPMENT_TYPES
                                            if total.get(t.code)) or "jihoz yo'q"), ""]
        for j in jobs:
            if j.path != p and j.done:
                lines.append(os.path.relpath(j.path, folder))
        with open(p, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    add("Tarkib", os.path.join(folder, "Tarkib.txt"), contents)

    if o.zip:
        def make_zip(step, p):
            with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
                for root, _, files in os.walk(folder):
                    for fn in files:
                        full = os.path.join(root, fn)
                        z.write(full, os.path.join(os.path.basename(folder), os.path.relpath(full, folder)))
        jobs.append(Job("ZIP arxiv", folder + ".zip", lambda step, p=folder + ".zip": make_zip(step, p)))
    return folder, jobs
