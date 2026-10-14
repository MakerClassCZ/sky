"""Oblačnost na noc z Open-Meteo (bez klíče, nekomerční použití, CC BY 4.0).

Souřadnice se zaokrouhlují na 0,05° (~5 km) a předpověď se cachuje hodinu, aby
veřejná instance s mnoha panely nedělala zbytečné dotazy. Vedle celkové oblačnosti
se bere i nízká / střední / vysoká vrstva a dohlednost: pro pozorování rozhoduje
nízká oblačnost a mlha, řídké vysoké cirry jasné objekty propustí.
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
HOURLY = "cloud_cover,cloud_cover_low,cloud_cover_mid,cloud_cover_high,visibility"
CLEAR_BELOW = 20        # pod tolik % průměru se vrstva neuvádí
LOW_DECIDES = 50        # nízká oblačnost nad tolik % rozhoduje bez ohledu na ostatní
FOG_VIS_M = 1000        # dohlednost pod 1 km = mlha


@dataclass(frozen=True)
class CloudInfo:
    mean: int           # průměrná celková oblačnost v noci v %
    best: int           # celková oblačnost v nejlepší hodině v %
    best_at: datetime   # nejlepší hodina (UTC) podle „efektivní“ oblačnosti (nízká + střední + ½ vysoké)
    layer: str = ""     # "" | "low" | "mid" | "high" | "fog" – převládající vrstva za noc


def cache_key(lat: float, lon: float) -> str:
    return f"{round(lat * 20) / 20:.2f}_{round(lon * 20) / 20:.2f}"


def build_url(cfg: Config, lat: float, lon: float) -> str:
    la, lo = round(lat * 20) / 20, round(lon * 20) / 20
    return f"{cfg.weather_url}?latitude={la:g}&longitude={lo:g}&hourly={HOURLY}&forecast_days=2&timezone=UTC"


def _series(hourly: dict, key: str, n: int) -> list | None:
    vals = hourly.get(key)
    return vals if isinstance(vals, list) and len(vals) == n else None


def night_cloud(text: str, start: datetime, end: datetime) -> CloudInfo | None:
    """Souhrn oblačnosti v hodinách mezi `start` a `end` (UTC)."""
    try:
        hourly = json.loads(text)["hourly"]
        times = hourly["time"]
        cover = hourly["cloud_cover"]
    except (ValueError, KeyError, TypeError):
        return None
    n = len(times)
    low, mid, high, vis = (_series(hourly, k, n) for k in ("cloud_cover_low", "cloud_cover_mid",
                                                           "cloud_cover_high", "visibility"))
    layers = low is not None and mid is not None and high is not None
    rows = []       # (čas, celkem, efektivní, nízká, střední, vysoká, mlha?)
    for i, (ts, c) in enumerate(zip(times, cover)):
        if c is None:
            continue
        try:
            dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if not (start <= dt <= end):
            continue
        if layers and None not in (low[i], mid[i], high[i]):
            lo, mi, hi = int(low[i]), int(mid[i]), int(high[i])
            eff = min(100, lo + mi + hi // 2)
        else:
            lo = mi = hi = 0
            eff = int(c)
        fog = vis is not None and vis[i] is not None and float(vis[i]) < FOG_VIS_M
        rows.append((dt, int(c), eff, lo, mi, hi, fog))
    if not rows:
        return None
    best_at, best = min(((r[0], r[1]) for r in rows), key=lambda h: (next(r[2] for r in rows if r[0] == h[0]), h[0]))
    mean = round(sum(r[1] for r in rows) / len(rows))
    layer = ""
    if sum(r[6] for r in rows) * 2 > len(rows):
        layer = "fog"
    elif layers and mean >= CLEAR_BELOW:
        means = {k: sum(r[j] for r in rows) / len(rows) for k, j in (("low", 3), ("mid", 4), ("high", 5))}
        layer = "low" if means["low"] >= LOW_DECIDES else max(means, key=lambda k: (means[k], k == "low"))
    return CloudInfo(mean, best, best_at, layer)


def line(lang: str, tz: ZoneInfo, info: CloudInfo, max_chars: int) -> str:
    """Nejdelší varianta, která se vejde: s vrstvou a minimem, s vrstvou, zkráceně s vrstvou, bez vrstvy, zkráceně."""
    layer = f" {tr(lang, 'layer_' + info.layer)}" if info.layer else ""
    when = f"min {info.best} % {tr(lang, 'at')} {info.best_at.astimezone(tz).strftime('%H:%M')}"
    variants = [
        f"{tr(lang, 'clouds')} {info.mean} %{layer}, {when}",
        f"{tr(lang, 'clouds')} {info.mean} %{layer}",
        f"{tr(lang, 'clouds_short')} {info.mean} %{layer}",
        f"{tr(lang, 'clouds')} {info.mean} %",
        f"{tr(lang, 'clouds_short')} {info.mean} %",
    ]
    return next((v for v in variants if len(v) <= max_chars), variants[-1])


def tonight(cfg: Config, lat: float, lon: float, start: datetime, end: datetime) -> CloudInfo | None:
    text = fetch_text(build_url(cfg, lat, lon), cfg.cache_dir / f"weather_{cache_key(lat, lon)}.json", WEATHER_MAX_AGE_S)
    return night_cloud(text, start, end) if text else None
