"""Prove the Options screen's ACTION COMMANDS row works, and broke nothing else.

The screen was re-laid from three boxes to four to make room for the row, so
the layout is read straight out of wTileMap rather than eyeballed: every label,
every choice line and CANCEL has to be where the cursor code expects it. The
new row is then cycled with left and right, and wOptions is checked after every
press, along with the three older rows, so a change on one row that disturbs
another fails. Finally the menu is closed and opened again, to prove the
cursors are rebuilt from the saved options byte.

Usage:
    python test/optionscheck.py pokered.gbc pokered.sym [shot.png]
"""
import sys

from pyboy import PyBoy

from rominspect import load_symbols
from statuscheck import SCREEN_WIDTH, read_screen

TEXT_DELAY_MASK = 0b111
TEXT_SPEED = {1: 0b001, 7: 0b011, 14: 0b101}  # cursor X -> delay bits
BIT_BATTLE_SHIFT = 1 << 6
BIT_BATTLE_ANIMATION = 1 << 7
ACTION_COMMANDS_MASK = 0b110000
ACTION_COMMANDS = {1: 0b000000, 7: 0b010000, 14: 0b100000}  # cursor X -> bits
ARROW, UNFILLED_ARROW = 0xED, 0xEC

# row -> (column, text); a choice line starts one column in, past its cursor
LAYOUT = {
    1: (1, "TEXT SPEED"),
    2: (2, "FAST  MEDIUM SLOW"),
    5: (1, "BATTLE ANIMATION"),
    6: (2, "ON       OFF"),
    9: (1, "BATTLE STYLE"),
    10: (2, "SHIFT    SET"),
    13: (1, "ACTION COMMANDS"),
    14: (2, "ON    ASSIST OFF"),
    16: (2, "CANCEL"),
}

failures = []


def check(ok, message):
    print(("  ok    " if ok else "  FAIL  ") + message)
    if not ok:
        failures.append(message)


def press(p, button, hold=4, release=12):
    p.button_press(button)
    for _ in range(hold):
        p.tick()
    p.button_release(button)
    for _ in range(release):
        p.tick()


class Options:
    def __init__(self, p, at):
        self.p, self.at = p, at

    def mem(self, name):
        return self.p.memory[self.at[name]]

    @property
    def cursor(self):
        return self.mem("wTopMenuItemY"), self.mem("wTopMenuItemX")

    @property
    def options(self):
        return self.mem("wOptions")

    def screen(self):
        return read_screen(self.p, self.at["wTileMap"])

    def tile(self, x, y):
        return self.p.memory[self.at["wTileMap"] + y * SCREEN_WIDTH + x]

    def is_open(self):
        return "ACTION COMMANDS" in self.screen()[13]


def open_options(p, opt):
    """From the main menu with no save: NEW GAME, then OPTION."""
    press(p, "down")
    press(p, "a")
    for _ in range(120):
        p.tick()
        if opt.is_open() and opt.cursor[0] == 2:
            for _ in range(10):  # let the cursor be drawn
                p.tick()
            return True
    return False


def expect(opt, want, label):
    """want: the four settings as (text speed X, animation on, shift, action X)."""
    speed, animation, shift, action = want
    o = opt.options
    got = (
        {v: k for k, v in TEXT_SPEED.items()}.get(o & TEXT_DELAY_MASK),
        not o & BIT_BATTLE_ANIMATION,
        not o & BIT_BATTLE_SHIFT,
        {v: k for k, v in ACTION_COMMANDS.items()}.get(o & ACTION_COMMANDS_MASK),
    )
    check(got == want, f"{label}: wOptions {o:08b} reads {got} (want {want})")


