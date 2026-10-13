"""HTTP rozhraní (spec §3.1)."""
from __future__ import annotations

import logging
import secrets
import threading
import time

from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse

from sky import astro, config, service
from sky.params import ParamError, parse

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"
_limiter: dict[str, list[float]] = {}     # IP → časy požadavků v posledním okně
_limiter_lock = threading.Lock()
RATE_WINDOW_S = 60.0
LIMITER_MAX_IPS = 10_000


def _prune(now: float) -> None:
    """Úklid tabulky bez ztráty aktivních čítačů: nejdřív IP bez zásahu v okně, pak nejstarší."""
    for ip in [ip for ip, hits in _limiter.items() if not hits or now - hits[-1] >= RATE_WINDOW_S]:
        del _limiter[ip]
    if len(_limiter) > LIMITER_MAX_IPS:
        for ip, _ in sorted(_limiter.items(), key=lambda kv: kv[1][-1])[: len(_limiter) - LIMITER_MAX_IPS]:
            del _limiter[ip]


def _rate_limited(ip: str, limit: int) -> bool:
    """Posuvné okno 60 s na IP; při překročení True. Veřejná instance bez tokenu."""
    if limit <= 0:
        return False
    now = time.time()
    with _limiter_lock:
        if len(_limiter) > LIMITER_MAX_IPS:
            _prune(now)
        hits = [t for t in _limiter.get(ip, ()) if now - t < RATE_WINDOW_S]
        if len(hits) >= limit:
            _limiter[ip] = hits
            return True
        hits.append(now)
        _limiter[ip] = hits
    return False


def _client_ip(request: Request, trust_proxy: bool) -> str:
    """Za důvěryhodnou proxy platí poslední položka X-Forwarded-For (tu doplnila proxy);
    bez proxy se hlavička ignoruje, protože si ji může poslat sám klient."""
    if trust_proxy:
        xff = request.headers.get("x-forwarded-for", "")
        last = xff.split(",")[-1].strip() if xff else ""
        if last:
            return last
    return request.client.host if request.client else "?"


def create_app(cfg: config.Config | None = None) -> FastAPI:
    cfg = cfg or config.load()
    app = FastAPI(title="sky-epaper", docs_url=None, redoc_url=None)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html",
                            headers={"Cache-Control": "no-cache"})

    @app.get("/health")
    def health():
        eph = astro.get_ephemeris(cfg.cache_dir)
        return {"status": "ok" if eph.available else "degraded",
                "ephemeris": "ok" if eph.available else "missing"}

    @app.get("/sky.{fmt}")
    def sky(fmt: str, request: Request):
        q = dict(request.query_params)
        if _rate_limited(_client_ip(request, cfg.trust_proxy), cfg.rate_limit):
            return PlainTextResponse("příliš mnoho požadavků, zkuste to za minutu", status_code=429,
                                     headers={"Retry-After": "60"})
        if cfg.token and not secrets.compare_digest(q.get("token", "").encode(), cfg.token.encode()):
            return PlainTextResponse("forbidden", status_code=403)
        try:
            params = parse(q, cfg, fmt)
        except ParamError as exc:
            return PlainTextResponse(str(exc), status_code=400)
        try:
            res = service.build(params, cfg)
        except service.EphemerisMissing as exc:
            return PlainTextResponse(str(exc), status_code=503)
        except Exception:  # noqa: BLE001 – detail do logu, klientovi jen obecná hláška
            log.exception("render failed for %s", params)
            return PlainTextResponse("vykreslení selhalo", status_code=500)
        return Response(res.data, media_type=res.mime,
                        headers={"Cache-Control": "no-store", "X-Sky-Mode": res.mode})

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
