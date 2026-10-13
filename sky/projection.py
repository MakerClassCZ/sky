"""Projekce alt/az → pixely a ořez úseček (spec §5.2, §5.3)."""
from __future__ import annotations

import math
from dataclasses import dataclass

Point = tuple[float, float]


def normalize_daz(d: float) -> float:
    return ((d + 180.0) % 360.0) - 180.0


@dataclass(frozen=True)
class SkyProjection:
    """Azimutální ekvidistantní, zenit uprostřed, `az_down` dole, východ vlevo."""
    size: int
    az_down: float
    margin: int = 18

    @property
    def center(self) -> Point:
        return (self.size / 2.0, self.size / 2.0)

    @property
    def radius(self) -> float:
        return self.size / 2.0 - self.margin

    def project(self, alt: float, az: float) -> Point:
        cx, cy = self.center
        r = (90.0 - alt) / 90.0 * self.radius
        th = math.radians(az - self.az_down)
        return (cx + r * math.sin(th), cy + r * math.cos(th))

    def inside(self, x: float, y: float) -> bool:
        cx, cy = self.center
        return (x - cx) ** 2 + (y - cy) ** 2 <= self.radius ** 2 + 1e-6


@dataclass(frozen=True)
class HorizonProjection:
    """Rovnoběžná azimut × výška: obzor dole, `az_center` uprostřed."""
    width: int
    height: int
    az_center: float
    fov: float

    @property
    def alt_max(self) -> float:
        return self.fov * self.height / self.width

    def project(self, alt: float, az: float) -> Point:
        daz = normalize_daz(az - self.az_center)
        x = (daz / self.fov + 0.5) * self.width
        y = self.height - alt / self.alt_max * self.height
        return (x, y)

    def visible(self, alt: float, az: float) -> bool:
        daz = normalize_daz(az - self.az_center)
        return 0.0 <= alt <= self.alt_max and abs(daz) <= self.fov / 2.0

    def segment_wraps(self, az0: float, az1: float) -> bool:
        """True, když kratší oblouk mezi azimuty prochází „za zády“ (az_center + 180)."""
        d0 = normalize_daz(az0 - self.az_center)
        d1 = normalize_daz(az1 - self.az_center)
        return abs(d0 - d1) > 180.0


def clip_segment_circle(p0: Point, p1: Point, center: Point, r: float):
    """Část úsečky uvnitř kruhu, nebo None."""
    cx, cy = center
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    fx, fy = p0[0] - cx, p0[1] - cy
    a = dx * dx + dy * dy
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - r * r
    if a == 0.0:
        return (p0, p1) if c <= 0 else None
    disc = b * b - 4.0 * a * c
    if disc < 0:
        return None
    sq = math.sqrt(disc)
    t0 = max(0.0, (-b - sq) / (2.0 * a))
    t1 = min(1.0, (-b + sq) / (2.0 * a))
    if t0 > t1:
        return None
    q0 = (p0[0] + dx * t0, p0[1] + dy * t0)
    q1 = (p0[0] + dx * t1, p0[1] + dy * t1)
    return (q0, q1)


def clip_segment_rect(p0: Point, p1: Point, w: float, h: float):
    """Liang–Barsky ořez na obdélník [0,w]×[0,h], nebo None."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, p0[0]), (dx, w - p0[0]), (-dy, p0[1]), (dy, h - p0[1])):
        if p == 0.0:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            if t > t1:
                return None
            t0 = max(t0, t)
        else:
            if t < t0:
                return None
            t1 = min(t1, t)
    return ((p0[0] + dx * t0, p0[1] + dy * t0), (p0[0] + dx * t1, p0[1] + dy * t1))
