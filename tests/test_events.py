from datetime import date
from pathlib import Path

from sky.events import Event, classify, parse_events, select

ICS = Path("tests/data/events_sample.ics").read_text(encoding="utf-8")
TODAY = date(2026, 10, 13)


def test_classify():
    assert classify("👁️ Meteorický roj Tauridy") == ("eye", "Meteorický roj Tauridy")
    assert classify("🔭 Uran v opozici") == ("scope", "Uran v opozici")
    assert classify("⚠️ Zatmění") == ("warn", "Zatmění")
    assert classify("🌕 Úplněk") == ("moon", "Úplněk")
    assert classify("🌓 První čtvrt") == ("moon", "První čtvrt")
    assert classify("⛒ Konjunkce") == ("none", "Konjunkce")
    assert classify("ℹ️ Info") == ("info", "Info")
    assert classify("Bez emoji") == ("other", "Bez emoji")


def test_parse_window_and_order():
    ev = parse_events(ICS, TODAY, days=60)
    dates = [e.date for e in ev]
    assert dates == sorted(dates)
    assert ev[0] == Event(date(2026, 10, 13), "Uran v opozici", "scope")
    assert all(TODAY <= e.date <= date(2026, 12, 12) for e in ev)
    assert not any(e.title == "Něco starého" for e in ev)


def test_recurrence_override_not_duplicated():
    ev = parse_events(ICS, TODAY, days=60)
    taur = [e for e in ev if "Tauridy" in e.title]
    assert taur == [Event(date(2026, 11, 6), "Meteorický roj Tauridy (maximum)", "eye")]


def test_select_filters_kinds_and_limits():
    ev = parse_events(ICS, TODAY, days=60)
    out = select(ev, ("eye", "scope", "warn", "moon"), 2)
    assert [e.kind for e in out] == ["scope", "moon"]
    assert not any(e.kind in ("none", "info") for e in select(ev, ("eye", "scope", "warn", "moon"), 10))
