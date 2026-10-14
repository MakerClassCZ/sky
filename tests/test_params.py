from datetime import datetime, timezone

import pytest

from sky import config
from sky.params import ParamError, Params, parse, parse_time

CFG = config.load({})
CFG_LOC = config.load({"SKY_LAT": "49.747", "SKY_LON": "13.378"})


def test_defaults():
    p = parse({"lat": "49.747", "lon": "13.378"}, CFG, "png")
    assert p == Params(lat=49.747, lon=13.378)
    assert p.view == "sky" and p.az == 180.0 and p.fov == 120.0
    assert (p.w, p.h) == (800, 480) and p.colors == "bw" and p.rot == 0
    assert p.t is None and p.iss and p.events and p.lang == "cs" and p.fmt == "png"


def test_env_location_fallback():
    p = parse({}, CFG_LOC, "bmp")
    assert (p.lat, p.lon, p.fmt) == (49.747, 13.378, "bmp")


def test_missing_location():
    with pytest.raises(ParamError):
        parse({}, CFG, "png")


@pytest.mark.parametrize("q", [
    {"lat": "91"}, {"lon": "x"}, {"view": "dome"}, {"az": "361"}, {"fov": "20"},
    {"w": "10"}, {"h": "3000"}, {"colors": "rgb"}, {"rot": "45"}, {"iss": "yes"},
    {"lang": "de"}, {"t": "včera"}, {"lines": "wavy"},
])
def test_invalid(q):
    with pytest.raises(ParamError):
        parse(q, CFG_LOC, "png")


def test_invalid_format():
    with pytest.raises(ParamError):
        parse({}, CFG_LOC, "gif")


def test_full():
    p = parse({"view": "horizon", "az": "200", "fov": "90", "w": "480", "h": "800",
               "colors": "bwry", "rot": "90", "t": "2026-10-13T22:00+02:00",
               "iss": "0", "events": "0", "lang": "en"}, CFG_LOC, "png")
    assert p.view == "horizon" and p.az == 200 and p.fov == 90
    assert (p.w, p.h, p.colors, p.rot) == (480, 800, "bwry", 90)
    assert p.t == datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc)
    assert not p.iss and not p.events and p.lang == "en"


def test_parse_time_naive_is_utc():
    assert parse_time("2026-01-01T00:00") == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_lines_style():
    assert parse({}, CFG_LOC, "png").lines == "solid"
    assert parse({"lines": "dotted"}, CFG_LOC, "png").lines == "dotted"


def test_rockets_flag():
    assert parse({}, CFG_LOC, "png").rockets is False
    assert parse({"rockets": "1"}, CFG_LOC, "png").rockets is True


def test_spectra_colors():
    assert parse({"colors": "spectra"}, CFG_LOC, "png").colors == "spectra"


def test_clock_time_and_mode_and_flags():
    p = parse({"t": "22:00"}, CFG_LOC, "png")
    assert p.t is None and p.t_clock == "22:00"
    p = parse({"t": "2026-10-13T22:00+02:00"}, CFG_LOC, "png")
    assert p.t_clock is None
    assert parse({}, CFG_LOC, "png").mode == "auto"
    assert parse({"mode": "night"}, CFG_LOC, "png").mode == "night"
    assert parse({}, CFG_LOC, "png").weather is True and parse({"weather": "0"}, CFG_LOC, "png").weather is False
    assert parse({}, CFG_LOC, "png").ecliptic is True and parse({"ecliptic": "0"}, CFG_LOC, "png").ecliptic is False
    for bad in ({"t": "25:00"}, {"t": "7:5"}, {"mode": "dark"}):
        with pytest.raises(ParamError):
            parse(bad, CFG_LOC, "png")


def test_sunmoon_and_starnames():
    p = parse({}, CFG_LOC, "png")
    assert p.sunmoon is False and p.starnames is None
    p = parse({"sunmoon": "1", "starnames": "2.5"}, CFG_LOC, "png")
    assert p.sunmoon is True and p.starnames == 2.5
    assert parse({"starnames": "0"}, CFG_LOC, "png").starnames == 0.0     # 0 mag je platná mez (Vega)
    assert parse({"starnames": ""}, CFG_LOC, "png").starnames is None
    with pytest.raises(ParamError):
        parse({"starnames": "9"}, CFG_LOC, "png")


def test_constnames_flag():
    assert parse({}, CFG_LOC, "png").constnames is True
    assert parse({"constnames": "0"}, CFG_LOC, "png").constnames is False


def test_comets_limit():
    assert parse({}, CFG_LOC, "png").comets == 6.0
    assert parse({"comets": "8"}, CFG_LOC, "png").comets == 8.0
    assert parse({"comets": "0"}, CFG_LOC, "png").comets is None
    assert parse({"comets": "off"}, CFG_LOC, "png").comets is None
    with pytest.raises(ParamError):
        parse({"comets": "20"}, CFG_LOC, "png")


def test_equator_flag():
    assert parse({}, CFG_LOC, "png").equator is False
    assert parse({"equator": "1"}, CFG_LOC, "png").equator is True


def test_halo_flag():
    assert parse({}, CFG_LOC, "png").halo is False
    assert parse({"halo": "1"}, CFG_LOC, "png").halo is True
