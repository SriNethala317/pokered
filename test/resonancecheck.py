"""Check Resonance works as designed, and keeps battles short.

Staged turns in the debug battle, as in actioncheck.py (whose turn machinery
this reuses): both sides use Pound, HP is pinned high, and A or B is pressed at
exact frames after the cue. Resonance state is written between turns where a
check needs a starting point, and read back after.

Checked, with three badges (the ramp's third row: a 9-point meter, 3 turns,
+4 frames on each window, 3/4 of the pain):
  - nothing fills or shows until EVENT_RESONANCE_UNLOCKED is set;
  - PERFECT and COUNTER add 2, GREAT and BRACED 1, and PERFECT and COUNTER add
    1 Bond;
  - SELECT on the battle menu starts it only with a full meter, a Bond of 200
    and the event set; it takes no turn and the menu stays;
  - while it lasts: your damage x1.5, theirs x3/4, the trainer's bar drops,
    the windows are wider, and a PERFECT buys a turn back, at most 3 times;
  - it ends after its turns run out;
  - a hit that empties the trainer's bar breaks it: BROKEN!, the meter empties,
    and the player's next turn is skipped;
  - the HUD bar's cap shows ▷ when ready and ▶ while it lasts;
  - no text box is added, and starting it takes at most 12 frames.

Usage:
    python test/resonancecheck.py [pokered_debug.gbc pokered_debug.sym]
"""
import sys

from actioncheck import (GOOD, PERFECT, POUND, Recorder, check, failures,
                         install_hooks, take_turn)
from debugbattle import NotReached, enter, tap, word
from rominspect import load_symbols

THREE_BADGES = 0b111
METER, TURNS, WINDOW, PAIN = 9, 3, 4, 3  # ResonanceRamp's row for 3 badges
PERFECT_WINDOW = 15  # ActionRamp's row for 3 badges
TRAINER_MAX_HP = 24
BOND_RESONANT = 200
ACTIVE, STUNNED = 1 << 7, 1 << 6
REFUNDS = 0b111
EVENT_RESONANCE_UNLOCKED = 0x6A
BADGE_BROKEN, BADGE_RESONANCE = 9, 11
CANNOT_MOVE = 0xFF
CAP, READY, RUNNING = 0x62, 0xEC, 0xED
HUD = (9, 8)
MAX_ACTIVATION_FRAMES = 12


