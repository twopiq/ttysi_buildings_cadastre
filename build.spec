# PyInstaller sozlamasi: pyinstaller build.spec
# Natija: dist/TTYSI_Kadastr/TTYSI_Kadastr.exe

a = Analysis(
    ["run.py"],
    pathex=["."],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtPdf", "shapely", "ezdxf", "openpyxl"],
    excludes=["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "tkinter", "matplotlib"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="TTYSI_Kadastr",
          console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="TTYSI_Kadastr", upx=False)
