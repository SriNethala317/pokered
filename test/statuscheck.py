"""Open the status screen, photograph it, and read the text back off it.

`BUGS.md` records that the status screen cannot be corrected because nothing in
the project can look at it. This is that missing tool.

Walking a fresh save far enough to own a Pokemon is the routing problem the
run-to-credits harness is still stuck on, so this borrows the debug build's test
battle instead: it builds a real level 20 Rhydon with `AddPartyMon`, which is a
genuine party Pokemon read by the real status screen code. From the battle menu
the route is PKMN -> the Pokemon -> STATS.

Two outputs, and the second is the useful one. A PNG for a person to look at,
and a decoded copy of the stats box read straight out of `wTileMap`, so the
labels and the numbers can be asserted instead of eyeballed.

Usage:
    python test/statuscheck.py pokeblue_debug.gbc pokeblue_debug.sym [shot.png]
"""
import sys

from rominspect import load_symbols
from debugbattle import NotReached, enter, tap

SCREEN_WIDTH = 20

# The stats box is drawn by TextBoxBorder at (0, 8) and is nine columns wide,
# so its text lives in rows 9-16, columns 1-8.
STATS_ROWS = range(9, 17)
STATS_COLS = range(0, 10)

# Labels the box is expected to carry. Vanilla spells out four stat names; the
# fifth row arrives with the Sp.Atk / Sp.Def split.
EXPECTED_LABELS = ("ATTACK", "DEFENSE", "SPEED", "SPECIAL")


def decode(tile):
    """Turn one Game Boy text tile back into a character."""
    if tile == 0x7F:
        return " "
    if 0x80 <= tile <= 0x99:
        return chr(ord("A") + tile - 0x80)
    if 0xA0 <= tile <= 0xB9:
        return chr(ord("a") + tile - 0xA0)
    if 0xF6 <= tile <= 0xFF:
        return chr(ord("0") + tile - 0xF6)
    if tile == 0xF3:
        return "/"
    if tile == 0xE8:
        return "."
    if tile == 0xE1:
        return ":"
    return "."


def read_screen(p, tilemap):
    """Return the whole text screen as a list of 18 strings."""
    rows = []
    for y in range(18):
        base = tilemap + y * SCREEN_WIDTH
        rows.append("".join(decode(p.memory[base + x]) for x in range(SCREEN_WIDTH)))
    return rows


def open_status_screen(p, at):
    """Walk the battle menu to the status screen. Raises NotReached on failure."""
    # The send-out messages are still on screen when the battle starts. B
    # advances text and does nothing at the battle menu, so it is safe to mash.
    for _ in range(10):
        tap(p, "b", hold=4, release=16)

    # The battle menu is a two by two block: FIGHT and PKMN on the top row,
    # ITEM and RUN below. The cursor starts on FIGHT, so one press right
    # selects PKMN.
    tap(p, "right", hold=8, release=24)
    tap(p, "a", hold=8, release=40)
    for _ in range(90):
        p.tick()

    # Only one Pokemon is in the party, so the cursor is already on it.
    tap(p, "a", hold=8, release=40)
    for _ in range(90):
        p.tick()

    # SWITCH, STATS, CANCEL. STATS is the second entry.
    tap(p, "down", hold=8, release=24)
    tap(p, "a", hold=8, release=40)
    for _ in range(180):
        p.tick()


def main():
    rom_path = sys.argv[1] if len(sys.argv) > 1 else "pokeblue_debug.gbc"
    sym_path = sys.argv[2] if len(sys.argv) > 2 else "pokeblue_debug.sym"
    shot = sys.argv[3] if len(sys.argv) > 3 else "status.png"

    symbols = load_symbols(sym_path)
    tilemap = symbols["wTileMap"][1]

    try:
        p, at = enter(rom_path, sym_path)
    except NotReached as e:
        print(f"FAIL: {e}")
        return 1

    open_status_screen(p, at)
    p.screen.image.save(shot)
    rows = read_screen(p, tilemap)
    p.stop(save=False)

    print(f"screenshot written to {shot}")
    print()
    print("stats box, read out of wTileMap:")
    for y in STATS_ROWS:
        cells = "".join(rows[y][x] for x in STATS_COLS)
        print(f"  row {y:2}  |{cells}|")
    print()

    box = "\n".join(rows[y] for y in STATS_ROWS)
    missing = [label for label in EXPECTED_LABELS if label not in box]

    # A blank screen means the route went somewhere else, or the ROM stopped.
    if not box.strip():
        print("FAIL: the stats box is empty - the status screen was never reached")
        return 1
    if missing:
        print(f"FAIL: labels missing from the stats box: {', '.join(missing)}")
        return 1
    print(f"PASS: the status screen opens and shows {len(EXPECTED_LABELS)} stat rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
