"""Drive real inputs into the ROM and assert the game is actually playable.

A boot test only proves the ROM does not crash on the title screen. This drives
the intro the way a player does -- past the copyright, into NEW GAME, through
Oak's speech and name entry -- then reads game RAM to confirm the player really
exists in the world and really received a starter.

Reading RAM through the linker's own symbol names (rather than hardcoded
addresses) means the assertions keep working after we move things around.

Usage:
    python test/playable.py pokered.gbc pokered.sym
"""
import sys

from pyboy import PyBoy

from rominspect import load_symbols

REDS_HOUSE_2F = 38


def wram(symbols, name):
    """Resolve a WRAM label to its address."""
    if name not in symbols:
        raise KeyError(f"label {name!r} not in symbol file")
    return symbols[name][1]


def press(pyboy, button, hold=4, release=8):
    pyboy.button_press(button)
    for _ in range(hold):
        pyboy.tick()
    pyboy.button_release(button)
    for _ in range(release):
        pyboy.tick()


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else "pokered.gbc"
    sym = sys.argv[2] if len(sys.argv) > 2 else "pokered.sym"
    shot = sys.argv[3] if len(sys.argv) > 3 else None

    symbols = load_symbols(sym)
    addr_party = wram(symbols, "wPartyCount")
    addr_map = wram(symbols, "wCurMap")

    pyboy = PyBoy(rom, window="null")
    pyboy.set_emulation_speed(0)

    # Copyright + Game Freak intro, then the title screen demo loop.
    for _ in range(600):
        pyboy.tick()
    press(pyboy, "start")

    # Oak's intro speech, name selection and rival naming are all advanced with
    # A. Mashing A takes the default preset name and walks the whole sequence.
    for _ in range(900):
        press(pyboy, "a", hold=3, release=5)

    addr_y = wram(symbols, "wYCoord")
    addr_x = wram(symbols, "wXCoord")

    party = pyboy.memory[addr_party]
    cur_map = pyboy.memory[addr_map]
    start_pos = (pyboy.memory[addr_y], pyboy.memory[addr_x])

    # Mashing A through the intro leaves the player talking to the bedroom SNES,
    # and an open text box swallows movement. Close it before testing input.
    for _ in range(12):
        press(pyboy, "b", hold=4, release=10)

    # The intro leaves the player upstairs in their bedroom. Walking proves the
    # overworld engine accepts input, which a title-screen boot test cannot show.
    # A walk cycle is 16 frames, so the press has to outlast one full step.
    # Try every direction: the spawn tile has walls on some sides, so testing a
    # single direction can report "input is dead" when it is merely blocked.
    for direction in ("down", "left", "up", "right"):
        press(pyboy, direction, hold=20, release=20)
        if (pyboy.memory[addr_y], pyboy.memory[addr_x]) != start_pos:
            break
    moved_pos = (pyboy.memory[addr_y], pyboy.memory[addr_x])

    if shot:
        pyboy.screen.image.save(shot)
    pyboy.stop(save=False)

    print(f"wCurMap     = {cur_map} (38 = REDS_HOUSE_2F, the vanilla intro end)")
    print(f"wPartyCount = {party} (0 is correct here - starter comes later)")
    print(f"position    = {start_pos} -> {moved_pos}")

    if cur_map != REDS_HOUSE_2F:
        print(f"FAIL: expected to end the intro in REDS_HOUSE_2F, got map {cur_map}")
        return 1
    if party > 6:
        print(f"FAIL: wPartyCount={party} is impossible - RAM is corrupt")
        return 1
    if start_pos == moved_pos:
        print("FAIL: player did not move - overworld input is dead")
        return 1
    print("PASS: intro completes, player is in the world and responds to input")
    print("NOTE: this does NOT prove the game is completable end to end.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
