"""Komety: dráhové elementy z Minor Planet Center (CometEls.txt), poloha a odhad jasnosti.

Soubor má pevné sloupce (viz MPC „Export format for comet orbits“). Skyfield z elementů
spočítá heliocentrickou dráhu; jasnost se odhaduje klasicky m = H + 5·log Δ + 2,5·G·log r,
což u komet bývá přesné jen na 1–2 mag.

Výkon: propagace jedné dráhy stojí ~5 ms, `observe` ~20 ms. Proto se jednou denně udělá
předvýběr (geometrický dolní odhad jasnosti bez propagace, pak propagace ~100 komet) a při
renderu se propaguje jen předvýběr; `observe` dostanou jen komety, které se opravdu kreslí.
"""
from __future__ import annotations

import logging
import math
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
from skyfield.api import wgs84
from skyfield.constants import GM_SUN_Pitjeva_2005_km3_s2 as GM_SUN
from skyfield.data.spice import inertial_frames
from skyfield.keplerlib import _KeplerOrbit

from sky.config import Config
from sky.netcache import fetch_text

log = logging.getLogger(__name__)
ELEMENTS_MAX_AGE_S = 86400
PERIHELION_WINDOW_Y = 3        # komety s perihelem dál než ±3 roky nemohou být jasné
SHORTLIST_MAG = 12.0           # předvýběr pokrývá limity do 10 mag (+2 mag rezerva na změnu za den)
EARTH_AU = 1.02                # max. vzdálenost Země od Slunce, pro dolní odhad Δ
_PAREN = re.compile(r"\(([^)]+)\)\s*$")


@dataclass(frozen=True)
class Elements:
    name: str
    perihelion_year: int
    perihelion_month: int
    perihelion_day: float
    perihelion_distance_au: float
    eccentricity: float
    argument_of_perihelion_degrees: float
    longitude_of_ascending_node_degrees: float
    inclination_degrees: float
    h: float | None        # absolutní (celková) magnituda
    g: float | None        # sklon jasnosti

    def __getitem__(self, key: str):          # Skyfield čte row['designation']
        if key == "designation":
            return self.name
        return getattr(self, key)


@dataclass(frozen=True)
class CometPos:
    name: str              # krátké jméno pro popisek
    alt: float
    az: float
    mag: float


def short_name(name: str) -> str:
    """„C/1995 O1 (Hale-Bopp)“ → „Hale-Bopp“; periodické „12P/Pons-Brooks“ zůstávají."""
    m = _PAREN.search(name)
    return m.group(1).strip() if m else name.strip()


def _f(s: str) -> float | None:
    s = s.strip()
    return float(s) if s else None


def parse_elements(text: str) -> list[Elements]:
    out = []
    for line in text.splitlines():
        if len(line) < 103:
            continue
        try:
            el = Elements(
                name=line[102:158].strip(),
                perihelion_year=int(line[14:18]), perihelion_month=int(line[19:21]), perihelion_day=float(line[22:29]),
                perihelion_distance_au=float(line[30:39]), eccentricity=float(line[41:49]),
                argument_of_perihelion_degrees=float(line[51:59]), longitude_of_ascending_node_degrees=float(line[61:69]),
                inclination_degrees=float(line[71:79]), h=_f(line[91:95]), g=_f(line[96:100]),
            )
        except ValueError:
            continue
        if el.name:
            out.append(el)
    return out


_elements_cache: tuple[int, list[Elements]] = (0, [])


def load_elements(cfg: Config) -> list[Elements]:
    """Parsovaný seznam se drží v paměti, dokud se text souboru nezmění (shortlist se klíčuje identitou seznamu)."""
    global _elements_cache
    text = fetch_text(cfg.comets_url, cfg.cache_dir / "comets.txt", ELEMENTS_MAX_AGE_S)
    if not text:
        return []
    key = hash(text)
    if _elements_cache[0] != key:
        _elements_cache = (key, parse_elements(text))
    return _elements_cache[1]


def comet_orbit(el: Elements, ts):
    """Totéž co skyfield.data.mpc.comet_orbit, ale bez importu pandas (ten modul ho tahá při importu)."""
    e = el.eccentricity
    if e == 1.0:
        p = el.perihelion_distance_au * 2.0
    else:
        p = el.perihelion_distance_au / (1.0 - e) * (1.0 - e * e)
    t_peri = ts.tt(el.perihelion_year, el.perihelion_month, el.perihelion_day)
    orbit = _KeplerOrbit._from_periapsis(p, e, el.inclination_degrees, el.longitude_of_ascending_node_degrees,
                                         el.argument_of_perihelion_degrees, t_peri, GM_SUN, 10, el.name)
    orbit._rotation = inertial_frames["ECLIPJ2000"].T
    return orbit


