import json
import os
import subprocess
import sys
import zipfile

import pytest

from ttysi_cadastre import updater

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_version_compare():
    assert updater.version_tuple("v0.10.0") > updater.version_tuple("0.9.9")
    assert updater.version_tuple("1.2") == (1, 2)


def _publish(tmp_path, version, notes="yangi"):
    """Repo nusxasida versiyani o'zgartirib, tools/release.py publish bilan yangilanish papkasini yasaydi."""
    import shutil
    repo = tmp_path / f"repo_{version}"
    shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns(".git", "build", "dist", "__pycache__"))
    init = repo / "ttysi_cadastre" / "__init__.py"
    init.write_text(init.read_text().replace(f'"{updater.current_version()}"', f'"{version}"'))
    out = tmp_path / "net"
    subprocess.run([sys.executable, str(repo / "tools" / "release.py"), "publish", str(out), "--notes", notes],
                   check=True, capture_output=True)
    return out


def test_folder_update_install(tmp_path, monkeypatch):
    monkeypatch.setenv("TTYSI_UPDATES_DIR", str(tmp_path / "upd"))
    net = _publish(tmp_path, "99.0.0", "Eshik va zinalar")
    src = updater.FolderSource(str(net))
    info = updater.check(src)
    assert info is not None and info.version == "99.0.0" and info.notes == "Eshik va zinalar"
    assert updater.check(src, current="99.0.0") is None          # eng yangisi bo'lsa - None
    man = json.loads((net / "update.json").read_text())
    assert not info.needs_full(man["libs"]) and info.needs_full("boshqa")

    seen = []
    target = updater.install_code_update(info, lambda d, t: seen.append((d, t)))
    assert seen and seen[-1][0] == seen[-1][1]
    with zipfile.ZipFile(os.path.join(target, "ttysi_cadastre.zip")) as z:
        assert '__version__ = "99.0.0"' in z.read("ttysi_cadastre/__init__.py").decode()
    assert json.loads(open(os.path.join(target, "manifest.json")).read())["version"] == "99.0.0"


def test_corrupted_download_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("TTYSI_UPDATES_DIR", str(tmp_path / "upd"))
    net = _publish(tmp_path, "99.0.1")
    man = json.loads((net / "update.json").read_text())
    with open(net / man["app_zip"], "ab") as f:
        f.write(b"buzuq")                                         # tarmoqda buzilgan fayl
    info = updater.check(updater.FolderSource(str(net)))
    with pytest.raises(RuntimeError, match="SHA-256"):
        updater.install_code_update(info)
    assert not os.path.exists(tmp_path / "upd" / "99.0.1")


def test_full_update_only_on_windows_exe():
    info = updater.UpdateInfo({"version": "9.9.9", "full_zip": "x.zip"}, updater.FolderSource("."))
    if os.name != "nt" or not updater.is_frozen():
        with pytest.raises(RuntimeError):
            updater.prepare_full_update(info)


def test_powershell_quoting():
    assert updater._ps(r"C:\O'quv\TTYSI") == r"'C:\O''quv\TTYSI'"


def test_ui_background_check(tmp_path, monkeypatch):
    """Fonda tekshirish natijasi asosiy oynaga yetib keladi (oyna qotmaydi)."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QMessageBox
    from ttysi_cadastre.ui import update_dialog
    from ttysi_cadastre.ui.main_window import MainWindow
    QApplication.instance() or QApplication([])
    net = _publish(tmp_path, "99.1.0", "Yangi imkoniyatlar")
    monkeypatch.setattr(update_dialog, "load_settings",
                        lambda: {"kind": "folder", "folder": str(net), "repo": "", "token": "", "auto": False})
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: shown.append(a[2]))
    w = MainWindow()
    w.updater.check(silent=True)
    for _ in range(100):
        if shown:
            break
        QTest.qWait(50)
    assert shown and "99.1.0" in shown[0]
    w.dirty = False
    w.close()
