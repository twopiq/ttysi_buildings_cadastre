"""Reliz fayllarini tayyorlash (GitHub Actions va qo'lda ishlatish uchun).

  python tools/release.py app            -> build/app/ttysi_cadastre.zip + build/app/manifest.json
                                            (.exe ichiga joylanadi, build.spec ishlatadi)
  python tools/release.py publish OUTDIR --full TTYSI_Kadastr_Windows.zip [--notes "..."]
                                         -> OUTDIR/update.json, OUTDIR/ttysi_app-<versiya>.zip
                                            (relizga yoki tarmoq papkasiga qo'yiladi)

"libs" - kutubxonalar belgisi: requirements.txt, build.spec, run.py va Python versiyasining xeshi.
U o'zgarmasa, foydalanuvchilarga faqat kichik kod arxivi yuboriladi; o'zgarsa - to'liq paket.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "ttysi_cadastre")


def version() -> str:
    with open(os.path.join(PKG, "__init__.py"), encoding="utf-8") as f:
        return re.search(r'__version__\s*=\s*"([^"]+)"', f.read()).group(1)


def libs_id() -> str:
    h = hashlib.sha256()
    for name in ("requirements.txt", "build.spec", "run.py"):
        with open(os.path.join(ROOT, name), "rb") as f:
            h.update(f.read().replace(b"\r\n", b"\n"))
    h.update(f"python{sys.version_info.major}.{sys.version_info.minor}".encode())
    return h.hexdigest()[:16]


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def build_app_zip(dest: str) -> None:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, dirs, files in os.walk(PKG):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fn in sorted(files):
                # kod va unga kerakli fayllar (shriftlar, litsenziya) - zip ichidan o'qiladi
                if fn.endswith((".py", ".woff", ".txt")):
                    full = os.path.join(folder, fn)
                    z.write(full, os.path.relpath(full, ROOT).replace(os.sep, "/"))


def cmd_app(_args) -> None:
    out = os.path.join(ROOT, "build", "app")
    os.makedirs(out, exist_ok=True)
    build_app_zip(os.path.join(out, "ttysi_cadastre.zip"))
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"version": version(), "libs": libs_id()}, f)
    print("app:", version(), libs_id())


def clean_notes(text: str) -> str:
    """Commit xabaridan foydalanuvchiga ko'rinadigan izoh: texnik qatorlar va [release] olib tashlanadi."""
    skip = ("co-authored-by:", "claude-session:", "signed-off-by:")
    lines = [ln.replace("[release]", "").rstrip() for ln in (text or "").splitlines()
             if not ln.strip().lower().startswith(skip)]
    return "\n".join(lines).strip()


def cmd_publish(args) -> None:
    os.makedirs(args.outdir, exist_ok=True)
    v = version()
    app_name = f"ttysi_app-{v}.zip"
    app_path = os.path.join(args.outdir, app_name)
    build_app_zip(app_path)
    manifest = {"version": v, "libs": libs_id(), "notes": clean_notes(args.notes),
                "app_zip": app_name, "app_sha256": sha256(app_path)}
    if args.full:
        full_name = os.path.basename(args.full)
        if os.path.abspath(os.path.dirname(args.full)) != os.path.abspath(args.outdir):
            shutil.copy2(args.full, os.path.join(args.outdir, full_name))
        manifest.update(full_zip=full_name, full_sha256=sha256(args.full))
    with open(os.path.join(args.outdir, "update.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print(json.dumps(manifest, ensure_ascii=False, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("app")
    p = sub.add_parser("publish")
    p.add_argument("outdir")
    p.add_argument("--full")
    p.add_argument("--notes")
    args = ap.parse_args()
    {"app": cmd_app, "publish": cmd_publish}[args.cmd](args)


if __name__ == "__main__":
    main()
