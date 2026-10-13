"""Nálezy bezpečnostní revize: limit stažení, URL bez query v logu, vadné TLE, token."""
import io
import logging
import urllib.request
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sky import config, iss, netcache
from sky.app import create_app
from sky.params import parse


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_download_is_size_capped(monkeypatch):
    from tests.conftest import REAL_DOWNLOAD
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: _Resp(b"x" * (netcache.MAX_BYTES + 10)))
    with pytest.raises(netcache.TooLarge):
        REAL_DOWNLOAD("http://x/a.ics", 1.0)


def test_log_hides_query(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(netcache, "_download", lambda url, timeout: (_ for _ in ()).throw(OSError("net")))
    with caplog.at_level(logging.WARNING):
        netcache.fetch_text("https://h.example/p/basic.ics?secret=abc", tmp_path / "x", 10)
    assert "secret" not in caplog.text and "h.example/p/basic.ics" in caplog.text


def test_malformed_tle_is_unavailable():
    bad = ("ISS", "1 25544U 98067A   ZZ285.85396186  .00006018  00000+0  11791-3 0  9995",
           "2 25544  51.6314  77.7958 0006705 255.2292 104.7953 15.48843879589996")
    with pytest.raises(ValueError):
        iss.tle_epoch(bad[1])
    p = parse({"lat": "49.747", "lon": "13.378"}, config.load({}), "png")

    class E:
        available = True
        ts = None
        eph = None

    from datetime import datetime, timezone
    info = iss.compute(p, E(), ("ISS", "1 garbage" + " " * 60, "2 garbage" + " " * 60), datetime.now(timezone.utc))
    assert info == iss.IssInfo(False, None, None, None)


def test_token_compare_accepts_correct_token():
    c = TestClient(create_app(config.load({"SKY_CACHE_DIR": "cache", "SKY_TOKEN": "s3cret"})))
    # špatný token → 403, správný → projde až k parametrům (400 kvůli lat mimo rozsah)
    assert c.get("/sky.png?lat=99&lon=1&token=s3cre").status_code == 403
    assert c.get("/sky.png?lat=99&lon=1&token=s3cret").status_code == 400


def test_serve_binds_localhost_by_default():
    from sky.cli import build_parser
    a = build_parser().parse_args(["serve"])
    assert a.host == "127.0.0.1" and a.port == 8080


def test_log_hides_userinfo(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(netcache, "_download", lambda url, timeout: (_ for _ in ()).throw(OSError("net")))
    with caplog.at_level(logging.WARNING):
        netcache.fetch_text("https://user:pw@h.example/p.ics", tmp_path / "x", 10)
    assert "pw" not in caplog.text and "h.example/p.ics" in caplog.text


@pytest.mark.skipif(not Path("cache/de421.bsp").exists(), reason="de421.bsp missing")
def test_render_failure_is_500_not_crash(monkeypatch):
    from sky import service
    monkeypatch.setattr(service.render, "render", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    c = TestClient(create_app(config.load({"SKY_CACHE_DIR": "cache"})), raise_server_exceptions=False)
    r = c.get("/sky.png?lat=49&lon=13&t=2026-05-05T00:00Z&w=100&h=100")
    assert r.status_code == 500 and "vykreslení selhalo" in r.text and "cache" not in r.text


def test_non_ascii_token_is_403_not_500():
    c = TestClient(create_app(config.load({"SKY_CACHE_DIR": "cache", "SKY_TOKEN": "s3cret"})),
                   raise_server_exceptions=False)
    assert c.get("/sky.png?lat=49&lon=13&token=%C4%8D").status_code == 403
    c2 = TestClient(create_app(config.load({"SKY_CACHE_DIR": "cache", "SKY_TOKEN": "heslíčko"})),
                    raise_server_exceptions=False)
    assert c2.get("/sky.png?lat=99&lon=13&token=hesl%C3%AD%C4%8Dko").status_code == 400


@pytest.mark.skipif(not Path("cache/de421.bsp").exists(), reason="de421.bsp missing")
def test_time_outside_ephemeris_is_400():
    c = TestClient(create_app(config.load({"SKY_CACHE_DIR": "cache"})), raise_server_exceptions=False)
    r = c.get("/sky.png?lat=49&lon=13&t=1850-01-01T00:00Z")
    assert r.status_code == 400 and "1900" in r.text


def test_tz_lookup_is_consistent_across_threads():
    from concurrent.futures import ThreadPoolExecutor
    from sky.geo import tz_for, _tz_lock
    pts = [(49.747, 13.378), (40.7, -74.0), (35.7, 139.7), (-33.9, 151.2)] * 25
    with ThreadPoolExecutor(8) as ex:
        keys = list(ex.map(lambda p: tz_for(*p).key, pts))
    assert keys == [tz_for(*p).key for p in pts]
    assert _tz_lock is not None


def test_serve_disables_access_log(monkeypatch):
    import uvicorn
    from sky.cli import main
    calls = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.update(kw))
    assert main(["serve", "--port", "1"]) == 0
    assert calls.get("access_log") is False


def test_dockerfile_disables_access_log():
    assert "--no-access-log" in Path("Dockerfile").read_text(encoding="utf-8")


def test_render_cache_bounded_by_bytes(monkeypatch):
    from datetime import datetime, timezone
    from sky import service
    from sky.params import parse
    service._cache.clear()
    cfg = config.load({"SKY_CACHE_DIR": "cache", "SKY_RENDER_CACHE_S": "300"})
    big = service.Result(b"x" * (service.MAX_CACHE_BYTES + 1), "image/png", "night")
    small = service.Result(b"y", "image/png", "night")
    p = parse({"lat": "1", "lon": "2"}, cfg, "png")
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    service._store(p, t, big, cfg)
    assert service._cache == {}
    service._store(p, t, small, cfg)
    assert len(service._cache) == 1
    # prošlé položky se při vkládání uklidí
    key = next(iter(service._cache))
    service._cache[key] = (0.0, small)
    service._store(parse({"lat": "3", "lon": "4"}, cfg, "png"), t, small, cfg)
    assert key not in service._cache and len(service._cache) == 1
    service._cache.clear()


def test_rate_limit_per_ip():
    from sky import app as app_mod
    app_mod._limiter.clear()
    c = TestClient(create_app(config.load({"SKY_CACHE_DIR": "cache", "SKY_RATE_LIMIT": "3"})))
    codes = [c.get("/sky.png?lat=99&lon=1").status_code for _ in range(4)]
    assert codes == [400, 400, 400, 429]
    assert c.get("/health").status_code == 200        # health a stránka se nelimitují
    assert c.get("/").status_code == 200
    app_mod._limiter.clear()
    c0 = TestClient(create_app(config.load({"SKY_CACHE_DIR": "cache", "SKY_RATE_LIMIT": "0"})))
    assert all(c0.get("/sky.png?lat=99&lon=1").status_code == 400 for _ in range(5))


def test_forwarded_for_is_ignored_unless_trusted():
    from sky import app as app_mod
    app_mod._limiter.clear()
    c = TestClient(create_app(config.load({"SKY_CACHE_DIR": "cache", "SKY_RATE_LIMIT": "2"})))
    # bez SKY_TRUST_PROXY se počítá skutečný klient, podvržená hlavička limit neobejde
    codes = [c.get("/sky.png?lat=99&lon=1", headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code for i in range(3)]
    assert codes == [400, 400, 429]
    app_mod._limiter.clear()
    c2 = TestClient(create_app(config.load({"SKY_CACHE_DIR": "cache", "SKY_RATE_LIMIT": "2", "SKY_TRUST_PROXY": "1"})))
    # za proxy platí poslední položka (doplněná proxy); klientem předřazené hodnoty se ignorují
    codes = [c2.get("/sky.png?lat=99&lon=1", headers={"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.5"}).status_code
             for i in range(3)]
    assert codes == [400, 400, 429]
    app_mod._limiter.clear()


def test_limiter_prune_keeps_active_counters():
    from sky import app as app_mod
    app_mod._limiter.clear()
    now = __import__("time").time()
    app_mod._limiter["active"] = [now, now, now]
    for i in range(app_mod.LIMITER_MAX_IPS + 5):
        app_mod._limiter[f"stale{i}"] = [now - 3600]
    assert app_mod._rate_limited("active", 3) is True          # čítač aktivní IP přežil úklid
    assert len(app_mod._limiter) <= app_mod.LIMITER_MAX_IPS + 1
    app_mod._limiter.clear()