def magnitude(h: float, g: float, delta_au: float, r_au: float) -> float:
    return h + 5.0 * math.log10(max(delta_au, 1e-6)) + 2.5 * g * math.log10(max(r_au, 1e-6))


def min_magnitude(el: Elements) -> float:
    """Dolní odhad jasnosti bez propagace: r ≥ q a Δ ≥ q − 1,02 AU (pro q uvnitř dráhy Země neomezeno)."""
    q = el.perihelion_distance_au
    dmin = q - EARTH_AU
    if dmin <= 0:
        return -99.0
    return el.h + 2.5 * el.g * math.log10(q) + 5.0 * math.log10(dmin)


def _candidates(elements: list[Elements], year: int, limit: float) -> list[Elements]:
    return [el for el in elements
            if el.h is not None and el.g is not None and abs(el.perihelion_year - year) <= PERIHELION_WINDOW_Y
            and min_magnitude(el) <= limit]


def _geometry(el: Elements, ts, tt, sun, sun_pos, earth_pos):
    """(dráha, r [AU], Δ [AU]) geometricky, bez světelného času (na jasnost nemá vliv)."""
    orbit = sun + comet_orbit(el, ts)
    pos = orbit.at(tt).position.au
    return orbit, float(np.linalg.norm(pos - sun_pos)), float(np.linalg.norm(pos - earth_pos))


def compute(elements: list[Elements], eph, lat: float, lon: float, t: datetime, limit: float) -> list[CometPos]:
    """Komety jasnější než `limit` (odhad) s alt/az pro stanoviště; od nejjasnější."""
    ts, e = eph.ts, eph.eph
    tt = ts.from_datetime(t)
    sun, earth = e["sun"], e["earth"]
    sun_pos, earth_pos = sun.at(tt).position.au, earth.at(tt).position.au
    observer = (earth + wgs84.latlon(lat, lon)).at(tt)
    found = []
    for el in _candidates(elements, t.year, limit):
        try:
            orbit, r_au, delta_au = _geometry(el, ts, tt, sun, sun_pos, earth_pos)
            m = magnitude(el.h, el.g, delta_au, r_au)
            if m > limit:
                continue
            alt, az, _ = observer.observe(orbit).apparent().altaz()
            found.append(CometPos(short_name(el.name), float(alt.degrees), float(az.degrees), round(m, 1)))
        except Exception as exc:                   # jedna vadná dráha nesmí shodit mapu
            log.warning("kometa %s: %s", el.name, exc)
    found.sort(key=lambda c: c.mag)
    return found


_shortlist: dict = {}
_lock = threading.Lock()


def shortlist(elements: list[Elements], eph, t: datetime) -> list[Elements]:
    """Elementy komet, které mohou být dnes jasnější než SHORTLIST_MAG; počítá se jednou denně (~0,5 s)."""
    key = (id(elements), t.date())
    with _lock:
        hit = _shortlist.get(key)
        if hit is not None:
            return hit
        ts, e = eph.ts, eph.eph
        noon = t.replace(hour=12, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        tt = ts.from_datetime(noon)
        sun, earth = e["sun"], e["earth"]
        sun_pos, earth_pos = sun.at(tt).position.au, earth.at(tt).position.au
        chosen = []
        for el in _candidates(elements, t.year, SHORTLIST_MAG):
            try:
                _, r_au, delta_au = _geometry(el, ts, tt, sun, sun_pos, earth_pos)
                if magnitude(el.h, el.g, delta_au, r_au) <= SHORTLIST_MAG:
                    chosen.append(el)
            except Exception as exc:
                log.warning("kometa %s: %s", el.name, exc)
        _shortlist.clear()
        _shortlist[key] = chosen
        return chosen


def tonight(cfg: Config, eph, lat: float, lon: float, t: datetime, limit: float) -> list[CometPos]:
    elements = load_elements(cfg)
    if not elements:
        return []
    pool = shortlist(elements, eph, t) if limit <= SHORTLIST_MAG - 2.0 else elements
    return compute(pool, eph, lat, lon, t, limit)
