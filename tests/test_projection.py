import pytest

from sky.projection import (HorizonProjection, SkyProjection, clip_segment_circle,
                            clip_segment_rect, normalize_daz)


def test_normalize_daz():
    assert normalize_daz(190) == -170
    assert normalize_daz(-190) == 170
    assert normalize_daz(45) == 45


def test_sky_zenith_center():
    p = SkyProjection(480, 180)
    assert p.project(90, 123) == pytest.approx((240, 240))
    assert p.radius == 240 - 18


def test_sky_az_down_is_bottom_east_left():
    p = SkyProjection(480, 180)
    x, y = p.project(0, 180)
    assert (x, y) == pytest.approx((240, 240 + p.radius))
    x, y = p.project(0, 90)           # východ při pohledu na jih vlevo
    assert (x, y) == pytest.approx((240 - p.radius, 240))
    x, y = p.project(0, 0)
    assert (x, y) == pytest.approx((240, 240 - p.radius))


def test_sky_inside():
    p = SkyProjection(480, 0)
    assert p.inside(240, 240)
    assert not p.inside(0, 0)


def test_horizon_center_and_scale():
    p = HorizonProjection(800, 300, 180, 120)
    assert p.alt_max == pytest.approx(45)
    assert p.project(0, 180) == pytest.approx((400, 300))
    assert p.project(45, 180) == pytest.approx((400, 0))
    assert p.project(0, 120) == pytest.approx((0, 300))
    assert p.visible(10, 200) and not p.visible(50, 180) and not p.visible(10, 10)


def test_horizon_wraps_azimuth():
    p = HorizonProjection(800, 300, 10, 120)
    x, _ = p.project(0, 350)
    assert x == pytest.approx(400 - 20 / 120 * 800)


def test_horizon_segment_across_back_is_dropped():
    # body na az 350 a 10 leží „za zády“ pozorovatele (střed 180); naivní ořez by
    # nakreslil čáru přes celou šířku, proto se takový segment musí poznat a vynechat
    p = HorizonProjection(800, 300, 180, 120)
    assert clip_segment_rect(p.project(10, 350), p.project(10, 10), 800, 300) is not None
    assert p.segment_wraps(350, 10)
    assert not p.segment_wraps(170, 190)
    assert not p.segment_wraps(100, 260)


def test_clip_segment_circle_partial():
    c, r = (100, 100), 50
    seg = clip_segment_circle((100, 100), (300, 100), c, r)
    assert seg is not None
    (x0, y0), (x1, y1) = seg
    assert (x0, y0) == pytest.approx((100, 100))
    assert (x1, y1) == pytest.approx((150, 100))


def test_clip_segment_circle_outside():
    assert clip_segment_circle((200, 200), (300, 300), (0, 0), 10) is None


def test_clip_segment_circle_inside_untouched():
    seg = clip_segment_circle((10, 10), (20, 20), (0, 0), 100)
    assert seg == ((10, 10), (20, 20))


def test_clip_segment_rect():
    seg = clip_segment_rect((-10, 50), (50, 50), 100, 100)
    assert seg is not None and seg[0] == pytest.approx((0, 50))
    assert clip_segment_rect((-10, -10), (-5, -5), 100, 100) is None
