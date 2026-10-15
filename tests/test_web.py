"""Sayt versiyasi (web/): API va Qt'siz yadro."""

import os
import subprocess
import sys

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from ttysi_cadastre.detection import encode_jpg  # noqa: E402
from ttysi_cadastre.model import Building, Door, Equipment, Floor, Room  # noqa: E402
from ttysi_cadastre.workspace import ORG_MARK  # noqa: E402
from web.server import create_app  # noqa: E402


def test_core_has_no_qt():
    """Sayt serveri PySide6'siz ishlashi kerak: yadro modullari Qt'ni import qilmaydi."""
    code = ("import sys; sys.modules['PySide6'] = None\n"
            "import ttysi_cadastre.workspace, ttysi_cadastre.plan_json, ttysi_cadastre.report, "
            "ttysi_cadastre.marks, ttysi_cadastre.detection, web.server")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    r = subprocess.run([sys.executable, "-c", code], cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def _workspace(tmp_path):
    import numpy as np
    ws = tmp_path / "Binolar"
    org = ws / "5-maktab"
    org.mkdir(parents=True)
    (org / ORG_MARK).touch()
    for name, folder in (("1-bino", org), ("2-bino", org), ("3-bino", ws)):
        b = Building(name=name)
        f = Floor(name="1-qavat", width=400, height=300, scale_m_per_px=0.05,
                  image=encode_jpg(np.full((150, 200, 3), 240, np.uint8)))
        f.rooms = [Room(points=[(20, 20), (200, 20), (200, 200), (20, 200)], name="101"),
                   Room(points=[(200, 20), (380, 20), (380, 200), (200, 200)], kind="stairs")]
        f.doors = [Door(x=110, y=20, width=20)]
        f.equipment = [Equipment(code="K", x=50, y=50), Equipment(code="?", x=100, y=100)]
        b.floors.append(f)
        b.save(str(folder / f"{name}.ttysi"))
    return ws


def test_web_api(tmp_path):
    ws = _workspace(tmp_path)
    c = TestClient(create_app(str(ws), pin=""))
    info = c.get("/api/info").json()
    assert {t["code"] for t in info["equipment"]} >= {"SER", "K", "T", "?"} and not info["pin_required"]

    tree = c.get("/api/workspace").json()
    assert [b["name"] for b in tree["buildings"]] == ["3-bino"]
    assert tree["orgs"][0]["name"] == "5-maktab" and [b["id"] for b in tree["orgs"][0]["buildings"]] == \
        ["5-maktab/1-bino.ttysi", "5-maktab/2-bino.ttysi"]

    r = c.get("/api/building", params={"id": "5-maktab/1-bino.ttysi"})
    b, tag = r.json(), r.headers["etag"]
    assert b["org"] == "5-maktab"
    f = b["floors"][0]
    assert f["unknown"] == 1 and f["counts"] == {"K": 1, "?": 1} and f["has_image"]
    assert f["rooms"][0]["area_m2"] == pytest.approx(81.0) and f["rooms"][0]["label"].startswith("101")
    assert f["rooms"][1]["stairs"] and f["doors"][0]["lines"] and f["symbol_r"] > 0

    img = c.get("/api/floor-image", params={"id": "5-maktab/1-bino.ttysi", "floor": 0})
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"

    # belgi: "?" -> Wi-Fi, yangi T qo'shish, K o'chirish
    q = next(e for e in f["equipment"] if e["code"] == "?")
    url = "/api/equipment?id=5-maktab/1-bino.ttysi"
    r = c.post(url, json={"action": "update", "floor": 0, "id": q["id"], "code": "W", "status": "planned"},
               headers={"If-Match": tag})
    assert r.status_code == 200 and r.json()["floors"][0]["unknown"] == 0
    tag2 = r.headers["etag"]
    assert c.post(url, json={"action": "add", "floor": 0, "code": "T", "x": 150, "y": 150},   # eski etag
                  headers={"If-Match": tag}).status_code == 409
    r = c.post(url, json={"action": "add", "floor": 0, "code": "T", "x": 150, "y": 150}, headers={"If-Match": tag2})
    assert r.json()["floors"][0]["counts"]["T"] == 1
    k = next(e for e in r.json()["floors"][0]["equipment"] if e["code"] == "K")
    assert k["room"] == "101"
    r = c.post(url, json={"action": "delete", "floor": 0, "id": k["id"]})
    assert "K" not in r.json()["floors"][0]["counts"]
    saved = Building.load(str(ws / "5-maktab" / "1-bino.ttysi"))             # faylga yozildi (desktop ochadi)
    assert sorted((e.code, e.status) for e in saved.floors[0].equipment) == [("T", "existing"), ("W", "planned")]
    assert c.post(url, json={"action": "add", "floor": 0, "code": "XYZ", "x": 1, "y": 1}).status_code == 422

    # xavfsizlik: ish joyidan tashqari fayl o'qilmaydi
    assert c.get("/api/building", params={"id": "../secret.ttysi"}).status_code == 404
    assert c.get("/api/building", params={"id": "5-maktab/../../x.ttysi"}).status_code == 404

    rep = c.get("/api/report.xlsx", params={"org": "5-maktab"})
    assert rep.status_code == 200 and rep.content[:2] == b"PK"
    assert c.get("/api/report.xlsx", params={"id": "3-bino.ttysi"}).status_code == 200
    page = c.get("/")
    assert page.status_code == 200 and "app.js" in page.text
    assert c.get("/static/app.js").status_code == 200


def test_web_pin(tmp_path):
    ws = _workspace(tmp_path)
    c = TestClient(create_app(str(ws), pin="4321"))
    assert c.get("/api/info").json()["pin_required"]
    assert c.get("/api/workspace").status_code == 401
    assert c.post("/api/login", json={"pin": "0000"}).status_code == 401
    assert c.post("/api/login", json={"pin": "4321"}).status_code == 200
    assert c.get("/api/workspace").status_code == 200                       # cookie bilan


def test_web_users_roles_and_journal(tmp_path):
    from web.auth import Store
    ws = _workspace(tmp_path)
    c = TestClient(create_app(str(ws), pin=""))
    me = c.get("/api/me").json()
    assert me["mode"] == "open" and me["setup"]                  # foydalanuvchi yo'q - shu kompyuterdan sozlash
    assert c.post("/api/setup", json={"login": "Admin", "password": "123"}).status_code == 422   # qisqa parol
    r = c.post("/api/setup", json={"login": "Admin", "password": "maxfiy123", "name": "Bosh admin"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
    assert c.post("/api/setup", json={"login": "x", "password": "maxfiy123"}).status_code == 409
    assert c.get("/api/me").json()["user"]["login"] == "admin"

    other = TestClient(create_app(str(ws)))                       # boshqa brauzer - kirmagan
    assert other.get("/api/workspace").status_code == 401
    assert other.post("/api/login", json={"login": "admin", "password": "noto'g'ri"}).status_code == 401

    # admin xodimlarni qo'shadi
    assert c.post("/api/users", json={"login": "aziz", "role": "editor", "password": "parol123"}).status_code == 200
    assert c.post("/api/users", json={"login": "kozim", "role": "viewer", "password": "parol123"}).status_code == 200
    assert c.post("/api/users", json={"login": "admin", "role": "viewer"}).status_code == 422   # oxirgi admin
    assert {u["login"] for u in c.get("/api/users").json()["users"]} == {"admin", "aziz", "kozim"}

    # ko'ruvchi: ko'radi, lekin o'zgartira olmaydi
    v = TestClient(create_app(str(ws)))
    assert v.post("/api/login", json={"login": "KOZIM", "password": "parol123"}).status_code == 200
    assert v.get("/api/workspace").status_code == 200
    b = v.get("/api/building", params={"id": "3-bino.ttysi"}).json()
    eid = b["floors"][0]["equipment"][1]["id"]
    assert v.post("/api/equipment?id=3-bino.ttysi", json={"action": "delete", "floor": 0, "id": eid}).status_code == 403
    assert v.get("/api/users").status_code == 403

    # tahrirlovchi: o'zgartiradi, jurnalga yoziladi
    e = TestClient(create_app(str(ws)))
    e.post("/api/login", json={"login": "aziz", "password": "parol123"})
    assert e.post("/api/equipment?id=3-bino.ttysi",
                  json={"action": "update", "floor": 0, "id": eid, "code": "T"}).status_code == 200
    j = e.get("/api/journal", params={"id": "3-bino.ttysi"}).json()["items"]
    assert j[0]["user"] == "aziz" and j[0]["action"] == "update" and j[0]["was"] == "?" and j[0]["code"] == "T"
    assert e.get("/api/journal").status_code == 403                # umumiy jurnal - faqat admin
    assert any(r["action"] == "login" for r in c.get("/api/journal").json()["items"])

    # parol o'zgarsa eski sessiya bekor bo'ladi; foydalanuvchi o'chirilsa ham
    c.post("/api/users", json={"login": "aziz", "role": "editor", "password": "yangi12345"})
    assert e.get("/api/workspace").status_code == 401
    c.delete("/api/users", params={"login": "kozim"})
    assert v.get("/api/workspace").status_code == 401
    raw = (ws / ".ttysi-web" / "users.json").read_text()
    assert "parol123" not in raw and "yangi12345" not in raw       # parollar ochiq saqlanmaydi
    assert Store(str(ws)).check_password("aziz", "yangi12345")
    assert [b["name"] for b in c.get("/api/workspace").json()["buildings"]] == ["3-bino"]   # .ttysi-web - tashkilot emas
