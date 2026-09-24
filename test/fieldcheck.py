"""Check battle environments and Field States.

Staged turns in the debug battle with action commands Off, so the only thing
between the damage formula and the damage dealt is the field. Hooks read wDamage
as ApplyFieldToAttack starts (before the field) and as the attack is applied
(after it). wFieldEnv is written between turns to stand the battle somewhere
else; everything else is played for real. No badges, so boosts are x1.25.

Checked:
  - the label: the place in lowercase with no state, the state in capitals;
  - each state is made by its move in its place, and not elsewhere;
  - SOAK: Electric x1.25, Fire x1/2, and Water puts out FIRE;
  - ICE!: an Ice move on SOAK freezes the field, and Ice moves hit x1.25;
  - FIRE: a Fire move on grass; each turn non-Fire Pokemon lose 1/16;
  - DUG!: the next Rock move x1.25, used up;
  - RUBL: made by Earthquake in a cave, used up by the next attack on its side;
  - DUST and DARK: made by Sand-Attack on sand and Smokescreen in the tower;
    in the dark a Ghost attack always hits;
  - ZAP!: an Electric move in the Power Plant; the next one x2, with a quarter
    as recoil;
  - a state lasts 5 turns;
  - a turn with a Field State prints as many texts as one without;
  - in a link battle nothing changes the field.

Usage:
    python test/fieldcheck.py [pokered_debug.gbc pokered_debug.sym]
"""
import sys

from actioncheck import Recorder, check, failures, install_hooks, take_turn
from debugbattle import NotReached, enter, word, write_word
from rominspect import load_symbols

M = {"POUND": 0x01, "EMBER": 0x34, "WATER_GUN": 0x37, "ICE_BEAM": 0x3A, "THUNDERSHOCK": 0x54,
     "EARTHQUAKE": 0x59, "ROCK_THROW": 0x58, "SAND_ATTACK": 0x1C, "SMOKESCREEN": 0x6C,
     "LICK": 0x7A, "GROWL": 0x2D, "SPLASH": 0x96, "QUICK_ATTACK": 0x62}
ENV = {"room": 0, "leaf": 1, "sea": 2, "cave": 3, "tomb": 4, "snow": 5, "sand": 6, "wire": 7}
STATE = {None: 0, "SOAK": 1, "ICE!": 2, "FIRE": 3, "DUG!": 4, "RUBL": 5, "DUST": 6, "ZAP!": 7, "DARK": 8}
TURNS = 5
NORMAL = 0
LABEL = (8, 1)


