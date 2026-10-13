"""Dasturni ishga tushirish: python run.py

O'rnatilgan (.exe) dasturda bu fayl "qobiq" vazifasini bajaradi: dastur kodi (ttysi_cadastre)
.exe ichida emas, alohida zip arxivda turadi. Ishga tushishda eng yangi mos kod tanlanadi:
  1. %LOCALAPPDATA%/TTYSI_Kadastr/updates/<versiya>/ttysi_cadastre.zip - yuklangan yangilanishlar
     (faqat kutubxonalari - "libs" - shu .exe bilan bir xil bo'lganlari);
  2. aks holda .exe bilan kelgan app/ttysi_cadastre.zip.
Yangilangan kod ishga tushmasa, u "buzilgan" deb belgilanadi va o'rnatilgan kod ishlatiladi.

Bu faylni yangilanish o'zgartira olmaydi - u faqat to'liq qayta yig'ishda yangilanadi.
"""

import json
import os
import sys


def _vt(v):
    return tuple(int("".join(c for c in p if c.isdigit()) or 0) for p in v.strip().lstrip("vV").split("."))


def _updates_dir():
    # ttysi_cadastre/updater.py dagi updates_dir() bilan bir xil bo'lishi kerak
    if os.environ.get("TTYSI_UPDATES_DIR"):
        return os.environ["TTYSI_UPDATES_DIR"]
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "TTYSI_Kadastr", "updates")


def _candidates():
    """(versiya, zip yo'li, yangilanish papkasi yoki None) - eng yangisi birinchi."""
    base = getattr(sys, "_MEIPASS", None)
    man_path = os.path.join(base, "app", "manifest.json") if base else None
    if not man_path or not os.path.exists(man_path):
        return []  # manba koddan ishlayapti - oddiy import
    with open(man_path, encoding="utf-8") as f:
        bundled = json.load(f)
    out = [(_vt(bundled["version"]), os.path.join(base, "app", "ttysi_cadastre.zip"), None)]
    upd = _updates_dir()
    if os.path.isdir(upd):
        for name in os.listdir(upd):
            d = os.path.join(upd, name)
            try:
                if os.path.exists(os.path.join(d, "BROKEN")):
                    continue
                with open(os.path.join(d, "manifest.json"), encoding="utf-8") as f:
                    m = json.load(f)
                z = os.path.join(d, "ttysi_cadastre.zip")
                if m.get("libs") == bundled.get("libs") and os.path.exists(z):
                    out.append((_vt(m["version"]), z, d))
            except (OSError, ValueError, KeyError):
                continue
    out.sort(key=lambda c: c[0], reverse=True)
    return out


def _load():
    """ttysi_cadastre ni eng yangi ishlaydigan arxivdan yuklaydi; (main funksiya, manba) qaytaradi."""
    cands = _candidates()
    if not cands:
        from ttysi_cadastre.__main__ import main
        return main, "source"
    last_error = None
    for _, zpath, upd_dir in cands:
        sys.path.insert(0, zpath)
        try:
            import ttysi_cadastre
            from ttysi_cadastre.__main__ import main
            os.environ["TTYSI_RUNNING_VERSION"] = ttysi_cadastre.__version__
            return main, zpath
        except Exception as e:  # yangilanish buzilgan - keyingisiga o'tamiz
            last_error = e
            sys.path.remove(zpath)
            for mod in [m for m in sys.modules if m == "ttysi_cadastre" or m.startswith("ttysi_cadastre.")]:
                del sys.modules[mod]
            if upd_dir:
                try:
                    with open(os.path.join(upd_dir, "BROKEN"), "w", encoding="utf-8") as f:
                        f.write(repr(e))
                except OSError:
                    pass
    raise last_error


def _self_test(out_path):
    """CI uchun: kodni yuklab, oynani ekransiz ochib yopadi va natijani faylga yozadi."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    main, source = _load()
    import ttysi_cadastre
    from PySide6.QtWidgets import QApplication
    from ttysi_cadastre.ui.main_window import MainWindow
    app = QApplication([])
    w = MainWindow()
    w.dirty = False
    w.close()
    app.quit()
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"version": ttysi_cadastre.__version__, "source": source}, f)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--self-test":
        _self_test(sys.argv[2])
        sys.exit(0)
    main, _ = _load()
    main()
