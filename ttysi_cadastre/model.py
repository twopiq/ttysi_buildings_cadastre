"""Ma'lumotlar modeli: Bino -> Etajlar -> Xonalar va AT jihozlari.

Loyiha fayli (.ttysi) - bu ZIP arxiv: ichida project.json va etaj rasmlari.
Barcha koordinatalar etaj rasmining piksellarida saqlanadi.
"""

from __future__ import annotations

import json
import os
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

    def contains(self, x: float, y: float) -> bool:
        """Nuqta xona ichidami (nur kesish usuli)."""
        inside = False
        pts = self.points
        j = len(pts) - 1
        for i in range(len(pts)):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
        return inside

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
    status: str = "existing"    # existing - mavjud, planned - kerak (o'rnatilishi rejada)

    @property
    def planned(self) -> bool:
        return self.status == "planned"


@dataclass
class Wall:
    """Mustaqil devor (xona chegarasidan tashqari): siniq chiziq va qalinlik (piksel)."""
    points: list[tuple[float, float]]
    thickness: float = 10.0
    id: str = field(default_factory=new_id)


@dataclass
class Door:
    """Eshik: devor o'qidagi markazi, devor yo'nalishi (gradus) va kengligi (piksel)."""
    x: float
    y: float
    angle: float = 0.0
    width: float = 30.0
    leaves: int = 1             # 1 - bir tabaqali, 2 - ikki tabaqali
    flip: bool = False          # ochilish tomoni (devorning qaysi tarafiga)
    mirror: bool = False        # sharnir (petlya) chapda yoki o'ngda
    id: str = field(default_factory=new_id)


@dataclass
class Floor:
    name: str
    image: bytes | None = None  # fon rasmi (JPG/PNG), perspektivasi to'g'rilangan
    width: int = 2000
    height: int = 1400
    rooms: list[Room] = field(default_factory=list)
    equipment: list[Equipment] = field(default_factory=list)
    doors: list[Door] = field(default_factory=list)
    walls: list[Wall] = field(default_factory=list)
    scale_m_per_px: float | None = None   # masshtab (1 piksel necha metr)
    wall_m: float = 0.30                  # xona devorlarining qalinligi (metr)
    id: str = field(default_factory=new_id)

    def room_of(self, e: "Equipment") -> "Room | None":
        """Jihoz joylashgan xona (ustma-ust bo'lsa - eng kichigi)."""
        hits = [r for r in self.rooms if r.contains(e.x, e.y)]
        return min(hits, key=lambda r: r.area()) if hits else None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "scale_m_per_px": self.scale_m_per_px,
            "wall_m": self.wall_m,
            "rooms": [asdict(r) for r in self.rooms],
            "equipment": [asdict(e) for e in self.equipment],
            "doors": [asdict(d) for d in self.doors],
            "walls": [asdict(w) for w in self.walls],
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
        self.wall_m = d.get("wall_m", 0.30)
        self.rooms = [Room(points=[tuple(p) for p in r["points"]], kind=r.get("kind", "room"),
                           name=r.get("name", ""), id=r.get("id") or new_id())
                      for r in d.get("rooms", [])]
        self.equipment = [Equipment(code=e["code"], x=e["x"], y=e["y"], note=e.get("note", ""),
                                    id=e.get("id") or new_id(), status=e.get("status", "existing"))
                          for e in d.get("equipment", [])]
        self.doors = [Door(x=o["x"], y=o["y"], angle=o.get("angle", 0.0), width=o.get("width", 30.0),
                           leaves=o.get("leaves", 1), flip=o.get("flip", False), mirror=o.get("mirror", False),
                           id=o.get("id") or new_id())
                      for o in d.get("doors", [])]
        self.walls = [Wall(points=[tuple(p) for p in o["points"]], thickness=o.get("thickness", 10.0),
                           id=o.get("id") or new_id())
                      for o in d.get("walls", [])]

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
        """Avval vaqtinchalik faylga yoziladi, keyin almashtiriladi - saqlash uzilsa eski fayl buzilmaydi."""
        tmp = path + ".saving"
        try:
            self._write(tmp)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def _write(self, path: str) -> None:
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
    def load(cls, path: str, images: bool = True) -> "Building":
        """images=False - rasmlarsiz tez o'qish (bosh sahifadagi ro'yxat uchun)."""
        with zipfile.ZipFile(path) as z:
            data = json.loads(z.read("project.json").decode("utf-8"))
            if data.get("format") != "ttysi-cadastre":
                raise ValueError("Bu fayl TTYSI kadastr loyihasi emas")
            b = cls(name=data.get("name", ""), address=data.get("address", ""))
            for d in data.get("floors", []):
                img = z.read(d["image"]) if images and d.get("image") else None
                b.floors.append(Floor.from_dict(d, img))
        return b
