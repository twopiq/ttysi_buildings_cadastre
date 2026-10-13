# PyInstaller sozlamasi.
#   python tools/release.py app      (avval: dastur kodi arxivi va manifest)
#   pyinstaller build.spec
# Natija: dist/TTYSI_Kadastr/TTYSI_Kadastr.exe
#
# Dastur kodi (ttysi_cadastre) .exe ichiga kompilyatsiya qilinmaydi - u alohida
# app/ttysi_cadastre.zip da turadi. Shu tufayli kod yangilanishi uchun .exe ni qayta
# yig'ish shart emas (run.py va ttysi_cadastre/updater.py ga qarang).
import os

a = Analysis(
    ["run.py"],
    pathex=["."],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtPdf", "shapely", "ezdxf", "openpyxl",
                   # kod yangilanishlarida kerak bo'lishi mumkin bo'lgan standart modullar
                   "urllib.request", "ssl", "hashlib", "zipfile", "tempfile", "subprocess",
                   "shutil", "uuid", "csv", "html", "difflib", "statistics", "itertools"],
    datas=[(os.path.join("build", "app", "ttysi_cadastre.zip"), "app"),
           (os.path.join("build", "app", "manifest.json"), "app")],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "tkinter", "matplotlib"],
)
# dastur kodi PYZ ga kirmaydi (aks holda zip'dagi yangilanish o'rniga eski kod yuklanardi)
a.pure = [m for m in a.pure if not (m[0] == "ttysi_cadastre" or m[0].startswith("ttysi_cadastre."))]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TTYSI_Kadastr",
          console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="TTYSI_Kadastr", upx=False)
