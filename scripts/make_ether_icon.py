"""Write a small standalone ETHER.ico (32x32) next to this file.

No third-party deps. Called by install_desktop_shortcut.ps1.
"""
from __future__ import annotations

import struct
from pathlib import Path

OUT = Path(__file__).resolve().parent / "ETHER.ico"
SIZE = 32


def _pixel(x: int, y: int) -> tuple[int, int, int, int]:
    # Deep slate field + cyan gem mark. BGRA later.
    cx, cy = 15.5, 15.5
    dx, dy = x - cx, y - cy
    r2 = dx * dx + dy * dy
    if r2 > 14.6 * 14.6:
        return (0, 0, 0, 0)
    if r2 > 13.2 * 13.2:
        return (40, 210, 230, 255)
    # diamond
    if abs(dx) + abs(dy) < 8.4:
        t = abs(dx) / 8.4
        return (20, int(180 + 50 * t), int(200 + 30 * t), 255)
    return (18, 28, 42, 255)


def _dib() -> bytes:
    # BITMAPINFOHEADER + BGRA XOR + 1bpp AND mask
    header = struct.pack(
        "<IiiHHIIiiII",
        40,
        SIZE,
        SIZE * 2,
        1,
        32,
        0,
        SIZE * SIZE * 4,
        0,
        0,
        0,
        0,
    )
    xor = bytearray()
    for y in range(SIZE - 1, -1, -1):
        for x in range(SIZE):
            r, g, b, a = _pixel(x, y)
            xor.extend((b, g, r, a))
    and_row = ((SIZE + 31) // 32) * 4
    mask = bytes(and_row * SIZE)
    return header + bytes(xor) + mask


def write_icon(path: Path = OUT) -> Path:
    dib = _dib()
    # ICONDIR + ICONDIRENTRY + DIB
    icondir = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack(
        "<BBBBHHII",
        SIZE,
        SIZE,
        0,
        0,
        1,
        32,
        len(dib),
        6 + 16,
    )
    path.write_bytes(icondir + entry + dib)
    return path


if __name__ == "__main__":
    out = write_icon()
    print(out)
