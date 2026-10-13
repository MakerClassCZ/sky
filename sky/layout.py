"""Rozložení panelu (spec §5.4)."""
from __future__ import annotations

from dataclasses import dataclass

U = 16              # výška řádku fontu 8×16
MARGIN = 8
MIN_INFO_W = 112    # 14 znaků 8 px
WIDE_COL_W = 160    # min. šířka sloupce při dvou sloupcích
WIDE3_COL_W = 200   # min. šířka sloupce při třech sloupcích
MIN_INFO_H = (16 + U + MARGIN) + 3 * U   # malá hlavička + 3 řádky
BIG_HEADER_H = 32 + U + MARGIN
SMALL_HEADER_H = 16 + U + MARGIN
HORIZON_BAR = 24            # pás pod obzorem pro světové strany (u `horizon`)
ALL_SECTIONS = ("sun", "moon", "iss", "events")
SECTION_GAP = U // 2
# výška sekce bez mezery: titulek (U + 4) + řádky; úkazy nemají pevnou výšku (plní, co zbývá)
SECTION_H = {"sun": U + 4 + 3 * U, "moon": U + 4 + 3 * U, "iss": U + 4 + 2 * U}


def column_groups(n: int) -> tuple[tuple[str, ...], ...]:
    """Které sekce patří do kterého sloupce (sdílí layout i render)."""
    if n >= 3:
        return (("sun", "moon"), ("iss",), ("events",))
    if n == 2:
        return (("sun", "moon"), ("iss", "events"))
    return (ALL_SECTIONS,)


def _needed_body_h(n: int, sections: tuple[str, ...]) -> int:
    """Výška těla infopanelu, kterou sekce (bez úkazů) skutečně potřebují."""
    best = 0
    for group in column_groups(n):
        best = max(best, sum(SECTION_H[s] + SECTION_GAP for s in group if s in sections and s in SECTION_H))
    return best


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h


@dataclass(frozen=True)
class Zones:
    map: Rect
    info: Rect | None
    header: Rect | None
    columns: tuple[Rect, ...]
    header_big: bool


def _split(info: Rect, header_big: bool) -> tuple[Rect, tuple[Rect, ...]]:
    hh = BIG_HEADER_H if header_big else 16 + U + MARGIN
    header = Rect(info.x, info.y, info.w, hh)
    body = Rect(info.x, header.bottom, info.w, max(0, info.bottom - header.bottom))
    wide = body.w >= 1.5 * body.h
    if wide and body.w >= 3 * WIDE3_COL_W:
        n = 3
    elif wide and body.w >= 2 * WIDE_COL_W:
        n = 2
    else:
        n = 1
    cw = body.w // n
    cols = tuple(Rect(body.x + i * cw, body.y, cw, body.h) for i in range(n))
    return header, cols


def _zones(m: Rect, info: Rect | None) -> Zones:
    if info is None:
        return Zones(m, None, None, (), False)
    # Velká hlavička jen tehdy, když pod ní zbude místo na Slunce + Měsíc v jednom
    # sloupci (2× titulek + 3 řádky, mezera): jinak by na 800×480 horizon vypadl řádek Fáze.
    big = info.h >= 128 and info.w >= 224 and info.h - BIG_HEADER_H >= 9 * U
    header, cols = _split(info, big)
    return Zones(m, info, header, cols, big)


def compute(w: int, h: int, view: str, sections: tuple[str, ...] = ALL_SECTIONS,
            fov: float = 120.0) -> Zones:
    if view == "sky":
        if w >= h:
            m = Rect(0, 0, h, h)
            info = Rect(h, 0, w - h, h) if w - h >= MIN_INFO_W else None
        else:
            m = Rect(0, 0, w, w)
            info = Rect(0, w, w, h - w) if h - w >= 6 * U else None
    else:
        mh = max(int(h * 0.6), h - 12 * U) if w >= h else int(w * 0.6)
        # Obzor→zenit je 90°; při stejném měřítku na obou osách nemá mapa co ukázat výš.
        max_map = int(w * 90 / fov) + HORIZON_BAR
        mh = min(mh, max_map)
        if h - mh >= MIN_INFO_H:
            m = Rect(0, 0, w, mh)
            info = Rect(0, mh, w, h - mh)
        else:
            m = Rect(0, 0, w, h)
            info = None
        if info is not None and "events" not in sections:
            # Bez úkazů není co roztahovat: infopanel dostane jen to, co sekce
            # potřebují, zbytek připadne výseku obzoru. Nikdy ne víc než výchozí výška.
            z = _zones(m, info)
            for _ in range(2):   # nižší tělo může změnit počet sloupců → druhý průchod
                need = z.header.h + _needed_body_h(len(z.columns), sections)
                if need >= info.h:
                    break
                mh = min(h - need, max_map)
                info = Rect(0, mh, w, h - mh)
                m = Rect(0, 0, w, mh)
                z = _zones(m, info)
            return z
    return _zones(m, info)
