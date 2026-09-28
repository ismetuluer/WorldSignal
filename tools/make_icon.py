"""Draw World Signal's icon (blue rounded square, white signal arcs - the same mark as in the app's
sidebar) and write it as a multi-size .ico. Pure Python (zlib + struct), no image library.

    .venv\\Scripts\\python tools\\make_icon.py
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "worldsignal" / "assets" / "worldsignal.ico"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
SUPER = 4  # supersampling for smooth edges

TOP = (0x2A, 0x9B, 0xFF)  # gradient of the tile
BOTTOM = (0x00, 0x6E, 0xE6)


def inside_rounded_square(x: float, y: float, size: float, radius: float) -> bool:
    cx = min(max(x, radius), size - radius)
    cy = min(max(y, radius), size - radius)
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def on_mark(x: float, y: float, size: float) -> bool:
    """The signal mark of the sidebar logo: two upper half-rings and a dot (24-unit design grid)."""
    unit = size / 24 * 0.95
    gx = (x - size / 2) / unit + 12
    gy = (y - size / 2) / unit + 13.5
    stroke = 2.0 if size >= 32 else 3.0  # thicker lines stay visible at 16 px
    d = math.hypot(gx - 12, gy - 16)
    if gy <= 16.3:
        for r in (7.0, 3.5):
            if abs(d - r) <= stroke / 2:
                return True
    return d <= stroke * 0.62


def render(size: int) -> bytes:
    """RGBA pixels, row by row."""
    radius = size * 0.225
    rows = bytearray()
    n = SUPER * SUPER
    for py in range(size):
        rows.append(0)  # PNG filter type: none
        for px in range(size):
            cover = mark = 0
            for sy in range(SUPER):
                for sx in range(SUPER):
                    x = px + (sx + 0.5) / SUPER
                    y = py + (sy + 0.5) / SUPER
                    if inside_rounded_square(x, y, size, radius):
                        cover += 1
                        if on_mark(x, y, size):
                            mark += 1
            if cover == 0:
                rows += b"\x00\x00\x00\x00"
                continue
            t = py / max(1, size - 1)
            base = [round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)]
            w = mark / cover
            rgb = [round(c + (255 - c) * w) for c in base]
            rows += bytes((*rgb, round(255 * cover / n)))
    return bytes(rows)


def png(size: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(render(size), 9)) + chunk(b"IEND", b"")


def ico(sizes: tuple[int, ...]) -> bytes:
    images = [png(s) for s in sizes]
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for s, data in zip(sizes, images, strict=True):
        dim = 0 if s >= 256 else s
        out += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return out + b"".join(images)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(ico(SIZES))
    (OUT.parent / "worldsignal-256.png").write_bytes(png(256))  # preview / documentation
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
