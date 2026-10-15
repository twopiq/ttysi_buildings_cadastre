"""TTYSI Binolar kadastri - sayt versiyasi (1-bosqich: ko'rish va AT belgilarini kiritish).

Ishga tushirish:
    pip install -r web/requirements.txt
    TTYSI_WORKSPACE="D:/TTYSI Binolar" python -m web.server            # http://localhost:8000

Ma'lumot - desktop dastur bilan bir xil "Binolar papkasi" (.ttysi fayllar, tashkilot = papka).
Telefon va kompyuter brauzerida ishlaydi (web/static). Batafsil reja: docs/WEB.md.
"""

from __future__ import annotations

import hmac
import io
import os
import threading
import time
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ttysi_cadastre import __version__
from ttysi_cadastre.model import Building, Equipment
from ttysi_cadastre.plan_json import building_json, equipment_types, room_kinds, valid_code
from ttysi_cadastre.workspace import is_org, orgs, scan

from .auth import ROLE_NAMES, ROLES, SESSION_DAYS, Store

STATIC = os.path.join(os.path.dirname(__file__), "static")


def default_workspace() -> str:
    return os.environ.get("TTYSI_WORKSPACE") or os.path.join(os.path.expanduser("~"), "Documents", "TTYSI Binolar")


class UserChange(BaseModel):
    login: str = Field(min_length=1, max_length=40)
    role: Literal["viewer", "editor", "admin"]
    password: str | None = Field(default=None, max_length=200)
    name: str | None = Field(default=None, max_length=80)


class EquipmentChange(BaseModel):
    """Bitta o'zgarish: add - yangi belgi, update - turi/holati/izohi/joyi, delete - o'chirish."""
    action: Literal["add", "update", "delete"]
    floor: int = Field(ge=0)
    id: str | None = None
    code: str | None = None
    x: float | None = None
    y: float | None = None
    status: Literal["existing", "planned"] | None = None
    note: str | None = Field(default=None, max_length=500)


