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
SECTION_H = {"sun": U + 4 + 3 * U, "moon": U + 4 + 3 * U, "iss": U + 4 + 2 * U,
             "events": U + 4 + 6 * U}        # úkazy: aspoň 6 řádků, víc jen když zbyde místo
LINE_HEADER_H = 24 + MARGIN                  # jednořádková hlavička (datum 12×24, zbytek 8×16)


def column_groups(n: int) -> tuple[tuple[str, ...], ...]:
    """Které sekce patří do kterého sloupce (sdílí layout i render)."""
    if n >= 3:
        return (("sun",), ("moon",), ("events",))      # ISS jde do pásu přes 1. + 2. sloupec
    if n == 2:
        return (("sun", "moon"), ("iss", "events"))
    return (ALL_SECTIONS,)


def _needed_body_h(n: int, sections: tuple[str, ...]) -> int:
    """Výška těla infopanelu, kterou zobrazené sekce potřebují (nejvyšší sloupec)."""
    best = 0
    extra = U if "weather" in sections else 0        # řádek oblačnosti v sekci Slunce
    for group in column_groups(n):
        best = max(best, sum(SECTION_H[s] + SECTION_GAP + (extra if s == "sun" else 0)
                             for s in group if s in sections and s in SECTION_H))
    if n >= 3 and "iss" in sections:
        # pás ISS pod Sluncem/Měsícem: nejvyšší z obou sloupců + ISS
        top = max((SECTION_H[s] + SECTION_GAP + (extra if s == "sun" else 0)
                   for s in ("sun", "moon") if s in sections), default=0)
        best = max(best, top + SECTION_H["iss"] + SECTION_GAP)
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
    header_line: bool = False      # datum, čas a poloha na jednom řádku (horizon na šířku)
    span: Rect | None = None       # pás přes 1. + 2. sloupec pod Sluncem a Měsícem (ISS), jen u 3 sloupců


def _split(info: Rect, header_big: bool, header_line: bool = False,
           weather: bool = False) -> tuple[Rect, tuple[Rect, ...], Rect | None]:
    hh = LINE_HEADER_H if header_line else (BIG_HEADER_H if header_big else SMALL_HEADER_H)
    header = Rect(info.x, info.y, info.w, hh)
    body = Rect(info.x, header.bottom, info.w, max(0, info.bottom - header.bottom))
    wide = body.w >= 1.5 * body.h
    if wide and body.w >= 3 * WIDE3_COL_W:
        n = 3
    elif wide and body.w >= 2 * WIDE_COL_W:
        n = 2
    else:
        n = 1
    if n == 3:
        # 25 / 25 / 50 %: úkazy potřebují nejvíc místa; ISS v pásu pod prvními dvěma
        q = body.w // 4
        cols = (Rect(body.x, body.y, q, body.h), Rect(body.x + q, body.y, q, body.h),
                Rect(body.x + 2 * q, body.y, body.w - 2 * q, body.h))
        top = max(SECTION_H["sun"] + (U if weather else 0), SECTION_H["moon"]) + SECTION_GAP
        span = Rect(body.x, body.y + top, 2 * q, max(0, body.h - top))
        return header, cols, span
    cw = body.w // n
    cols = tuple(Rect(body.x + i * cw, body.y, cw, body.h) for i in range(n))
    return header, cols, None


def _zones(m: Rect, info: Rect | None, line: bool = False, weather: bool = False) -> Zones:
    if info is None:
        return Zones(m, None, None, (), False)
    # Velká hlavička jen tehdy, když pod ní zbude místo na Slunce + Měsíc v jednom
    # sloupci (2× titulek + 3 řádky, mezera): jinak by vypadl řádek Fáze.
    big = not line and info.h >= 128 and info.w >= 224 and info.h - BIG_HEADER_H >= 9 * U
    header, cols, span = _split(info, big, line, weather)
    return Zones(m, info, header, cols, big, line, span)


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
        line = w >= h          # na šířku: datum, čas a poloha na jednom řádku
        wx = "weather" in sections
        if info is not None:
            # Infopanel dostane jen výšku, kterou zobrazené sekce potřebují (úkazy
            # aspoň 6 řádků); zbytek připadne výseku obzoru. Nikdy ne víc než výchozí.
            z = _zones(m, info, line, wx)
            for _ in range(2):   # nižší tělo může změnit počet sloupců → druhý průchod
                need = z.header.h + _needed_body_h(len(z.columns), sections)
                if need >= info.h:
                    break
                mh = min(h - need, max_map)
                info = Rect(0, mh, w, h - mh)
                m = Rect(0, 0, w, mh)
                z = _zones(m, info, line, wx)
            return z
    return _zones(m, info, False, "weather" in sections)
