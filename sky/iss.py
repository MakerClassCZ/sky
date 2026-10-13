"""ISS: TLE z Celestrak s cache, aktuální poloha, nejbližší viditelný přelet (spec §6.2)."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from skyfield.api import EarthSatellite, wgs84

from sky.config import Config
from sky.netcache import fetch_text
from sky.params import Params

log = logging.getLogger(__name__)
TLE_MAX_AGE_S = 86400
MIN_ALT = 10.0
CIVIL_DUSK = -6.0
LOOKAHEAD = timedelta(hours=48)


@dataclass(frozen=True)
class Pass:
    start: datetime
    end: datetime
    max_alt: float
    max_az: float


@dataclass(frozen=True)
class IssInfo:
    available: bool
    alt: float | None
    az: float | None
    next_pass: Pass | None


def parse_tle(text: str) -> tuple[str, str, str] | None:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for i, ln in enumerate(lines):
        if ln.startswith("1 ") and i + 1 < len(lines) and lines[i + 1].startswith("2 "):
            if len(ln) < 60 or len(lines[i + 1]) < 60:
                return None
            name = lines[i - 1] if i > 0 else "ISS"
            return (name, ln, lines[i + 1])
    return None


def load_tle(cfg: Config) -> tuple[str, str, str] | None:
    text = fetch_text(cfg.tle_url, cfg.cache_dir / "iss.tle", TLE_MAX_AGE_S)
    return parse_tle(text) if text else None


def tle_epoch(line1: str) -> datetime:
    yy = int(line1[18:20])
    doy = float(line1[20:32])
    year = 2000 + yy if yy < 57 else 1900 + yy
    return datetime(year, 1, 1, tzinfo=timezone.utc) + timedelta(days=doy - 1)


def find_visible_passes(sat, observer, topos, eph, t0, t1) -> list[Pass]:
    """Přelety nad MIN_ALT, při kulminaci osvětlené Sluncem a za občanského soumraku."""
    times, events = sat.find_events(topos, t0, t1, altitude_degrees=MIN_ALT)
    passes: list[Pass] = []
    start = culm = None
    for ti, ev in zip(times, events):
        if ev == 0:
            start, culm = ti, None
        elif ev == 1:
            culm = ti
        elif ev == 2 and start is not None and culm is not None:
            sunlit = bool(sat.at(culm).is_sunlit(eph.eph))
            sun_alt = observer.at(culm).observe(eph.eph["sun"]).apparent().altaz()[0].degrees
            if sunlit and sun_alt < CIVIL_DUSK:
                alt, az, _ = (sat - topos).at(culm).altaz()
                passes.append(Pass(start.utc_datetime(), ti.utc_datetime(),
                                   float(alt.degrees), float(az.degrees)))
            start = culm = None
    return passes


def compute(params: Params, eph, tle, t: datetime | None) -> IssInfo:
    if tle is None or eph is None or not eph.available or t is None:
        return IssInfo(False, None, None, None)
    name, l1, l2 = tle
    try:
        sat = EarthSatellite(l1, l2, name, eph.ts)
        topos = wgs84.latlon(params.lat, params.lon)
        observer = eph.eph["earth"] + topos
        tt = eph.ts.from_datetime(t)
        alt, az, _ = (sat - topos).at(tt).altaz()
        passes = find_visible_passes(sat, observer, topos, eph, tt, eph.ts.from_datetime(t + LOOKAHEAD))
    except Exception as exc:  # noqa: BLE001 – vadné TLE ze sítě nesmí shodit render
        log.warning("ISS: výpočet selhal (%s)", type(exc).__name__)
        return IssInfo(False, None, None, None)
    return IssInfo(True, float(alt.degrees), float(az.degrees), passes[0] if passes else None)
