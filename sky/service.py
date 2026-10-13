"""Pipeline: parametry → model → render → bytes, s paměťovou cache (spec §6.4)."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sky import astro, events, iss, output, render
from sky.catalog import load_catalog
from sky.config import Config
from sky.params import Params

log = logging.getLogger(__name__)
_cache: dict[tuple, tuple[float, "Result"]] = {}
CACHE_MAX_ENTRIES = 256


class EphemerisMissing(RuntimeError):
    pass


@dataclass(frozen=True)
class Result:
    data: bytes
    mime: str
    mode: str


def _key(p: Params, t: datetime) -> tuple:
    return (p, t.replace(second=0, microsecond=0, minute=t.minute - t.minute % 5))


def build(params: Params, cfg: Config, now: datetime | None = None) -> Result:
    t = params.t or now or datetime.now(timezone.utc)
    key = _key(params, t)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < cfg.render_cache_s:
        return hit[1]
    eph = astro.get_ephemeris(cfg.cache_dir)
    if not eph.available:
        log.error("chybí %s v %s", astro.EPHEMERIS, cfg.cache_dir)
        raise EphemerisMissing(f"chybí efemerida {astro.EPHEMERIS}; spusť `python -m sky warmup`")
    t0 = time.perf_counter()
    model = astro.compute(params, eph, load_catalog(), params.lang, t)
    if params.iss:
        iss_info = iss.compute(params, eph, iss.load_tle(cfg), t)
    else:
        iss_info = iss.IssInfo(False, None, None, None)
    evs = events.upcoming(cfg, t.astimezone(model.tz).date()) if params.events else []
    img = render.render(params, model, iss_info, evs)
    data, mime = output.encode(img, params.fmt, params.rot)
    log.info("render %s %dx%d %s %s mode=%s %.0f ms", params.view, params.w, params.h, params.colors,
             params.fmt, model.mode, (time.perf_counter() - t0) * 1000)
    res = Result(data, mime, model.mode)
    if len(_cache) >= CACHE_MAX_ENTRIES:
        _cache.clear()
    _cache[key] = (time.time(), res)
    return res
