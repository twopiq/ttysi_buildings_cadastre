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


def _wait(cond, ms=8000):
    from PySide6.QtTest import QTest
    for _ in range(ms // 50):
        if cond():
            return True
        QTest.qWait(50)
    return cond()


def _ui(monkeypatch, net):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from ttysi_cadastre.ui import update_dialog
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(update_dialog, "load_settings",
                        lambda: {"kind": "folder", "folder": str(net), "repo": "", "token": "", "auto": False})
    from ttysi_cadastre.ui.main_window import MainWindow
    return MainWindow()


def test_ui_background_check_source_mode(tmp_path, monkeypatch):
    """Manba koddan ishlaganda: yangi versiya haqida tepada panel chiqadi, hech narsa yuklanmaydi."""
    monkeypatch.setenv("TTYSI_UPDATES_DIR", str(tmp_path / "upd"))
    net = _publish(tmp_path, "99.1.0", "Yangi imkoniyatlar")
    w = _ui(monkeypatch, net)
    w.updater.check(silent=True)
    assert _wait(lambda: w.updater.state == "available")
    assert not w.update_banner.isHidden()
    assert "99.1.0" in w.update_banner.text.text() and "git pull" in w.update_banner.text.text()
    assert not os.path.exists(tmp_path / "upd" / "99.1.0")
    w.dirty = False
    w.close()


def test_ui_auto_download_and_ready(tmp_path, monkeypatch):
    """O'rnatilgan dastur: kod yangilanishi so'ramasdan fonda yuklanadi, panelda "Qayta ochish"."""
    monkeypatch.setenv("TTYSI_UPDATES_DIR", str(tmp_path / "upd"))
    net = _publish(tmp_path, "99.2.0", "- Bosh sahifa\n- Tezroq eksport")
    libs = json.loads((net / "update.json").read_text())["libs"]
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    monkeypatch.setattr(updater, "bundled_manifest", lambda: {"version": "0.0.1", "libs": libs})
    w = _ui(monkeypatch, net)
    w.updater.check(silent=True)
    assert _wait(lambda: w.updater.state in ("ready", "error")), w.updater.state
    assert w.updater.state == "ready", w.updater.error
    assert updater.downloaded("99.2.0")["notes"].startswith("- Bosh sahifa")
    assert w.update_banner.act.text() == "Qayta ochish"
    # qayta tekshirilsa - qayta yuklanmaydi
    w.updater.state = "idle"
    w.updater.check(silent=True)
    assert _wait(lambda: w.updater.state == "ready")
    # ishga tushmagan (BROKEN) versiya - to'liq paket taklif qilinadi
    open(tmp_path / "upd" / "99.2.0" / "BROKEN", "w").close()
    w.updater.state = "idle"
    w.updater.check(silent=True)
    assert _wait(lambda: w.updater.state == "available")
    assert w.updater.full and w.update_banner.act.text() == "Yuklab o'rnatish"
    w.update_banner.dismiss()
    assert w.update_banner.isHidden()
    w.dirty = False
    w.close()


def test_ui_error_is_friendly(tmp_path, monkeypatch):
    w = _ui(monkeypatch, tmp_path / "yoq_papka")
    w.updater.check(silent=True)
    assert _wait(lambda: w.updater.state == "error")
    assert "topilmadi" in w.updater.message()
    assert w.update_banner.isHidden()                        # fonda xato - bezovta qilmaydi
    assert w.updater.action() == "Qayta urinish"
    w.dirty = False
    w.close()


def test_github_private_repo_message(monkeypatch):
    import urllib.error
    src = updater.GitHubSource("x/y")

    def fail(url, accept=""):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
    monkeypatch.setattr(src, "_request", fail)
    with pytest.raises(updater.UpdateError, match="token"):
        src.manifest()
    assert "Internetga" in updater.friendly_error(urllib.error.URLError("x"))


def test_whats_new_after_update(monkeypatch):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from ttysi_cadastre.ui import update_dialog
    QApplication.instance() or QApplication([])
    shown = []
    monkeypatch.setattr(update_dialog.NotesDialog, "exec", lambda self: shown.append(self.windowTitle()))
    QSettings("TTYSI", "BinolarKadastr").setValue("app/last_version", "0.0.1")
    assert update_dialog.show_whats_new(None) and shown
    assert not update_dialog.show_whats_new(None)            # faqat bir marta
    html = update_dialog.notes_html("Yangiliklar:\n- Bosh sahifa\n- Eksport")
    assert "<li>Bosh sahifa</li>" in html and "<p>Yangiliklar:</p>" in html
