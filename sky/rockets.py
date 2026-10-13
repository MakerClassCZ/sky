"""Starty raket z Launch Library 2 (The Space Devs), bez klíče, 15 dotazů/h → cache 6 h."""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sky.config import Config
from sky.events import Event
from sky.netcache import fetch_text

log = logging.getLogger(__name__)
LAUNCHES_MAX_AGE_S = 6 * 3600
WINDOW_DAYS = 60
# proběhlé starty a starty bez známého data se nezobrazují
SKIP_STATUS = {"Success", "Failure", "Partial Failure", "TBD"}


def short_title(name: str) -> str:
    """'Falcon 9 Block 5 | Starlink Group 15-25' → 'Starlink 15-25 (Falcon 9)'."""
    rocket, sep, mission = name.partition("|")
    rocket = re.sub(r"\s+Block\s+\d+\w*", "", rocket).strip()
    if not sep or not mission.strip():
        return rocket or name.strip()
    mission = mission.replace("Group ", "").strip()
    return f"{mission} ({rocket})"


def parse_launches(text: str, start: date, tz: ZoneInfo, days: int = WINDOW_DAYS) -> list[Event]:
    try:
        data = json.loads(text)
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []
    end = start + timedelta(days=days)
    out: list[Event] = []
    for r in data.get("results", []):
        try:
            net = datetime.fromisoformat(str(r["net"]).replace("Z", "+00:00")).astimezone(tz)
            name = str(r["name"]).strip()
            status = (r.get("status") or {}).get("abbrev", "")
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if not name or status in SKIP_STATUS:
            continue
        if start <= net.date() <= end:
            out.append(Event(net.date(), short_title(name), "rocket", net.strftime("%H:%M")))
    out.sort(key=lambda e: (e.date, e.time))
    return out


def upcoming(cfg: Config, today: date, tz: ZoneInfo, n: int = 12) -> list[Event]:
    text = fetch_text(cfg.rockets_url, cfg.cache_dir / "launches.json", LAUNCHES_MAX_AGE_S)
    return parse_launches(text, today, tz)[:n] if text else []
