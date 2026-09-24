"""Open the stats boxes, photograph them, and read the text back off them.

There are two stats boxes: the one on the status screen, and the one drawn when
a Pokemon grows a level. They share their printing code but not their position,
so both are checked. The level-up box has two callers, a battle win and a Rare
Candy, and both are exercised.

Walking a fresh save far enough to own a Pokemon is the routing problem the
run-to-credits harness is still stuck on, so this borrows the debug build's test
battle instead: it builds a real level 20 Rhydon with `AddPartyMon`, which is a
genuine party Pokemon read by the real status screen code. From the battle menu
the route is PKMN -> the Pokemon -> STATS. For the level-up box the same
Rhydon is left one experience point short of level 21 and wins a turn. For the
Rare Candy the debug build's new game is started instead, which hands out 99
of them and a level 90 Exeggutor.

Two outputs per box, and the second is the useful one. A PNG for a person to
look at, and a decoded copy of the box read straight out of `wTileMap`, so the
labels and the numbers can be asserted instead of eyeballed.

Usage:
    python test/statuscheck.py pokered_debug.gbc pokered_debug.sym [shot.png]

The other screenshots are written next to the first, with `_levelup` and
`_candy` added.
"""
import sys

from rominspect import load_symbols
from debugbattle import NotReached, boot_to_debug_menu, enter, tap, word, write_word

SCREEN_WIDTH = 20

# The stats box is drawn by TextBoxBorder at (0, 8) and is nine columns wide,
# so its text lives in rows 9-16, columns 1-8.
STATS_ROWS = range(9, 17)
STATS_COLS = range(0, 10)

# Labels the box is expected to carry. Vanilla spelled out four stat names, each
# above its value; with Special split into two roles there are five, so each
# label now shares a row with its value.
EXPECTED_LABELS = ("ATK", "DEF", "SPE", "SPA", "SPD")

# Rhydon's two special split factors are both 16, so on the stock test Pokemon
# SPA and SPD print the same number and a swapped or unscaled row would pass.
# The party Pokemon is turned into an Alakazam (20 attacking, 12 defending, in
# sixteenths) with a stored Special that both factors divide cleanly.
ALAKAZAM = 0x95
STORED_SPECIAL = 100
EXPECTED_SPECIAL = {"SPA": 125, "SPD": 75}

# The level-up box is drawn by TextBoxBorder at (9, 2) and is ten columns wide
# inside, so its text lives in rows 3-10, columns 10-18.
LEVEL_UP_ROWS = range(3, 11)
LEVEL_UP_COLS = range(9, 20)

# Rhydon grows on the slow curve, where level 21 starts at 11,576 experience.
# Beating a level 20 Rhydon is worth far more than one point and far less than
# the 13,310 level 22 needs, so exactly one level is gained.
EXP_ONE_SHORT_OF_21 = 11575
SWIFT = 0x81
LEVEL_UP_FRAMES = 3000

# The value the box should print beside each label, read from the party data
# after the level has been gained. Rhydon's special factors are both 16, so SPA
# and SPD both equal the stored Special; the scaling itself is proven above.
PARTY_STATS = {
    "ATK": "wPartyMon1Attack",
    "DEF": "wPartyMon1Defense",
    "SPE": "wPartyMon1Speed",
    "SPA": "wPartyMon1Special",
    "SPD": "wPartyMon1Special",
}

# Exeggutor's factors are 21 attacking and 11 defending, in sixteenths, so the
# Rare Candy box proves the scaling on the level-up layout as well.
EXEGGUTOR_FACTORS = {"SPA": 21, "SPD": 11}

# Frames of A presses allowed to get through the debug new game's intro and
# the Oak speech before the START menu is expected to open.
INTRO_TAPS = 400


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


def read_values(rows, box_rows, box_cols):
    """Map each label in a box to the number printed beside it."""
    values = {}
    for y in box_rows:
        words = "".join(rows[y][x] for x in box_cols).strip(" .").split()
        if len(words) == 2 and words[1].isdigit():
            values[words[0]] = int(words[1])
    return values


def print_box(title, rows, box_rows, box_cols):
    print(f"{title}, read out of wTileMap:")
    for y in box_rows:
        cells = "".join(rows[y][x] for x in box_cols)
        print(f"  row {y:2}  |{cells}|")
    print()


