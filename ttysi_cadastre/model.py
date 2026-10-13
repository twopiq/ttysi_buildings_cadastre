"""Ma'lumotlar modeli: Bino -> Etajlar -> Xonalar va AT jihozlari.

Loyiha fayli (.ttysi) - bu ZIP arxiv: ichida project.json va etaj rasmlari.
Barcha koordinatalar etaj rasmining piksellarida saqlanadi.
"""

from __future__ import annotations

import json
import uuid
import zipfile
from dataclasses import dataclass, field, asdict

FORMAT_VERSION = 1


def new_id() -> str:
    return uuid.uuid4().hex[:10]


@dataclass
class Room:
    points: list[tuple[float, float]]
    kind: str = "room"          # room / corridor / stairs / wc / other
    name: str = ""
    id: str = field(default_factory=new_id)

    def centroid(self) -> tuple[float, float]:
        pts = self.points
        a = cx = cy = 0.0
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % n]
            c = x0 * y1 - x1 * y0
            a += c
            cx += (x0 + x1) * c
            cy += (y0 + y1) * c
        if abs(a) < 1e-9:
            return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)
        a *= 0.5
        return (cx / (6 * a), cy / (6 * a))

    def area(self) -> float:
        pts = self.points
        s = 0.0
        for i in range(len(pts)):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % len(pts)]
            s += x0 * y1 - x1 * y0
        return abs(s) / 2


@dataclass
class Equipment:
    code: str                   # SER / KX / K / W / S / T / ?
    x: float
    y: float
    note: str = ""
    id: str = field(default_factory=new_id)


@dataclass
class Floor:
    name: str
    image: bytes | None = None  # fon rasmi (JPG/PNG), perspektivasi to'g'rilangan
    width: int = 2000
    height: int = 1400
    rooms: list[Room] = field(default_factory=list)
    equipment: list[Equipment] = field(default_factory=list)
    scale_m_per_px: float | None = None   # masshtab (1 piksel necha metr)
    id: str = field(default_factory=new_id)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "scale_m_per_px": self.scale_m_per_px,
            "rooms": [asdict(r) for r in self.rooms],
            "equipment": [asdict(e) for e in self.equipment],
        }

    def content_dict(self) -> dict:
        """Bekor qilish (undo) uchun - rasmsiz holat."""
        d = self.to_dict()
        d.pop("id")
        return d

    def load_content(self, d: dict) -> None:
        self.name = d["name"]
        self.width = d["width"]
        self.height = d["height"]
        self.scale_m_per_px = d.get("scale_m_per_px")
        self.rooms = [Room(points=[tuple(p) for p in r["points"]], kind=r.get("kind", "room"),
                           name=r.get("name", ""), id=r.get("id") or new_id())
                      for r in d.get("rooms", [])]
        self.equipment = [Equipment(code=e["code"], x=e["x"], y=e["y"], note=e.get("note", ""),
                                    id=e.get("id") or new_id())
                          for e in d.get("equipment", [])]

    @classmethod
    def from_dict(cls, d: dict, image: bytes | None) -> "Floor":
        f = cls(name=d["name"], image=image, id=d.get("id") or new_id())
        f.load_content(d)
        return f


@dataclass
class Building:
    name: str = "Yangi bino"
    address: str = ""
    floors: list[Floor] = field(default_factory=list)

    def save(self, path: str) -> None:
        data = {
            "format": "ttysi-cadastre",
            "version": FORMAT_VERSION,
            "name": self.name,
            "address": self.address,
            "floors": [],
        }
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in self.floors:
                d = f.to_dict()
                if f.image:
                    img_name = f"images/{f.id}.img"
                    z.writestr(img_name, f.image, compress_type=zipfile.ZIP_STORED)
                    d["image"] = img_name
                data["floors"].append(d)
            z.writestr("project.json", json.dumps(data, ensure_ascii=False, indent=1))

    @classmethod
    def load(cls, path: str) -> "Building":
        with zipfile.ZipFile(path) as z:
            data = json.loads(z.read("project.json").decode("utf-8"))
            if data.get("format") != "ttysi-cadastre":
                raise ValueError("Bu fayl TTYSI kadastr loyihasi emas")
            b = cls(name=data.get("name", ""), address=data.get("address", ""))
            for d in data.get("floors", []):
                img = z.read(d["image"]) if d.get("image") else None
                b.floors.append(Floor.from_dict(d, img))
        return b
