"""Výpočet oblohy přes Skyfield (spec §4, §5.1, §6.1)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from skyfield import almanac
from skyfield.api import Loader, Star, wgs84

from sky.catalog import Catalog
from sky.geo import tz_for
from sky.params import Params

NIGHT_SUN_ALT = -0.8333
EPHEMERIS = "de421.bsp"
PLANETS = [("mercury", "Merkur", "Mercury"), ("venus", "Venuše", "Venus"), ("mars", "Mars", "Mars"),
           ("jupiter barycenter", "Jupiter", "Jupiter"), ("saturn barycenter", "Saturn", "Saturn"),
           ("uranus barycenter", "Uran", "Uranus"), ("neptune barycenter", "Neptun", "Neptune")]
OBLIQUITY_DEG = 23.44


def ecliptic_radec(step_deg: float = 5.0) -> np.ndarray:
    """Body ekliptiky (ra_hours, dec_deg) po `step_deg` ekliptikální délky, J2000."""
    lam = np.radians(np.arange(0.0, 360.0, step_deg))
    eps = np.radians(OBLIQUITY_DEG)
    ra = np.degrees(np.arctan2(np.sin(lam) * np.cos(eps), np.cos(lam))) % 360.0 / 15.0
    dec = np.degrees(np.arcsin(np.sin(lam) * np.sin(eps)))
    return np.column_stack([ra, dec])


class Ephemeris:
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.load = Loader(str(self.cache_dir), verbose=False)
        self.ts = self.load.timescale(builtin=True)
        self.available = (self.cache_dir / EPHEMERIS).exists()
        self.eph = self.load(EPHEMERIS) if self.available else None


@lru_cache(maxsize=4)
def get_ephemeris(cache_dir: Path) -> Ephemeris:
    return Ephemeris(Path(cache_dir))


def ensure_ephemeris(cache_dir: Path) -> Path:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    Loader(str(cache_dir), verbose=False)(EPHEMERIS)   # stáhne, pokud chybí
    get_ephemeris.cache_clear()
    return cache_dir / EPHEMERIS


@dataclass(frozen=True)
class Body:
    key: str
    name: str
    alt: float
    az: float


@dataclass(frozen=True)
class SunInfo:
    alt: float
    az: float
    rise: datetime | None
    set: datetime | None
    next_rise: datetime | None
    next_set: datetime | None


@dataclass(frozen=True)
class MoonInfo:
    alt: float
    az: float
    phase_deg: float
    fraction: float
    rise: datetime | None
    set: datetime | None


@dataclass(frozen=True)
class SkyModel:
    t: datetime
    tz: ZoneInfo
    lat: float
    lon: float
    mode: str
    stars: np.ndarray                                   # (n, 3): alt, az, mag
    lines: list[tuple[str, list[np.ndarray]]]           # (n, 2): alt, az
    labels: list[tuple[str, float, float]]              # text, alt, az
    planets: list[Body]
    sun: SunInfo
    moon: MoonInfo
    ecliptic: np.ndarray = None                         # (n, 2): alt, az podél ekliptiky


def first_or_none(times, oks) -> datetime | None:
    for ti, ok in zip(times, oks):
        if ok:
            return ti.utc_datetime()
    return None


def _altaz(observer_at, target) -> tuple[float, float]:
    alt, az, _ = observer_at.observe(target).apparent().altaz(temperature_C=10.0, pressure_mbar=1010.0)
    return float(alt.degrees), float(az.degrees)


def _stars_altaz(at, ra_hours: np.ndarray, dec_deg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(ra_hours) == 0:
        return np.zeros(0), np.zeros(0)
    alt, az, _ = at.observe(Star(ra_hours=ra_hours, dec_degrees=dec_deg)).apparent().altaz()
    return np.asarray(alt.degrees, dtype=float), np.asarray(az.degrees, dtype=float)


def compute(params: Params, eph: Ephemeris, catalog: Catalog, lang: str, t: datetime) -> SkyModel:
    ts, e = eph.ts, eph.eph
    tz = tz_for(params.lat, params.lon)
    topos = wgs84.latlon(params.lat, params.lon)
    observer = e["earth"] + topos
    tt = ts.from_datetime(t)
    at = observer.at(tt)

    # Hvězdy: jeden vektorový výpočet, bez refrakce
    alt, az = _stars_altaz(at, catalog.ra_hours, catalog.dec_deg)
    stars = np.column_stack([alt, az, catalog.mag])

    # Čáry souhvězdí: všechny vrcholy najednou, pak rozřezat zpět
    parts = [seg for _, segs in catalog.lines for seg in segs]
    flat = np.concatenate(parts) if parts else np.zeros((0, 2))
    lalt, laz = _stars_altaz(at, flat[:, 0], flat[:, 1])
    lines, i = [], 0
    for cid, segs in catalog.lines:
        out = []
        for seg in segs:
            n = len(seg)
            out.append(np.column_stack([lalt[i:i + n], laz[i:i + n]]))
            i += n
        lines.append((cid, out))

    # Popisky souhvězdí (rank 1–2)
    ids = [k for k, v in catalog.names.items() if v.rank <= 2]
    calt, caz = _stars_altaz(at, np.array([catalog.names[k].ra_hours for k in ids]),
                             np.array([catalog.names[k].dec for k in ids]))
    labels = [(catalog.names[k].label(lang), float(calt[j]), float(caz[j])) for j, k in enumerate(ids)]

    planets = [Body(key, cs if lang == "cs" else en, *_altaz(at, e[key])) for key, cs, en in PLANETS]

    sun_alt, sun_az = _altaz(at, e["sun"])
    moon_alt, moon_az = _altaz(at, e["moon"])
    mode = params.mode if params.mode != "auto" else ("night" if sun_alt < NIGHT_SUN_ALT else "day")

    ecl = ecliptic_radec()
    ealt, eaz = _stars_altaz(at, ecl[:, 0], ecl[:, 1])
    ecliptic = np.column_stack([ealt, eaz])

    local0 = t.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    day0 = ts.from_datetime(local0)
    day1 = ts.from_datetime(local0 + timedelta(days=1))
    t48 = ts.from_datetime(t + timedelta(hours=48))

    sun = SunInfo(
        sun_alt, sun_az,
        rise=first_or_none(*almanac.find_risings(observer, e["sun"], day0, day1)),
        set=first_or_none(*almanac.find_settings(observer, e["sun"], day0, day1)),
        next_rise=first_or_none(*almanac.find_risings(observer, e["sun"], tt, t48)),
        next_set=first_or_none(*almanac.find_settings(observer, e["sun"], tt, t48)),
    )
    moon = MoonInfo(
        moon_alt, moon_az,
        phase_deg=float(almanac.moon_phase(e, tt).degrees) % 360.0,
        fraction=float(almanac.fraction_illuminated(e, "moon", tt)),
        rise=first_or_none(*almanac.find_risings(observer, e["moon"], day0, day1)),
        set=first_or_none(*almanac.find_settings(observer, e["moon"], day0, day1)),
    )
    return SkyModel(t, tz, params.lat, params.lon, mode, stars, lines, labels, planets, sun, moon, ecliptic)
