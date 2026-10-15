"""Binolar papkasi (ish joyi): binolar va tashkilotlar ro'yxati - Qt'siz.

Muharrir (PySide6) va kelajakdagi sayt (web/) bir xil mantiqdan foydalanadi.

Tuzilma:  <ish joyi>/1-bino.ttysi                 tashkilotsiz bino
          <ish joyi>/<Tashkilot>/2-bino.ttysi     tashkilotdagi bino
          <ish joyi>/<Tashkilot>/.ttysi-tashkilot  bo'sh tashkilot ham ko'rinishi uchun belgi
"""

from __future__ import annotations

import os
import re
import shutil
import time

ORG_MARK = ".ttysi-tashkilot"        # bo'sh tashkilot papkasi ham ko'rinishi uchun belgi fayl

_cache: dict[str, tuple[float, dict]] = {}


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


def safe_file_name(name: str) -> str:
    return "".join(c for c in name if c not in '\\/:*?"<>|').strip().rstrip(".") or "Bino"


def free_path(folder: str, base: str, ext: str = ".ttysi") -> str:
    """Papkada band bo'lmagan nom: "1-bino.ttysi", band bo'lsa "1-bino (2).ttysi"."""
    path = os.path.join(folder, base + ext)
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    return path


def natural_key(text: str):
    """"2-bino" "10-bino" dan oldin keladi."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text)]


def is_org(path: str) -> bool:
    if not os.path.isdir(path) or os.path.basename(path).startswith("."):
        return False
    if os.path.exists(os.path.join(path, ORG_MARK)):
        return True
    try:
        return any(n.lower().endswith(".ttysi") for n in os.listdir(path))
    except OSError:
        return False


def orgs(folder: str) -> list[dict]:
    """Binolar papkasidagi tashkilotlar: [{"name", "path", "buildings": scan(...)}]."""
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    out = []
    for n in names:
        p = os.path.abspath(os.path.join(folder, n))
        if is_org(p):
            out.append({"name": n, "path": p, "buildings": scan(p)})
    return sorted(out, key=lambda o: natural_key(o["name"]))


def scan(folder: str) -> list[dict]:
    """Papkadagi barcha binolar (rasmlarsiz tez o'qiladi, o'zgarmagan fayllar keshdan)."""
    from .model import Building
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


def drop_cache(path: str) -> None:
    """Fayl yoki papka (ichidagi barcha binolar) keshdan chiqariladi."""
    path = os.path.abspath(path)
    for k in [k for k in _cache if k == path or k.startswith(path + os.sep)]:
        _cache.pop(k)


def move_file(path: str, folder: str) -> str:
    """Bino faylini boshqa papkaga ko'chirish (nom band bo'lsa raqam qo'shiladi). Natija - yangi yo'l."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.abspath(path)
    if os.path.normcase(os.path.dirname(path)) == os.path.normcase(os.path.abspath(folder)):
        return path
    new = free_path(folder, os.path.splitext(os.path.basename(path))[0])
    shutil.move(path, new)
    drop_cache(path)
    return os.path.abspath(new)


def workspace_tree(folder: str) -> dict:
    """Butun ish joyi: {"buildings": [...tashkilotsiz], "orgs": [{"name","path","buildings"}]}."""
    return {"buildings": scan(folder), "orgs": orgs(folder)}


def create_org(folder: str, name: str) -> str:
    """Yangi tashkilot papkasi (nomi band bo'lsa raqam qo'shiladi)."""
    path = free_path(folder, safe_file_name(name) or "Tashkilot", "")
    os.makedirs(path)
    open(os.path.join(path, ORG_MARK), "w").close()
    return path


def create_building(folder: str, name: str, address: str = "") -> str:
    """Papkada (ish joyi yoki tashkilot) yangi bo'sh bino fayli. Natija - fayl yo'li."""
    from .model import Building
    os.makedirs(folder, exist_ok=True)
    path = free_path(folder, safe_file_name(name) or "Bino")
    Building(name=name.strip() or "Bino", address=address.strip()).save(path)
    return os.path.abspath(path)
