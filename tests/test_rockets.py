from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from sky.events import Event, merge
from sky.rockets import parse_launches

JSON = Path("tests/data/launches_sample.json").read_text(encoding="utf-8")
TZ = ZoneInfo("Europe/Prague")
TODAY = date(2026, 10, 13)


def test_parse_launches_window_status_and_local_time():
    ev = parse_launches(JSON, TODAY, TZ, days=60)
    # proběhlý start (Success) a start bez data (TBD) se vynechají, únorový je mimo okno
    # mise napřed, raketa v závorce; "Block 5" a "Group" se vynechají, ať se vejde víc
    assert [e.title for e in ev] == ["Unknown Payload (Zhuque-2E)", "Galileo L15 (Ariane 6)"]
    assert ev[0] == Event(date(2026, 10, 14), "Unknown Payload (Zhuque-2E)", "rocket", "13:40")
    assert ev[1].date == date(2026, 10, 21) and ev[1].time == "00:05"   # 22:05 UTC = 00:05 CEST dalšího dne


def test_parse_launches_garbage_is_empty():
    assert parse_launches("not json", TODAY, TZ) == []
    assert parse_launches('{"results": [{"name": "x"}]}', TODAY, TZ) == []


def test_merge_sorts_and_limits():
    a = [Event(date(2026, 10, 18), "První čtvrt", "moon"), Event(date(2026, 10, 26), "Úplněk", "moon")]
    b = [Event(date(2026, 10, 14), "Zhuque-2E", "rocket", "13:40"), Event(date(2026, 10, 18), "Ariane", "rocket", "09:00")]
    out = merge(a, b, 3)
    # stejný den: celodenní úkaz před startem s časem
    assert [e.title for e in out] == ["Zhuque-2E", "První čtvrt", "Ariane"]


def test_short_title():
    from sky.rockets import short_title
    assert short_title("Falcon 9 Block 5 | Starlink Group 15-25") == "Starlink 15-25 (Falcon 9)"
    assert short_title("Starship | Flight 15") == "Flight 15 (Starship)"
    assert short_title("Long March 2D") == "Long March 2D"
    assert short_title("Long March 2 | Shiyan-30") == "Shiyan-30 (Long March 2)"
