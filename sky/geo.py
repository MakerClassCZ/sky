"""Časová zóna, formátování a texty (cs/en)."""
from __future__ import annotations

import threading
from datetime import date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

DAYS = {"cs": ["po", "út", "st", "čt", "pá", "so", "ne"],
        "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]}
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
COMPASS = {"cs": ["S", "SV", "V", "JV", "J", "JZ", "Z", "SZ"],
           "en": ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]}
TEXTS = {
    "cs": {"sun": "Slunce", "moon": "Měsíc", "iss": "ISS", "events": "Úkazy",
           "rise": "Východ", "set": "Západ", "night_from": "Noc od", "dawn_at": "Svítá v",
           "phase": "Fáze", "waxing": "dorůstá", "waning": "couvá",
           "no_pass": "žádný do 48 h", "unavailable": "nedostupné", "max": "max",
           "none": "nic do 60 dnů", "data_from": "Zdroj: jantichy.cz/ukazy"},
    "en": {"sun": "Sun", "moon": "Moon", "iss": "ISS", "events": "Events",
           "rise": "Rise", "set": "Set", "night_from": "Night from", "dawn_at": "Dawn at",
           "phase": "Phase", "waxing": "waxing", "waning": "waning",
           "no_pass": "none in 48 h", "unavailable": "unavailable", "max": "max",
           "none": "none in 60 days", "data_from": "Source: jantichy.cz/ukazy"},
}


_tz_lock = threading.Lock()   # TimezoneFinder není thread-safe (viz docstring knihovny)


@lru_cache(maxsize=None)
def _finder():
    from timezonefinder import TimezoneFinder
    return TimezoneFinder()


def tz_for(lat: float, lon: float) -> ZoneInfo:
    try:
        with _tz_lock:
            name = _finder().timezone_at(lat=lat, lng=lon)
        return ZoneInfo(name or "UTC")
    except Exception:  # noqa: BLE001 – neznámá zóna nesmí shodit render
        return ZoneInfo("UTC")


def fmt_date(d: date, lang: str) -> str:
    day = DAYS[lang][d.weekday()]
    if lang == "en":
        return f"{day} {d.day} {MONTHS_EN[d.month - 1]}"
    return f"{day} {d.day}. {d.month}."


def fmt_time(dt: datetime | None, tz: ZoneInfo) -> str:
    if dt is None:
        return "–"
    return dt.astimezone(tz).strftime("%H:%M")


def compass(az: float, lang: str) -> str:
    return COMPASS[lang][int(((az % 360) + 22.5) // 45) % 8]


def tr(lang: str, key: str) -> str:
    return TEXTS[lang][key]


def fmt_coords(lat: float, lon: float) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{abs(lat):.2f}{ns} {abs(lon):.2f}{ew}"
