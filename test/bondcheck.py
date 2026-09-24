"""Check that Bond starts, grows and falls as designed.

Bond lives in each party Pokemon's catch rate byte (MON_BOND), see
engine/pokemon/bond.asm. Each check plays the real thing in the debug build
rather than calling the routine:

  - the debug new game's party is built by AddPartyMon, so every member starts
    with no Bond, whatever its species' catch rate;
  - walking: the lead gains BOND_WALK every BOND_STEPS steps, and a lead that
    has fainted is passed over for the next Pokemon that can fight;
  - winning: a Pokemon that takes part gains BOND_WIN for the enemy it beat,
    once even when Exp. All shares the experience, and stops at MAX_BOND;
  - fainting: the Pokemon loses 10, and stops at 0;
  - losing still counts: after a lost battle every Pokemon in the party gains 3.

Usage:
    python test/bondcheck.py [pokered_debug.gbc pokered_debug.sym]
"""
import sys

from debugbattle import NotReached, boot_to_debug_menu, enter, tap, word, write_word
from rominspect import load_symbols
from statuscheck import read_screen

BOND_STEPS, BOND_WALK, BOND_WIN, BOND_FAINT, BOND_LOSS = 16, 1, 2, -10, 3
PARTYMON_STRUCT_LENGTH = 44
SWIFT, POUND = 129, 1
BATTLE_FRAMES = 6000
INTRO_TAPS = 300

failures = []


def check(ok, message):
    print(("  ok    " if ok else "  FAIL  ") + message)
    if not ok:
        failures.append(message)


def bond(p, symbols, n):
    return p.memory[symbols["wPartyMon1Bond"][1] + n * PARTYMON_STRUCT_LENGTH]


def set_bond(p, symbols, n, value):
    p.memory[symbols["wPartyMon1Bond"][1] + n * PARTYMON_STRUCT_LENGTH] = value


def finish_battle(p, at):
    """Press A through the battle until it is over."""
    for frame in range(BATTLE_FRAMES):
        p.tick()
        if not p.memory[at["wIsInBattle"]]:
            break
        if frame % 30 == 0:
            tap(p, "a", hold=4, release=4)
    for _ in range(60):
        p.tick()
    return not p.memory[at["wIsInBattle"]]


def win_battle(rom, sym, symbols, start):
    """Win the debug battle in one Swift, starting from Bond `start`."""
    p, at = enter(rom, sym)
    set_bond(p, symbols, 0, start)
    write_word(p, at["wEnemyMonHP"], 1)
    p.memory[at["wTestBattlePlayerSelectedMove"]] = SWIFT
    p.memory[at["wBattleMonMoves"]] = SWIFT
    p.memory[at["wBattleMonPP"]] = 40
    tap(p, "a", hold=6, release=20)
    tap(p, "a", hold=6, release=20)
    over = finish_battle(p, at)
    after = bond(p, symbols, 0)
    p.stop(save=False)
    return over, after


def faint(rom, sym, symbols, start):
    """Let the enemy knock the player's Pokemon out, starting from Bond `start`."""
    p, at = enter(rom, sym)
    enemy_moves = symbols["wEnemyMonMoves"][1]
    set_bond(p, symbols, 0, start)
    write_word(p, at["wBattleMonHP"], 1)
    write_word(p, at["wBattleMonSpeed"], 1)
    write_word(p, at["wEnemyMonHP"], 999)
    write_word(p, at["wEnemyMonMaxHP"], 999)
    for i in range(4):
        p.memory[enemy_moves + i] = SWIFT
    p.memory[at["wTestBattlePlayerSelectedMove"]] = POUND
    tap(p, "a", hold=6, release=20)
    tap(p, "a", hold=6, release=20)
    fainted = False
    for frame in range(BATTLE_FRAMES):
        p.tick()
        if word(p, at["wBattleMonHP"]) == 0 and bond(p, symbols, 0) != start:
            fainted = True
            break
        if frame % 30 == 0:
            tap(p, "a", hold=4, release=4)
    # Let the lost battle play out to the blackout, which adds its own Bond.
    # The debug battle then starts over and rebuilds the party, so read the
    # Bond the moment the blackout handler has added it.
    seen = []
    p.hook_register(*symbols["HandlePlayerBlackOut.notRival1Battle"],
                    lambda _: seen.append(bond(p, symbols, 0)), None)
    for frame in range(900 if fainted else 0):
        p.tick()
        if seen:
            break
        if frame % 30 == 0:
            tap(p, "a", hold=4, release=4)
    after = seen[0] if seen else bond(p, symbols, 0)
    p.stop(save=False)
    return fainted, after


