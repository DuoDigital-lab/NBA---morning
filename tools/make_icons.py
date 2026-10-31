"""Vygeneruje PNG ikonky appky (vlastná basketbalová lopta, nie logo NBA). Len štandardná knižnica.

    python3 tools/make_icons.py
"""
import math
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "icons")
NAVY = (7, 13, 31)
ORANGE = (240, 138, 36)
SEAM = (26, 12, 0)
RED = (224, 40, 60)
BLUE = (42, 107, 242)


def png(path, w, h, pixels):
    """pixels: RGB alebo RGBA n-tice (podľa dĺžky prvého pixelu)."""
    raw = b"".join(b"\x00" + bytes(c for px in pixels[y * w:(y + 1) * w] for c in px) for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    ctype = 6 if len(pixels[0]) == 4 else 2
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(data)


def color_at(x, y, scale):
    """x, y v rozsahu 0..1. scale = veľkosť lopty (maskable má menšiu kvôli bezpečnej zóne)."""
    cx, cy = 0.5, 0.47
    # pruhy dole: modrá / červená
    if y > 0.86:
        return BLUE if x < 0.5 else RED
    dx, dy = (x - cx) / scale, (y - cy) / scale
    r = math.hypot(dx, dy)
    if r > 0.5:
        return NAVY
    lw = 0.028
    seam = abs(dx) < lw or abs(dy) < lw
    for side in (-1, 1):  # zakrivené švy
        if abs(math.hypot(dx - side * 0.62, dy) - 0.44) < lw:
            seam = True
    if seam:
        return SEAM
    shade = 1 - 0.18 * max(0, (dx + dy) / 0.7)
    return tuple(int(c * shade) for c in ORANGE)


def render(size, scale, ss=3):
    px = []
    for y in range(size):
        for x in range(size):
            acc = [0, 0, 0]
            for sy in range(ss):
                for sx in range(ss):
                    c = color_at((x + (sx + .5) / ss) / size, (y + (sy + .5) / ss) / size, scale)
                    acc = [a + b for a, b in zip(acc, c)]
            px.append(tuple(a // (ss * ss) for a in acc))
    return px


def render_mac(size, ss=2):
    """macOS štýl: zaoblený štvorec 824/1024 s priehľadným okrajom (Big Sur a novšie)."""
    inset, side, radius = 100 / 1024, 824 / 1024, 185 / 1024
    px = []
    for y in range(size):
        for x in range(size):
            acc, alpha = [0, 0, 0], 0
            for sy in range(ss):
                for sx in range(ss):
                    fx, fy = (x + (sx + .5) / ss) / size, (y + (sy + .5) / ss) / size
                    u, v = (fx - inset) / side, (fy - inset) / side
                    if not (0 <= u <= 1 and 0 <= v <= 1):
                        continue
                    cx = min(max(fx, inset + radius), inset + side - radius)
                    cy = min(max(fy, inset + radius), inset + side - radius)
                    if math.hypot(fx - cx, fy - cy) > radius:
                        continue
                    c = color_at(u, v, 0.74)
                    acc = [a + b for a, b in zip(acc, c)]
                    alpha += 1
            if alpha:
                px.append(tuple(a // alpha for a in acc) + (255 * alpha // (ss * ss),))
            else:
                px.append((0, 0, 0, 0))
    return px


def main():
    os.makedirs(OUT, exist_ok=True)
    mac = os.path.join(os.path.dirname(OUT), "..", "tools", "mac-icon-1024.png")
    png(os.path.normpath(mac), 1024, 1024, render_mac(1024))
    print("ok mac-icon-1024.png")
    for name, size, scale in (("icon-192.png", 192, 0.74), ("icon-512.png", 512, 0.74),
                              ("icon-maskable-512.png", 512, 0.56), ("apple-touch-icon.png", 180, 0.74)):
        png(os.path.join(OUT, name), size, size, render(size, scale))
        print("ok", name)


if __name__ == "__main__":
    main()
