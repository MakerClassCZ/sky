"""Kalendář úkazů (ICS Google kalendáře Jana Tichého), spec §6.3."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import icalendar
import recurring_ical_events

from sky.config import Config
from sky.netcache import fetch_text

log = logging.getLogger(__name__)
ICS_MAX_AGE_S = 86400
WINDOW_DAYS = 60

# (prefix, kind)
EMOJI_KINDS = [
    ("👁", "eye"), ("🔭", "scope"), ("⚠", "warn"),
    ("🌑", "moon"), ("🌒", "moon"), ("🌓", "moon"), ("🌔", "moon"),
    ("🌕", "moon"), ("🌖", "moon"), ("🌗", "moon"), ("🌘", "moon"),
    ("⛒", "none"), ("ℹ", "info"),
]
_STRIP = "️‍ \t"


@dataclass(frozen=True)
class Event:
    date: date
    title: str
    kind: str


def classify(summary: str) -> tuple[str, str]:
    s = summary.strip()
    for prefix, kind in EMOJI_KINDS:
        if s.startswith(prefix):
            return kind, s[len(prefix):].lstrip(_STRIP)
    return "other", s


def parse_events(ics_text: str, start: date, days: int = WINDOW_DAYS) -> list[Event]:
    cal = icalendar.Calendar.from_ical(ics_text)
    end = start + timedelta(days=days)
    seen: set[tuple[date, str]] = set()
    out: list[Event] = []
    for comp in recurring_ical_events.of(cal).between(start, end):
        d = comp.get("DTSTART").dt
        if isinstance(d, datetime):
            d = d.date()
        kind, title = classify(str(comp.get("SUMMARY", "")))
        key = (d, title)
        if key in seen or not title:
            continue
        seen.add(key)
        out.append(Event(d, title, kind))
    out.sort(key=lambda e: (e.date, e.title))
    return out


def select(events: list[Event], kinds: tuple[str, ...], n: int) -> list[Event]:
    return [e for e in events if e.kind in kinds][:n]


def upcoming(cfg: Config, today: date, n: int = 12) -> list[Event] | None:
    """Dalších n úkazů od dneška; None = data nedostupná."""
    text = fetch_text(cfg.events_url, cfg.cache_dir / "events.ics", ICS_MAX_AGE_S)
    if not text:
        return None
    try:
        return select(parse_events(text, today), cfg.event_types, n)
    except Exception as exc:  # noqa: BLE001 – vadný ICS nesmí shodit render
        log.warning("ICS parse failed: %s", exc)
        return None
