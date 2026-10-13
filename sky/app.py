"""HTTP rozhraní (spec §3.1)."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

from sky import astro, config, service
from sky.params import ParamError, parse

log = logging.getLogger(__name__)


def create_app(cfg: config.Config | None = None) -> FastAPI:
    cfg = cfg or config.load()
    app = FastAPI(title="sky-epaper", docs_url=None, redoc_url=None)

    @app.get("/health")
    def health():
        eph = astro.get_ephemeris(cfg.cache_dir)
        return {"status": "ok" if eph.available else "degraded",
                "ephemeris": "ok" if eph.available else "missing"}

    @app.get("/sky.{fmt}")
    def sky(fmt: str, request: Request):
        q = dict(request.query_params)
        if cfg.token and q.get("token") != cfg.token:
            return PlainTextResponse("forbidden", status_code=403)
        try:
            params = parse(q, cfg, fmt)
        except ParamError as exc:
            return PlainTextResponse(str(exc), status_code=400)
        try:
            res = service.build(params, cfg)
        except service.EphemerisMissing as exc:
            return PlainTextResponse(str(exc), status_code=503)
        return Response(res.data, media_type=res.mime,
                        headers={"Cache-Control": "no-store", "X-Sky-Mode": res.mode})

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
