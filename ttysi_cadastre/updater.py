"""Dasturni yangilash.

Ikki xil yangilanish:
  * kod yangilanishi (kichik, ~100 KB) - kutubxonalar (Qt, OpenCV ...) o'zgarmagan bo'lsa.
    Yangi kod %LOCALAPPDATA%/TTYSI_Kadastr/updates/<versiya>/ ga yuklanadi va keyingi ishga
    tushishda run.py uni o'zidagi koddan ustun qo'yadi;
  * to'liq yangilanish (~100 MB) - kutubxonalar o'zgargan bo'lsa (manifestdagi "libs" farq qiladi).
    Zip yuklanadi, dastur yopilgach PowerShell skript papkani almashtirib, dasturni qayta ochadi.

Manba: GitHub Releases (ochiq repo yoki token bilan) yoki tarmoq/mahalliy papka. Ikkalasida ham
update.json manifesti bo'ladi:
  {"version": "0.2.0", "libs": "ab12...", "notes": "...",
   "app_zip": "ttysi_app-0.2.0.zip", "app_sha256": "...",
   "full_zip": "TTYSI_Kadastr_Windows.zip", "full_sha256": "..."}
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass

from . import __version__

DEFAULT_REPO = "twopiq/ttysi_buildings_cadastre"
MANIFEST_NAME = "update.json"
APP_ZIP_NAME = "ttysi_cadastre.zip"


def version_tuple(v: str) -> tuple[int, ...]:
    v = v.strip().lstrip("vV")
    out = []
    for part in v.split("."):
        num = "".join(ch for ch in part if ch.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out)


def data_dir() -> str:
    """Foydalanuvchi ma'lumotlari papkasi (yangilanishlar shu yerga yuklanadi)."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "TTYSI_Kadastr")


def updates_dir() -> str:
    return os.environ.get("TTYSI_UPDATES_DIR") or os.path.join(data_dir(), "updates")


def bundled_manifest() -> dict | None:
    """Ishlab turgan dastur paketi bilan kelgan manifest (manba koddan ishlaganda - None)."""
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    path = os.path.join(base, "app", "manifest.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


# ------------------------------------------------------------------ manbalar

@dataclass
class UpdateInfo:
    manifest: dict
    source: "Source"

    @property
    def version(self) -> str:
        return self.manifest["version"]

    @property
    def notes(self) -> str:
        return self.manifest.get("notes", "")

    def needs_full(self, libs: str | None) -> bool:
        """Kutubxonalar farq qiladimi (to'liq yangilanish kerak)."""
        return libs is not None and self.manifest.get("libs") != libs


class Source:
    def manifest(self) -> dict:
        raise NotImplementedError

    def download(self, name: str, dest: str, progress=None) -> None:
        raise NotImplementedError


class FolderSource(Source):
    """Tarmoq yoki mahalliy papka: update.json va zip fayllar shu papkada."""

    def __init__(self, folder: str):
        self.folder = folder

    def manifest(self) -> dict:
        with open(os.path.join(self.folder, MANIFEST_NAME), encoding="utf-8") as f:
            return json.load(f)

    def download(self, name: str, dest: str, progress=None) -> None:
        src = os.path.join(self.folder, os.path.basename(name))
        total = os.path.getsize(src)
        done = 0
        with open(src, "rb") as fi, open(dest, "wb") as fo:
            while chunk := fi.read(1 << 20):
                fo.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)


class GitHubSource(Source):
    """GitHub Releases: oxirgi reliz. Yopiq repo uchun faqat o'qish huquqli token kerak."""

    def __init__(self, repo: str = DEFAULT_REPO, token: str = ""):
        self.repo = repo
        self.token = token.strip()
        self._assets: dict[str, str] | None = None

    def _request(self, url: str, accept: str = "application/vnd.github+json"):
        req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "TTYSI-Kadastr"})
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        return urllib.request.urlopen(req, timeout=30)

    def _asset_urls(self) -> dict[str, str]:
        if self._assets is None:
            with self._request(f"https://api.github.com/repos/{self.repo}/releases/latest") as r:
                rel = json.load(r)
            self._assets = {a["name"]: a["url"] for a in rel.get("assets", [])}
        return self._assets

    def manifest(self) -> dict:
        url = self._asset_urls().get(MANIFEST_NAME)
        if not url:
            raise RuntimeError("Oxirgi relizda update.json topilmadi")
        with self._request(url, "application/octet-stream") as r:
            return json.load(r)

    def download(self, name: str, dest: str, progress=None) -> None:
        url = self._asset_urls().get(name)
        if not url:
            raise RuntimeError(f"Relizda fayl topilmadi: {name}")
        with self._request(url, "application/octet-stream") as r, open(dest, "wb") as fo:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while chunk := r.read(1 << 20):
                fo.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)


def make_source(settings: dict) -> Source:
    """settings: {"kind": "github"|"folder", "folder": ..., "repo": ..., "token": ...}"""
    if settings.get("kind") == "folder":
        return FolderSource(settings.get("folder", ""))
    return GitHubSource(settings.get("repo") or DEFAULT_REPO, settings.get("token", ""))