def walk_checks(rom, sym, symbols):
    p, at = boot_to_debug_menu(rom, sym)
    count = symbols["wPartyCount"][1]
    # The second debug menu entry starts a new game with the debug party. B
    # advances the intro's text and answers NO to each "give a nickname?", and
    # the overworld is reached once START opens the START menu.
    tap(p, "down", hold=8, release=24)
    tap(p, "a", hold=8, release=40)
    in_world = False
    for n in range(INTRO_TAPS):
        tap(p, "b", hold=4, release=20)
        if n % 10 == 9:
            tap(p, "start", hold=6, release=40)
            if "ITEM" in "".join(read_screen(p, symbols["wTileMap"][1])):
                in_world = True
                break
    check(in_world, "the debug new game reaches the overworld")
    if not in_world:
        p.stop(save=False)
        return
    tap(p, "b", hold=6, release=60)  # close the START menu

    n = p.memory[count]
    check(n >= 2, f"the debug party has {n} Pokemon")
    starts = [bond(p, symbols, i) for i in range(n)]
    check(all(b == 0 for b in starts), f"every Pokemon AddPartyMon made starts with no Bond: {starts}")

    step_counter = symbols["wStepCounter"][1]
    xy = (symbols["wXCoord"][1], symbols["wYCoord"][1])

    def one_step():
        """Take one step, trying each direction until the player moves."""
        for direction in ("down", "up", "left", "right"):
            before = (p.memory[xy[0]], p.memory[xy[1]])
            tap(p, direction, hold=3, release=30)
            for _ in range(30):
                p.tick()
            if (p.memory[xy[0]], p.memory[xy[1]]) != before:
                return True
        return False

    def step_bonds(counter):
        """Set the step counter, take one step, and return every Bond after."""
        p.memory[step_counter] = counter
        moved = one_step()
        return moved, [bond(p, symbols, i) for i in range(n)]

    set_bond(p, symbols, 0, 10)
    # The counter is decremented before the check, so 17 lands on 16.
    moved, after = step_bonds(BOND_STEPS + 1)
    check(moved and after[0] == 10 + BOND_WALK,
          f"the {BOND_STEPS}th step gives the lead +{BOND_WALK}: 10 -> {after[0]}")
    moved, after = step_bonds(BOND_STEPS + 2)
    check(moved and after[0] == 10 + BOND_WALK, f"any other step gives nothing: {after[0]}")

    set_bond(p, symbols, 0, MAX_BOND - 0)
    moved, after = step_bonds(BOND_STEPS + 1)
    check(after[0] == 255, f"walking stops at 255: {after[0]}")

    # A fainted lead is passed over.
    hp = symbols["wPartyMon1HP"][1]
    saved = (p.memory[hp], p.memory[hp + 1])
    p.memory[hp] = p.memory[hp + 1] = 0
    set_bond(p, symbols, 1, 20)
    moved, after = step_bonds(BOND_STEPS + 1)
    check(after[1] == 20 + BOND_WALK and after[0] == 255,
          f"with the lead fainted the next Pokemon gains instead: {after[:2]}")
    p.memory[hp], p.memory[hp + 1] = saved
    p.stop(save=False)


MAX_BOND = 255
WATER, TACKLE = 0x15, 0x21


def field_ability_checks(rom, sym, symbols):
    """A Water-type that does not know Surf gets SURF in its menu at Bond 120."""
    tilemap = symbols["wTileMap"][1]

    def menu_text(bond):
        p, at = boot_to_debug_menu(rom, sym)
        tap(p, "down", hold=8, release=24)
        tap(p, "a", hold=8, release=40)
        for n in range(INTRO_TAPS):
            tap(p, "b", hold=4, release=20)
            if n % 10 == 9:
                tap(p, "start", hold=6, release=40)
                if "ITEM" in "".join(read_screen(p, tilemap)):
                    break
        base = symbols["wPartyMon1"][1]
        p.memory[base + 5] = WATER  # MON_TYPE1
        p.memory[base + 6] = WATER  # MON_TYPE2
        for i in range(4):
            p.memory[symbols["wPartyMon1Moves"][1] + i] = TACKLE if i == 0 else 0
        set_bond(p, symbols, 0, bond)
        # POKeMON is the second START menu entry; the first Pokemon; its menu
        tap(p, "down", hold=6, release=20)
        tap(p, "a", hold=6, release=60)
        tap(p, "a", hold=6, release=60)
        text = "\n".join(read_screen(p, tilemap))
        p.stop(save=False)
        return text

    check("SURF" in menu_text(120), "Bond 120: a Water-type that never learned Surf can SURF")
    check("SURF" not in menu_text(119), "Bond 119: it cannot")


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else "pokered_debug.gbc"
    sym = sys.argv[2] if len(sys.argv) > 2 else "pokered_debug.sym"
    symbols = load_symbols(sym)
    try:
        print("winning")
        over, after = win_battle(rom, sym, symbols, 100)
        check(over and after == 100 + BOND_WIN, f"a win gives +{BOND_WIN}: 100 -> {after}")
        over, after = win_battle(rom, sym, symbols, 254)
        check(over and after == 255, f"a win stops at 255: 254 -> {after}")

        print("fainting")
        # The debug battle has one Pokemon, so its fainting is also a lost
        # battle, and losing still counts: -10, then +3 for having fought.
        fainted, after = faint(rom, sym, symbols, 50)
        want = 50 + BOND_FAINT + BOND_LOSS
        check(fainted and after == want, f"fainting costs {-BOND_FAINT}, the loss gives {BOND_LOSS}: 50 -> {after} (want {want})")
        fainted, after = faint(rom, sym, symbols, 5)
        check(fainted and after == BOND_LOSS, f"fainting stops at 0 before the loss's +{BOND_LOSS}: 5 -> {after}")

        print("walking")
        walk_checks(rom, sym, symbols)

        print("field abilities")
        field_ability_checks(rom, sym, symbols)
    except NotReached as e:
        check(False, str(e))

    print()
    print("FAILED" if failures else "all Bond checks passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
