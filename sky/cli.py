"""CLI: render / serve / warmup (spec §3.2)."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sky import config, service
from sky.params import ParamError, parse

QUERY_KEYS = ("lat", "lon", "view", "az", "fov", "w", "h", "colors", "rot", "t", "lang")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="sky", description="Aktuální obloha pro e-paper.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="vykreslí obrázek do souboru (formát podle přípony .png/.bmp)")
    for k in QUERY_KEYS:
        r.add_argument(f"--{k}")
    r.add_argument("--no-iss", action="store_true")
    r.add_argument("--no-events", action="store_true")
    r.add_argument("--out", required=True)

    s = sub.add_parser("serve", help="spustí HTTP službu (v kontejneru použij --host 0.0.0.0)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8080)

    sub.add_parser("warmup", help="stáhne efemeridu do cache")
    return ap


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    cfg = config.load()

    if a.cmd == "warmup":
        from sky.astro import ensure_ephemeris
        print(ensure_ephemeris(cfg.cache_dir))
        return 0
    if a.cmd == "serve":
        import uvicorn
        # access log vypnut: URL nese token; vlastní INFO řádek je v service.build
        uvicorn.run("sky.app:app", host=a.host, port=a.port, access_log=False)
        return 0

    q = {k: v for k, v in vars(a).items() if k in QUERY_KEYS and v}
    if a.no_iss:
        q["iss"] = "0"
    if a.no_events:
        q["events"] = "0"
    fmt = Path(a.out).suffix.lstrip(".").lower() or "png"
    try:
        params = parse(q, cfg, fmt)
        res = service.build(params, cfg)
    except (ParamError, service.EphemerisMissing) as exc:
        print(f"chyba: {exc}", file=sys.stderr)
        return 2
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_bytes(res.data)
    print(f"{a.out}: {len(res.data)} B, mode={res.mode}")
    return 0
