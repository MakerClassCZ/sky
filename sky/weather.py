"""Oblačnost na noc z Open-Meteo (bez klíče, nekomerční použití, CC BY 4.0).

Souřadnice se zaokrouhlují na 0,05° (~5 km) a předpověď se cachuje hodinu, aby
veřejná instance s mnoha panely nedělala zbytečné dotazy.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sky.config import Config
from sky.geo import tr
from sky.netcache import fetch_text

log = logging.getLogger(__name__)
WEATHER_MAX_AGE_S = 3600


@dataclass(frozen=True)
class CloudInfo:
    mean: int           # průměrná oblačnost v noci v %
    best: int           # nejnižší hodinová oblačnost v %
    best_at: datetime   # kdy (UTC, celá hodina)


def cache_key(lat: float, lon: float) -> str:
    return f"{round(lat * 20) / 20:.2f}_{round(lon * 20) / 20:.2f}"


def build_url(cfg: Config, lat: float, lon: float) -> str:
    la, lo = round(lat * 20) / 20, round(lon * 20) / 20
    return f"{cfg.weather_url}?latitude={la:g}&longitude={lo:g}&hourly=cloud_cover&forecast_days=2&timezone=UTC"


def night_cloud(text: str, start: datetime, end: datetime) -> CloudInfo | None:
    """Průměr a minimum oblačnosti v hodinách mezi `start` a `end` (UTC)."""
    try:
        data = json.loads(text)
        times = data["hourly"]["time"]
        cover = data["hourly"]["cloud_cover"]
    except (ValueError, KeyError, TypeError):
        return None
    hours: list[tuple[datetime, int]] = []
    for ts, c in zip(times, cover):
        if c is None:
            continue
        try:
            dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if start <= dt <= end:
            hours.append((dt, int(c)))
    if not hours:
        return None
    best_at, best = min(hours, key=lambda h: (h[1], h[0]))
    return CloudInfo(round(sum(c for _, c in hours) / len(hours)), best, best_at)


def line(lang: str, tz: ZoneInfo, info: CloudInfo, max_chars: int) -> str:
    full = f"{tr(lang, 'clouds')} {info.mean} %, min {info.best} % {tr(lang, 'at')} {info.best_at.astimezone(tz).strftime('%H:%M')}"
    short = f"{tr(lang, 'clouds')} {info.mean} %"
    return full if len(full) <= max_chars else short


def tonight(cfg: Config, lat: float, lon: float, start: datetime, end: datetime) -> CloudInfo | None:
    text = fetch_text(build_url(cfg, lat, lon), cfg.cache_dir / f"weather_{cache_key(lat, lon)}.json", WEATHER_MAX_AGE_S)
    return night_cloud(text, start, end) if text else None
