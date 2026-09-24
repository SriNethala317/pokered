"""Action command edge cases the staged check (actioncheck.py) and the random
wild-battle fuzz cannot reach: real trainer battles, the Oak tutorial text,
Substitute around a counter, link battles, and the result badge surviving onto
other screens.

Trainer battles are made from the debug build's test battle: a hook on
InitOpponent swaps the wild Rhydon for a real trainer party, so the battle
runs the genuine trainer code path (wIsInBattle 2, wTrainerClass, sending out
the next Pokemon, the start-of-battle text).

Usage:
    python test/actionedge.py [rom sym [shot-prefix [test,test...]]]
"""
import sys

from debugbattle import boot_to_debug_menu, tap, word, write_word
from rominspect import load_symbols

POUND, GROWL = 0x01, 0x2D
LEAD_IN, WINDOW, CLOSED, BADGE = 1, 2, 3, 4
NONE, EARLY, GOOD, PERFECT = 0, 1, 2, 3
TIMED = 1 << 1
B_FOE_GREAT, B_FOE_BRACED, B_COUNTER = 7, 8, 5
OPP_ID_OFFSET = 200
RIVAL1, BROCK = 0x19, 0x22
LINK_STATE_BATTLING = 4
SHIFT_OFF = 1 << 6  # wOptions: battle style SET, no "switch?" prompt
EVENT_BATTLED_RIVAL_IN_OAKS_LAB = 35
HAS_SUBSTITUTE_UP = 1 << 4
BADGE_STRINGS = ["TOO SOON", "GREAT!", "PERFECT!", "BRACED!", "COUNTER!",
                 "PERFECT", "FOE GREAT", "FOE BRACED"]

failures = []


def check(ok, msg):
    print(("  ok    " if ok else "  FAIL  ") + msg)
    if not ok:
        failures.append(msg)


def encode(s):
    out = []
    for ch in s:
        if "A" <= ch <= "Z":
            out.append(0x80 + ord(ch) - ord("A"))
        elif ch == " ":
            out.append(0x7F)
        elif ch == "!":
            out.append(0xE7)
        else:
            raise ValueError(ch)
    return out


