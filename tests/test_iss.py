from datetime import timedelta
from pathlib import Path

import pytest

from sky import astro, config, iss
from sky.params import parse

CACHE = Path("cache")
ephem = pytest.mark.skipif(not (CACHE / "de421.bsp").exists(), reason="de421.bsp missing")
TLE_TEXT = Path("tests/data/iss.tle").read_text(encoding="utf-8")


def test_parse_tle():
    name, l1, l2 = iss.parse_tle(TLE_TEXT)
    assert name.startswith("ISS") and l1.startswith("1 25544") and l2.startswith("2 25544")
    assert iss.parse_tle("garbage") is None
    assert iss.parse_tle("1 25544U\n2 25544 ") is None


def test_tle_epoch_is_recent():
    _, l1, _ = iss.parse_tle(TLE_TEXT)
    ep = iss.tle_epoch(l1)
    assert ep.year >= 2026


def test_unavailable_without_tle():
    p = parse({"lat": "49.747", "lon": "13.378"}, config.load({}), "png")
    info = iss.compute(p, None, None, None)
    assert info == iss.IssInfo(False, None, None, None)


@ephem
def test_passes_near_epoch():
    p = parse({"lat": "49.747", "lon": "13.378"}, config.load({}), "png")
    e = astro.get_ephemeris(CACHE)
    tle = iss.parse_tle(TLE_TEXT)
    t = iss.tle_epoch(tle[1])
    info = iss.compute(p, e, tle, t)
    assert info.available and info.alt is not None and -90 <= info.alt <= 90
    if info.next_pass is not None:
        assert t <= info.next_pass.start <= t + timedelta(hours=48)
        assert info.next_pass.end > info.next_pass.start
        assert info.next_pass.max_alt >= 10


@ephem
def test_stale_tle_is_unavailable():
    p = parse({"lat": "49.747", "lon": "13.378"}, config.load({}), "png")
    e = astro.get_ephemeris(CACHE)
    tle = iss.parse_tle(TLE_TEXT)
    t = iss.tle_epoch(tle[1]) + timedelta(days=15)
    assert iss.compute(p, e, tle, t) == iss.IssInfo(False, None, None, None)
    assert iss.compute(p, e, tle, t - timedelta(days=2)).available


@ephem
def test_track_before_pass():
    from skyfield.api import EarthSatellite, wgs84
    p = parse({"lat": "49.747", "lon": "13.378"}, config.load({}), "png")
    e = astro.get_ephemeris(CACHE)
    tle = iss.parse_tle(TLE_TEXT)
    t0 = iss.tle_epoch(tle[1])
    sat = EarthSatellite(tle[1], tle[2], tle[0], e.ts)
    topos = wgs84.latlon(49.747, 13.378)
    passes = iss.find_visible_passes(sat, e.eph["earth"] + topos, topos, e, e.ts.from_datetime(t0),
                                     e.ts.from_datetime(t0 + timedelta(days=10)))
    assert passes, "v 10 dnech má být aspoň jeden viditelný přelet"
    t = passes[0].start - timedelta(minutes=30)
    info = iss.compute(p, e, tle, t)
    assert info.next_pass is not None and abs((info.next_pass.start - passes[0].start).total_seconds()) < 1.0
    assert len(info.track) >= 5 and all(a >= 9.0 for a, _ in info.track)
    # hodinu a více před přeletem se dráha nekreslí
    assert iss.compute(p, e, tle, t - timedelta(minutes=45)).track == ()
