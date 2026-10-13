from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sky import config
from sky.app import create_app

CACHE = Path("cache")
ephem = pytest.mark.skipif(not (CACHE / "de421.bsp").exists(), reason="de421.bsp missing")


def client(env):
    return TestClient(create_app(config.load(env)))


def test_health():
    r = client({"SKY_CACHE_DIR": "cache"}).get("/health")
    assert r.status_code == 200 and "ephemeris" in r.json()


def test_bad_params_400():
    c = client({"SKY_CACHE_DIR": "cache"})
    assert c.get("/sky.png?lat=99&lon=1").status_code == 400
    assert c.get("/sky.gif?lat=49&lon=13").status_code == 400
    assert c.get("/sky.png").status_code == 400


def test_token_403():
    c = client({"SKY_CACHE_DIR": "cache", "SKY_TOKEN": "s3cret"})
    assert c.get("/sky.png?lat=49&lon=13").status_code == 403
    assert c.get("/sky.png?lat=49&lon=13&token=wrong").status_code == 403


def test_missing_ephemeris_503(tmp_path):
    c = client({"SKY_CACHE_DIR": str(tmp_path)})
    r = c.get("/sky.png?lat=49&lon=13")
    assert r.status_code == 503
    assert str(tmp_path) not in r.text and "warmup" in r.text


@ephem
def test_render_png_and_bmp(monkeypatch):
    from sky import service
    monkeypatch.setattr(service.iss, "load_tle", lambda cfg: None)
    monkeypatch.setattr(service.events, "upcoming", lambda cfg, today, n=12: [])
    c = client({"SKY_CACHE_DIR": "cache"})
    r = c.get("/sky.png?lat=49.747&lon=13.378&t=2026-10-13T22:00%2B02:00")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["x-sky-mode"] == "night" and r.content[:4] == b"\x89PNG"
    assert r.headers["cache-control"] == "no-store"
    r = c.get("/sky.bmp?lat=49.747&lon=13.378&view=horizon&az=200&colors=bwry&w=480&h=800&t=2026-10-13T12:00Z")
    assert r.status_code == 200 and r.content[:2] == b"BM" and r.headers["x-sky-mode"] == "day"


@ephem
def test_render_cache_hit(monkeypatch):
    from sky import service
    calls = []
    real = service.render.render

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(service.iss, "load_tle", lambda cfg: None)
    monkeypatch.setattr(service.events, "upcoming", lambda cfg, today, n=12: [])
    monkeypatch.setattr(service.render, "render", counting)
    c = client({"SKY_CACHE_DIR": "cache"})
    url = "/sky.png?lat=49.747&lon=13.378&t=2026-10-13T23:00%2B02:00&w=200&h=200"
    assert c.get(url).status_code == 200
    assert c.get(url).status_code == 200
    assert len(calls) == 1


def test_configurator_page():
    c = client({"SKY_CACHE_DIR": "cache"})
    r = c.get("/")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    for name in ("lat", "lon", "view", "az", "fov", "w", "h", "colors", "rot", "t", "iss", "events", "lang", "mode", "weather", "ecliptic", "rockets", "lines"):
        assert f'name="{name}"' in r.text, name
    assert "/sky." in r.text
    assert 'name="token"' not in r.text and 'name="base"' not in r.text   # veřejné rozhraní bez tokenu a adresy služby
    assert ">Spectra6<" in r.text and ">BWRY<" in r.text
