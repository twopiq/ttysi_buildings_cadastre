"""Kadastr rasmidan etaj yaratish (Qt'siz): desktop dastur va sayt bir xil ishlatadi.

    img, paper = load_upload(data, "1-qavat.pdf", page=0)      # PDF sahifasi yoki rasm (telefon rasmi to'g'rilanadi)
    floor, msg = new_floor(img, "1-qavat", paper, ratio=300)     # masshtab, xonalar, eshiklar, AT belgilari
"""

from __future__ import annotations

import math

import numpy as np

from .detection import (DetectParams, decode_image, detect, encode_jpg, find_paper_corners, limit_size,
                        warp_to_rect)
from .geometry import bg_map
from .metrics import meter_px
from .model import Door, Equipment, Floor, Room

PDF_DPI = 200


def is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def pdf_page_count(data: bytes) -> int:
    import pypdfium2 as pdfium
    return len(pdfium.PdfDocument(data))


def render_pdf(data: bytes, page: int = 0, dpi: int = PDF_DPI) -> tuple[np.ndarray, float]:
    """PDF sahifasi -> rasm (BGR) va qog'ozda 1 piksel necha mm."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(data)
    if not 0 <= page < len(doc):
        raise ValueError(f"PDF'da {len(doc)} ta sahifa bor")
    bmp = doc[page].render(scale=dpi / 72)
    rgb = np.asarray(bmp.to_numpy())[..., :3]
    if bmp.mode in ("BGRA", "BGRX", "BGR"):
        img = rgb.copy()
    else:
        img = rgb[..., ::-1].copy()
    return img, 25.4 / dpi


def load_upload(data: bytes, page: int = 0, straighten: bool = True) -> tuple[np.ndarray, float | None]:
    """Yuklangan fayl -> (rasm, qog'oz mm/piksel). Telefon rasmida qog'oz burchaklari topilsa - to'g'rilanadi."""
    if is_pdf(data):
        return render_pdf(data, page)
    img = decode_image(data)
    if img is None:
        raise ValueError("Rasmni o'qib bo'lmadi (JPG, PNG yoki PDF yuboring)")
    if img.ndim == 2:
        import cv2
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if straighten:
        h, w = img.shape[:2]
        c = find_paper_corners(img)
        full = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
        if not np.allclose(c, full):
            img = warp_to_rect(img, c)
    return img, None


def apply_detection(floor: Floor, img: np.ndarray, params: DetectParams, keep_eq: bool,
                    numbering: bool = True) -> str:
    """Rasmdan xonalar, kirish eshiklari va AT belgilari nomzodlarini topib, etajga yozadi."""
    res = detect(img, params)
    k = floor.width / max(1, img.shape[1])
    if abs(k - 1) > 1e-9 or not floor.bg_identity():
        # rasm piksellari -> chizma koordinatalari (fon surilgan/burilgan bo'lsa ham)
        def mp(x, y):
            return bg_map(floor, x * k, y * k)
        for r in res.rooms:
            r.points = [mp(x, y) for x, y in r.points]
        res.marks = [mp(x, y) for x, y in res.marks]
        for d in res.doors:
            d.x, d.y = mp(d.x, d.y)
            d.angle += floor.bg_rot
            d.width *= k * floor.bg_scale
    floor.rooms = [Room(points=r.points, kind=r.kind, name=str(i) if numbering else "", shape=r.shape)
                   for i, r in enumerate(res.rooms, 1)]
    # doira binolar kirishlaridagi eshiklar (mavjud eshik bilan ustma-ust tushmasa)
    for d in res.doors:
        if all(math.hypot(d.x - o.x, d.y - o.y) > d.width for o in floor.doors):
            wide = d.width > meter_px(floor) * 1.6          # keng kirish - ikki tabaqali
            floor.doors.append(Door(x=d.x, y=d.y, angle=d.angle, width=d.width, leaves=2 if wide else 1))
    kept = [e for e in floor.equipment if e.code != "?"] if keep_eq else []
    floor.equipment = kept + [Equipment(code="?", x=x, y=y) for x, y in res.marks]
    domes = sum(1 for r in res.rooms if r.shape == "ellipse")
    return (f"Topildi: {len(res.rooms)} ta xona/koridor"
            + (f" (shundan {domes} ta gumbaz, {len(res.doors)} ta kirish)" if domes else "")
            + f", {len(res.marks)} ta belgi nomzodi. "
            "Chizmani tekshirib, tuzating.")


def new_floor(img: np.ndarray, name: str, paper_mm_per_px: float | None = None, ratio: int = 0,
              auto: bool = True, params: DetectParams | None = None, numbering: bool = True) -> tuple[Floor, str]:
    """Rasm (kesilgan, to'g'rilangan) -> yangi etaj. Nisbat va qog'oz o'lchami ma'lum bo'lsa - masshtab."""
    corrected = limit_size(img)
    k = img.shape[1] / corrected.shape[1]
    paper = paper_mm_per_px * k if paper_mm_per_px else None
    mpp = paper * ratio / 1000.0 if paper and ratio > 0 else None
    h, w = corrected.shape[:2]
    floor = Floor(name=name, image=encode_jpg(corrected), width=w, height=h, scale_m_per_px=mpp)
    floor.paper_mm_per_px = paper
    floor.ratio = int(ratio or 0)
    msg = "Etaj qo'shildi."
    if auto:
        p = params or DetectParams()
        p.m_per_px = mpp
        msg = apply_detection(floor, corrected, p, keep_eq=False, numbering=numbering)
    return floor, msg
