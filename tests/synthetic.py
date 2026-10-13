"""Sinov uchun sun'iy kadastr rejasi (devorlar, eshiklar, koridor, ko'k ruchka belgilari)."""

import cv2
import numpy as np

BLUE = (190, 60, 20)  # BGR - ko'k ruchka

# Kutilgan xonalar: (x0, y0, x1, y1) devor o'qlari bo'yicha
ROOMS = [
    (100, 100, 400, 400),
    (400, 100, 700, 400),
    (700, 100, 1100, 400),
    (100, 400, 1100, 520),   # koridor
    (100, 520, 500, 800),
    (500, 520, 1100, 800),
]
MARKS = [((180, 200), "Ser."), ((520, 250), "K.x."), ((850, 300), "W"),
         ((600, 470), "K."), ((250, 650), "T"), ((800, 700), "S")]


def make_plan(with_marks: bool = True) -> np.ndarray:
    img = np.full((900, 1200, 3), 250, np.uint8)
    t = 10
    cv2.rectangle(img, (20, 20), (1180, 880), (0, 0, 0), 2)  # ramka
    walls = set()
    for x0, y0, x1, y1 in ROOMS:
        walls |= {(x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1), (x1, y0, x1, y1)}
    for x0, y0, x1, y1 in walls:
        cv2.rectangle(img, (x0 - t // 2, y0 - t // 2), (x1 + t // 2, y1 + t // 2), (20, 20, 20), -1)
    # eshiklar (devordagi bo'shliqlar)
    for (x, y, horiz) in [(250, 400, True), (550, 400, True), (900, 400, True),
                          (300, 520, True), (800, 520, True), (400, 250, False)]:
        if horiz:
            cv2.rectangle(img, (x - 18, y - t), (x + 18, y + t), (250, 250, 250), -1)
        else:
            cv2.rectangle(img, (x - t, y - 18), (x + t, y + 18), (250, 250, 250), -1)
    # bosma raqamlar va maydonlar
    for i, (x0, y0, x1, y1) in enumerate(ROOMS, 1):
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        cv2.putText(img, str(i), (cx - 10, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
        cv2.putText(img, f"{(x1-x0)*(y1-y0)/10000:.1f}", (cx - 25, cy + 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    # o'lcham chiziqlari (tashqarida)
    cv2.line(img, (100, 60), (1100, 60), (0, 0, 0), 1)
    cv2.putText(img, "25.00", (580, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    if with_marks:
        for (x, y), label in MARKS:
            cv2.putText(img, label, (x, y), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, 0.9, BLUE, 2)
    return img


def make_phone_photo(plan: np.ndarray) -> np.ndarray:
    """Qiyshiq burchakdan olingan, soyali "telefon rasmi"."""
    h, w = plan.shape[:2]
    canvas = np.full((h + 300, w + 300, 3), (60, 70, 80), np.uint8)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([[180, 120], [w + 200, 170], [w + 150, h + 250], [110, h + 200]])
    m = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(plan, m, (canvas.shape[1], canvas.shape[0]))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), m, (canvas.shape[1], canvas.shape[0]))
    canvas[mask > 0] = warped[mask > 0]
    # soya: chapdan o'ngga yorug'lik pasayadi
    grad = np.linspace(1.0, 0.65, canvas.shape[1])[None, :, None]
    return (canvas * grad).astype(np.uint8)


DOORS = [(250, 400, True), (550, 400, True), (900, 400, True),
         (300, 520, True), (800, 520, True), (400, 250, False)]


def make_double_line_plan(m_per_px: float = 0.025) -> np.ndarray:
    """Kadastrdagidek: devorlar qo'sh ingichka chiziq, eshiklar - bo'shliq va ochilish yoyi.

    1 piksel = 2.5 sm: devor ~0.25 m, eshik ~0.9 m, koridor 3 m.
    """
    img = np.full((900, 1200, 3), 252, np.uint8)
    t = 10  # devor qalinligi (qo'sh chiziqlar orasi)
    ink = (40, 40, 40)
    door = 36
    walls = set()
    for x0, y0, x1, y1 in ROOMS:
        walls |= {(x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1), (x1, y0, x1, y1)}
    for x0, y0, x1, y1 in walls:
        if y0 == y1:
            for dy in (-t // 2, t // 2):
                cv2.line(img, (x0 - t // 2, y0 + dy), (x1 + t // 2, y0 + dy), ink, 1)
        else:
            for dx in (-t // 2, t // 2):
                cv2.line(img, (x0 + dx, y0 - t // 2), (x0 + dx, y1 + t // 2), ink, 1)
    for x, y, horiz in DOORS:
        if horiz:
            cv2.rectangle(img, (x - door // 2, y - t // 2 - 1), (x + door // 2, y + t // 2 + 1), (252, 252, 252), -1)
            cv2.line(img, (x - door // 2, y - t // 2), (x - door // 2, y + t // 2), ink, 1)
            cv2.line(img, (x + door // 2, y - t // 2), (x + door // 2, y + t // 2), ink, 1)
            cv2.ellipse(img, (x - door // 2, y + t // 2), (door, door), 0, 0, 90, ink, 1)  # ochilish yoyi
        else:
            cv2.rectangle(img, (x - t // 2 - 1, y - door // 2), (x + t // 2 + 1, y + door // 2), (252, 252, 252), -1)
            cv2.line(img, (x - t // 2, y - door // 2), (x + t // 2, y - door // 2), ink, 1)
            cv2.line(img, (x - t // 2, y + door // 2), (x + t // 2, y + door // 2), ink, 1)
            cv2.ellipse(img, (x + t // 2, y - door // 2), (door, door), 0, 0, 90, ink, 1)
    for i, (x0, y0, x1, y1) in enumerate(ROOMS, 1):
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        cv2.putText(img, str(i), (cx - 6, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.45, ink, 1)
        area = (x1 - x0) * (y1 - y0) * m_per_px ** 2
        cv2.putText(img, f"{area:.2f}", (cx - 18, cy + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, ink, 1)
    # skaner shovqini va JPEG siqilishi
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 60])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)
