"""AT (axborot texnologiyalari) jihozlari turlari va ularning ko'rinishi."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EquipmentType:
    code: str      # ichki kod (fayllarda saqlanadi)
    label: str     # chizmadagi qisqa belgi
    name: str      # to'liq nomi
    color: str     # hex rang
    key: str       # klaviatura tugmasi


EQUIPMENT_TYPES = [
    EquipmentType("SER", "Ser.", "Serverxona", "#c62828", "1"),
    EquipmentType("KX", "K.x.", "Kommutatsion xona", "#6a1b9a", "2"),
    EquipmentType("K", "K.", "Kamera", "#2e7d32", "3"),
    EquipmentType("W", "W", "Wi-Fi", "#0277bd", "4"),
    EquipmentType("S", "S", "Switch / Hub", "#ef6c00", "5"),
    EquipmentType("T", "T", "Internet nuqtasi (tochka)", "#5d4037", "6"),
]

# Rasmdan topilgan, lekin turi hali tasdiqlanmagan belgi
UNKNOWN = EquipmentType("?", "?", "Tasdiqlanmagan belgi", "#9e9e9e", "0")

BY_CODE = {t.code: t for t in EQUIPMENT_TYPES}
BY_CODE[UNKNOWN.code] = UNKNOWN
BY_KEY = {t.key: t for t in EQUIPMENT_TYPES}


def get_type(code: str) -> EquipmentType:
    return BY_CODE.get(code, UNKNOWN)


ROOM_KINDS = {
    "room": ("Xona", "#ffffff"),
    "corridor": ("Koridor", "#fff8e1"),
    "computer": ("Kompyuter xona", "#e8f5e9"),
    "stairs": ("Zinapoya", "#eceff1"),
    "wc": ("Hojatxona", "#e0f7fa"),
    "other": ("Boshqa", "#f3e5f5"),
}