def check_status_screen(rom_path, sym_path, shot):
    """Return None on success, or the reason for failure."""
    symbols = load_symbols(sym_path)
    tilemap = symbols["wTileMap"][1]

    try:
        p, at = enter(rom_path, sym_path)
    except NotReached as e:
        return str(e)

    # The status screen copies the party Pokemon into wLoadedMon when it opens,
    # so writing the party copy while the battle menu is up is enough.
    p.memory[symbols["wPartySpecies"][1]] = ALAKAZAM
    p.memory[symbols["wPartyMon1Species"][1]] = ALAKAZAM
    write_word(p, symbols["wPartyMon1Special"][1], STORED_SPECIAL)

    open_status_screen(p, at)
    p.screen.image.save(shot)
    rows = read_screen(p, tilemap)
    p.stop(save=False)

    print(f"screenshot written to {shot}")
    print()
    print_box("stats box", rows, STATS_ROWS, STATS_COLS)

    box = "\n".join(rows[y] for y in STATS_ROWS)
    missing = [label for label in EXPECTED_LABELS if label not in box]

    # A blank screen means the route went somewhere else, or the ROM stopped.
    if not box.strip():
        return "the stats box is empty - the status screen was never reached"
    if missing:
        return f"labels missing from the stats box: {', '.join(missing)}"

    values = read_values(rows, STATS_ROWS, STATS_COLS)
    for label, want in EXPECTED_SPECIAL.items():
        got = values.get(label)
        if got != want:
            return (f"{label} shows {got}, expected {want} from a stored "
                    f"Special of {STORED_SPECIAL} on Alakazam")
    return None


def check_level_up_box(rom_path, sym_path, shot):
    """Return None on success, or the reason for failure."""
    symbols = load_symbols(sym_path)
    tilemap = symbols["wTileMap"][1]
    level = symbols["wPartyMon1Level"][1]

    try:
        p, at = enter(rom_path, sym_path)
    except NotReached as e:
        return str(e)

    # Experience is three bytes, high byte first. The enemy is left on 1 HP and
    # the player is given Swift, which can no longer miss, so the first turn
    # ends the battle whoever moves first.
    exp = symbols["wPartyMon1Exp"][1]
    for i, b in enumerate(EXP_ONE_SHORT_OF_21.to_bytes(3, "big")):
        p.memory[exp + i] = b
    write_word(p, at["wEnemyMonHP"], 1)
    p.memory[at["wTestBattlePlayerSelectedMove"]] = SWIFT
    p.memory[at["wBattleMonMoves"]] = SWIFT
    p.memory[at["wBattleMonPP"]] = 40

    # FIGHT, then the first move.
    tap(p, "a", hold=6, release=20)
    tap(p, "a", hold=6, release=20)

    # The faint and experience messages each wait for a button, and the level
    # is written before the box is drawn. So A is pressed only while the level
    # is still 20; after that the box is left up waiting for its own press.
    drawn = False
    for frame in range(LEVEL_UP_FRAMES):
        p.tick()
        if "ATK" in read_screen(p, tilemap)[LEVEL_UP_ROWS[1]]:
            drawn = True
            break
        if frame % 40 == 0 and p.memory[level] == 20:
            tap(p, "a", hold=4, release=4)
    for _ in range(20):
        p.tick()

    p.screen.image.save(shot)
    rows = read_screen(p, tilemap)
    stats = {label: word(p, symbols[name][1]) for label, name in PARTY_STATS.items()}
    new_level = p.memory[level]
    p.stop(save=False)

    print(f"screenshot written to {shot}")
    print()
    print_box("level-up box", rows, LEVEL_UP_ROWS, LEVEL_UP_COLS)

    if new_level != 21:
        return f"the Pokemon is level {new_level} after the win, expected 21"
    if not drawn:
        return "the level-up stats box never appeared"
    values = read_values(rows, LEVEL_UP_ROWS, LEVEL_UP_COLS)
    for label, want in stats.items():
        got = values.get(label)
        if got != want:
            return f"level-up box shows {label} {got}, the party data holds {want}"
    return None