class Battle:
    HOOKS = ("DisplayBattleMenu", "WaitForTextScrollButtonPress", "ArmActionCommand",
             "ApplyActionCommand", "ApplyAttackToEnemyPokemon",
             "ApplyAttackToPlayerPokemon", "PrintText", "InitOpponent")

    def __init__(self, rom, sym_path, opponent=None, trainer_no=1, options=None,
                 event_battled_rival=False):
        self.sym = load_symbols(sym_path)
        self.p, _ = boot_to_debug_menu(rom, sym_path)
        self.opponent = opponent
        self.trainer_no = trainer_no
        self.options = options
        self.event_battled_rival = event_battled_rival
        self.tutorial = 0
        self.menu = self.prompt = False
        self.link_on_arm = False
        self.reset()
        for name in self.HOOKS:
            b, a = self.sym[name]
            self.p.hook_register(b, a, self.on, name)
        tap(self.p, "a", hold=10, release=0)
        for _ in range(150):
            if word(self.p, self.a("wBattleMonHP")) and self.menu:
                break
            tap(self.p, "b", hold=6, release=24)
        self.tick(60)

    def a(self, name):
        return self.sym[name][1]

    def m(self, name, off=0):
        return self.p.memory[self.a(name) + off]

    def w(self, name, v):
        self.p.memory[self.a(name)] = v

    def tick(self, n=1):
        for _ in range(n):
            self.p.tick()

    def reset(self):
        self.arms = []       # (side, wLinkState) at each ArmActionCommand
        self.before = {}     # side -> damage entering ApplyActionCommand
        self.dealt = {}      # side -> damage entering ApplyAttackTo*
        self.result = {}
        self.badge = {}      # side -> wActionCommandResult as the attack lands
        self.foe = {}
        self.enemy_hp = {}   # side -> [enemy HP entering Apply, entering ApplyAttack]
        self.sub_hp = {}

    def on(self, name):
        p = self.p
        side = self.m("hWhoseTurn")
        if name == "InitOpponent":
            # the debug menu wrote wOptions itself; ours goes in afterwards
            if self.options is not None:
                self.w("wOptions", self.options)
            if self.opponent is not None:
                self.w("wCurOpponent", self.opponent)
                self.w("wTrainerNo", self.trainer_no)
            flags = self.a("wEventFlags") + EVENT_BATTLED_RIVAL_IN_OAKS_LAB // 8
            bit = 1 << (EVENT_BATTLED_RIVAL_IN_OAKS_LAB % 8)
            if self.event_battled_rival:
                p.memory[flags] |= bit
            else:
                p.memory[flags] &= ~bit
        elif name == "DisplayBattleMenu":
            self.menu = True
        elif name == "WaitForTextScrollButtonPress":
            self.prompt = True
        elif name == "PrintText":
            b, addr = self.sym["ActionCommandTutorialText"]
            if p.register_file.HL == addr and self.m("hLoadedROMBank") == b:
                self.tutorial += 1
        elif name == "ArmActionCommand":
            if self.link_on_arm:
                self.w("wLinkState", LINK_STATE_BATTLING)
            self.arms.append((side, self.m("wLinkState")))
        elif name == "ApplyActionCommand":
            if self.link_on_arm:
                self.w("wLinkState", 0)
            if side not in self.before:
                self.before[side] = word(p, self.a("wDamage"))
                self.result[side] = self.m("wActionCommandResult")
                self.foe[side] = self.m("wActionCommandFoe")
                self.enemy_hp[side] = [word(p, self.a("wEnemyMonHP")), None]
                self.sub_hp[side] = self.m("wEnemySubstituteHP")
        elif name.startswith("ApplyAttackTo"):
            if side not in self.dealt:
                self.dealt[side] = word(p, self.a("wDamage"))
                self.badge[side] = self.m("wActionCommandResult")
                if side in self.enemy_hp:
                    self.enemy_hp[side][1] = word(p, self.a("wEnemyMonHP"))

    def row4(self, base="wTileMap"):
        start = self.a(base) + 4 * 20 + 1
        return [self.p.memory[start + i] for i in range(10)]

    def badge_on_screen(self, base="wTileMap"):
        row = self.row4(base)
        return next((s for s in BADGE_STRINGS
                     if row[:len(encode(s))] == encode(s)), None)

    def wait_menu(self, limit=4000):
        for _ in range(limit):
            if self.menu or not self.m("wIsInBattle"):
                return self.menu
            if self.prompt:
                self.prompt = False
                tap(self.p, "b", hold=3, release=3)
                continue
            self.tick()
        return False

    def stage(self, player_move=POUND, enemy_move=POUND, player_fast=True,
              badges=0b111, enemy_hp=900, player_hp=999):
        p = self.p
        write_word(p, self.a("wEnemyMonMaxHP"), 999)
        write_word(p, self.a("wEnemyMonHP"), enemy_hp)
        write_word(p, self.a("wBattleMonMaxHP"), 999)
        write_word(p, self.a("wBattleMonHP"), player_hp)
        self.w("wTestBattlePlayerSelectedMove", player_move)
        self.w("wBattleMonMoves", player_move)
        self.w("wBattleMonPP", 40)
        for i in range(4):
            p.memory[self.a("wEnemyMonMoves") + i] = enemy_move
        write_word(p, self.a("wBattleMonSpeed"), 900 if player_fast else 1)
        write_word(p, self.a("wEnemyMonSpeed"), 1 if player_fast else 900)
        write_word(p, self.a("wBattleMonAttack"), 400)
        write_word(p, self.a("wEnemyMonAttack"), 400)
        self.w("wObtainedBadges", badges)
        self.w("wActionCommandStreak", 0)
        self.w("wEnemyMonStatus", 0)
        self.w("wBattleMonStatus", 0)

    def turn(self, presses=None, limit=2500, stage=None, during=None, wait=True):
        """presses: side -> frames after that side's first cue to press
        (A for side 0, B for side 1). Returns once the battle menu is back."""
        presses = dict(presses or {})
        if wait:
            if not self.wait_menu():
                return False
            self.tick(30)
        if stage:
            stage()
        self.menu = False
        self.reset()
        tap(self.p, "a", hold=6, release=20)
        tap(self.p, "a", hold=6, release=0)
        cue = {}
        held = None
        for f in range(limit):
            st = self.m("wActionCommandState")
            side = self.m("hWhoseTurn")
            if st == WINDOW and side not in cue:
                cue[side] = f
            if held and f >= held:
                self.p.button_release("a")
                self.p.button_release("b")
                held = None
            if side in presses and side in cue and f == cue[side] + presses[side]:
                self.p.button_press("a" if side == 0 else "b")
                held = f + 3
                del presses[side]
            if during:
                during(self, f)
            if self.prompt and st not in (LEAD_IN, WINDOW) and held is None:
                self.prompt = False
                self.p.button_press("b")
                held = f + 3
            self.tick()
            if self.menu or not self.m("wIsInBattle"):
                break
        self.p.button_release("a")
        self.p.button_release("b")
        return True


