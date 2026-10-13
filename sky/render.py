"""Kreslení mapy a infopanelu do obrazu v režimu P (spec §5)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from PIL import Image, ImageDraw

from sky import layout
from sky.astro import SkyModel
from sky.events import Event
from sky.fonts import BdfFont, draw_text, fit, load_font, text_width
from sky.geo import compass, fmt_coords, fmt_date, fmt_time, tr
from sky.icons import draw_icon
from sky.iss import IssInfo
from sky.layout import Rect, Zones
from sky.palette import Palette, make_palette
from sky.params import Params
from sky.projection import HorizonProjection, SkyProjection, clip_segment_circle, clip_segment_rect

STAR_SIZES = ((1.0, 5), (2.0, 4), (3.0, 3), (4.0, 2), (99.0, 1))
LINE_MIN_ALT = -15.0
LABEL_MIN_ALT = 10.0
LABEL_MIN_MAP = 300       # popisky souhvězdí jen na mapách aspoň takto velkých (px)
HORIZON_BAR = layout.HORIZON_BAR
DASH = {"solid": None, "dashed": (4, 4), "dotted": (1, 2)}   # (kreslit, vynechat) v px
Box = tuple[int, int, int, int]


@dataclass
class Ctx:
    img: Image.Image
    d: ImageDraw.ImageDraw
    pal: Palette
    lang: str
    small: BdfFont
    mid: BdfFont
    big: BdfFont


def render(params: Params, model: SkyModel, iss_info: IssInfo, events: list[Event] | None) -> Image.Image:
    pal = make_palette(params.colors, model.mode)
    img = Image.new("P", (params.w, params.h), pal["bg"])
    img.putpalette(pal.flat())
    ctx = Ctx(img, ImageDraw.Draw(img), pal, params.lang,
              load_font("8x16"), load_font("12x24"), load_font("16x32"))
    show_events = params.events or params.rockets
    sections = tuple(s for s in layout.ALL_SECTIONS
                     if (s != "iss" or params.iss) and (s != "events" or show_events))
    zones = layout.compute(params.w, params.h, params.view, sections, params.fov)
    if params.view == "sky":
        _draw_sky(ctx, zones.map, params, model, iss_info)
    else:
        _draw_horizon(ctx, zones.map, params, model, iss_info)
    if zones.info is not None:
        _draw_info(ctx, zones, params, model, iss_info, events)
    return img


# ---------- mapa: společné prvky ----------

def _star_size(mag: float) -> int:
    for lim, px in STAR_SIZES:
        if mag <= lim:
            return px
    return 1


def _dot(ctx: Ctx, x: float, y: float, px: int, idx: int) -> None:
    if px <= 1:
        ctx.d.point((round(x), round(y)), fill=idx)
    elif px == 2:
        ctx.d.rectangle((round(x), round(y), round(x) + 1, round(y) + 1), fill=idx)
    else:
        r = px / 2.0
        ctx.d.ellipse((x - r, y - r, x + r, y + r), fill=idx)


def _planet(ctx: Ctx, x: float, y: float, key: str = "") -> None:
    if key.startswith("saturn"):
        # prstenec: plochá elipsa pod kotoučem, kotouč ji uprostřed překryje
        ctx.d.ellipse((x - 8, y - 2.5, x + 8, y + 2.5), outline=ctx.pal["planet"])
    ctx.d.ellipse((x - 3.5, y - 3.5, x + 3.5, y + 3.5), fill=ctx.pal["planet"], outline=ctx.pal["fg"])


def _moon(ctx: Ctx, x: float, y: float, phase_deg: float, r: int = 8) -> None:
    """Kotouč s fází: dorůstá (0–180°) osvětlen vpravo, couvá vlevo."""
    ctx.d.ellipse((x - r, y - r, x + r, y + r), fill=ctx.pal["moon_dark"], outline=ctx.pal["fg"])
    ph = phase_deg % 360.0
    cosp = math.cos(math.radians(ph))
    for yy in range(-r + 1, r):
        c = math.sqrt(r * r - yy * yy)
        if ph < 180.0:
            x0, x1 = c * cosp, c
        else:
            x0, x1 = -c, -c * cosp
        if x1 - x0 >= 1.0:
            ctx.d.line((x + x0, y + yy, x + x1, y + yy), fill=ctx.pal["moon_lit"])
    ctx.d.ellipse((x - r, y - r, x + r, y + r), outline=ctx.pal["fg"])


def _sun(ctx: Ctx, x: float, y: float, r: int = 7) -> None:
    for k in range(8):
        a = math.radians(k * 45)
        ctx.d.line((x + (r + 2) * math.cos(a), y + (r + 2) * math.sin(a),
                    x + (r + 6) * math.cos(a), y + (r + 6) * math.sin(a)), fill=ctx.pal["sun"])
    ctx.d.ellipse((x - r, y - r, x + r, y + r), fill=ctx.pal["sun"], outline=ctx.pal["fg"])


def _iss_marker(ctx: Ctx, x: float, y: float) -> None:
    c = ctx.pal["iss"]
    ctx.d.line((x - 4, y, x + 4, y), fill=c)
    ctx.d.line((x, y - 4, x, y + 4), fill=c)


def _overlaps(a: Box, b: Box) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def choose_box(placed: list[Box], w: int, h: int, candidates, bounds) -> Box | None:
    """První kandidát (x0, y0), jehož box je v hranicích a nekoliduje s `placed`; neregistruje."""
    for x0, y0 in candidates:
        box = (int(x0), int(y0), int(x0) + w, int(y0) + h)
        if bounds(box) and not any(_overlaps(box, b) for b in placed):
            return box
    return None


def _label(ctx: Ctx, placed: list[Box], text: str, idx: int, candidates, bounds) -> None:
    box = choose_box(placed, text_width(ctx.small, text), ctx.small.height, candidates, bounds)
    if box is None:
        return
    placed.append(box)
    draw_text(ctx.img, (box[0], box[1]), text, ctx.small, idx)


def _place_label(ctx: Ctx, placed: list[Box], x: float, y: float, text: str, bounds) -> None:
    """Popisek souhvězdí vystředěný na (x, y); vynechá se mimo hranice nebo při kolizi."""
    w, h = text_width(ctx.small, text), ctx.small.height
    _label(ctx, placed, text, ctx.pal["label"], [(x - w / 2, y - h / 2)], bounds)


def _body_label(ctx: Ctx, placed: list[Box], x: float, y: float, text: str, idx: int, bounds) -> None:
    """Popisek tělesa: vpravo, vlevo, nad, pod – první volná pozice. Glyf sám se registruje."""
    placed.append((int(x) - 5, int(y) - 5, int(x) + 6, int(y) + 6))
    w, h = text_width(ctx.small, text), ctx.small.height
    gap = 11 if text == "Saturn" else 6     # Saturn má prstenec, popisek dál od středu
    _label(ctx, placed, text, idx,
           [(x + gap, y - h / 2), (x - gap - w, y - h / 2), (x - w / 2, y - 7 - h), (x - w / 2, y + 7)], bounds)


def _draw_bodies(ctx: Ctx, placed: list[Box], bounds, project, visible,
                 model: SkyModel, iss_info: IssInfo, params: Params) -> None:
    """Tělesa a jejich popisky; glyfy i popisky se registrují do `placed`."""
    for b in model.planets:
        if visible(b.alt, b.az):
            x, y = project(b.alt, b.az)
            _planet(ctx, x, y, b.key)
            if b.key.startswith("saturn"):
                placed.append((int(x) - 9, int(y) - 4, int(x) + 10, int(y) + 5))
            _body_label(ctx, placed, x, y, b.name, ctx.pal["label"], bounds)
    if visible(model.moon.alt, model.moon.az):
        x, y = project(model.moon.alt, model.moon.az)
        _moon(ctx, x, y, model.moon.phase_deg)
        placed.append((int(x) - 9, int(y) - 9, int(x) + 10, int(y) + 10))
    if model.mode == "day" and visible(model.sun.alt, model.sun.az):
        x, y = project(model.sun.alt, model.sun.az)
        _sun(ctx, x, y)
        placed.append((int(x) - 14, int(y) - 14, int(x) + 15, int(y) + 15))
    if params.iss and iss_info.available and iss_info.alt is not None and visible(iss_info.alt, iss_info.az):
        x, y = project(iss_info.alt, iss_info.az)
        _iss_marker(ctx, x, y)
        _body_label(ctx, placed, x, y, "ISS", ctx.pal["iss"], bounds)


def _styled_line(d: ImageDraw.ImageDraw, p0, p1, fill: int, pattern) -> None:
    """Úsečka plná, nebo s opakovaným vzorem (kreslit, vynechat) v pixelech."""
    if pattern is None:
        d.line((p0[0], p0[1], p1[0], p1[1]), fill=fill, width=1)
        return
    on, off = pattern
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy)
    if length < 1.0:
        d.point((round(p0[0]), round(p0[1])), fill=fill)
        return
    ux, uy = dx / length, dy / length
    t = 0.0
    while t < length:
        t1 = min(t + on, length)
        if on == 1:
            d.point((round(p0[0] + ux * t), round(p0[1] + uy * t)), fill=fill)
        else:
            d.line((p0[0] + ux * t, p0[1] + uy * t, p0[0] + ux * t1, p0[1] + uy * t1), fill=fill, width=1)
        t += on + off


def _draw_lines(ctx: Ctx, model: SkyModel, clip, wraps, ox: int, oy: int, style: str) -> None:
    pattern = DASH[style]
    for _, segs in model.lines:
        for seg in segs:
            for (a0, z0), (a1, z1) in zip(seg[:-1], seg[1:]):
                if (a0 < LINE_MIN_ALT and a1 < LINE_MIN_ALT) or wraps(z0, z1):
                    continue
                clipped = clip(a0, z0, a1, z1)
                if clipped:
                    (x0, y0), (x1, y1) = clipped
                    _styled_line(ctx.d, (x0 + ox, y0 + oy), (x1 + ox, y1 + oy), ctx.pal["line"], pattern)


# ---------- mapa: celá obloha ----------

def _draw_sky(ctx: Ctx, m: Rect, params: Params, model: SkyModel, iss_info: IssInfo) -> None:
    proj = SkyProjection(m.w, params.az, margin=18 if m.w >= 200 else 10)
    cx, cy = proj.center
    R = proj.radius
    ox, oy = m.x, m.y

    def project(alt, az):
        x, y = proj.project(alt, az)
        return (x + ox, y + oy)

    def visible(alt, az):
        return alt >= 0.0

    def clip(a0, z0, a1, z1):
        return clip_segment_circle(proj.project(a0, z0), proj.project(a1, z1), (cx, cy), R)

    _draw_lines(ctx, model, clip, lambda z0, z1: False, ox, oy, params.lines)
    for alt, az, mag in model.stars:
        if alt >= 0.0:
            x, y = project(alt, az)
            _dot(ctx, x, y, _star_size(mag), ctx.pal["star"])

    def inside_circle(b: Box) -> bool:
        return all(proj.inside(px - ox, py - oy)
                   for px, py in ((b[0], b[1]), (b[2], b[3]), (b[0], b[3]), (b[2], b[1])))

    placed: list[Box] = []
    _draw_bodies(ctx, placed, inside_circle, project, visible, model, iss_info, params)
    if m.w >= LABEL_MIN_MAP:
        for text, alt, az in model.labels:
            if alt >= LABEL_MIN_ALT:
                x, y = project(alt, az)
                _place_label(ctx, placed, x, y, text, inside_circle)
    ctx.d.ellipse((cx - R + ox, cy - R + oy, cx + R + ox, cy + R + oy), outline=ctx.pal["horizon"], width=1)

    font = ctx.mid if m.w >= 300 else ctx.small
    for az in (0, 90, 180, 270):
        lbl = compass(az, ctx.lang)
        x, y = proj.project(0.0, az)
        dxn, dyn = (x - cx) / R, (y - cy) / R          # jednotkový směr ven z kružnice
        px = x + dxn * (proj.margin / 2 + 1) + ox - text_width(font, lbl) / 2
        py = y + dyn * (proj.margin / 2 + 1) + oy - font.height / 2
        draw_text(ctx.img, (px, py), lbl, font, ctx.pal["fg"])


# ---------- mapa: pohled na obzor ----------

def _draw_horizon(ctx: Ctx, m: Rect, params: Params, model: SkyModel, iss_info: IssInfo) -> None:
    bar = HORIZON_BAR if m.h >= 4 * HORIZON_BAR else 0
    mh = m.h - bar
    proj = HorizonProjection(m.w, mh, params.az, params.fov)
    ox, oy = m.x, m.y

    def project(alt, az):
        x, y = proj.project(alt, az)
        return (x + ox, y + oy)

    def clip(a0, z0, a1, z1):
        return clip_segment_rect(proj.project(a0, z0), proj.project(a1, z1), m.w, mh)

    _draw_lines(ctx, model, clip, proj.segment_wraps, ox, oy, params.lines)
    for alt, az, mag in model.stars:
        if proj.visible(alt, az):
            x, y = project(alt, az)
            _dot(ctx, x, y, _star_size(mag), ctx.pal["star"])

    def inside_rect(b: Box) -> bool:
        return b[0] >= ox and b[2] <= ox + m.w and b[1] >= oy and b[3] <= oy + mh

    placed: list[Box] = []
    _draw_bodies(ctx, placed, inside_rect, project, proj.visible, model, iss_info, params)
    if mh >= LABEL_MIN_MAP // 2:
        for text, alt, az in model.labels:
            if alt >= LABEL_MIN_ALT and proj.visible(alt, az):
                x, y = project(alt, az)
                _place_label(ctx, placed, x, y, text, inside_rect)

    hy = oy + mh - 1
    ctx.d.line((ox, hy, ox + m.w - 1, hy), fill=ctx.pal["horizon"], width=1)
    if bar:
        for az in range(0, 360, 45):
            if abs(((az - params.az + 180) % 360) - 180) <= params.fov / 2:
                x, _ = project(0.0, az)
                ctx.d.line((x, hy - 4, x, hy + 3), fill=ctx.pal["horizon"])
                lbl = compass(az, ctx.lang)
                draw_text(ctx.img, (x - text_width(ctx.small, lbl) / 2, hy + 5), lbl, ctx.small, ctx.pal["fg"])


# ---------- infopanel ----------

class Cursor:
    """Kurzor pro řádkový výpis do sloupce; `line`/`title` vrátí False, když došlo místo."""

    def __init__(self, ctx: Ctx, col: Rect):
        self.ctx, self.col = ctx, col
        self.x = col.x + layout.MARGIN
        self.y = col.y
        self.w = col.w - 2 * layout.MARGIN
        self.bottom = col.bottom

    def room(self, lines: int = 1) -> bool:
        return self.y + lines * layout.U <= self.bottom

    def line(self, text: str, idx: int | None = None, box: bool = False) -> bool:
        if not self.room():
            return False
        f = self.ctx.small
        t = fit(f, text, self.w)
        draw_text(self.ctx.img, (self.x, self.y), t, f, self.ctx.pal["fg"] if idx is None else idx)
        if box:
            self.ctx.d.rectangle((self.x - 2, self.y - 1, self.x + text_width(f, t) + 1, self.y + f.height - 1),
                                 outline=self.ctx.pal["fg"])
        self.y += layout.U
        return True

    def title(self, icon: str, text: str) -> bool:
        if not self.room(2):
            return False
        draw_icon(self.ctx.img, (self.x, self.y), icon, self.ctx.pal["fg"])
        draw_text(self.ctx.img, (self.x + 20, self.y), fit(self.ctx.small, text, self.w - 20),
                  self.ctx.small, self.ctx.pal["fg"])
        self.ctx.d.line((self.x, self.y + 17, self.x + self.w - 1, self.y + 17), fill=self.ctx.pal["fg"])
        self.y += layout.U + 4
        return True

    def gap(self) -> None:
        self.y += layout.U // 2


def _draw_header(ctx: Ctx, z: Zones, model: SkyModel) -> None:
    h = z.header
    local = model.t.astimezone(model.tz)
    x, y = h.x + layout.MARGIN, h.y + layout.MARGIN // 2
    maxw = h.w - 2 * layout.MARGIN
    if z.header_line:
        # datum větším písmem, čas a poloha menším na stejné lince
        dw = draw_text(ctx.img, (x, y), fmt_date(local.date(), ctx.lang), ctx.mid, ctx.pal["fg"])
        rest = f"{local.strftime('%H:%M')}  {fmt_coords(model.lat, model.lon)}"
        draw_text(ctx.img, (x + dw + 16, y + 4), fit(ctx.small, rest, maxw - dw - 16), ctx.small, ctx.pal["fg"])
        return
    font = ctx.big if z.header_big else ctx.small
    draw_text(ctx.img, (x, y), fit(font, fmt_date(local.date(), ctx.lang), maxw), font, ctx.pal["fg"])
    y += font.height
    draw_text(ctx.img, (x, y), fit(ctx.small, f"{local.strftime('%H:%M')}  {fmt_coords(model.lat, model.lon)}", maxw),
              ctx.small, ctx.pal["fg"])


def _sec_sun(c: Cursor, model: SkyModel) -> None:
    L, tz = c.ctx.lang, model.tz
    if not c.title("sun", tr(L, "sun")):
        return
    c.line(f"{tr(L, 'rise'):<7}{fmt_time(model.sun.rise, tz)}")
    c.line(f"{tr(L, 'set'):<7}{fmt_time(model.sun.set, tz)}")
    if model.mode == "night":
        c.line(f"{tr(L, 'dawn_at')} {fmt_time(model.sun.next_rise, tz)}")
    else:
        c.line(f"{tr(L, 'night_from')} {fmt_time(model.sun.next_set, tz)}")
    c.gap()


def _sec_moon(c: Cursor, model: SkyModel) -> None:
    L, tz = c.ctx.lang, model.tz
    if not c.title("moon", tr(L, "moon")):
        return
    c.line(f"{tr(L, 'rise'):<7}{fmt_time(model.moon.rise, tz)}")
    c.line(f"{tr(L, 'set'):<7}{fmt_time(model.moon.set, tz)}")
    trend = tr(L, "waxing") if model.moon.phase_deg % 360 < 180 else tr(L, "waning")
    c.line(f"{tr(L, 'phase')} {round(model.moon.fraction * 100):d} % {trend}")
    c.gap()


def _sec_iss(c: Cursor, model: SkyModel, info: IssInfo) -> None:
    L, tz = c.ctx.lang, model.tz
    if not c.title("iss", tr(L, "iss")):
        return
    if not info.available:
        c.line(tr(L, "unavailable"))
    elif info.next_pass is None:
        c.line(tr(L, "no_pass"))
    else:
        p = info.next_pass
        s = p.start.astimezone(tz)
        c.line(f"{fmt_date(s.date(), L)} {s.strftime('%H:%M')}–{p.end.astimezone(tz).strftime('%H:%M')}")
        c.line(f"{tr(L, 'max')} {round(p.max_alt)}° {compass(p.max_az, L)}")
    c.gap()


def _sec_events(c: Cursor, model: SkyModel, events: list[Event] | None) -> None:
    L = c.ctx.lang
    if not c.title("cal", tr(L, "events")):
        return
    if events is None:
        c.line(tr(L, "unavailable"))
        return
    if not events:
        c.line(tr(L, "none"))
        return
    today = model.t.astimezone(model.tz).date()
    for e in events:
        if not c.room():
            break
        is_today = e.date == today
        idx = c.ctx.pal["today"] if is_today else None
        box = is_today and c.ctx.pal.ncolors == 2
        when = f"{e.date.day:>2}. {e.date.month:>2}." + (f" {e.time}" if e.time else "")
        c.line(f"{when} {e.title}", idx=idx, box=box)


def _draw_info(ctx: Ctx, z: Zones, params: Params, model: SkyModel, iss_info: IssInfo,
               events: list[Event] | None) -> None:
    _draw_header(ctx, z, model)
    sections = [("sun", lambda c: _sec_sun(c, model)), ("moon", lambda c: _sec_moon(c, model))]
    if params.iss:
        sections.append(("iss", lambda c: _sec_iss(c, model, iss_info)))
    if params.events or params.rockets:
        sections.append(("events", lambda c: _sec_events(c, model, events)))
    for col, group in zip(z.columns, layout.column_groups(len(z.columns))):
        cur = Cursor(ctx, col)
        for name, fn in sections:
            if name in group:
                fn(cur)
