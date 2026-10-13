from sky.catalog import load_catalog, lon_to_ra_hours


def test_lon_to_ra():
    assert lon_to_ra_hours(0) == 0
    assert lon_to_ra_hours(180) == 12
    assert lon_to_ra_hours(-90) == 18


def test_catalog_loaded():
    c = load_catalog()
    assert 300 < len(c.mag) < 1200
    assert c.mag.max() <= 4.5
    assert len(c.lines) == 89          # Hadonoš/Had: Serpens je ve dvou částech
    assert c.ra_hours.min() >= 0 and c.ra_hours.max() < 24
    uma = c.names["UMa"]
    assert uma.cs == "Velká medvědice" and uma.en == "Big Dipper" and uma.rank == 1
    assert " " not in uma.cs and " " in uma.cs   # U+2005 z dat se normalizuje na mezeru
    assert 8 < uma.ra_hours < 14
    assert all(seg.shape[1] == 2 for _, segs in c.lines for seg in segs)
