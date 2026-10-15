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
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ttysi_cadastre import __version__
from ttysi_cadastre.model import Building, Equipment
from ttysi_cadastre.plan_json import building_json, equipment_types, room_kinds, valid_code
from ttysi_cadastre.detection import DetectParams, decode_image, encode_jpg, limit_size
from ttysi_cadastre.geometry import bg_unmap
from ttysi_cadastre.metrics import meter_px
from ttysi_cadastre.floor_build import is_pdf, load_upload, new_floor, pdf_page_count, render_pdf
from ttysi_cadastre.workspace import create_building, create_org, is_org, orgs, scan

from .auth import ROLE_NAMES, ROLES, SESSION_DAYS, Store

STATIC = os.path.join(os.path.dirname(__file__), "static")


def default_workspace() -> str:
    return os.environ.get("TTYSI_WORKSPACE") or os.path.join(os.path.expanduser("~"), "Documents", "TTYSI Binolar")


MAX_UPLOAD = 60 * 2**20


class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class BuildingIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    address: str | None = Field(default=None, max_length=300)
    org: str | None = None


class FloorIn(BaseModel):
    token: str
    page: int = Field(default=0, ge=0)
    name: str | None = Field(default=None, max_length=80)
    ratio: int = Field(default=0, ge=0, le=100000)
    auto: bool = True
    straighten: bool = True
    sensitivity: float = Field(default=0.5, ge=0, le=1)


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

    @app.get("/api/mark-crop")
    def mark_crop(id: str = Query(...), floor: int = Query(..., ge=0), x: float = Query(...), y: float = Query(...)):
        """Belgi atrofidagi asl kadastr rasmi bo'lagi (~5 m) - qo'lyozmaga qarab turini tanlash uchun."""
        import cv2
        import numpy as np
        path = resolve(id)
        b = Building.load(path, images=False)
        if floor >= len(b.floors):
            raise HTTPException(404, "Etaj topilmadi")
        f = b.floors[floor]
        data = Building.read_image(path, floor)
        if not data:
            raise HTTPException(404, "Rasm yo'q")
        img = decode_image(data)
        k = img.shape[1] / max(1, f.width)                       # etaj -> rasm piksellari
        ix, iy = (v * k for v in bg_unmap(f, x, y))
        half = max(meter_px(f) * 2.5, 60) * k / max(0.1, f.bg_scale)
        W, H = 360, 240
        hw, hh = half * W / H, half
        src = np.float32([[ix - hw, iy - hh], [ix + hw, iy - hh], [ix - hw, iy + hh]])
        dst = np.float32([[0, 0], [W, 0], [0, H]])
        out = cv2.warpAffine(img, cv2.getAffineTransform(src, dst), (W, H), flags=cv2.INTER_AREA,
                             borderMode=cv2.BORDER_CONSTANT, borderValue=(245, 245, 245))
        cv2.circle(out, (W // 2, H // 2), int(H * 0.22), (40, 40, 211), 2, cv2.LINE_AA)
        return Response(encode_jpg(out, 85), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=300"})

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

    # ------------------------------------------------------------ yangi bino, tashkilot, etaj yuklash
    uploads = os.path.join(store.dir, "uploads")
    jobs: dict[str, dict] = {}
    pool = ThreadPoolExecutor(max_workers=2)

    @app.post("/api/orgs")
    def org_create(body: NameIn, request: Request):
        u = need(request, "admin")
        path = create_org(root, body.name)
        store.log(u["login"], "org_add", target=os.path.basename(path))
        return {"id": rel(path), "name": os.path.basename(path)}

    @app.post("/api/buildings")
    def building_create(body: BuildingIn, request: Request):
        u = need(request, "editor")
        folder = root
        if body.org:
            folder = os.path.realpath(os.path.join(root, body.org))
            if os.path.dirname(folder) != os.path.realpath(root) or not is_org(folder):
                raise HTTPException(404, "Tashkilot topilmadi")
        path = create_building(folder, body.name, body.address or "")
        store.log(u["login"], "building_add", building=rel(path))
        return {"id": rel(path)}

    def upload_path(token: str) -> str:
        if not token.isalnum() or len(token) != 32:
            raise HTTPException(404, "Fayl topilmadi (qaytadan yuklang)")
        p = os.path.join(uploads, token)
        if not os.path.isfile(p):
            raise HTTPException(404, "Fayl topilmadi (qaytadan yuklang)")
        return p

    @app.post("/api/upload")
    async def upload(request: Request, file: UploadFile = File(...)):
        """Kadastr fayli (PDF yoki rasm) vaqtincha saqlanadi; PDF bo'lsa sahifalar soni qaytadi."""
        need(request, "editor")
        data = await file.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, f"Fayl juda katta ({MAX_UPLOAD // 2**20} MB gacha)")
        pages = 1
        try:
            if is_pdf(data):
                pages = pdf_page_count(data)
            elif decode_image(data) is None:
                raise ValueError
        except Exception:
            raise HTTPException(422, "Faylni o'qib bo'lmadi: PDF, JPG yoki PNG yuboring")
        os.makedirs(uploads, exist_ok=True)
        for old in os.listdir(uploads):                      # bir kundan eski vaqtinchalik fayllar
            p = os.path.join(uploads, old)
            if time.time() - os.path.getmtime(p) > 86400:
                os.remove(p)
        token = secrets.token_hex(16)
        with open(os.path.join(uploads, token), "wb") as f:
            f.write(data)
        return {"token": token, "kind": "pdf" if is_pdf(data) else "image", "pages": pages}

    @app.get("/api/upload/preview")
    def upload_preview(request: Request, token: str, page: int = Query(0, ge=0)):
        need(request, "editor")
        with open(upload_path(token), "rb") as f:
            data = f.read()
        try:
            img, _ = render_pdf(data, page, dpi=40) if is_pdf(data) else (decode_image(data), None)
        except ValueError as e:
            raise HTTPException(422, str(e))
        img = limit_size(img, 900)
        return Response(encode_jpg(img, 80), media_type="image/jpeg")

    @app.post("/api/floors")
    def floor_create(body: FloorIn, request: Request, id: str = Query(...)):
        """Yuklangan fayldan yangi etaj (fon vazifasi): xonalar, eshiklar va AT belgilari nomzodlari topiladi."""
        u = need(request, "editor")
        path = resolve(id)
        src = upload_path(body.token)
        job = secrets.token_hex(8)
        jobs[job] = {"status": "queued", "message": "Navbatda…"}

        def work():
            st = jobs[job]
            try:
                st.update(status="running", message="Rasm tayyorlanmoqda…")
                with open(src, "rb") as f:
                    data = f.read()
                img, paper = load_upload(data, body.page, straighten=body.straighten)
                st["message"] = "Xonalar va AT belgilari aniqlanmoqda…" if body.auto else "Etaj yaratilmoqda…"
                params = DetectParams(blue_sensitivity=body.sensitivity)
                with guard:
                    lock = locks.setdefault(path, threading.Lock())
                with lock:
                    b = Building.load(path)
                    name = (body.name or "").strip() or f"{len(b.floors) + 1}-qavat"
                    floor, msg = new_floor(img, name, paper, body.ratio, auto=body.auto, params=params)
                    b.floors.append(floor)
                    b.save(path)
                store.log(u["login"], "floor_add", building=id, floor=floor.name,
                          rooms=len(floor.rooms), marks=sum(1 for e in floor.equipment if e.code == "?"))
                st.update(status="done", message=msg, floor=len(b.floors) - 1)
                try:
                    os.remove(src)
                except OSError:
                    pass
            except Exception as e:                       # noqa: BLE001 - foydalanuvchiga ko'rsatiladi
                st.update(status="error", message=f"Etaj yaratilmadi: {e}")
        pool.submit(work)
        return {"job": job}

    @app.get("/api/jobs/{job}")
    def job_status(job: str):
        if job not in jobs:
            raise HTTPException(404, "Vazifa topilmadi")
        return jobs[job]

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
