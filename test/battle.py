"""Fight a real battle and watch the engine resolve turns.

Every engine change we made lives in the battle loop, and until now nothing had
observed a single turn. Walking a fresh save to a wild encounter is a long,
brittle route, so this uses the debug build's own test battle instead: holding
SELECT on the title screen opens the debug menu, and FIGHT drops straight into a
level 20 Rhydon mirror match. The battle code is identical between the release
and debug builds -- only the entry point differs.

Usage:
    python test/battle.py pokered_debug.gbc pokered_debug.sym [shot-prefix]
"""
import sys

from pyboy import PyBoy

from rominspect import load_symbols

WANTED = (
    "wIsInBattle",
    "wBattleMonHP",
    "wBattleMonMaxHP",
    "wEnemyMonHP",
    "wEnemyMonMaxHP",
    "wPartyCount",
    "wCriticalHitOrOHKO",
    "wTopMenuItemY",
    "wMaxMenuItem",
)


def word(p, a):
    return (p.memory[a] << 8) | p.memory[a + 1]


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else "pokered_debug.gbc"
    sym = sys.argv[2] if len(sys.argv) > 2 else "pokered_debug.sym"
    prefix = sys.argv[3] if len(sys.argv) > 3 else None

    s = load_symbols(sym)
    at = {k: s[k][1] for k in WANTED if k in s}

    p = PyBoy(rom, window="null")
    p.set_emulation_speed(0)

    # Hold SELECT across the title screen so the title hands off to DebugMenu
    # instead of the main menu: the check reads hJoyHeld at the moment the title
    # loop exits, so SELECT has to still be down when START lands. How long the
    # intro takes before the title even appears is not worth guessing, so keep
    # tapping START until the debug menu's own cursor layout shows up.
    p.button_press("select")
    reached = False
    for i in range(4000):
        p.tick()
        if i % 120 == 0 and i > 240:
            p.button_press("start")
            for _ in range(8):
                p.tick()
            p.button_release("start")
        # DebugMenu is the only menu with two entries drawn at row 7.
        if p.memory[at["wTopMenuItemY"]] == 7 and p.memory[at["wMaxMenuItem"]] == 1:
            reached = True
            break
    p.button_release("select")
    for _ in range(60):
        p.tick()

    if not reached:
        if prefix:
            p.screen.image.save(f"{prefix}-nomenu.png")
        print("FAIL: never reached the debug menu")
        p.stop(save=False)
        return 1

    # FIGHT is the first entry and the cursor starts on it. TestBattle builds the
    # party with AddPartyMon, which stops on a "give a nickname?" prompt, so keep
    # answering B (no) until the battle itself is actually up.
    p.button_press("a")
    for _ in range(10):
        p.tick()
    p.button_release("a")

    for _ in range(80):
        if p.memory[at["wIsInBattle"]]:
            break
        p.button_press("b")
        for _ in range(6):
            p.tick()
        p.button_release("b")
        for _ in range(24):
            p.tick()

    if not p.memory[at["wIsInBattle"]]:
        if prefix:
            p.screen.image.save(f"{prefix}-nobattle.png")
        print("FAIL: debug FIGHT did not start a battle")
        p.stop(save=False)
        return 1

    # wIsInBattle is set before the player's mon is copied into the battle
    # struct, so only the enemy side is readable this early. That is enough: the
    # enemy losing HP is what proves our damage path ran.
    start_enemy = word(p, at["wEnemyMonHP"])
    print(f"battle started: enemy HP {start_enemy}/{word(p, at['wEnemyMonMaxHP'])}")

    # Mashing A walks FIGHT -> first move and clears every message, so each pass
    # is roughly one full turn for both sides.
    crits = 0
    damage_seen = False
    for turn in range(14):
        for _ in range(90):
            p.button_press("a")
            for _ in range(4):
                p.tick()
            p.button_release("a")
            for _ in range(8):
                p.tick()
        if "wCriticalHitOrOHKO" in at and p.memory[at["wCriticalHitOrOHKO"]]:
            crits += 1
        e, m = word(p, at["wEnemyMonHP"]), word(p, at["wBattleMonHP"])
        if e < start_enemy:
            damage_seen = True
        print(f"  turn {turn + 1:2}: our HP {m:3}, enemy HP {e:3}, "
              f"in battle = {p.memory[at['wIsInBattle']]}")
        if not p.memory[at["wIsInBattle"]]:
            break

    # The loop above stops the moment wIsInBattle clears, which is partway
    # through the fade out of the battle screen. A fade is blank, and a blank
    # screen is exactly what the crash check looks for, so let the game settle
    # on its next screen before judging it.
    for _ in range(240):
        p.button_press("a")
        for _ in range(4):
            p.tick()
        p.button_release("a")
        for _ in range(8):
            p.tick()

    if prefix:
        p.screen.image.save(f"{prefix}-battle.png")

    # A crashed Game Boy sits in a halt loop with a frozen, usually blank screen.
    screen = p.screen.ndarray
    alive = screen[:, :, :3].std() >= 1.0
    p.stop(save=False)

    print()
    print(f"damage was dealt : {damage_seen}")
    print(f"screen still live: {alive}")
    if not damage_seen:
        print("FAIL: no HP changed in 14 turns - the damage path is not running")
        return 1
    if not alive:
        print("FAIL: screen went blank - the ROM crashed during the battle")
        return 1
    print("PASS: a real battle ran, damage resolved, no crash")
    return 0


if __name__ == "__main__":
    sys.exit(main())
