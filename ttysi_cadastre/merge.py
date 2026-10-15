"""Bitta bino faylini ikki joyda (desktop dastur va sayt) o'zgartirishni birlashtirish (Qt'siz).

Uch tomonlama birlashtirish AT belgilari bo'yicha (har bir belgining doimiy id si bor):
  base   - fayl ochilgan/saqlangan paytdagi holat,
  mine   - dasturdagi joriy holat (saqlanmagan o'zgarishlar bilan),
  theirs - diskdagi yangi holat (saytda o'zgartirilgan).
Faqat bir tomonda o'zgargan narsa olinadi; ikkala tomonda turlicha o'zgargan belgida dastur (mine) ustun.
Xonalar, devorlar va boshqa chizma faqat dasturda tahrirlanadi - ular o'zgarmaydi.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import Building, Equipment

Snapshot = dict[str, dict[str, tuple]]


def _key(e: Equipment) -> tuple:
    return (e.code, round(e.x, 3), round(e.y, 3), e.note, e.status)


def snapshot(b: Building) -> Snapshot:
    """Etaj id -> {belgi id -> belgi holati}."""
    return {f.id: {e.id: _key(e) for e in f.equipment} for f in b.floors}


@dataclass
class MergeResult:
    added: int = 0
    changed: int = 0
    deleted: int = 0
    conflicts: int = 0             # ikkala tomonda turlicha o'zgargan - dasturdagisi qoldirildi
    floors: set[str] = field(default_factory=set)   # o'zgargan etajlar (id)

    @property
    def total(self) -> int:
        return self.added + self.changed + self.deleted

    def text(self) -> str:
        parts = []
        if self.added:
            parts.append(f"+{self.added} belgi")
        if self.changed:
            parts.append(f"{self.changed} ta o'zgardi")
        if self.deleted:
            parts.append(f"{self.deleted} ta o'chirildi")
        s = ", ".join(parts) or "o'zgarish yo'q"
        if self.conflicts:
            s += f"; {self.conflicts} ta belgi ikkala joyda o'zgargan - dasturdagisi qoldirildi"
        return s


def merge_equipment(base: Snapshot, mine: Building, theirs: Building) -> MergeResult:
    """theirs dagi (base ga nisbatan) o'zgarishlarni mine ga qo'shadi. mine o'zgartiriladi."""
    res = MergeResult()
    their_floors = {f.id: f for f in theirs.floors}
    for f in mine.floors:
        tf = their_floors.get(f.id)
        if tf is None:
            continue
        B = base.get(f.id, {})
        M = {e.id: e for e in f.equipment}
        T = {e.id: e for e in tf.equipment}
        before = res.total
        for eid, te in T.items():
            tk = _key(te)
            if eid not in B:
                if eid not in M:                                   # saytda qo'shilgan
                    f.equipment.append(Equipment(code=te.code, x=te.x, y=te.y, note=te.note, id=te.id,
                                                 status=te.status))
                    res.added += 1
            elif tk != B[eid]:                                     # saytda o'zgargan
                me = M.get(eid)
                if me is None:
                    continue                                       # dasturda o'chirilgan - o'chiqligicha
                if _key(me) == B[eid]:
                    me.code, me.x, me.y, me.note, me.status = te.code, te.x, te.y, te.note, te.status
                    res.changed += 1
                elif _key(me) != tk:
                    res.conflicts += 1
        for eid, bk in B.items():
            if eid not in T and eid in M:                          # saytda o'chirilgan
                if _key(M[eid]) == bk:
                    f.equipment.remove(M[eid])
                    res.deleted += 1
                else:
                    res.conflicts += 1
        if res.total != before:
            res.floors.add(f.id)
    return res
