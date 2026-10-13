from sky.palette import ROLES, make_palette


def test_bw_night_inverts():
    p = make_palette("bw", "night")
    assert p["bg"] == 1 and p["fg"] == 0 and p["star"] == 0 and p["planet"] == 0
    assert p["moon_dark"] == 1
    assert p.ncolors == 2 and p.flat() == [255, 255, 255, 0, 0, 0]


def test_bw_day():
    p = make_palette("bw", "day")
    assert p["bg"] == 0 and p["fg"] == 1 and p["label"] == 1


def test_bwr_roles():
    p = make_palette("bwr", "night")
    assert p["planet"] == 2 and p["sun"] == 2 and p["iss"] == 2 and p["today"] == 2
    assert p["moon_lit"] == 0 and p.ncolors == 3


def test_bwry_roles():
    p = make_palette("bwry", "day")
    assert p["sun"] == 3 and p["moon_lit"] == 3 and p["planet"] == 2
    assert p.ncolors == 4 and len(p.flat()) == 12


def test_all_roles_defined():
    p = make_palette("bwry", "night")
    for r in ROLES:
        assert isinstance(p[r], int)
