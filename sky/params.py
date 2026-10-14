"""Parametry požadavku (spec §3.1), společné pro HTTP i CLI."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from sky.config import Config

VIEWS = ("sky", "horizon")
COLORS = ("bw", "bwr", "bwry", "spectra")
ROTS = (0, 90, 180, 270)
LANGS = ("cs", "en")
FORMATS = ("png", "bmp")
LINES = ("solid", "dashed", "dotted")
MODES = ("auto", "night", "day")
CLOCK_RE = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


class ParamError(ValueError):
    """Nevalidní parametr; text je určen uživateli (HTTP 400)."""


@dataclass(frozen=True)
class Params:
    lat: float
    lon: float
    view: str = "sky"
    az: float = 180.0
    fov: float = 120.0
    w: int = 800
    h: int = 480
    colors: str = "bw"
    rot: int = 0
    t: datetime | None = None
    iss: bool = True
    events: bool = True
    lang: str = "cs"
    fmt: str = "png"
    lines: str = "solid"
    rockets: bool = False
    t_clock: str | None = None    # "HH:MM" = dnes v tento místní čas (řeší service podle zóny místa)
    mode: str = "auto"
    weather: bool = True
    ecliptic: bool = True
    sunmoon: bool = False           # popisky Slunce a Měsíce na mapě
    constnames: bool = True         # názvy souhvězdí na mapě
    starnames: float | None = None  # jména hvězd do této magnitudy; None = vypnuto


def _num(q, key, default, lo, hi, cast):
    raw = q.get(key)
    if raw is None or raw == "":
        if default is None:
            raise ParamError(f"chybí parametr {key}")
        return default
    try:
        v = cast(raw)
    except ValueError:
        raise ParamError(f"{key}: není číslo") from None
    if not (lo <= v <= hi):
        raise ParamError(f"{key}: mimo rozsah {lo}..{hi}")
    return v


def _choice(q, key, default, allowed, cast=str):
    raw = q.get(key)
    if raw is None or raw == "":
        return default
    try:
        v = cast(raw)
    except ValueError:
        v = raw
    if v not in allowed:
        raise ParamError(f"{key}: povolené hodnoty {', '.join(map(str, allowed))}")
    return v


def _flag(q, key, default):
    raw = q.get(key)
    if raw is None or raw == "":
        return default
    if raw not in ("0", "1"):
        raise ParamError(f"{key}: povolené hodnoty 0, 1")
    return raw == "1"


YEAR_MIN, YEAR_MAX = 1900, 2050     # pokrytí efemeridy de421


def parse_time(raw: str) -> datetime:
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        raise ParamError("t: očekáván čas ISO 8601, např. 2026-10-13T22:00+02:00") from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    if not (YEAR_MIN <= dt.year <= YEAR_MAX):
        raise ParamError(f"t: rok mimo rozsah efemeridy {YEAR_MIN}–{YEAR_MAX}")
    return dt


def parse(q: Mapping[str, str], cfg: Config, fmt: str = "png") -> Params:
    if fmt not in FORMATS:
        raise ParamError("formát: povolené png, bmp")
    t_raw = q.get("t")
    t_clock = None
    if t_raw and CLOCK_RE.match(t_raw.strip()):
        hh, mm = t_raw.strip().split(":")
        t_clock, t_raw = f"{int(hh):02d}:{mm}", None
    return Params(
        lat=_num(q, "lat", cfg.lat, -90.0, 90.0, float),
        lon=_num(q, "lon", cfg.lon, -180.0, 180.0, float),
        view=_choice(q, "view", "sky", VIEWS),
        az=_num(q, "az", 180.0, 0.0, 360.0, float),
        fov=_num(q, "fov", 120.0, 30.0, 180.0, float),
        w=_num(q, "w", 800, 64, 2000, int),
        h=_num(q, "h", 480, 64, 2000, int),
        colors=_choice(q, "colors", "bw", COLORS),
        rot=_choice(q, "rot", 0, ROTS, int),
        t=parse_time(t_raw) if t_raw else None,
        iss=_flag(q, "iss", True),
        events=_flag(q, "events", True),
        lang=_choice(q, "lang", "cs", LANGS),
        fmt=fmt,
        lines=_choice(q, "lines", "solid", LINES),
        rockets=_flag(q, "rockets", False),
        t_clock=t_clock,
        mode=_choice(q, "mode", "auto", MODES),
        weather=_flag(q, "weather", True),
        ecliptic=_flag(q, "ecliptic", True),
        sunmoon=_flag(q, "sunmoon", False),
        constnames=_flag(q, "constnames", True),
        starnames=_num(q, "starnames", None, -2.0, 4.5, float) if q.get("starnames") else None,
    )
