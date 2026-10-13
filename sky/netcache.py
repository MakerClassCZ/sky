"""Stažení textu s diskovou cache: čerstvá cache → síť → stará cache → None."""
from __future__ import annotations

import logging
import time
import urllib.parse
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)
MAX_BYTES = 4 * 1024 * 1024     # ICS úkazů má ~0,5 MB, TLE pár set B


class TooLarge(RuntimeError):
    pass


def _download(url: str, timeout: float) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "sky-epaper/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise TooLarge(f"odpověď přes {MAX_BYTES} B")
    return data.decode("utf-8", errors="replace")


def _safe_url(url: str) -> str:
    """URL bez query a bez user:pass (mohou nést tajemství) pro log."""
    s = urllib.parse.urlsplit(url)
    return f"{s.hostname or ''}{s.path}"


def fetch_text(url: str, path: Path, max_age_s: int, timeout: float = 10.0) -> str | None:
    if path.exists() and time.time() - path.stat().st_mtime < max_age_s:
        return path.read_text(encoding="utf-8")
    try:
        text = _download(url, timeout)
    except Exception as exc:  # noqa: BLE001 – síť nikdy nesmí shodit render
        if path.exists():
            log.warning("%s: stažení selhalo (%s), používám starou cache", _safe_url(url), type(exc).__name__)
            return path.read_text(encoding="utf-8")
        log.warning("%s: stažení selhalo (%s), cache není", _safe_url(url), type(exc).__name__)
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text
