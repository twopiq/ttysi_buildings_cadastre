"""Sayt foydalanuvchilari, rollar va o'zgarishlar jurnali (faqat standart kutubxona).

Ma'lumot binolar papkasining ichida, yashirin papkada: <ish joyi>/.ttysi-web/
    users.json      foydalanuvchilar (parol - PBKDF2 xeshi, ochiq holda saqlanmaydi) va sessiya kaliti
    journal.jsonl   har bir o'zgarish: kim, qachon, qaysi bino/etaj, nima qildi

Rollar:
    viewer  - faqat ko'rish va hisobot yuklab olish
    editor  - AT belgilarini qo'shish/o'zgartirish/o'chirish
    admin   - hammasi + foydalanuvchilarni boshqarish

Buyruq qatoridan:
    python -m web.auth --workspace "D:/TTYSI Binolar" add admin --role admin
    python -m web.auth --workspace "D:/TTYSI Binolar" list
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time

ROLES = ("viewer", "editor", "admin")
ROLE_NAMES = {"viewer": "Ko'ruvchi", "editor": "Tahrirlovchi", "admin": "Administrator"}
ITERATIONS = 200_000
SESSION_DAYS = 30


def _hash(password: str, salt: str | None = None, iterations: int = ITERATIONS) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return f"pbkdf2${iterations}${salt}${dk.hex()}"


def _check(password: str, stored: str) -> bool:
    try:
        _, it, salt, _h = stored.split("$")
        return hmac.compare_digest(_hash(password, salt, int(it)), stored)
    except ValueError:
        return False


class Store:
    def __init__(self, workspace: str):
        self.dir = os.path.join(workspace, ".ttysi-web")
        self.users_path = os.path.join(self.dir, "users.json")
        self.journal_path = os.path.join(self.dir, "journal.jsonl")
        self.lock = threading.Lock()
        self._cache: tuple[tuple, dict] | None = None

    # ------------------------------------------------------------ foydalanuvchilar
    def _load(self) -> dict:
        try:
            st = os.stat(self.users_path)
            m = (st.st_mtime_ns, st.st_size, st.st_ino)
        except OSError:
            return {"users": {}, "secret": ""}
        if self._cache is None or self._cache[0] != m:
            with open(self.users_path, encoding="utf-8") as f:
                self._cache = (m, json.load(f))
        return self._cache[1]

    def _save(self, data: dict) -> None:
        os.makedirs(self.dir, exist_ok=True)
        tmp = self.users_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.users_path)
        self._cache = None

    def has_users(self) -> bool:
        return bool(self._load()["users"])

    def users(self) -> list[dict]:
        return [{"login": k, "role": v["role"], "name": v.get("name", "")}
                for k, v in sorted(self._load()["users"].items())]

    def get(self, login: str) -> dict | None:
        u = self._load()["users"].get(login)
        return {"login": login, "role": u["role"], "name": u.get("name", "")} if u else None

    def set_user(self, login: str, role: str, password: str | None = None, name: str | None = None) -> None:
        login = login.strip().lower()
        if not login or not login.replace("_", "").replace(".", "").replace("-", "").isalnum() or len(login) > 40:
            raise ValueError("Login: harf, raqam, '.', '_', '-' (40 belgigacha)")
        if role not in ROLES:
            raise ValueError("Noma'lum rol")
        with self.lock:
            data = json.loads(json.dumps(self._load()))
            data.setdefault("secret", "")
            u = data["users"].get(login)
            if u is None and not password:
                raise ValueError("Yangi foydalanuvchiga parol kerak")
            if password is not None and len(password) < 6:
                raise ValueError("Parol kamida 6 belgi bo'lsin")
            u = u or {}
            u["role"] = role
            if name is not None:
                u["name"] = name.strip()[:80]
            if password:
                u["hash"] = _hash(password)
                u["gen"] = u.get("gen", 0) + 1            # parol o'zgarsa eski sessiyalar bekor bo'ladi
            data["users"][login] = u
            if not data["secret"]:
                data["secret"] = secrets.token_hex(32)
            self._save(data)

    def delete_user(self, login: str) -> None:
        with self.lock:
            data = json.loads(json.dumps(self._load()))
            data["users"].pop(login, None)
            self._save(data)

    def admins(self) -> int:
        return sum(1 for u in self._load()["users"].values() if u["role"] == "admin")

    def check_password(self, login: str, password: str) -> bool:
        u = self._load()["users"].get(login.strip().lower())
        if not u:
            _hash(password)                                   # vaqt bo'yicha farq qilmasin
            return False
        return _check(password, u["hash"])

    # ------------------------------------------------------------ sessiya
    def token(self, login: str) -> str:
        data = self._load()
        exp = int(time.time()) + SESSION_DAYS * 86400
        changed = data["users"][login].get("gen", 0)
        msg = f"{login}|{exp}|{changed}"
        sig = hmac.new(bytes.fromhex(data["secret"]), msg.encode(), hashlib.sha256).hexdigest()
        return f"{msg}|{sig}"

    def user_for(self, token: str | None) -> dict | None:
        if not token:
            return None
        try:
            login, exp, changed, sig = token.split("|")
        except ValueError:
            return None
        data = self._load()
        u = data["users"].get(login)
        if not u or not data.get("secret") or int(exp) < time.time() or int(changed) != u.get("gen", 0):
            return None
        good = hmac.new(bytes.fromhex(data["secret"]), f"{login}|{exp}|{changed}".encode(), hashlib.sha256).hexdigest()
        return self.get(login) if hmac.compare_digest(good, sig) else None

    # ------------------------------------------------------------ jurnal
    def log(self, user: str, action: str, **details) -> None:
        rec = {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "user": user, "action": action, **details}
        with self.lock:
            os.makedirs(self.dir, exist_ok=True)
            with open(self.journal_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def journal(self, building: str | None = None, limit: int = 50) -> list[dict]:
        try:
            with open(self.journal_path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return []
        out = []
        for ln in reversed(lines):
            try:
                rec = json.loads(ln)
            except ValueError:
                continue
            if building and rec.get("building") != building:
                continue
            out.append(rec)
            if len(out) >= limit:
                break
        return out


def main() -> None:
    import argparse
    import getpass
    ap = argparse.ArgumentParser(description="Sayt foydalanuvchilari")
    ap.add_argument("--workspace", default=os.environ.get("TTYSI_WORKSPACE"), required=not os.environ.get("TTYSI_WORKSPACE"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="qo'shish yoki parol/rolni o'zgartirish")
    a.add_argument("login")
    a.add_argument("--role", choices=ROLES, default="editor")
    a.add_argument("--name", default=None)
    sub.add_parser("list")
    d = sub.add_parser("delete")
    d.add_argument("login")
    args = ap.parse_args()
    st = Store(args.workspace)
    if args.cmd == "add":
        pw = getpass.getpass("Parol: ")
        if pw != getpass.getpass("Parol (yana): "):
            raise SystemExit("Parollar mos emas")
        st.set_user(args.login, args.role, pw, args.name)
        print(f"Saqlandi: {args.login} ({ROLE_NAMES[args.role]})")
    elif args.cmd == "list":
        for u in st.users():
            print(f"{u['login']:20} {ROLE_NAMES[u['role']]:15} {u['name']}")
    else:
        st.delete_user(args.login)
        print("O'chirildi")


if __name__ == "__main__":
    main()