# ------------------------------------------------------------------ tekshirish va o'rnatish

def current_version() -> str:
    return __version__


def check(source: Source, current: str | None = None) -> UpdateInfo | None:
    """Yangi versiya bo'lsa - UpdateInfo, aks holda None."""
    m = source.manifest()
    if version_tuple(m["version"]) > version_tuple(current or current_version()):
        return UpdateInfo(m, source)
    return None


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _verify(path: str, expected: str | None) -> None:
    if expected and _sha256(path).lower() != expected.lower():
        raise RuntimeError("Yuklangan fayl buzilgan (SHA-256 mos kelmadi). Qayta urinib ko'ring.")


def install_code_update(info: UpdateInfo, progress=None) -> str:
    """Kod yangilanishini yuklaydi. Natija dastur qayta ochilganda kuchga kiradi."""
    m = info.manifest
    target = os.path.join(updates_dir(), m["version"])
    os.makedirs(updates_dir(), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="ttysi_upd_", dir=updates_dir())
    try:
        zpath = os.path.join(tmp, APP_ZIP_NAME)
        info.source.download(m["app_zip"], zpath, progress)
        _verify(zpath, m.get("app_sha256"))
        with zipfile.ZipFile(zpath) as z:
            if z.testzip() is not None or "ttysi_cadastre/__init__.py" not in z.namelist():
                raise RuntimeError("Yangilanish arxivi noto'g'ri")
        with open(os.path.join(tmp, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"version": m["version"], "libs": m.get("libs")}, f)
        if os.path.exists(target):
            shutil.rmtree(target)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            shutil.rmtree(tmp, ignore_errors=True)
    cleanup_old(keep=m["version"])
    return target


def cleanup_old(keep: str) -> None:
    """Eski kod yangilanishlarini o'chiradi (oxirgisi va ishlayotgani qoladi)."""
    d = updates_dir()
    if not os.path.isdir(d):
        return
    running = os.environ.get("TTYSI_RUNNING_VERSION")
    for name in os.listdir(d):
        if name not in (keep, running) and os.path.isdir(os.path.join(d, name)):
            shutil.rmtree(os.path.join(d, name), ignore_errors=True)


def _ps(text: str) -> str:
    """PowerShell satri: bitta tirnoq ichida, apostroflar ikkilanadi ("O'quv" kabi nomlar uchun)."""
    return "'" + text.replace("'", "''") + "'"


def install_dir() -> str:
    """Dastur papkasi (TTYSI_Kadastr.exe joylashgan)."""
    return os.path.dirname(os.path.abspath(sys.executable))


def prepare_full_update(info: UpdateInfo, progress=None) -> str:
    """To'liq paketni yuklaydi va almashtiruvchi PowerShell skriptini tayyorlaydi (yo'lini qaytaradi).

    Skript dastur yopilishini kutadi, papkani yangisi bilan almashtiradi va dasturni qayta ochadi.
    """
    if os.name != "nt" or not is_frozen():
        raise RuntimeError("To'liq yangilanish faqat Windows'dagi o'rnatilgan dasturda ishlaydi")
    m = info.manifest
    work = tempfile.mkdtemp(prefix="ttysi_full_")
    zpath = os.path.join(work, "full.zip")
    info.source.download(m["full_zip"], zpath, progress)
    _verify(zpath, m.get("full_sha256"))
    target = install_dir()
    exe = sys.executable
    script = os.path.join(work, "update.ps1")
    with open(script, "w", encoding="utf-8-sig") as f:
        f.write(f"""$ErrorActionPreference = 'Stop'
$pidToWait = {os.getpid()}
$zip = {_ps(zpath)}
$work = {_ps(work)}
$target = {_ps(target)}
$exe = {_ps(exe)}
try {{ Wait-Process -Id $pidToWait -Timeout 120 -ErrorAction SilentlyContinue }} catch {{}}
Expand-Archive -Path $zip -DestinationPath (Join-Path $work 'new') -Force
$src = Get-ChildItem (Join-Path $work 'new') -Directory | Select-Object -First 1
$backup = $target + '.old'
if (Test-Path $backup) {{ Remove-Item $backup -Recurse -Force }}
try {{
    Copy-Item $target $backup -Recurse -Force
    Get-ChildItem $src.FullName | Copy-Item -Destination $target -Recurse -Force
    Remove-Item $backup -Recurse -Force
}} catch {{
    if (Test-Path $backup) {{ Copy-Item (Join-Path $backup '*') $target -Recurse -Force }}
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("Yangilab bo'lmadi: $($_.Exception.Message)", 'TTYSI Kadastr') | Out-Null
}}
Start-Process -FilePath $exe
""")
    return script


def launch_full_update(script: str) -> None:
    """Skriptni alohida jarayonda ishga tushiradi (keyin dastur yopilishi kerak)."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                      "-File", script], creationflags=flags, close_fds=True)
