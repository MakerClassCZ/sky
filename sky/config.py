"""Konfigurace z proměnných prostředí (spec §3.3)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

DEFAULT_EVENTS_URL = (
    "https://calendar.google.com/calendar/ical/"
    "c_f45884b2c6eaf4644407e4587ff09bc7205bb9b47cb965f5566c02083578eecb"
    "%40group.calendar.google.com/public/basic.ics"
)
DEFAULT_TLE_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=tle"
DEFAULT_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_COMETS_URL = "https://www.minorplanetcenter.net/iau/MPCORB/CometEls.txt"
DEFAULT_ROCKETS_URL = "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=40&format=json&mode=list"


@dataclass(frozen=True)
class Config:
    cache_dir: Path
    lat: float | None
    lon: float | None
    token: str | None
    events_url: str
    tle_url: str
    rockets_url: str
    weather_url: str
    comets_url: str
    render_cache_s: int
    event_types: tuple[str, ...]
    rate_limit: int            # požadavků na /sky.* za minutu a IP; 0 = bez limitu
    trust_proxy: str           # "0" = IP ze spojení; "1" = poslední X-Forwarded-For; "cloudflare" = navíc CF-Connecting-IP


def _float_or_none(v: str | None) -> float | None:
    return None if v in (None, "") else float(v)


def load(env: Mapping[str, str] | None = None) -> Config:
    e = os.environ if env is None else env
    types = tuple(s.strip() for s in e.get("SKY_EVENT_TYPES", "eye,scope,warn,moon").split(",") if s.strip())
    return Config(
        cache_dir=Path(e.get("SKY_CACHE_DIR", "cache")),
        lat=_float_or_none(e.get("SKY_LAT")),
        lon=_float_or_none(e.get("SKY_LON")),
        token=e.get("SKY_TOKEN") or None,
        events_url=e.get("SKY_EVENTS_URL", DEFAULT_EVENTS_URL),
        tle_url=e.get("SKY_TLE_URL", DEFAULT_TLE_URL),
        rockets_url=e.get("SKY_ROCKETS_URL", DEFAULT_ROCKETS_URL),
        weather_url=e.get("SKY_WEATHER_URL", DEFAULT_WEATHER_URL),
        comets_url=e.get("SKY_COMETS_URL", DEFAULT_COMETS_URL),
        render_cache_s=int(e.get("SKY_RENDER_CACHE_S", "300")),
        event_types=types,
        rate_limit=int(e.get("SKY_RATE_LIMIT", "60")),
        trust_proxy=e.get("SKY_TRUST_PROXY", "0").strip().lower(),
    )
