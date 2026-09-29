"""Render a map's blocks to a PNG, with a grid of player coordinates.

Usage: python3 tools/rendermap.py MapName out.png [scale]
MapName is the file name in maps/ (e.g. PokemonTower7F).
"""
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent


def tileset_of(name):
    header = (ROOT / f"data/maps/headers/{name}.asm").read_text()
    m = re.search(r"map_header\s+\w+,\s*(\w+),\s*(\w+)", header)
    return m.group(1), m.group(2)


def width_of(const):
    for line in open(ROOT / "constants/map_constants.asm"):
        m = re.match(r"\s*map_const\s+(\w+),\s*(\d+),\s*(\d+)", line)
        if m and m.group(1) == const:
            return int(m.group(2)), int(m.group(3))
    raise KeyError(const)


def gfx_names(tileset):
    """(tileset png, blockset bst) for a tileset constant, from gfx/tilesets.asm."""
    src = (ROOT / "gfx/tilesets.asm").read_text()
    block = None
    for line in (ROOT / "data/tilesets/tileset_headers.asm").read_text().splitlines():
        m = re.match(r"\s*tileset\s+(\w+),", line)
        if m and re.sub(r"(?<!^)(?=[A-Z])", "_", m.group(1)).upper() == tileset:
            block = m.group(1)
    gfx = re.search(rf"^{block}_GFX::\s*INCBIN \"([^\"]+)\.2bpp\"", src, re.M).group(1)
    bst = re.search(rf"^{block}_Block::\s*INCBIN \"([^\"]+)\"", src, re.M).group(1)
    return gfx + ".png", bst


def render(name, scale=2, labels=True):
    const, tileset = tileset_of(name)
    w, h = width_of(const)
    png, bst = gfx_names(tileset)
    tiles = Image.open(ROOT / png).convert("L")
    blocks = (ROOT / bst).read_bytes()
    blk = (ROOT / f"maps/{name}.blk").read_bytes()
    out = Image.new("L", (w * 32, h * 32), 255)
    per_row = tiles.size[0] // 8
    for by in range(h):
        for bx in range(w):
            b = blk[by * w + bx]
            for i in range(16):
                t = blocks[b * 16 + i]
                if t >= per_row * (tiles.size[1] // 8):
                    continue
                tile = tiles.crop(((t % per_row) * 8, (t // per_row) * 8, (t % per_row) * 8 + 8, (t // per_row) * 8 + 8))
                out.paste(tile, (bx * 32 + (i % 4) * 8, by * 32 + (i // 4) * 8))
    out = out.convert("RGB").resize((out.size[0] * scale, out.size[1] * scale), Image.NEAREST)
    if not labels:
        return out
    d = ImageDraw.Draw(out)
    for x in range(0, w * 2):
        for y in range(0, h * 2):
            if (x + y) % 2 == 0:
                d.text((x * 16 * scale + 1, y * 16 * scale + 1), f"{x},{y}", fill=(255, 0, 0))
    return out


if __name__ == "__main__":
    render(sys.argv[1], int(sys.argv[3]) if len(sys.argv) > 3 else 2).save(sys.argv[2])
