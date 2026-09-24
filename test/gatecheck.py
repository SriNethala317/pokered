"""Check the opened-up field moves: Cut needs no badge, Surf needs any three.

In the debug new game, a party Pokemon is given the move and the menu is used
from the overworld, then the message the game prints says which rule held:
"No! A new BADGE is required." means the badge check refused it, and anything
else ("There isn't anything to CUT!", "No SURFing on ... here!") means it got
past the badge check to the move itself.

  - CUT with no badges at all gets past the badge check;
  - SURF with two badges (not the Soul Badge) is refused, and with three
    badges (still not the Soul Badge) it gets past.

Saffron's guards letting you through after Brock is a flag set in Pewter Gym's
badge script (BIT_GAVE_SAFFRON_GUARDS_DRINK) and is not walked here.

Usage:
    python test/gatecheck.py [pokered_debug.gbc pokered_debug.sym]
"""
import sys

from actioncheck import check, failures
from debugbattle import boot_to_debug_menu, tap
from rominspect import load_symbols
from statuscheck import read_screen

CUT, SURF = 0x0F, 0x39
INTRO_TAPS = 300


def use_field_move(rom, sym, move, badges):
    s = load_symbols(sym)
    tilemap = s["wTileMap"][1]
    p, at = boot_to_debug_menu(rom, sym)
    tap(p, "down", hold=8, release=24)
    tap(p, "a", hold=8, release=40)
    for n in range(INTRO_TAPS):
        tap(p, "b", hold=4, release=20)
        if n % 10 == 9:
            tap(p, "start", hold=6, release=40)
            if "ITEM" in "".join(read_screen(p, tilemap)):
                break
    p.memory[s["wObtainedBadges"][1]] = badges
    for i in range(4):
        p.memory[s["wPartyMon1Moves"][1] + i] = move if i == 0 else 0
    # POKeMON, the first Pokemon, then its first entry: the field move
    tap(p, "down", hold=6, release=20)
    tap(p, "a", hold=6, release=60)
    tap(p, "a", hold=6, release=60)
    tap(p, "a", hold=6, release=90)
    screen = " ".join(read_screen(p, tilemap))
    p.stop(save=False)
    return screen


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else "pokered_debug.gbc"
    sym = sys.argv[2] if len(sys.argv) > 2 else "pokered_debug.sym"

    text = use_field_move(rom, sym, CUT, 0)
    check("BADGE" not in text and "CUT" in text,
          f"CUT with no badges gets past the badge check: {text.strip()[-60:]!r}")
    text = use_field_move(rom, sym, SURF, 0b00000011)
    check("BADGE" in text, f"SURF with two badges is refused: {text.strip()[-60:]!r}")
    text = use_field_move(rom, sym, SURF, 0b00000111)
    check("BADGE" not in text and "SURF" in text,
          f"SURF with three badges, none of them the Soul Badge, gets past: {text.strip()[-60:]!r}")

    print()
    print("FAILED" if failures else "all gate checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
