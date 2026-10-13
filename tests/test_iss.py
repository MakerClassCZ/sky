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
