"""Check the Frenzy Snorlax: calm it, fight it, or be worn out.

Walking to Route 12's Snorlax is a long way for a scripted player, and nothing
in the Frenzy depends on the map, so the test calls Route12Frenzy directly from
the debug new game's overworld: at the top of OverworldLoop it fakes a call
into Bankswitch (hl = Route12Frenzy, b = its bank), with the loop as the
return address. The Dodge Phase's outcome is forced as dodgecheck.py does:
new hazards are held off (a clean round), or a hazard is put on the player's
tile every time (hit after hit).

  - three clean rounds, answering YES to keep calming: it is calmed, both
    EVENT_BEAT_ and EVENT_CALMED_ROUTE12_SNORLAX are set, and YES to "take it
    along" adds a level 30 Snorlax to the party;
  - the same, answering NO: a Rare Candy instead;
  - one round, then NO to keep calming: EVENT_FIGHT_ROUTE12_SNORLAX is set
    (the map script then starts the usual battle) and nothing else;
  - hit until the trainer's bar is dry: worn out, and no event at all;
  - every round the screen comes back as it was.

Usage:
    python test/frenzycheck.py [pokered_debug.gbc pokered_debug.sym]
"""
import sys

from actioncheck import check, failures
from debugbattle import boot_to_debug_menu, tap
from rominspect import load_symbols
from statuscheck import read_screen

SNORLAX, RARE_CANDY = 0x84, 0x28
EVENTS = {"FIGHT": 0x48E, "BEAT": 0x48F, "CALMED": 0x489}  # EVENT_*_ROUTE12_SNORLAX
ROCK = 0x7C  # a struck column ('│')
INTRO_TAPS = 300


def run(rom, sym, force, keep_calming, take_it):
    s = load_symbols(sym)
    A = lambda n: s[n][1]
    tilemap = A("wTileMap")
    p, at = boot_to_debug_menu(rom, sym)
    tap(p, "down", hold=8, release=24)
    tap(p, "a", hold=8, release=40)
    for n in range(INTRO_TAPS):
        tap(p, "b", hold=4, release=20)
        if n % 10 == 9:
            tap(p, "start", hold=6, release=40)
            if "ITEM" in "".join(read_screen(p, tilemap)):
                break
    tap(p, "b", hold=6, release=60)
    for _ in range(60):
        p.tick()

    m = p.memory
    for i in range(0, 2 * m[A("wNumBagItems")], 2):  # the debug bag's 99 leaves no room
        if m[A("wBagItems") + i] == RARE_CANDY:
            m[A("wBagItems") + i + 1] = 50
    state = {"called": False, "phases": 0, "restored": [], "screen": None}

    def enter(_):
        if state["called"]:
            return
        state["called"] = True
        r = p.register_file
        # push the loop's own address and "call" Bankswitch
        r.SP -= 2
        m[r.SP] = r.PC & 0xFF
        m[r.SP + 1] = r.PC >> 8
        bank, addr = s["Route12Frenzy"]
        r.HL = addr
        r.B = bank
        r.PC = s["Bankswitch"][1]

    def dodge_start(_):
        state["phases"] += 1
        state["shot_at"] = p.frame_count + 60
        state["screen"] = bytes(m[tilemap + i] for i in range(360))

    def check_hit(_):
        if force == "clean":
            m[A("wActionCommandFrame")] = 200  # the spawn timer: nothing new falls
        elif not m[A("wActionCommandBadgeTimer")]:
            y, x = m[A("wDodgeY")], m[A("wDodgeX")]
            m[tilemap + y * 20 + x] = ROCK

    p.hook_register(*s["OverworldLoop"], enter, None)
    p.hook_register(*s["DodgePhaseWithPattern"], dodge_start, None)
    p.hook_register(*s["CheckDodgeHit"], check_hit, None)
    beat = A("wEventFlags") + EVENTS["BEAT"] // 8, 1 << (EVENTS["BEAT"] % 8)

    def question(_):
        # after it is calmed the question is "take it along?"; before, "keep calming?"
        state["question"] = (p.frame_count, bool(m[beat[0]] & beat[1]))
    p.hook_register(*s["YesNoChoice"], question, None)

    answers = {"keep": keep_calming, "take": take_it}
    party_before = None
    for frame in range(12000):
        p.tick()
        if party_before is None and state["called"]:
            party_before = m[A("wPartyCount")]
        if "-v" in sys.argv and state.get("shot_at") and p.frame_count >= state["shot_at"]:
            state["shot_at"] = None
            p.screen.image.save("test/out/frenzy_arena.png")
        text = " ".join(read_screen(p, tilemap))
        if state["called"] and (state.get("question") or frame % 12 == 0):
            if state.get("question"):
                asked, is_join = state.pop("question")
                for _ in range(30):  # let the YES/NO box start taking input
                    p.tick()
                if not (answers["take"] if is_join else answers["keep"]):
                    tap(p, "down", hold=6, release=16)
                tap(p, "a", hold=6, release=40)
            elif "DODGE!" not in text:
                tap(p, "a", hold=4, release=8)
    flags = A("wEventFlags")
    events = {k: bool(m[flags + v // 8] & (1 << (v % 8))) for k, v in EVENTS.items()}
    party = [m[A("wPartySpecies") + i] for i in range(m[A("wPartyCount")])]
    # the debug party is full, so a Pokemon that joins goes to the PC box
    party += [m[A("wBoxSpecies") + i] for i in range(m[A("wBoxCount")])]
    bag = {m[A("wBagItems") + i]: m[A("wBagItems") + i + 1] for i in range(0, 2 * m[A("wNumBagItems")], 2)}
    p.stop(save=False)
    return state, events, party, bag


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else "pokered_debug.gbc"
    sym = sys.argv[2] if len(sys.argv) > 2 else "pokered_debug.sym"
    state, events, party, bag = run(rom, sym, "clean", True, True)
    check(state["phases"] == 3, f"three clean rounds calm it ({state['phases']} rounds)")
    check(events["BEAT"] and events["CALMED"] and not events["FIGHT"],
          f"calmed: the road is clear and the calm remembered ({events})")
    check(party.count(SNORLAX) == 1, f"YES: Snorlax joins (the box, the party being full): {[hex(x) for x in party]}")

    state, events, party, bag = run(rom, sym, "clean", True, False)
    check(events["CALMED"] and SNORLAX not in party and bag.get(RARE_CANDY, 0) == 51,
          f"NO: it stays and leaves a Rare Candy (50 -> {bag.get(RARE_CANDY)})")

    state, events, party, bag = run(rom, sym, "clean", False, True)
    check(state["phases"] == 1 and events["FIGHT"] and not events["BEAT"] and not events["CALMED"],
          f"NO to keep calming after one round: the usual battle is set up ({events})")

    state, events, party, bag = run(rom, sym, "hit", True, True)
    check(not any(events.values()), f"worn out: nothing is set ({events}, {state['phases']} rounds)")

    print()
    print("FAILED" if failures else "all Frenzy checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