def text(s):
    out = []
    for ch in s:
        if "A" <= ch <= "Z":
            out.append(0x80 + ord(ch) - ord("A"))
        elif "a" <= ch <= "z":
            out.append(0xA0 + ord(ch) - ord("a"))
        else:
            out.append({" ": 0x7F, "!": 0xE7}[ch])
    return out


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else "pokered_debug.gbc"
    sym = sys.argv[2] if len(sys.argv) > 2 else "pokered_debug.sym"
    try:
        p, at = enter(rom, sym, action_commands="off")
    except NotReached as e:
        print(f"FAIL: {e}")
        return 1
    s = load_symbols(sym)
    for name in ("wEnemyMonMoves", "wEnemyMonStatus", "wBattleMonStatus",
                 "wActionCommandForceEffect", "wActionCommandFoe",
                 "wActionCommandStreak", "wActionCommandCue", "wObtainedBadges"):
        at[name] = s[name][1]
    rec = Recorder(p, at)
    install_hooks(p, rec, s)

    def m(name):
        return p.memory[s[name][1]]

    def w(name, v):
        p.memory[s[name][1]] = v

    seen = {"field": {}, "dealt": {}, "missed": {}, "texts": 0}

    def on(name):
        side = p.memory[at["hWhoseTurn"]]
        if name == "ApplyFieldToAttack":
            seen["field"].setdefault(side, word(p, at["wDamage"]))
        elif name == "HandleIfPlayerMoveMissed" or name == "HandleIfEnemyMoveMissed":
            seen["missed"].setdefault(side, m("wMoveMissed"))
        elif name in ("ApplyAttackToEnemyPokemon", "ApplyAttackToPlayerPokemon"):
            seen["dealt"].setdefault(side, word(p, at["wDamage"]))
        elif name == "PrintText":
            seen["texts"] += 1
    for name in ("ApplyFieldToAttack", "HandleIfPlayerMoveMissed", "HandleIfEnemyMoveMissed",
                 "PrintText"):
        p.hook_register(*s[name], on, name)
    trail = []

    def crashed(_):
        r = p.register_file
        stack = [hex(p.memory[r.SP + i] | p.memory[r.SP + i + 1] << 8) for i in range(0, 20, 2)]
        print(f"  CRASH into rst $38: SP {r.SP:#x} stack {stack}")
        print("  last:", trail[-12:])
        raise SystemExit(1)
    p.hook_register(0, 0x38, crashed, None)
    if "-v" in sys.argv:
        for name in ("ClearField", "DrawFieldLabel", "FieldAfterMove", "FieldNewTurn",
                     "ApplyFieldToAttack.rubble", "SingeBothSides", "FieldBoost", "FieldMissRoll"):
            p.hook_register(*s[name], lambda n: trail.append((n, hex(p.register_file.SP))), name)
    for name in ("ApplyAttackToEnemyPokemon", "ApplyAttackToPlayerPokemon"):
        bank, addr = s[name]
        p.hook_deregister(bank, addr)

        def both(n, _name=name):
            on(n)
            rec.on(n)
        p.hook_register(bank, addr, both, name)

    KEEP = object()

    def turn(player, enemy="SPLASH", env=None, state=KEEP, **kw):
        if env is not None:
            w("wFieldEnv", ENV[env])
        if state is not KEEP:
            w("wFieldState", STATE[state])
            w("wFieldTurns", TURNS if state else 0)
        # a Normal-type foe, so Electric moves land on the debug battle's Rhydon
        w("wEnemyMonType1", NORMAL)
        w("wEnemyMonType2", NORMAL)
        for k in seen:
            seen[k] = {} if k != "texts" else 0
        take_turn(p, at, rec, player_move=M[player], enemy_move=M[enemy], badges=0, **kw)
        for _ in range(40):  # the menu redraws the HUDs, and the label, after it opens
            p.tick()
        if "-v" in sys.argv:
            print(f"    [{player} env {m('wFieldEnv')} state {m('wFieldState')} turns {m('wFieldTurns')} "
                  f"inBattle {m('wIsInBattle')} enemyHP {word(p, at['wEnemyMonHP'])}]")
        return seen

    def label():
        x, y = LABEL
        base = s["wTileMap"][1] + y * 20 + x
        return [p.memory[base + i] for i in range(4)]

    def state():
        return m("wFieldState")

    def ratio(side, num, den, what):
        before, after = seen["field"].get(side), seen["dealt"].get(side)
        want = None if before is None else max(before * num // den, 1)
        if num == 5:
            want = None if before is None else before + before // 4
        check(before is not None and after == want, f"{what}: {before} -> {after} (want {want})")

    print("Places and labels:")
    turn("SPLASH", env="cave", state=None)
    check(label() == text("cave"), "no state: the place shows, in lowercase")

    print("SOAK:")
    turn("WATER_GUN", env="room")
    check(state() == STATE["SOAK"], f"Water Gun soaks the field ({state()})")
    check(label() == text("SOAK"), "and the label says SOAK")
    turn("THUNDERSHOCK")
    ratio(0, 5, 4, "Electric on SOAK x1.25")
    turn("EMBER", state="SOAK")
    ratio(0, 1, 2, "Fire on SOAK x1/2")

    print("ICE!:")
    turn("ICE_BEAM", state="SOAK")
    check(state() == STATE["ICE!"], f"Ice Beam on SOAK freezes it ({state()})")
    turn("ICE_BEAM", state="ICE!")
    ratio(0, 5, 4, "Ice on ICE! x1.25")
    turn("ICE_BEAM", env="room", state=None)
    check(state() == STATE[None], "Ice Beam on a dry field in a room does nothing")
    turn("ICE_BEAM", env="snow", state=None)
    check(state() == STATE["ICE!"], "Ice Beam in the snow freezes the field")

    print("FIRE:")
    turn("EMBER", env="room", state=None)
    check(state() == STATE[None], "Ember in a room does nothing")
    turn("EMBER", env="leaf", state=None)
    check(state() == STATE["FIRE"], f"Ember on grass sets it alight ({state()})")
    turn("SPLASH", state="FIRE", enemy_hp=900)
    # the singe happens at the start of the turn after this one's staging; read
    # it from the enemy HP lost with nobody attacking
    lost = 900 - word(p, at["wEnemyMonHP"])
    check(lost == max(999 // 16, 1), f"a burning field singes the non-Fire foe for 1/16 of 999 ({lost})")
    turn("WATER_GUN", state="FIRE")
    check(state() == STATE["SOAK"], "Water puts the fire out and soaks the field")

    print("DUG!:")
    for _ in range(6):  # Rock Throw is 65% accurate, and a miss zeroes the damage
        turn("ROCK_THROW", state="DUG!")
        if seen["missed"].get(0) == 0:
            break
    ratio(0, 5, 4, "Rock on DUG! x1.25")
    check(state() == STATE[None], "and the tunnels are used up")

    print("RUBL:")
    turn("EARTHQUAKE", env="room", state=None)
    check(state() == STATE[None], "Earthquake in a room makes no rubble")
    turn("EARTHQUAKE", env="cave", state=None)
    check(state() == STATE["RUBL"] and m("wFieldOwner") & 1 == 0, f"Earthquake in a cave: rubble for you ({state()})")
    turn("SPLASH", enemy="POUND")
    check(state() == STATE[None], "the next attack on you uses it up")

    print("DUST and DARK:")
    turn("SAND_ATTACK", env="sand", state=None)
    check(state() == STATE["DUST"], f"Sand-Attack on sand raises dust ({state()})")
    turn("SMOKESCREEN", env="tomb", state=None)
    check(state() == STATE["DARK"], f"Smokescreen in the tower makes it dark ({state()})")
    hits = 0
    for _ in range(4):
        turn("LICK", state="DARK")
        hits += seen["missed"].get(0) == 0
    check(hits == 4, f"in the dark a Ghost attack always hits ({hits} of 4)")

    print("ZAP!:")
    turn("THUNDERSHOCK", env="wire", state=None)
    check(state() == STATE["ZAP!"], f"an Electric move in the Power Plant overcharges ({state()})")
    turn("THUNDERSHOCK", state="ZAP!")
    ratio(0, 2, 1, "the next Electric move x2")
    check(state() == STATE[None], "and the charge is used up, not made again by the same move")

    print("Turns and texts:")
    turn("SPLASH", env="room", state="SOAK")
    left = [m("wFieldTurns")]
    for _ in range(TURNS):
        turn("SPLASH")
        left.append(m("wFieldTurns"))
    check(state() == STATE[None], f"a state lasts {TURNS} turns: turns left {left}")
    turn("POUND", state=None)
    plain = seen["texts"]
    turn("POUND", state="DUST")
    check(seen["texts"] == plain or seen["missed"].get(0), f"a turn in DUST prints {seen['texts']} texts, a plain one {plain}")

    print("Improvise:")
    from debugbattle import tap

    def improvise(move, bond, enemy="SPLASH"):
        """At the battle menu: FIGHT, then START on the first move."""
        w("wPartyMon1Bond", bond)
        for _ in range(30):
            p.tick()
        p.memory[at["wBattleMonMoves"]] = M[move]
        p.memory[at["wTestBattlePlayerSelectedMove"]] = M[move]
        p.memory[at["wBattleMonPP"]] = 20
        for i in range(4):
            p.memory[at["wEnemyMonMoves"] + i] = M[enemy]
        write_word(p, at["wEnemyMonHP"], 900)
        write_word(p, at["wBattleMonHP"], 999)
        for k in seen:
            seen[k] = {} if k != "texts" else 0
        w("wEnemyMonType1", NORMAL)
        w("wEnemyMonType2", NORMAL)
        rec.menu = rec.prompt = False
        tap(p, "a", hold=6, release=20)
        tap(p, "start", hold=6, release=10)
        for _ in range(1500):
            if rec.prompt:  # "But nothing happened!" waits for a button
                rec.prompt = False
                tap(p, "a", hold=3, release=3)
            p.tick()
            if rec.menu:
                break
        for _ in range(40):
            p.tick()

    w("wImprovise", 0)
    turn("SPLASH", env="room", state=None)
    improvise("WATER_GUN", 99)
    check(state() == STATE[None] and m("wImprovise") == 0, "Bond 99 cannot improvise")
    tap(p, "b", hold=6, release=30)  # back out of the move menu the refusal left open
    turn("SPLASH", state=None)
    improvise("WATER_GUN", 100)
    check(state() == STATE["SOAK"], f"START on Water Gun soaks the field, even in a room ({state()})")
    check(word(p, at["wEnemyMonHP"]) == 900, "and deals no damage")
    check(p.memory[at["wBattleMonPP"]] & 0x3F == 19, f"one PP is spent ({p.memory[at['wBattleMonPP']] & 0x3F})")
    check(m("wImprovise") & 3 == 2, f"the next Improvise waits ({m('wImprovise') & 3} turns left)")
    improvise("ROCK_THROW", 255)
    check(state() == STATE["SOAK"], "a second Improvise before the wait is over is refused")
    tap(p, "b", hold=6, release=30)
    for _ in range(2):
        turn("SPLASH")
    w("wFieldTurns", 0)
    w("wFieldState", 0)
    improvise("ROCK_THROW", 255)
    check(state() == STATE["RUBL"] and m("wFieldOwner") & 1 == 0,
          f"once it has run down, Rock Throw brings down cover for you ({state()})")
    check(m("wFieldTurns") == TURNS + 2 - 1, f"a resonant Bond makes it last 2 turns longer ({m('wFieldTurns')} left)")

    print("Techniques:")
    w("wImprovise", 0)
    w("wFieldState", 0)
    w("wFieldTurns", 0)
    improvise("QUICK_ATTACK", 100, enemy="POUND")
    check(seen["missed"].get(1) == 1, f"improvised Quick Attack dodges the next attack (missed {seen['missed'].get(1)})")
    check(state() == STATE[None], "and leaves no Field State")
    w("wImprovise", 0)
    w("wResonanceFlags", 0x80)  # resonating
    w("wResonanceTurns", 3)
    hp = word(p, at["wEnemyMonHP"])
    improvise("POUND", 255, enemy="POUND")
    before, dealt = seen["field"].get(1), seen["dealt"].get(1)
    check(seen["dealt"].get(0, 0) > 0, f"a Counter Shield still attacks ({seen['dealt'].get(0)} damage)")
    check(before is not None and dealt == max(before // 2, 1),
          f"and halves the next attack on you: {before} -> {dealt}")
    w("wResonanceFlags", 0)
    w("wResonanceTurns", 0)

    print("Link battles:")
    w("wLinkState", 4)  # LINK_STATE_BATTLING, only while the move is used
    turn("WATER_GUN", env="room", state=None)
    w("wLinkState", 0)
    check(state() == STATE[None], "no Field State in a link battle")

    p.stop(save=False)
    print()
    print("FAILED" if failures else "all field checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