def main():
    rom_path = sys.argv[1] if len(sys.argv) > 1 else "pokered.gbc"
    sym_path = sys.argv[2] if len(sys.argv) > 2 else "pokered.sym"
    shot = sys.argv[3] if len(sys.argv) > 3 else None

    symbols = load_symbols(sym_path)
    at = {k: symbols[k][1] for k in ("wTileMap", "wTopMenuItemY", "wTopMenuItemX",
                                     "wOptions", "wOptionsActionCmdCursorX")}
    p = PyBoy(rom_path, window="null")
    p.set_emulation_speed(0)
    opt = Options(p, at)

    # START skips the intro, then leaves the title screen for the main menu.
    for _ in range(40):
        press(p, "start", release=60)
        if any("NEW GAME" in row for row in opt.screen()):
            break
    if not open_options(p, opt):
        print("FAIL: never reached the Options screen")
        p.stop(save=False)
        return 1

    print("Layout:")
    rows = opt.screen()
    for y, row in enumerate(rows):
        print(f"    {y:2} |{row}|")
    if shot:
        p.screen.image.save(shot)
    for y, (x, text) in LAYOUT.items():
        got = rows[y][x:x + len(text)]
        check(got == text, f"row {y} reads {got!r} at x={x} (want {text!r})")
    # the four boxes are 4 rows each, stacked straight on top of one another
    for top in (0, 4, 8, 12):
        check(rows[top][0] != " " and rows[top + 3][0] != " ",
              f"a box spans rows {top} to {top + 3}")
    speed_x = {v: k for k, v in TEXT_SPEED.items()}.get(opt.options & TEXT_DELAY_MASK)
    check(opt.cursor == (2, speed_x) and opt.tile(speed_x, 2) == ARROW,
          f"the cursor starts on the saved text speed, at {opt.cursor}")
    for x, y in ((1, 6), (1, 10), (1, 14)):
        check(opt.tile(x, y) == UNFILLED_ARROW, f"row {y} marks its setting at x={x}")
    state = [speed_x, True, True, 1]
    expect(opt, tuple(state), "fresh options")

    print("Action commands row:")
    for _ in range(3):
        press(p, "down")
    check(opt.cursor == (14, 1), f"three downs reach the new row, on ON ({opt.cursor})")
    for button, x, name in (("right", 7, "ASSIST"), ("right", 14, "OFF"),
                            ("right", 14, "OFF, the end of the row"),
                            ("left", 7, "ASSIST"), ("left", 1, "ON"),
                            ("left", 1, "ON, the start of the row")):
        press(p, button)
        state[3] = x
        check(opt.cursor == (14, x) and opt.tile(x, 14) == ARROW,
              f"{button} moves to {name} ({opt.cursor})")
        expect(opt, tuple(state), f"{button} to {name}")

    print("Other rows:")
    press(p, "right")
    state[3] = 7
    press(p, "up")
    check(opt.cursor[0] == 10, f"up from the new row is BATTLE STYLE ({opt.cursor})")
    press(p, "right")
    state[2] = False
    expect(opt, tuple(state), "battle style SET keeps Assist")
    press(p, "up")
    press(p, "right")
    state[1] = False
    expect(opt, tuple(state), "animation OFF keeps the rest")
    press(p, "up")
    check(opt.cursor[0] == 2, f"up again is TEXT SPEED ({opt.cursor})")
    press(p, "right")
    press(p, "right")
    state[0] = 14
    expect(opt, tuple(state), "text speed SLOW keeps the rest")
    press(p, "left")
    press(p, "left")
    state[0] = 1
    expect(opt, tuple(state), "text speed FAST keeps the rest")
    press(p, "up")
    check(opt.cursor == (16, 1), f"up from the top wraps to CANCEL ({opt.cursor})")
    press(p, "down")
    check(opt.cursor[0] == 2, f"down from CANCEL wraps to the top ({opt.cursor})")
    for want in (6, 10, 14, 16):
        press(p, "down")
        check(opt.cursor[0] == want, f"down steps to row {want} ({opt.cursor})")

    print("Reopened:")
    saved = opt.options
    press(p, "b", release=60)
    reopened = open_options(p, opt)
    check(reopened, "the Options screen opens again")
    if reopened:
        check(opt.options == saved, f"wOptions survived ({opt.options:08b})")
        check(opt.mem("wOptionsActionCmdCursorX") == 7 and opt.tile(7, 14) == UNFILLED_ARROW,
              "the new row comes back on ASSIST")
        check(opt.tile(1, 2) == ARROW and opt.tile(10, 6) == UNFILLED_ARROW
              and opt.tile(10, 10) == UNFILLED_ARROW,
              "the other rows come back on FAST, OFF and SET")
        expect(opt, tuple(state), "after reopening")

    p.stop(save=False)
    if failures:
        print(f"FAIL: {len(failures)} check(s) failed")
        return 1
    print("PASS: the Action Commands row sets its bits, and the other rows still work")
    return 0


if __name__ == "__main__":
    sys.exit(main())
