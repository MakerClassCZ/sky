from datetime import date, datetime, timezone

from sky.geo import compass, fmt_coords, fmt_date, fmt_time, tr, tz_for


def test_tz_plzen():
    assert tz_for(49.747, 13.378).key == "Europe/Prague"


def test_tz_ocean_fallback_utc():
    assert tz_for(0.0, -140.0).key in ("UTC", "Etc/GMT+9", "Etc/GMT+10")


def test_fmt_date():
    assert fmt_date(date(2026, 10, 13), "cs") == "út 13. 10."
    assert fmt_date(date(2026, 10, 13), "en") == "Tue 13 Oct"


def test_fmt_time():
    tz = tz_for(49.747, 13.378)
    assert fmt_time(datetime(2026, 10, 13, 16, 19, tzinfo=timezone.utc), tz) == "18:19"
    assert fmt_time(None, tz) == "–"


def test_compass():
    assert compass(0, "cs") == "S" and compass(44, "cs") == "SV" and compass(181, "cs") == "J"
    assert compass(350, "en") == "N" and compass(225, "en") == "SW"


def test_tr_and_coords():
    assert tr("cs", "sun") == "Slunce" and tr("en", "sun") == "Sun"
    assert fmt_coords(49.747, 13.378) == "49.75N 13.38E"
    assert fmt_coords(-33.9, -70.6) == "33.90S 70.60W"