def test_tutorial(rom, sym):
    print("Oak's tutorial text (trainer battle start):")
    b = Battle(rom, sym, opponent=OPP_ID_OFFSET + RIVAL1, options=0x03 | SHIFT_OFF)
    check(b.m("wIsInBattle") == 2, f"rival battle is a trainer battle ({b.m('wIsInBattle')})")
    check(b.tutorial == 1, f"shown once with the event unset and the option On ({b.tutorial})")
    b.p.stop(save=False)
    b = Battle(rom, sym, opponent=OPP_ID_OFFSET + RIVAL1, options=0x03 | SHIFT_OFF | 0b100000)
    check(b.tutorial == 0, f"not shown with the option Off ({b.tutorial})")
    b.p.stop(save=False)
    b = Battle(rom, sym, opponent=OPP_ID_OFFSET + RIVAL1, options=0x03 | SHIFT_OFF,
               event_battled_rival=True)
    check(b.tutorial == 0, f"not shown once the rival has been battled ({b.tutorial})")
    b.p.stop(save=False)
    b = Battle(rom, sym, options=0x03 | SHIFT_OFF)
    check(b.tutorial == 0, f"not shown in a wild battle ({b.tutorial})")
    b.p.stop(save=False)


def test_trainer(rom, sym, shot):
    print("Real trainer battle (Brock, 8 badges):")
    b = Battle(rom, sym, opponent=OPP_ID_OFFSET + BROCK, options=0x03 | SHIFT_OFF,
               event_battled_rival=True)
    check(b.m("wIsInBattle") == 2 and b.m("wTrainerClass") == BROCK,
          f"in a trainer battle against class {b.m('wTrainerClass'):#x}")
    timed = {0: 0, 1: 0}
    n = bad = 0
    for i in range(24):
        # a GOOD press on both halves; 7-8 badges is 50% plus the 15% boss bonus
        if not b.turn(presses={0: 16, 1: 16},
                      stage=lambda: b.stage(badges=0xFF, player_fast=True)):
            break
        for side in (0, 1):
            if side not in b.before or side not in b.dealt:
                continue
            before, dealt = b.before[side], b.dealt[side]
            is_timed = b.foe[side] & TIMED
            timed[side] += bool(is_timed)
            if b.result[side] != GOOD:
                continue
            if side == 0:
                want = before if is_timed else min(before + before // 2, 0xFFFF)
                want_badge = B_FOE_BRACED if is_timed else 2
            else:
                boost = before + before // 2 if is_timed else before
                want = max(boost // 2, 1)
                want_badge = 4
            if dealt != want or b.badge[side] != want_badge:
                bad += 1
                check(False, f"turn {i} side {side} foe {b.foe[side]}: {before}->{dealt} "
                             f"(want {want}), badge {b.badge[side]} (want {want_badge})")
        n += 1
        if i == 3 and shot:
            b.p.screen.image.save(f"{shot}_trainer.png")
    check(n >= 20, f"played {n} trainer turns")
    check(bad == 0, "every GOOD result scaled as documented, with FOE BRACED / FOE GREAT")
    check(timed[0] > 3 and timed[1] > 3,
          f"the boss timed attacks: yours {timed[0]}, theirs {timed[1]} of {n}")
    b.p.stop(save=False)


def test_trainer_sendout(rom, sym, shot):
    print("Trainer's Pokemon fainting with a badge up, next one sent out:")
    b = Battle(rom, sym, opponent=OPP_ID_OFFSET + BROCK, options=0x03 | SHIFT_OFF,
               event_battled_rival=True)
    first = b.m("wEnemyMonPartyPos")
    b.turn(presses={0: 3}, stage=lambda: b.stage(enemy_hp=1, enemy_move=GROWL))
    check(b.badge.get(0) in (2, 3), f"the knockout showed a badge ({b.badge.get(0)})")
    b.wait_menu()
    b.tick(200)
    if shot:
        b.p.screen.image.save(f"{shot}_sendout.png")
    check(b.m("wEnemyMonPartyPos") != first, "Brock sent out his next Pokemon")
    st = b.m("wActionCommandState")
    check(b.badge_on_screen() is None or st == BADGE,
          f"no orphaned badge on screen after the send-out ({b.badge_on_screen()}, state {st})")
    check(b.badge_on_screen("wTileMapBackup") is None or st == BADGE,
          f"no orphaned badge in wTileMapBackup ({b.badge_on_screen('wTileMapBackup')})")
    b.p.stop(save=False)


def test_counter(rom, sym):
    print("Counter against a Pokemon behind a Substitute:")
    b = Battle(rom, sym, options=0x03 | SHIFT_OFF)

    def sub():
        b.stage(player_move=GROWL, enemy_move=POUND, player_fast=True)
        b.p.memory[b.a("wEnemyBattleStatus2")] |= HAS_SUBSTITUTE_UP
        b.w("wEnemySubstituteHP", 50)

    for _ in range(4):
        b.turn(presses={1: 3}, stage=sub)
        if b.result.get(1) == PERFECT:
            break
    hp0, hp1 = b.enemy_hp.get(1, [None, None])
    check(b.result.get(1) == PERFECT, f"perfect brace landed ({b.result.get(1)})")
    print(f"    enemy HP {hp0} -> {hp1}, substitute HP {b.sub_hp.get(1)} -> {b.m('wEnemySubstituteHP')}")
    check(hp0 == hp1, "the counter does not go through the attacker's Substitute")
    b.p.stop(save=False)


def test_link(rom, sym):
    print("Link battle: no window at all:")
    b = Battle(rom, sym, options=0x03 | SHIFT_OFF)
    b.link_on_arm = True
    b.turn(presses={0: 3, 1: 3}, stage=lambda: b.stage())
    check(b.arms and all(ls == LINK_STATE_BATTLING for _, ls in b.arms), f"armed in link state {b.arms}")
    check(all(b.dealt.get(s) == b.before.get(s) for s in (0, 1)),
          f"damage untouched: {b.before} -> {b.dealt}")
    check(all(b.result.get(s) == 0 for s in (0, 1)), f"no result recorded: {b.result}")
    b.p.stop(save=False)


# --- trainer-battle fuzz -----------------------------------------------------

FUZZ_MOVES = [0x01, 0x0C, 0x13, 0x18, 0x23, 0x25, 0x26, 0x29, 0x2A, 0x2C, 0x2D, 0x35,
              0x39, 0x3A, 0x3C, 0x3E, 0x3F, 0x44, 0x45, 0x48, 0x4B, 0x4C, 0x52, 0x53,
              0x55, 0x59, 0x5B, 0x5E, 0x75, 0x76, 0x77, 0x7C, 0x81, 0x88, 0x8A,
              0x8C, 0x8F, 0x9D, 0xA2, 0xA3, 0xA4, 0xA5, 0x5D, 0x37, 0x42, 0x34, 0x33]
SELF_KO = (0x99, 0x78)
# Rage is left out: it locks the user in until the battle ends, and against the
# fuzz's 900 HP targets that can outlast any wait for the battle menu. Thrash,
# Wrap, charging moves and Bide also skip the menu for a few turns, which is why
# arming is counted per move executed rather than per battle menu.


def expected(side, before, result, foe, streak):
    def boost(d):
        return min(d + d // 2, 0xFFFF)
    if side == 0:
        if result == PERFECT:
            return min(before * 2, 0xFFFF) if streak >= 3 else boost(before)
        if result == GOOD:
            return before if foe & TIMED else boost(before)
        return before
    d = boost(before) if foe & TIMED else before
    if result >= GOOD:
        return max(d // 2, 1)
    return d


def test_fuzz(rom, sym, shot, turns=250, seed=1):
    import random
    rng = random.Random(seed)
    print(f"Trainer fuzz ({turns} turns, seed {seed}):")
    # Lance (boss), Brock (boss), a Youngster, the champion
    trainers = [OPP_ID_OFFSET + 0x2F, OPP_ID_OFFSET + BROCK, OPP_ID_OFFSET + 0x01,
                OPP_ID_OFFSET + 0x2B]
    b = Battle(rom, sym, opponent=rng.choice(trainers), options=0x03 | SHIFT_OFF,
               event_battled_rival=True)
    ext = {"streak": {}, "apply_state": {}, "arm_count": {}, "most_arms": {}}
    orig_on = b.on

    def on(name):
        side = b.m("hWhoseTurn")
        if name == "ApplyActionCommand" and side not in b.before:
            ext["streak"][side] = b.m("wActionCommandStreak")
            ext["apply_state"][side] = b.m("wActionCommandState")
        if name == "ArmActionCommand":
            ext["arm_count"][side] = ext["arm_count"].get(side, 0) + 1
            ext["most_arms"][side] = max(ext["most_arms"].get(side, 0), ext["arm_count"][side])
        if name in ("ExecutePlayerMove", "ExecuteEnemyMove"):
            ext["arm_count"][0 if name == "ExecutePlayerMove" else 1] = 0
        if name == "InitOpponent":
            b.opponent = rng.choice(trainers)
        orig_on(name)
    for name in Battle.HOOKS:
        bank, addr = b.sym[name]
        b.p.hook_deregister(bank, addr)
        b.p.hook_register(bank, addr, on, name)
    for name in ("ExecutePlayerMove", "ExecuteEnemyMove"):
        if name not in Battle.HOOKS:
            b.p.hook_register(*b.sym[name], on, name)

    problems = []

    def problem(msg):
        problems.append(msg)
        print("  FAIL  " + msg)

    def menu_invariants(tag):
        st = b.m("wActionCommandState")
        for base in ("wTileMap", "wTileMapBackup"):
            s = b.badge_on_screen(base)
            if s is not None and st != BADGE:
                problem(f"{tag}: orphaned badge {s!r} in {base}, state {st}")
                if shot:
                    b.p.screen.image.save(f"{shot}_orphan_{len(problems)}.png")
        if st in (LEAD_IN, WINDOW, CLOSED):
            problem(f"{tag}: window state {st} left over at the battle menu")

    played = 0
    for t in range(turns):
        if not b.wait_menu(limit=6000):
            # battle over: TestBattle starts the next one
            for _ in range(200):
                if b.m("wIsInBattle") and b.menu:
                    break
                tap(b.p, "b", hold=6, release=24)
            if not b.menu:
                problem(f"turn {t}: never got back to a battle menu")
                break
        b.tick(40)
        menu_invariants(f"turn {t} menu")
        # sometimes look at the party first, with the badge maybe still up
        if rng.random() < 0.25:
            tap(b.p, "right", hold=6, release=10)
            tap(b.p, "a", hold=6, release=10)
            b.tick(rng.randint(20, 120))
            for _ in range(rng.randint(0, 6)):
                tap(b.p, "up", hold=4, release=8)
            tap(b.p, "b", hold=6, release=10)
            b.menu = False
            b.wait_menu(limit=600)
            b.tick(40)
            menu_invariants(f"turn {t} after party menu")
        tap(b.p, "up", hold=6, release=10)
        tap(b.p, "left", hold=6, release=10)
        pm = rng.choice(FUZZ_MOVES)
        em = rng.choice(FUZZ_MOVES + list(SELF_KO))
        badges = rng.choice([0, 1, 3, 0x0F, 0x3F, 0xFF])
        ehp = rng.choice([900, 900, 900, 60, 20, 1])
        mode = rng.choice([0, 0, 0, 0b010000])
        fast = rng.random() < 0.5
        timing = {s: rng.choice([None, 0, 3, 10, 16, 22, 40]) for s in (0, 1)}
        presses = {s: v for s, v in timing.items() if v is not None}

        def stage_it():
            b.stage(player_move=pm, enemy_move=em, player_fast=fast,
                    badges=badges, enemy_hp=ehp)
            write_word(b.p, b.a("wEnemyMonAttack"), 150)
            b.w("wOptions", (b.m("wOptions") & ~0b110000) | mode)
        ext["streak"].clear()
        ext["apply_state"].clear()
        ext["arm_count"].clear()
        ext["most_arms"].clear()
        b.menu = False
        if not b.turn(presses=presses, stage=stage_it, limit=4000, wait=False):
            problem(f"turn {t}: turn did not start")
            continue
        played += 1
        for side in (0, 1):
            if ext["most_arms"].get(side, 0) > 1:
                problem(f"turn {t} side {side}: armed {ext['most_arms'][side]} times in one move "
                        f"(moves {pm:#x}/{em:#x})")
            ast = ext["apply_state"].get(side)
            if ast in (LEAD_IN, WINDOW):
                problem(f"turn {t} side {side}: applied with the window open (state {ast}, "
                        f"moves {pm:#x}/{em:#x})")
            if ast == CLOSED and side in b.dealt:
                want = expected(side, b.before[side], b.result[side], b.foe[side],
                                ext["streak"].get(side, 0))
                if b.dealt[side] != want:
                    problem(f"turn {t} side {side}: {b.before[side]} -> {b.dealt[side]}, "
                            f"want {want} (result {b.result[side]}, foe {b.foe[side]}, "
                            f"moves {pm:#x}/{em:#x})")
                if side == 1 and b.result[side] == PERFECT and b.enemy_hp[side][1] is not None:
                    h0, h1 = b.enemy_hp[side]
                    if h1 == 0 or h1 > h0:
                        problem(f"turn {t}: counter took the attacker from {h0} to {h1} HP")
    check(played >= turns * 0.9, f"played {played} of {turns} turns")
    check(not problems, f"{len(problems)} invariant violations")
    b.p.stop(save=False)


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else "pokered_debug.gbc"
    sym = sys.argv[2] if len(sys.argv) > 2 else "pokered_debug.sym"
    shot = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else None
    only = sys.argv[4].split(",") if len(sys.argv) > 4 else None
    tests = {"tutorial": lambda: test_tutorial(rom, sym),
             "trainer": lambda: test_trainer(rom, sym, shot),
             "sendout": lambda: test_trainer_sendout(rom, sym, shot),
             "counter": lambda: test_counter(rom, sym),
             "link": lambda: test_link(rom, sym),
             "fuzz": lambda: test_fuzz(rom, sym, shot)}
    for name, fn in tests.items():
        if only is None or name in only:
            fn()
    print(f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
