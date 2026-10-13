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
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout: _Resp(b"x" * (netcache.MAX_BYTES + 10)))
    with pytest.raises(netcache.TooLarge):
        netcache._download("http://x/a.ics", 1.0)


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
def test_render_failure_is_500_not_crash():
    c = TestClient(create_app(config.load({"SKY_CACHE_DIR": "cache"})), raise_server_exceptions=False)
    r = c.get("/sky.png?lat=49&lon=13&t=2300-01-01T00:00Z")   # mimo rozsah efemeridy
    assert r.status_code == 500 and "vykreslení selhalo" in r.text and "cache" not in r.text