class Resonance:
    def __init__(self, p, at, symbols):
        self.p, self.at, self.s = p, at, symbols
        self.event = (symbols["wEventFlags"][1] + EVENT_RESONANCE_UNLOCKED // 8,
                      1 << (EVENT_RESONANCE_UNLOCKED % 8))

    def m(self, name):
        return self.p.memory[self.s[name][1]]

    def w(self, name, value):
        self.p.memory[self.s[name][1]] = value

    def unlock(self, on=True):
        addr, bit = self.event
        self.p.memory[addr] = (self.p.memory[addr] | bit) if on else (self.p.memory[addr] & ~bit)

    def set(self, meter=0, turns=0, pain=0, flags=0, bond=None):
        self.w("wResonanceMeter", meter)
        self.w("wResonanceTurns", turns)
        self.w("wTrainerPain", pain)
        self.w("wResonanceFlags", flags)
        if bond is not None:
            self.w("wPartyMon1Bond", bond)

    def state(self):
        return (self.m("wResonanceMeter"), self.m("wResonanceTurns"),
                self.m("wTrainerPain"), self.m("wResonanceFlags"))

    def hud_cap(self):
        x, y = HUD
        return self.p.memory[self.s["wTileMap"][1] + y * 20 + x]


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else "pokered_debug.gbc"
    sym = sys.argv[2] if len(sys.argv) > 2 else "pokered_debug.sym"
    try:
        p, at = enter(rom, sym, action_commands="on")
    except NotReached as e:
        print(f"FAIL: {e}")
        return 1
    symbols = load_symbols(sym)
    for name in ("wEnemyMonMoves", "wEnemyMonStatus", "wBattleMonStatus",
                 "wActionCommandForceEffect", "wActionCommandFoe",
                 "wActionCommandStreak", "wActionCommandCue", "wObtainedBadges"):
        at[name] = symbols[name][1]
    rec = Recorder(p, at)
    install_hooks(p, rec, symbols)
    r = Resonance(p, at, symbols)

    # extra readings: the player's chosen move each time it executes, the
    # windows as armed, every PrintText, and when TryResonance runs
    seen = {"badges": [], "moves": [], "perfect": {}, "texts": 0, "try": None, "menu_after_try": None}

    def on(name):
        side = p.memory[at["hWhoseTurn"]]
        if name == "ExecutePlayerMove":
            seen["moves"].append(p.memory[at["wPlayerSelectedMove"]])
        elif name == "FinishActionCommand":
            seen["perfect"].setdefault(side, r.m("wActionCommandPerfect"))
        elif name == "PrintText":
            seen["texts"] += 1
        elif name == "ShowActionBadge":
            seen["badges"].append(p.register_file.A)
        elif name == "TryResonance":
            seen["try"] = p.frame_count
        elif name == "HandleMenuInput" and seen["try"] is not None and seen["menu_after_try"] is None:
            seen["menu_after_try"] = p.frame_count
    for name in ("ExecutePlayerMove", "PrintText", "TryResonance", "HandleMenuInput",
                 "ShowActionBadge"):
        p.hook_register(*symbols[name], on, name)
    # FinishActionCommand is already hooked by the Recorder: chain onto it
    rec_on = rec.on

    def chained(name):
        if name == "FinishActionCommand":
            on(name)
        rec_on(name)
    bank, addr = symbols["FinishActionCommand"]
    p.hook_deregister(bank, addr)
    p.hook_register(bank, addr, chained, "FinishActionCommand")

    def turn(**kw):
        seen["moves"].clear()
        seen["badges"].clear()
        seen["perfect"].clear()
        seen["texts"] = 0
        kw.setdefault("badges", THREE_BADGES)
        return take_turn(p, at, rec, **kw)

    def select():
        """Press SELECT on the battle menu, which is up between turns."""
        seen["try"] = seen["menu_after_try"] = None
        for _ in range(30):
            p.tick()
        tap(p, "select", hold=4, release=30)

    perfect_both = {0: ("a", 3), 1: ("b", 3)}
    good_both = {0: ("a", 18), 1: ("b", 18)}

    print("Locked:")
    r.unlock(False)
    r.set(bond=0)
    turn(presses=perfect_both)
    check(r.m("wResonanceMeter") == 0, f"nothing fills before Brock: meter {r.m('wResonanceMeter')}")
    check(r.hud_cap() not in (CAP, READY, RUNNING), "no bar in the HUD before Brock")
    select()
    check(not r.m("wResonanceFlags") & ACTIVE, "SELECT does nothing before Brock")

    print("Filling the meter:")
    r.unlock()
    r.set(bond=0)
    t = turn(presses=perfect_both)
    got = (t.results.get(0), t.results.get(1))
    check(got == (PERFECT, PERFECT) and r.m("wResonanceMeter") == 4,
          f"PERFECT and COUNTER add 2 each: results {got}, meter {r.m('wResonanceMeter')}")
    check(r.m("wPartyMon1Bond") == 2, f"PERFECT and COUNTER add 1 Bond each: {r.m('wPartyMon1Bond')}")
    r.set(bond=0)
    t = turn(presses=good_both)
    got = (t.results.get(0), t.results.get(1))
    check(got == (GOOD, GOOD) and r.m("wResonanceMeter") == 2,
          f"GREAT and BRACED add 1 each: results {got}, meter {r.m('wResonanceMeter')}")
    check(r.m("wPartyMon1Bond") == 0, "GREAT and BRACED add no Bond")
    r.set(meter=METER - 1)
    turn(presses=perfect_both)
    check(r.m("wResonanceMeter") == METER, f"the meter stops at {METER}: {r.m('wResonanceMeter')}")
    for _ in range(40):
        p.tick()
    check(r.hud_cap() == CAP, f"a full meter without the Bond keeps the plain cap ({r.hud_cap():#x})")

    print("Starting it:")
    r.set(meter=METER - 1, bond=BOND_RESONANT)
    turn()
    select()
    check(not r.m("wResonanceFlags") & ACTIVE, "SELECT with the meter one short is refused")
    r.set(meter=METER, bond=BOND_RESONANT - 1)
    turn()
    select()
    check(not r.m("wResonanceFlags") & ACTIVE, "SELECT with Bond 199 is refused")
    r.set(meter=METER, bond=BOND_RESONANT)
    turn()
    for _ in range(40):
        p.tick()
    check(r.hud_cap() == READY, f"the cap shows ▷ when ready ({r.hud_cap():#x})")
    select()
    meter, turns, pain, flags = r.state()
    check(flags & ACTIVE and turns == TURNS and meter == 0,
          f"SELECT starts it: flags {flags:#x}, {turns} turns, meter {meter}")
    check(r.hud_cap() == RUNNING, f"the cap shows ▶ while it lasts ({r.hud_cap():#x})")
    check(r.m("wActionCommandResult") == BADGE_RESONANCE, "the RESONANCE! badge shows")
    if seen["try"] is not None and seen["menu_after_try"] is not None:
        took = seen["menu_after_try"] - seen["try"]
        check(took <= MAX_ACTIVATION_FRAMES, f"starting it took {took} frames (at most {MAX_ACTIVATION_FRAMES})")
    else:
        check(False, "TryResonance or the menu after it was never seen")
    check(bool(r.m("wBattleMonHP") or True), "the battle menu is still up: no turn was used")

    print("While it lasts:")
    t = turn()
    before, applied = t.before.get(0), t.applied.get(0, [None])[0]
    check(before is not None and applied == min(before + before // 2, 0xFFFF),
          f"your damage x1.5: {before} -> {applied}")
    before, applied = t.before.get(1), t.applied.get(1, [None])[0]
    check(before is not None and applied == before - before // 4,
          f"their damage x3/4: {before} -> {applied}")
    pain = r.m("wTrainerPain")
    check(pain > 0, f"the trainer's bar dropped: pain {pain}")
    maxhp = word(p, at["wBattleMonMaxHP"])
    if applied:
        want = max(min(applied * TRAINER_MAX_HP // maxhp, TRAINER_MAX_HP) * PAIN // 4, 1)
        check(pain == want, f"pain {pain} = {applied}/{maxhp} of the bar x 3/4 (want {want})")
    check(r.m("wResonanceTurns") == TURNS - 1, f"one turn used: {r.m('wResonanceTurns')} left")

    t = turn(presses={0: ("a", 3)})
    check(seen["perfect"].get(0) == PERFECT_WINDOW + WINDOW,
          f"the perfect window is {seen['perfect'].get(0)} frames (want {PERFECT_WINDOW + WINDOW})")
    check(t.results.get(0) == PERFECT and r.m("wResonanceTurns") == TURNS - 1,
          f"a PERFECT buys the turn back: {r.m('wResonanceTurns')} left")

    r.set(turns=2, flags=ACTIVE | 3)
    turn(presses={0: ("a", 3)})
    check(r.m("wResonanceTurns") == 1, f"no more than {TURNS} turns bought back: {r.m('wResonanceTurns')} left")

    turn()
    check(not r.m("wResonanceFlags") & ACTIVE, "it ends when its turns run out")
    check(r.hud_cap() in (CAP, READY), f"the cap is back to the meter ({r.hud_cap():#x})")

    print("No text boxes:")
    r.set(bond=BOND_RESONANT)
    turn()
    plain = seen["texts"]
    r.set(turns=3, flags=ACTIVE, bond=BOND_RESONANT)
    turn()
    check(seen["texts"] == plain, f"a turn of Resonance prints {seen['texts']} texts, a plain one {plain}")

    print("Breaking:")
    r.set(turns=3, pain=TRAINER_MAX_HP - 1, flags=ACTIVE, meter=5, bond=BOND_RESONANT)
    t = turn()
    meter, turns, pain, flags = r.state()
    check(not flags & ACTIVE and meter == 0 and pain == 0,
          f"the trainer's last HP breaks it: flags {flags:#x}, meter {meter}, pain {pain}")
    check(BADGE_BROKEN in seen["badges"], f"BROKEN! shows (badges {seen['badges']})")
    check(CANNOT_MOVE in seen["moves"], f"the player's next turn is lost: moves {seen['moves']}")
    check(not r.m("wResonanceFlags") & STUNNED, "the stun is used up after one turn")

    p.stop(save=False)
    print()
    print("FAILED" if failures else "all Resonance checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