def check_rare_candy_box(rom_path, sym_path, shot):
    """Return None on success, or the reason for failure."""
    symbols = load_symbols(sym_path)
    tilemap = symbols["wTileMap"][1]
    level = symbols["wPartyMon1Level"][1]

    try:
        p, at = boot_to_debug_menu(rom_path, sym_path)
    except NotReached as e:
        return str(e)

    def screen():
        return "\n".join(read_screen(p, tilemap))

    # The second debug menu entry starts a new game with the debug party and
    # bag. It still runs the intro, so A is pressed through it, trying START
    # every so often until the START menu opens in the overworld.
    tap(p, "down", hold=8, release=24)
    tap(p, "a", hold=8, release=40)
    in_world = False
    for n in range(INTRO_TAPS):
        tap(p, "a", hold=4, release=20)
        if n % 10 == 9:
            tap(p, "start", hold=6, release=40)
            if "ITEM" in screen():
                in_world = True
                break
    if not in_world:
        p.stop(save=False)
        return "the debug new game never reached the overworld"

    # ITEM is the third START menu entry and RARE CANDY the fifth item in the
    # bag. USE is the first choice, and Exeggutor leads the party.
    tap(p, "down", hold=6, release=20)
    tap(p, "down", hold=6, release=20)
    tap(p, "a", hold=6, release=60)
    for _ in range(4):
        tap(p, "down", hold=6, release=20)
    if "RARE CANDY" not in screen():
        p.stop(save=False)
        return "the bag did not show a RARE CANDY"
    tap(p, "a", hold=6, release=40)
    tap(p, "a", hold=6, release=60)
    before = p.memory[level]
    tap(p, "a", hold=6, release=0)

    # The party menu announces the new level and waits for a press before the
    # stats box goes up, so A is pressed once, after the level has changed.
    drawn = False
    pressed = False
    for frame in range(LEVEL_UP_FRAMES):
        p.tick()
        if "ATK" in read_screen(p, tilemap)[LEVEL_UP_ROWS[1]]:
            drawn = True
            break
        if not pressed and frame > 200 and p.memory[level] != before:
            tap(p, "a", hold=4, release=4)
            pressed = True
    for _ in range(20):
        p.tick()

    p.screen.image.save(shot)
    rows = read_screen(p, tilemap)
    stats = {label: word(p, symbols[name][1]) for label, name in PARTY_STATS.items()}
    after = p.memory[level]
    p.stop(save=False)

    # The scaling rounds down, the same as the damage code's.
    for label, factor in EXEGGUTOR_FACTORS.items():
        stats[label] = stats[label] * factor // 16

    print(f"screenshot written to {shot}")
    print()
    print_box("Rare Candy level-up box", rows, LEVEL_UP_ROWS, LEVEL_UP_COLS)

    if after != before + 1:
        return f"the Rare Candy took the Pokemon from level {before} to {after}"
    if not drawn:
        return "the Rare Candy stats box never appeared"
    values = read_values(rows, LEVEL_UP_ROWS, LEVEL_UP_COLS)
    for label, want in stats.items():
        got = values.get(label)
        if got != want:
            return f"Rare Candy box shows {label} {got}, expected {want}"
    return None


def main():
    rom_path = sys.argv[1] if len(sys.argv) > 1 else "pokered_debug.gbc"
    sym_path = sys.argv[2] if len(sys.argv) > 2 else "pokered_debug.sym"
    shot = sys.argv[3] if len(sys.argv) > 3 else "status.png"
    stem, dot, ext = shot.rpartition(".")
    level_up_shot = f"{stem}_levelup.{ext}" if dot else f"{shot}_levelup"
    candy_shot = f"{stem}_candy.{ext}" if dot else f"{shot}_candy"

    failure = check_status_screen(rom_path, sym_path, shot)
    if failure:
        print(f"FAIL: {failure}")
        return 1
    failure = check_level_up_box(rom_path, sym_path, level_up_shot)
    if failure:
        print(f"FAIL: {failure}")
        return 1
    failure = check_rare_candy_box(rom_path, sym_path, candy_shot)
    if failure:
        print(f"FAIL: {failure}")
        return 1
    print(f"PASS: both stats boxes show {len(EXPECTED_LABELS)} stat rows, SPA/SPD "
          f"carry the scaled values, and the level-up box is right after a "
          f"battle win and after a Rare Candy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