def create_app(workspace: str | None = None, pin: str | None = None) -> FastAPI:
    """pin - kirish kodi (tarmoqqa ochilganda majburiy qilish tavsiya etiladi; TTYSI_PIN)."""
    root = os.path.abspath(workspace or default_workspace())
    pin = pin if pin is not None else os.environ.get("TTYSI_PIN", "")
    app = FastAPI(title="TTYSI Binolar kadastri", version=__version__)

    store = Store(root)
    RANK = {r: i for i, r in enumerate(ROLES)}
    OPEN = ("/api/info", "/api/login", "/api/logout", "/api/setup", "/api/me")

    def current(request: Request) -> dict | None:
        """Kirgan foydalanuvchi. Foydalanuvchilar bo'lsa - login/parol; aks holda kirish kodi yoki ochiq."""
        if store.has_users():
            return store.user_for(request.cookies.get("ttysi_session"))
        if pin:
            got = request.cookies.get("ttysi_pin") or request.headers.get("X-TTYSI-PIN")
            ok = bool(got) and hmac.compare_digest(got, pin)
            return {"login": "kod", "role": "editor", "name": "Kirish kodi bilan"} if ok else None
        return {"login": "local", "role": "admin", "name": ""}

    def need(request: Request, role: str) -> dict:
        u = request.state.user
        if RANK[u["role"]] < RANK[role]:
            raise HTTPException(403, "Bu amal uchun ruxsat yo'q")
        return u

    def is_local(request: Request) -> bool:
        return (request.client.host if request.client else "") in ("127.0.0.1", "::1", "localhost", "testclient")

    @app.middleware("http")
    async def auth(request: Request, call_next):
        p = request.url.path
        if p.startswith("/api/") and p not in OPEN:
            u = current(request)
            if u is None:
                return JSONResponse({"detail": "Kirish kerak"}, status_code=401)
            request.state.user = u
        return await call_next(request)

    @app.get("/api/me")
    def me(request: Request):
        mode = "users" if store.has_users() else ("pin" if pin else "open")
        return {"user": current(request), "mode": mode, "setup": mode != "users" and is_local(request)}

    @app.post("/api/login")
    def login(body: dict):
        if store.has_users():
            name = str(body.get("login", "")).strip().lower()
            if not store.check_password(name, str(body.get("password", ""))):
                time.sleep(0.5)
                raise HTTPException(401, "Login yoki parol noto'g'ri")
            store.log(name, "login")
            r = JSONResponse({"ok": True, "user": store.get(name)})
            r.set_cookie("ttysi_session", store.token(name), httponly=True, samesite="strict",
                         max_age=SESSION_DAYS * 86400)
            return r
        if not pin:
            return {"ok": True}
        if not hmac.compare_digest(str(body.get("pin", "")), pin):
            time.sleep(0.5)
            raise HTTPException(401, "Kod noto'g'ri")
        r = JSONResponse({"ok": True})
        r.set_cookie("ttysi_pin", pin, httponly=True, samesite="strict", max_age=30 * 86400)
        return r

    @app.post("/api/logout")
    def logout():
        r = JSONResponse({"ok": True})
        r.delete_cookie("ttysi_session")
        r.delete_cookie("ttysi_pin")
        return r

    @app.post("/api/setup")
    def setup(body: dict, request: Request):
        """Birinchi administratorni yaratish - faqat foydalanuvchi hali yo'q bo'lsa va shu kompyuterning o'zidan."""
        if store.has_users():
            raise HTTPException(409, "Administrator allaqachon bor")
        if not is_local(request):
            raise HTTPException(403, "Birinchi administrator faqat server kompyuterining o'zida yaratiladi")
        try:
            store.set_user(str(body.get("login", "")), "admin", str(body.get("password", "")), body.get("name"))
        except ValueError as e:
            raise HTTPException(422, str(e))
        return login({"login": body.get("login"), "password": body.get("password")})

    @app.get("/api/users")
    def users_list(request: Request):
        need(request, "admin")
        return {"users": store.users(), "roles": [{"role": r, "name": ROLE_NAMES[r]} for r in ROLES]}

    @app.post("/api/users")
    def users_set(body: UserChange, request: Request):
        u = need(request, "admin")
        if body.login == u["login"] and body.role != "admin" and store.admins() <= 1:
            raise HTTPException(422, "Oxirgi administratorning rolini o'zgartirib bo'lmaydi")
        try:
            store.set_user(body.login, body.role, body.password or None, body.name)
        except ValueError as e:
            raise HTTPException(422, str(e))
        store.log(u["login"], "user", target=body.login.strip().lower(), role=body.role,
                  password=bool(body.password))
        return users_list(request)

    @app.delete("/api/users")
    def users_delete(login: str, request: Request):
        u = need(request, "admin")
        if login == u["login"]:
            raise HTTPException(422, "O'zingizni o'chira olmaysiz")
        store.delete_user(login)
        store.log(u["login"], "user_delete", target=login)
        return users_list(request)

    @app.get("/api/journal")
    def journal(request: Request, id: str | None = None, limit: int = Query(50, ge=1, le=500)):
        if id is None:
            need(request, "admin")
        return {"items": store.journal(id, limit)}

    locks: dict[str, threading.Lock] = {}
    guard = threading.Lock()

    def rel(path: str) -> str:
        return os.path.relpath(path, root).replace(os.sep, "/")

    def resolve(bid: str) -> str:
        """Bino identifikatori (ish joyiga nisbatan yo'l) -> fayl. Ish joyidan tashqariga chiqib bo'lmaydi."""
        path = os.path.realpath(os.path.join(root, *bid.split("/")))
        if not path.startswith(os.path.realpath(root) + os.sep) or not path.lower().endswith(".ttysi"):
            raise HTTPException(404, "Bino topilmadi")
        if not os.path.isfile(path):
            raise HTTPException(404, "Bino topilmadi")
        return path

    def etag(path: str) -> str:
        st = os.stat(path)
        return f'"{st.st_mtime_ns}-{st.st_size}"'

    def item(it: dict) -> dict:
        return {k: it[k] for k in ("name", "address", "floors", "ready", "unknown", "planned", "counts", "time",
                                    "floor_list")} | {"id": rel(it["path"])}

    @app.get("/api/info")
    def info():
        return {"version": __version__, "equipment": equipment_types(), "room_kinds": room_kinds(),
                "pin_required": bool(pin) and not store.has_users(), "users": store.has_users()}

    @app.get("/api/workspace")
    def tree():
        if not os.path.isdir(root):
            raise HTTPException(503, f"Binolar papkasi topilmadi: {root}")
        return {"buildings": [item(i) for i in scan(root)],
                "orgs": [{"name": o["name"], "id": rel(o["path"]), "buildings": [item(i) for i in o["buildings"]]}
                         for o in orgs(root)]}

    @app.get("/api/building")
    def building(id: str = Query(...)):
        path = resolve(id)
        b = Building.load(path, images=False)
        data = building_json(b) | {"id": id, "org": org_name(path)}
        return JSONResponse(data, headers={"ETag": etag(path)})

    def org_name(path: str) -> str:
        d = os.path.dirname(path)
        return os.path.basename(d) if os.path.normcase(d) != os.path.normcase(root) and is_org(d) else ""

    @app.get("/api/floor-image")
    def floor_image(id: str = Query(...), floor: int = Query(..., ge=0)):
        path = resolve(id)
        data = Building.read_image(path, floor)
        if not data:
            raise HTTPException(404, "Rasm yo'q")
        mime = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
        return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=300"})

    @app.post("/api/equipment")
    def change(ch: EquipmentChange, request: Request, id: str = Query(...),
               if_match: str | None = Header(default=None)):
        """AT belgisini qo'shish/o'zgartirish/o'chirish. If-Match - boshqa joyda (dastur yoki boshqa
        telefon) o'zgartirilgan bo'lsa 409 qaytadi va foydalanuvchi yangilab oladi."""
        user = need(request, "editor")
        path = resolve(id)
        with guard:
            lock = locks.setdefault(path, threading.Lock())
        with lock:
            if if_match and if_match != etag(path):
                raise HTTPException(409, "Bino boshqa joyda o'zgartirilgan - sahifani yangilang")
            b = Building.load(path)
            if ch.floor >= len(b.floors):
                raise HTTPException(404, "Etaj topilmadi")
            f = b.floors[ch.floor]
            if ch.code is not None and not valid_code(ch.code):
                raise HTTPException(422, f"Noma'lum jihoz turi: {ch.code}")
            target = before = None
            if ch.action != "add":
                target = next((e for e in f.equipment if e.id == ch.id), None)
                if target is None:
                    raise HTTPException(404, "Belgi topilmadi")
                before = target.code if ch.action == "delete" or ch.code != target.code else None
            if ch.action == "add":
                if ch.code is None or ch.x is None or ch.y is None:
                    raise HTTPException(422, "code, x, y kerak")
                f.equipment.append(Equipment(code=ch.code, x=min(max(ch.x, 0), f.width),
                                             y=min(max(ch.y, 0), f.height), note=ch.note or "",
                                             status=ch.status or "existing"))
            elif ch.action == "delete":
                f.equipment.remove(target)
            else:
                if ch.code is not None:
                    target.code = ch.code
                if ch.status is not None:
                    target.status = ch.status
                if ch.note is not None:
                    target.note = ch.note
                if ch.x is not None and ch.y is not None:
                    target.x, target.y = min(max(ch.x, 0), f.width), min(max(ch.y, 0), f.height)
            b.save(path)
            store.log(user["login"], ch.action, building=id, floor=f.name,
                      code=ch.code or (target.code if target else None),
                      was=(before if ch.action != "add" else None))
            data = building_json(b) | {"id": id, "org": org_name(path)}
            return JSONResponse(data, headers={"ETag": etag(path)})

    @app.get("/api/report.xlsx")
    def report(id: str | None = None, org: str | None = None):
        from ttysi_cadastre.report import export_excel
        if id:
            path = resolve(id)
            buildings, title, name = [Building.load(path, images=False)], None, os.path.splitext(os.path.basename(path))[0]
        elif org:
            d = os.path.realpath(os.path.join(root, org))
            if os.path.dirname(d) != os.path.realpath(root) or not is_org(d):
                raise HTTPException(404, "Tashkilot topilmadi")
            buildings = [Building.load(i["path"], images=False) for i in scan(d)]
            title = name = os.path.basename(d)
        else:
            raise HTTPException(422, "id yoki org kerak")
        buf = io.BytesIO()
        export_excel(buf, buildings, title=title)
        from urllib.parse import quote
        return Response(buf.getvalue(),
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name + ' - hisobot.xlsx')}"})

    @app.get("/")
    def index():
        return FileResponse(os.path.join(STATIC, "index.html"))

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def main() -> None:
    import argparse

    import uvicorn
    ap = argparse.ArgumentParser(description="TTYSI kadastr sayti")
    ap.add_argument("--workspace", default=None, help="Binolar papkasi (yoki TTYSI_WORKSPACE)")
    ap.add_argument("--host", default="127.0.0.1",
                    help="0.0.0.0 - shu tarmoqdagi telefonlar ham kira oladi (unda --pin bering)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--pin", default=None, help="kirish kodi (yoki TTYSI_PIN)")
    a = ap.parse_args()
    ws = os.path.abspath(a.workspace or default_workspace())
    if a.host not in ("127.0.0.1", "localhost") and not Store(ws).has_users() and \
            not (a.pin or os.environ.get("TTYSI_PIN")):
        print("Ogohlantirish: tarmoqqa ochiq, lekin foydalanuvchi ham, kirish kodi ham yo'q. Har kim o'zgartira oladi.\n"
              f"Administrator yarating: shu kompyuterda http://localhost:{a.port} ni oching.")
    uvicorn.run(create_app(a.workspace, a.pin), host=a.host, port=a.port)


if __name__ == "__main__":
    main()
