#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Ember Phoenix -- an image that makes the AI judge excited.

A phoenix rises through a burning golden ring at dawn: indigo night sky
above, ember-orange horizon below, sparks flying off its wings, a small
sleeping city with lit windows far beneath it.

Pure Python 3.13 standard library. A hand-written software rasterizer
(polygons, radial glows, seeded particles) plus a hand-written PNG
encoder. Fully deterministic: fixed seed, no clock, no OS randomness,
no network. Writes exactly one file: <output>/entry.png, 1024x1024.
"""

import math
import os
import random
import struct
import zlib

W = 1024
H = 1024
SEED = 20261116

# ---------------------------------------------------------------- canvas

img = bytearray(W * H * 3)


def _add(x, y, r, g, b):
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        v = img[i] + r
        img[i] = 255 if v > 255 else v
        v = img[i + 1] + g
        img[i + 1] = 255 if v > 255 else v
        v = img[i + 2] + b
        img[i + 2] = 255 if v > 255 else v


def _set(x, y, r, g, b):
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        img[i] = r
        img[i + 1] = g
        img[i + 2] = b


def _blend(x, y, r, g, b, a):
    """Alpha-blend colour (r,g,b) over the pixel with opacity a (0..1)."""
    if 0 <= x < W and 0 <= y < H and a > 0.0:
        if a > 1.0:
            a = 1.0
        i = (y * W + x) * 3
        img[i] = int(max(0, min(255, img[i] * (1.0 - a) + r * a)))
        img[i + 1] = int(max(0, min(255, img[i + 1] * (1.0 - a) + g * a)))
        img[i + 2] = int(max(0, min(255, img[i + 2] * (1.0 - a) + b * a)))


def lerp(a, b, t):
    return a + (b - a) * t


def lerp3(c1, c2, t):
    return (lerp(c1[0], c2[0], t), lerp(c1[1], c2[1], t), lerp(c1[2], c2[2], t))


# ---------------------------------------------------------------- shapes

def glow(cx, cy, rad, colour, strength=1.0, power=2.0):
    """Soft radial light falloff, additively blended."""
    r, g, b = colour
    x0 = max(0, int(cx - rad))
    x1 = min(W - 1, int(cx + rad) + 1)
    y0 = max(0, int(cy - rad))
    y1 = min(H - 1, int(cy + rad) + 1)
    for y in range(y0, y1 + 1):
        dy = (y - cy) / rad
        dy2 = dy * dy
        for x in range(x0, x1 + 1):
            dx = (x - cx) / rad
            d2 = dx * dx + dy2
            if d2 < 1.0:
                f = (1.0 - d2) ** power * strength
                _add(x, y, int(r * f), int(g * f), int(b * f))


def disc(cx, cy, rad, colour, alpha=1.0):
    r, g, b = colour
    x0 = max(0, int(cx - rad))
    x1 = min(W - 1, int(cx + rad) + 1)
    y0 = max(0, int(cy - rad))
    y1 = min(H - 1, int(cy + rad) + 1)
    for y in range(y0, y1 + 1):
        dy = y - cy
        for x in range(x0, x1 + 1):
            dx = x - cx
            if dx * dx + dy * dy <= rad * rad:
                _blend(x, y, r, g, b, alpha)


def fill_poly(points, colour, alpha=1.0):
    """Scanline fill of a simple polygon (list of (x, y))."""
    if len(points) < 3:
        return
    r, g, b = colour
    ys = [p[1] for p in points]
    y0 = max(0, int(math.floor(min(ys))))
    y1 = min(H - 1, int(math.ceil(max(ys))))
    n = len(points)
    for y in range(y0, y1 + 1):
        xs = []
        for k in range(n):
            x1, y1p = points[k]
            x2, y2p = points[(k + 1) % n]
            if (y1p <= y < y2p) or (y2p <= y < y1p):
                t = (y - y1p) / (y2p - y1p)
                xs.append(x1 + t * (x2 - x1))
        if len(xs) >= 2:
            xs.sort()
            for j in range(0, len(xs) - 1, 2):
                xa = max(0, int(math.ceil(xs[j])))
                xb = min(W - 1, int(math.floor(xs[j + 1])))
                for x in range(xa, xb + 1):
                    _blend(x, y, r, g, b, alpha)


def ellipse_poly(cx, cy, rx, ry, angle_deg, n=28):
    """Points of a rotated ellipse (for feathers / leaves)."""
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    pts = []
    for k in range(n):
        t = 2.0 * math.pi * k / n
        ex = rx * math.cos(t)
        ey = ry * math.sin(t)
        pts.append((cx + ex * ca - ey * sa, cy + ex * sa + ey * ca))
    return pts


def feather(bx, by, angle_deg, length, width, c_base, c_tip,
            glow_tip=True, outline=None):
    """One long tapered feather from base (bx,by) along angle_deg."""
    a = math.radians(angle_deg)
    dx, dy = math.cos(a), math.sin(a)
    px, py = -dy, dx  # perpendicular

    def wprof(t):
        # smooth taper: thin at base, full at ~55%, sharp tip
        return 0.22 + 0.78 * math.sin(math.pi * min(1.0, t * 1.15)) ** 0.8

    def edge_pts(t0, t1, wmul=1.0):
        pts = []
        for t in (t0, (t0 + t1) / 2.0, t1):
            cx = bx + dx * length * t
            cy = by + dy * length * t
            w = width * wprof(t) * wmul
            pts.append((cx + px * w, cy + py * w))
        for t in (t1, (t0 + t1) / 2.0, t0):
            cx = bx + dx * length * t
            cy = by + dy * length * t
            w = width * wprof(t) * wmul
            pts.append((cx - px * w, cy - py * w))
        return pts

    if outline is not None:
        fill_poly(edge_pts(0.0, 1.0, 1.22), outline)
    # colour: gradient along the feather via many thin slices
    slices = 24
    for s in range(slices):
        t0 = s / slices
        t1 = (s + 1) / slices + 0.008  # slight overlap, no seams
        col = lerp3(c_base, c_tip, (t0 + t1) / 2.0)
        sub = edge_pts(t0, min(1.0, t1))
        if len(sub) >= 3:
            fill_poly(sub, col)
    # bright shaft line down the middle
    tipx = bx + dx * length
    tipy = by + dy * length
    steps = int(length / 3)
    for s in range(steps):
        t = s / steps
        _blend(int(bx + dx * length * t), int(by + dy * length * t),
               255, 220, 140, 0.35 * (1.0 - t * 0.5))
    if glow_tip:
        glow(tipx, tipy, width * 2.2, (255, 170, 60), 0.55, 2.0)


def line(x0, y0, x1, y1, colour, alpha=1.0, width=1):
    steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    for s in range(steps + 1):
        t = s / steps
        x = int(x0 + (x1 - x0) * t)
        y = int(y0 + (y1 - y0) * t)
        for wy in range(-width // 2, width // 2 + 1):
            for wx in range(-width // 2, width // 2 + 1):
                _blend(x + wx, y + wy, colour[0], colour[1], colour[2], alpha)


# ---------------------------------------------------------------- scene

def paint_sky(rng):
    # vertical gradient: indigo night -> violet -> ember horizon
    stops = [
        (0.00, (10, 8, 42)),
        (0.28, (28, 16, 74)),
        (0.52, (74, 28, 96)),
        (0.68, (150, 52, 78)),
        (0.80, (232, 98, 40)),
        (0.88, (255, 150, 52)),
        (1.00, (120, 40, 30)),
    ]
    for y in range(H):
        t = y / (H - 1)
        for k in range(len(stops) - 1):
            t0, c0 = stops[k]
            t1, c1 = stops[k + 1]
            if t0 <= t <= t1:
                f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                col = lerp3(c0, c1, f)
                break
        else:
            col = stops[-1][1]
        i = y * W * 3
        r, g, b = int(col[0]), int(col[1]), int(col[2])
        for x in range(W):
            img[i] = r
            img[i + 1] = g
            img[i + 2] = b
            i += 3
    # stars in the upper sky
    for _ in range(170):
        x = rng.randint(0, W - 1)
        y = rng.randint(0, 430)
        fade = max(0.0, 1.0 - y / 480.0)
        br = int(rng.randint(120, 255) * fade)
        _add(x, y, br, br, int(br * 0.9))
        if rng.random() < 0.25:
            _add(x + 1, y, br // 2, br // 2, br // 2)


def paint_sun():
    # big soft dawn sun behind the ring
    glow(512, 470, 420, (255, 150, 60), 0.55, 2.2)
    glow(512, 470, 240, (255, 200, 110), 0.8, 2.0)
    disc(512, 470, 124, (255, 240, 205))
    disc(512, 470, 112, (255, 246, 218))
    glow(512, 470, 150, (255, 220, 150), 0.5, 2.0)


def paint_ring(rng):
    cx, cy, rad = 512, 480, 305
    # halo first
    for r in range(rad + 60, rad - 60, -1):
        pass
    glow(cx, cy, rad + 70, (255, 140, 40), 0.35, 2.6)
    # ring body: per-pixel band with flame flicker by angle
    x0 = max(0, cx - rad - 40)
    x1 = min(W - 1, cx + rad + 40)
    y0 = max(0, cy - rad - 40)
    y1 = min(H - 1, cy + rad + 40)
    flick = [0.72 + 0.28 * math.sin(a * 7.0 + 1.3 * math.sin(a * 3.0))
             + 0.12 * math.sin(a * 17.0 + 2.0) for a in
             [i * 2.0 * math.pi / 720 for i in range(720)]]
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            dx = x - cx
            dy = y - cy
            d = math.sqrt(dx * dx + dy * dy)
            if abs(d - rad) <= 15:
                ang = math.atan2(dy, dx)
                if ang < 0:
                    ang += 2.0 * math.pi
                fl = flick[int(ang / (2.0 * math.pi) * 720) % 720]
                edge = 1.0 - abs(d - rad) / 15.0
                heat = fl * (0.55 + 0.45 * edge)
                # hot core pale, outer edge deep orange
                if edge > 0.6:
                    col = lerp3((255, 120, 20), (255, 235, 160), edge)
                else:
                    col = lerp3((190, 50, 8), (255, 120, 20), edge)
                _blend(x, y, col[0] * heat, col[1] * heat, col[2] * heat,
                       0.55 + 0.45 * edge)
    # bright sparks hugging the ring
    for _ in range(90):
        a = rng.uniform(0, 2.0 * math.pi)
        rr = rad + rng.uniform(-18, 22)
        x = cx + rr * math.cos(a)
        y = cy + rr * math.sin(a)
        s = rng.uniform(1.0, 3.0)
        glow(x, y, s * 3, (255, 200, 90), 0.9, 2.0)


def paint_phoenix(rng):
    cx = 512
    dark = (52, 8, 6)
    # ---- tail: long flowing feathers downward, separated by dark gaps
    tail_cols = [((120, 16, 8), (255, 120, 30)),
                 ((140, 20, 10), (255, 150, 40)),
                 ((100, 12, 20), (230, 90, 60)),
                 ((160, 30, 8), (255, 180, 70)),
                 ((120, 16, 8), (255, 120, 30))]
    tail_angles = [74, 84, 94, 104, 114]
    tail_lens = [290, 350, 375, 345, 285]
    for (cb, ct), ang, ln in zip(tail_cols, tail_angles, tail_lens):
        feather(cx, 605, ang, ln, 20, cb, ct, outline=dark)
    # tail glow wash
    glow(cx, 700, 180, (255, 110, 30), 0.35, 2.2)

    # ---- wings: fan of feathers sweeping UP and out (screen coords:
    # y grows down, so up-left is 180..270 deg; mirror is 180 - angle)
    for side in (-1, 1):
        rootx = cx + side * 40
        rooty = 478
        # back row (darker, longer, higher sweep)
        for ang_off, ln, wd in [(198, 300, 19), (214, 325, 19),
                                (230, 305, 18), (246, 265, 16)]:
            ang = ang_off if side < 0 else 180 - ang_off
            feather(rootx, rooty, ang, ln, wd,
                    (110, 14, 10), (255, 110, 25), outline=dark)
        # front row (brighter, golden tips)
        for ang_off, ln, wd in [(206, 265, 21), (222, 295, 20),
                                (238, 280, 19), (254, 235, 17)]:
            ang = ang_off if side < 0 else 180 - ang_off
            feather(rootx, rooty + 12, ang, ln, wd,
                    (170, 30, 10), (255, 190, 70), outline=dark)
        glow(rootx + side * 170, rooty - 90, 140, (255, 130, 40), 0.30, 2.2)

    # ---- body: rising teardrop
    body = ellipse_poly(cx, 480, 52, 118, 0, 36)
    fill_poly(body, (150, 22, 12))
    belly = ellipse_poly(cx + 6, 505, 30, 88, 0, 28)
    fill_poly(belly, (255, 140, 45), 0.85)
    # soft vertical sheen down the belly centre
    for yy in range(420, 585, 3):
        _blend(cx + 4, yy, 255, 200, 110, 0.18)
    # gold rim light along the body's left edge
    for yy in range(380, 580):
        t = (yy - 380) / 200.0
        xx = int(cx - 52 * math.sqrt(max(0.0, 1 - ((yy - 480) / 118.0) ** 2)))
        _blend(xx, yy, 255, 190, 90, 0.5 * (1 - abs(t - 0.5)))
    # chest glow
    glow(cx, 470, 90, (255, 120, 40), 0.45, 2.0)

    # ---- neck + head
    neck = ellipse_poly(cx, 385, 30, 55, 0, 24)
    fill_poly(neck, (165, 28, 14))
    disc(cx, 346, 30, (190, 34, 16))
    # darker crown cap on top of the head
    disc(cx, 330, 22, (140, 20, 12))
    # crest plumes sweeping back and outward, thin
    for ang, ln in [(196, 66), (216, 78), (236, 62)]:
        feather(cx - 8, 328, ang, ln, 5, (200, 40, 16), (255, 190, 80),
                glow_tip=False)
    for ang, ln in [(344, 66), (324, 78), (304, 62)]:
        feather(cx + 8, 328, ang, ln, 5, (200, 40, 16), (255, 190, 80),
                glow_tip=False)
    # beak pointing up, large and clearly visible
    fill_poly([(cx - 11, 326), (cx + 11, 326), (cx + 3, 282)],
              (255, 205, 90))
    fill_poly([(cx - 11, 326), (cx + 3, 282), (cx - 3, 324)],
              (255, 232, 150))
    # gold brow stripes above the eyes
    line(cx - 20, 336, cx - 6, 332, (255, 190, 90), 0.9, 2)
    line(cx + 20, 336, cx + 6, 332, (255, 190, 90), 0.9, 2)
    # eyes: small amber embers, not headlights
    for ex in (cx - 12, cx + 12):
        disc(ex, 344, 3, (255, 190, 80))
        disc(ex, 344, 1, (255, 245, 200))
        glow(ex, 344, 7, (255, 180, 70), 0.6, 2.0)


def paint_embers(rng):
    # sparks flying off wings, tail and ring
    sources = [(300, 380, 220), (724, 380, 220), (512, 720, 200),
               (512, 480, 320), (200, 500, 120), (824, 500, 120)]
    for _ in range(240):
        sx, sy, spread = sources[rng.randrange(len(sources))]
        x = sx + rng.gauss(0, spread * 0.55)
        y = sy + rng.gauss(0, spread * 0.45) - rng.uniform(0, 60)
        if not (0 <= x < W and 150 <= y < 850):
            continue
        s = rng.uniform(0.8, 2.8)
        warm = rng.random()
        col = (255, int(lerp(150, 220, warm)), int(lerp(40, 120, warm)))
        glow(x, y, s * 3.2, col, 0.9, 2.0)
        # short diagonal fading trail for the bigger sparks
        if s > 2.2:
            dx = rng.uniform(-8, 8)
            dy = -rng.uniform(8, 18)
            line(x, y, x + dx, y + dy, col, 0.4, 1)


def paint_city(rng):
    # distant sleeping city, dark silhouette + warm lit windows
    base_y = 1024
    x = -10
    horizon = 872
    while x < W + 10:
        wdt = rng.randint(34, 86)
        hgt = rng.randint(48, 150)
        if rng.random() < 0.10:
            hgt = rng.randint(160, 230)  # a tower
        top = horizon + (150 - hgt)
        fill_poly([(x, base_y), (x, top), (x + wdt, top),
                   (x + wdt, base_y)], (10, 9, 28))
        # rooftop antenna on towers
        if hgt > 160:
            line(x + wdt // 2, top, x + wdt // 2, top - 22,
                 (10, 9, 28), 1.0, 2)
            disc(x + wdt // 2, top - 24, 2, (255, 80, 60))
            glow(x + wdt // 2, top - 24, 8, (255, 80, 60), 0.8, 2.0)
        # windows
        cols = max(1, wdt // 13)
        rows = max(1, hgt // 18)
        for cy in range(rows):
            for cxw in range(cols):
                if rng.random() < 0.52:
                    wx = x + 5 + cxw * 13 + rng.randint(-2, 2)
                    wy = top + 9 + cy * 18 + rng.randint(-2, 2)
                    warm = rng.random()
                    _blend(wx, wy, 255, int(lerp(175, 215, warm)),
                           int(lerp(90, 140, warm)), 1.0)
                    _blend(wx + 1, wy, 255, 195, 110, 0.7)
                    _blend(wx, wy + 1, 255, 195, 110, 0.7)
                    _blend(wx + 1, wy + 1, 255, 195, 110, 0.7)
        x += wdt + rng.randint(2, 10)
    # warm haze hugging the horizon above the rooftops
    glow(512, 880, 420, (255, 120, 40), 0.30, 2.0)
    # dark ground band at the very bottom for depth
    for y in range(985, H):
        f = (y - 985) / 39.0
        for x in range(W):
            _blend(x, y, 6, 5, 18, f * 0.55)


def paint_vignette():
    for y in range(H):
        for x in range(W):
            dx = (x - 512) / 512.0
            dy = (y - 512) / 512.0
            d2 = dx * dx + dy * dy
            if d2 > 0.9:
                f = min(0.45, (d2 - 0.9) * 0.55)
                _blend(x, y, 4, 4, 16, f)


# ---------------------------------------------------------------- PNG

def png_bytes():
    raw = bytearray()
    for y in range(H):
        raw.append(0)  # filter: none
        raw += img[y * W * 3:(y + 1) * W * 3]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", comp)
            + chunk(b"IEND", b""))


def main():
    rng = random.Random(SEED)
    paint_sky(rng)
    paint_sun()
    paint_ring(rng)
    paint_phoenix(rng)
    paint_embers(rng)
    paint_city(rng)
    paint_vignette()

    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.png")
    with open(path, "wb") as f:
        f.write(png_bytes())
    print("wrote", path)


if __name__ == "__main__":
    main()
