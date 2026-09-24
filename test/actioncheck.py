"""Prove the action command window scales damage as designed, and stays short.

Each staged turn has the player attack first and the opponent attack back with
the same move, so both halves of the window are exercised: A on your own attack
and B on the opponent's. Presses are timed from the moment the cue appears,
which is when wActionCommandState moves from the lead-in to the window.

The move's type picks the input, so each pattern is staged with a move of a
matching type: Pound taps, Confusion snaps, Water Gun holds, Submission asks
for three presses and Ember for a press on each of two cues.

The badge count sets the difficulty (ActionRamp), so every turn writes
wObtainedBadges first. Most checks run with three badges, the first row where
every input is in use and nothing feints. The ramp checks then walk every row.
The debug battle is a wild one, so a trainer's timing is either forced by
writing wActionCommandFoe during the lead-in, or rolled for real by making the
battle look like a trainer battle for the moment the attack is armed.

The readings come from pyboy hooks rather than from watching memory between
frames. ApplyActionCommand's entry sees the damage before any bonus, and
ApplyAttackTo*Pokemon's entry sees the damage that is actually dealt, so the
ratio between the two is exact and does not depend on how a frame happens to
line up with the code.

The battle-length budget is measured the same way: the frames between
FinishActionCommand being entered and the move's impact animation starting are
exactly the frames the window added to that attack. It may never exceed 20.

Usage:
    python test/actioncheck.py pokeblue_debug.gbc pokeblue_debug.sym [shot-prefix]
"""
import sys

from debugbattle import NotReached, enter, set_action_commands, tap, word, write_word
from rominspect import load_symbols

POUND = 0x01
SUBMISSION = 0x42
DOUBLESLAP = 0x03
GROWL = 0x2D
EMBER = 0x34
WATER_GUN = 0x37
CONFUSION = 0x5D

# wActionCommandState / wActionCommandResult, see constants/battle_constants.asm
LEAD_IN, WINDOW, BADGE = 1, 2, 4
NONE, EARLY, GOOD, PERFECT = 0, 1, 2, 3
# wActionCommandForceEffect
ROLL, FORCED, BLOCKED = 0, 1, 2
# wActionCommandFoe bits, and the badges ApplyActionCommand leaves behind
FEINT, TIMED = 1 << 0, 1 << 1
BADGE_DOUBLE, BADGE_FOE_GREAT, BADGE_FOE_BRACED = 6, 7, 8
CUE_FEINT = 9

# ActionRamp, one row per two badges: perfect and good windows, the patterns
# in use, then the trainer-timing and feint chances out of 256.
TAP, SNAP, HOLD, RAPID, DOUBLE = range(5)
EVERY = (1 << 5) - 1
RAMP = [
    (18, 30, 1 << TAP, 0, 0),
    (16, 26, (1 << TAP) | (1 << SNAP) | (1 << RAPID), 25, 0),
    (15, 24, EVERY, 51, 0),
    (14, 21, EVERY, 89, 43),
    (13, 19, EVERY, 127, 63),
]
SNAP_PERFECT, SNAP_GOOD = 3, 6
BADGES = [0, 0b1, 0b111, 0b11111, 0b1111111]  # one badge count for each row
DEFAULT_BADGES = BADGES[2]
BRN = 1 << 4
CONFUSED = 1 << 7  # in w*BattleStatus1

ATTACK = 600
MAX_EXTRA_FRAMES = 20
TURN_FRAMES = 1500
BIT_BATTLE_ANIMATION = 1 << 7

HOOKED = (
    "DisplayBattleMenu",
    "WaitForTextScrollButtonPress",
    "ApplyActionCommand",
    "ApplyAttackToEnemyPokemon",
    "ApplyAttackToPlayerPokemon",
    "FinishActionCommand",
    "PlayApplyingAttackAnimation",
    "ArmActionCommand",
    "ActionCommandTick",
)


class Recorder:
    """Collects what the hooks see during one turn."""

    def __init__(self, p, at):
        self.p = p
        self.at = at
        self.frame = 0
        self.reset()

    trainer = False  # arm every attack as if in a trainer battle
    _restore = False

    def reset(self):
        self.menu = False
        self.prompt = False
        self.before = {}    # side -> damage entering ApplyActionCommand
        self.applied = {}   # side -> list of damage values dealt, one per hit
        self.hp_before = {}  # side -> enemy HP entering ApplyActionCommand
        self.hp_after = {}   # side -> enemy HP once the attack is being dealt
        self.results = {}   # side -> wActionCommandResult entering Apply
        self.states = {}    # side -> wActionCommandState entering Apply
        self.force = {}     # side -> wActionCommandForceEffect as it is dealt
        self.extra = []     # frames each window added to an attack
        self.foe = {}       # side -> wActionCommandFoe entering Apply
        self.feinted = set()  # sides that showed a feint
        self.badge = {}     # side -> the badge Apply left in wActionCommandResult
        self._finish = None
        self._applying = None

    def side(self):
        return self.p.memory[self.at["hWhoseTurn"]]

    def on(self, name):
        p, at = self.p, self.at
        if self._applying is not None and name != "ApplyActionCommand":
            # the badge is set by the time anything else runs
            self.badge.setdefault(self._applying, p.memory[at["wActionCommandResult"]])
            self._applying = None
        # A trainer battle only for as long as it takes to arm the attack:
        # anything after it, from the window's first frame on, sees a wild one.
        if self._restore and name != "ArmActionCommand":
            p.memory[at["wIsInBattle"]] = 1
            self._restore = False
        if name == "ArmActionCommand":
            if self.trainer and p.memory[at["wIsInBattle"]] == 1:
                p.memory[at["wIsInBattle"]] = 2
                self._restore = True
        elif name == "DisplayBattleMenu":
            self.menu = True
        elif name == "WaitForTextScrollButtonPress":
            self.prompt = True
        elif name == "ApplyActionCommand":
            s = self.side()
            # Only the first entry of a turn half matters; multi-hit moves come
            # back here for every hit with nothing armed.
            if s not in self.before:
                self.before[s] = word(p, at["wDamage"])
                self.hp_before[s] = word(p, at["wEnemyMonHP"])
                self.results[s] = p.memory[at["wActionCommandResult"]]
                self.states[s] = p.memory[at["wActionCommandState"]]
                self.foe[s] = p.memory[at["wActionCommandFoe"]]
                self._applying = s
        elif name in ("ApplyAttackToEnemyPokemon", "ApplyAttackToPlayerPokemon"):
            s = self.side()
            self.applied.setdefault(s, []).append(word(p, at["wDamage"]))
            self.force.setdefault(s, p.memory[at["wActionCommandForceEffect"]])
            self.hp_after.setdefault(s, word(p, at["wEnemyMonHP"]))
        elif name == "FinishActionCommand":
            self._finish = self.frame
        elif name == "PlayApplyingAttackAnimation":
            if self._finish is not None:
                self.extra.append(self.frame - self._finish)
                self._finish = None


def install_hooks(p, rec, symbols):
    for name in HOOKED:
        bank, addr = symbols[name]
        p.hook_register(bank, addr, rec.on, name)


def stage(p, at, player_move, enemy_hp=900, enemy_move=POUND,
          badges=DEFAULT_BADGES, streak=0):
    """Give both sides plenty of HP and a known move for the coming turn.

    Rewritten before every turn, as in splitcheck.py: the engine owns this
    memory, and a faint restarts the debug battle with the real moveset.
    """
    write_word(p, at["wEnemyMonMaxHP"], 999)
    write_word(p, at["wEnemyMonHP"], enemy_hp)
    write_word(p, at["wBattleMonMaxHP"], 999)
    write_word(p, at["wBattleMonHP"], 999)
    p.memory[at["wTestBattlePlayerSelectedMove"]] = player_move
    p.memory[at["wBattleMonMoves"]] = player_move
    p.memory[at["wBattleMonPP"]] = 40
    for i in range(4):
        p.memory[at["wEnemyMonMoves"] + i] = enemy_move
    # a status from the last turn would block this turn's secondary effect
    p.memory[at["wEnemyMonStatus"]] = 0
    p.memory[at["wBattleMonStatus"]] = 0
    for name in ("wEnemyBattleStatus1", "wPlayerBattleStatus1"):
        p.memory[at[name]] &= ~CONFUSED
    write_word(p, at["wBattleMonSpeed"], 250)
    # Pound into a Rhydon does about 4, too little to see rounding go wrong.
    write_word(p, at["wBattleMonAttack"], ATTACK)
    write_word(p, at["wEnemyMonAttack"], ATTACK)
    write_word(p, at["wDamage"], 0)
    p.memory[at["wObtainedBadges"]] = badges
    # a streak run up by earlier turns would double a perfect hit
    p.memory[at["wActionCommandStreak"]] = streak


def plan(steps):
    """A side's inputs, one step at a time: (button, cue, frames, hold).

    cue is which cue of the attack to count from (0 for the first), None to
    press as soon as the lead-in starts, or "feint" to press on a feint. hold is how many frames the button
    stays down, or ("cue", k) to let go k frames after the next cue appears.
    The shorthand (button, when) is one press, when frames after the first cue
    or "lead-in"."""
    out = []
    for step in steps if isinstance(steps, list) else [steps]:
        if len(step) == 2:
            button, when = step
            step = (button, None, 0, 3) if when == "lead-in" else (button, 0, when, 3)
        out.append(step)
    return out


def take_turn(p, at, rec, player_move=POUND, presses=None, enemy_hp=900,
              enemy_move=None, shot=None, badges=DEFAULT_BADGES, streak=0,
              foe=None):
    """Play one turn. presses maps a side (0 player, 1 opponent) to its inputs,
    see plan(). enemy_move defaults to the player's move. shot is a filename
    prefix: the screen is saved as the player's cue and result badge appear.
    foe maps a side to wActionCommandFoe bits forced on as its lead-in starts."""
    plans = {side: plan(steps) for side, steps in (presses or {}).items()}
    if enemy_move is None:
        enemy_move = POUND if player_move in (GROWL, DOUBLESLAP) else player_move
    # The previous turn is over once the battle menu is being drawn again.
    for _ in range(TURN_FRAMES):
        if rec.menu:
            break
        p.tick()
        rec.frame += 1
    for _ in range(30):
        p.tick()
        rec.frame += 1
    stage(p, at, player_move, enemy_hp, enemy_move, badges, streak)
    tap(p, "a", hold=6, release=20)
    tap(p, "a", hold=6, release=0)
    rec.reset()

    state_at = at["wActionCommandState"]
    cues = {0: [], 1: []}
    held = None  # (button, frame pressed, hold, cues seen when pressed, side)
    prev = None
    pending_shot = None
    for _ in range(TURN_FRAMES):
        state = p.memory[state_at]
        side = p.memory[at["hWhoseTurn"]]
        if state != prev:
            if state == WINDOW:
                cues[side].append(rec.frame)
            if state == LEAD_IN and foe and side in foe and not cues[side]:
                p.memory[at["wActionCommandFoe"]] |= foe[side]
            if shot and side == 0 and state in (LEAD_IN, WINDOW, BADGE):
                name = {LEAD_IN: "lead_in", WINDOW: "cue", BADGE: "badge"}[state]
                pending_shot = (rec.frame + 4, name)
            prev = state
        if held is not None:
            button, pressed, hold, seen, hside = held
            if isinstance(hold, int):
                done = rec.frame - pressed >= hold
            else:
                c = cues[hside]
                done = (len(c) > seen and rec.frame - c[-1] >= hold[1]) \
                    or state not in (LEAD_IN, WINDOW)
            if done:
                p.button_release(button)
                held = None
        # Some messages, such as "It's not very effective", wait for a button.
        # Answer them, and only them, so no stray press reaches a window.
        if held is None and rec.prompt:
            p.button_press("a")
            held = ("a", rec.frame, 3, 0, side)
            rec.prompt = False
        elif held is None and plans.get(side):
            button, cue, when, hold = plans[side][0]
            if cue is None:
                fire = state == LEAD_IN
            elif cue == "feint":
                fire = state == LEAD_IN and p.memory[at["wActionCommandCue"]] == CUE_FEINT
            else:
                fire = len(cues[side]) > cue and rec.frame - cues[side][cue] == when
            if fire:
                p.button_press(button)
                held = (button, rec.frame, hold, len(cues[side]), side)
                plans[side].pop(0)
        p.tick()
        rec.frame += 1
        if state == LEAD_IN and p.memory[at["wActionCommandCue"]] == CUE_FEINT:
            if shot and side not in rec.feinted:
                pending_shot = (rec.frame + 1, "feint")
            rec.feinted.add(side)
        if pending_shot and rec.frame == pending_shot[0]:
            p.screen.image.save(f"{shot}_{pending_shot[1]}.png")
            pending_shot = None
        if rec.menu:
            break
    if held is not None:
        p.button_release(held[0])
    return rec


failures = []


def check(ok, message):
    print(("  ok    " if ok else "  FAIL  ") + message)
    if not ok:
        failures.append(message)


def half(rec, side):
    return rec.before.get(side), rec.applied.get(side, []), rec.results.get(side)


def expect_scaled(rec, side, result, scale, label):
    before, applied, got = half(rec, side)
    if before is None or not applied:
        check(False, f"{label}: the attack was never applied")
        return
    want = scale(before)
    check(got == result and applied[0] == want,
          f"{label}: result {got} (want {result}), damage {before} -> {applied[0]} (want {want})")


def unchanged(d):
    return d


def boosted(d):
    return min(d + d // 2, 0xFFFF)


def braced(d):
    return max(d // 2, 1)


def doubled(d):
    return min(d * 2, 0xFFFF)


def main():
    rom_path = sys.argv[1] if len(sys.argv) > 1 else "pokeblue_debug.gbc"
    sym_path = sys.argv[2] if len(sys.argv) > 2 else "pokeblue_debug.sym"
    prefix = sys.argv[3] if len(sys.argv) > 3 else None

    try:
        p, at = enter(rom_path, sym_path, action_commands="on")
    except NotReached as e:
        print(f"FAIL: {e}")
        return 1
    symbols = load_symbols(sym_path)
    for name in ("wEnemyMonMoves", "wEnemyMonStatus", "wBattleMonStatus",
                 "wActionCommandForceEffect", "wActionCommandFoe",
                 "wActionCommandStreak", "wActionCommandCue", "wObtainedBadges"):
        at[name] = symbols[name][1]
    rec = Recorder(p, at)
    install_hooks(p, rec, symbols)
    extra = []

    def turn(**kw):
        r = take_turn(p, at, rec, **kw)
        extra.extend(r.extra)
        return r

    print("On:")
    r = turn()
    expect_scaled(r, 0, NONE, unchanged, "no press, your attack")
    expect_scaled(r, 1, NONE, unchanged, "no press, their attack")

    r = turn(presses={0: ("a", 3), 1: ("b", 3)})
    expect_scaled(r, 0, PERFECT, boosted, "A on the cue")
    expect_scaled(r, 1, PERFECT, braced, "B on the cue")
    if 1 in r.before:
        blocked = r.before[1] - braced(r.before[1])
        want = max(blocked // 4, 1)
        got = r.hp_before[1] - r.hp_after[1]
        check(got == want, f"perfect brace counters for {got} (want {want})")

    r = turn(presses={0: ("a", 19), 1: ("b", 19)}, shot=prefix)
    expect_scaled(r, 0, GOOD, boosted, "A late in the window")
    expect_scaled(r, 1, GOOD, braced, "B late in the window")
    if 1 in r.before:
        check(r.hp_before[1] == r.hp_after[1], "a good brace does not counter")

    r = turn(presses={0: ("a", 30), 1: ("b", 30)})
    expect_scaled(r, 0, NONE, unchanged, "A after the window")
    expect_scaled(r, 1, NONE, unchanged, "B after the window")

    r = turn(presses={0: ("a", "lead-in"), 1: ("b", "lead-in")})
    expect_scaled(r, 0, EARLY, unchanged, "A before the cue is locked out")
    expect_scaled(r, 1, EARLY, unchanged, "B before the cue is locked out")

    r = turn(presses={0: ("b", 3), 1: ("a", 3)})
    expect_scaled(r, 0, EARLY, unchanged, "B on your own attack is locked out")
    expect_scaled(r, 1, EARLY, unchanged, "A on their attack is locked out")

    # A counter is chip damage, never a knockout.
    r = turn(player_move=GROWL, presses={1: ("b", 3)}, enemy_hp=1)
    expect_scaled(r, 1, PERFECT, braced, "perfect brace against a 1 HP attacker")
    if 1 in r.hp_after:
        check(r.hp_after[1] == 1, f"the counter leaves the attacker at {r.hp_after[1]} HP (want 1)")

    # The bonus is applied once, then every hit of a multi-hit move reuses it.
    # Doubleslap is 85% accurate, so a miss is retried rather than counted.
    for _ in range(4):
        r = turn(player_move=DOUBLESLAP, presses={0: ("a", 3)})
        before, applied, got = half(r, 0)
        if applied:
            break
    if before is None or len(applied) < 2:
        check(False, f"Doubleslap: expected several hits, saw {applied}")
    else:
        want = boosted(before)
        check(got == PERFECT and all(d == want for d in applied),
              f"Doubleslap: every hit {applied} deals {want}, not compounded")

    def turn_landing(**kw):
        # Submission is 80% accurate, and a Confusion can leave its target too
        # confused to hit back: retry either rather than count it
        for _ in range(5):
            presses = kw.get("presses") or {}
            r = turn(**{**kw, "presses": {k: list(v) if isinstance(v, list) else v
                                          for k, v in presses.items()}})
            if all(r.applied.get(side) for side in (0, 1)):
                break
        return r

    print("Patterns:")
    # Confusion is Psychic: a snap, with less time to press.
    r = turn_landing(player_move=CONFUSION, presses={0: ("a", 3), 1: ("b", 3)})
    expect_scaled(r, 0, PERFECT, boosted, "snap: A on the cue")
    expect_scaled(r, 1, PERFECT, braced, "snap: B on the cue")
    r = turn_landing(player_move=CONFUSION, presses={0: ("a", 14), 1: ("b", 14)})
    expect_scaled(r, 0, GOOD, boosted, "snap: A 14 frames on, perfect for a tap, is only good")
    expect_scaled(r, 1, GOOD, braced, "snap: B 14 frames on is only good")
    r = turn_landing(player_move=CONFUSION, presses={0: ("a", 20), 1: ("b", 20)})
    expect_scaled(r, 0, NONE, unchanged, "snap: A 20 frames on, good for a tap, is too late")
    expect_scaled(r, 1, NONE, unchanged, "snap: B 20 frames on is too late")

    # Water Gun: hold from the start, let go on the cue.
    r = turn(player_move=WATER_GUN, presses={0: ("a", None, 0, ("cue", 3)),
                                             1: ("b", None, 0, ("cue", 3))})
    expect_scaled(r, 0, PERFECT, boosted, "hold: A held, let go on the cue")
    expect_scaled(r, 1, PERFECT, braced, "hold: B held, let go on the cue")
    r = turn(player_move=WATER_GUN, presses={0: ("a", None, 0, ("cue", 19)),
                                             1: ("b", None, 0, ("cue", 19))},
             shot=prefix and f"{prefix}_hold")
    expect_scaled(r, 0, GOOD, boosted, "hold: A let go late is good")
    expect_scaled(r, 1, GOOD, braced, "hold: B let go late is good")
    r = turn(player_move=WATER_GUN, presses={0: ("a", None, 0, 8), 1: ("b", None, 0, 8)})
    expect_scaled(r, 0, EARLY, unchanged, "hold: A let go before the cue")
    expect_scaled(r, 1, EARLY, unchanged, "hold: B let go before the cue")
    r = turn(player_move=WATER_GUN, presses={0: ("a", 3), 1: ("b", 3)})
    expect_scaled(r, 0, NONE, unchanged, "hold: a plain tap does nothing")
    expect_scaled(r, 1, NONE, unchanged, "hold: a plain brace does nothing")

    # Submission is Fighting: three presses.
    three = lambda b: [(b, 0, 3, 3), (b, 0, 9, 3), (b, 0, 15, 3)]
    r = turn_landing(player_move=SUBMISSION, presses={0: three("a"), 1: three("b")},
                     shot=prefix and f"{prefix}_rapid")
    expect_scaled(r, 0, PERFECT, boosted, "rapid: three quick A presses")
    expect_scaled(r, 1, PERFECT, braced, "rapid: three quick B presses")
    r = turn_landing(player_move=SUBMISSION, presses={0: ("a", 3), 1: ("b", 3)})
    expect_scaled(r, 0, NONE, unchanged, "rapid: a single A press is not enough")
    expect_scaled(r, 1, NONE, unchanged, "rapid: a single B press is not enough")

    # Ember is Fire: a press on each of two cues, judged by the worse.
    two = lambda b, second: [(b, 0, 3, 3), (b, 1, second, 3)]
    r = turn(player_move=EMBER, presses={0: two("a", 3), 1: two("b", 3)})
    expect_scaled(r, 0, PERFECT, boosted, "double: A on both cues")
    expect_scaled(r, 1, PERFECT, braced, "double: B on both cues")
    check(r.force.get(1) == BLOCKED, f"double: a perfect brace blocks the burn ({r.force.get(1)})")
    r = turn(player_move=EMBER, presses={0: two("a", 19), 1: two("b", 19)})
    expect_scaled(r, 0, GOOD, boosted, "double: A late on the second cue is good")
    expect_scaled(r, 1, GOOD, braced, "double: B late on the second cue is good")
    check(r.force.get(0) == ROLL, f"double: a good attack rolls for the burn as usual ({r.force.get(0)})")
    r = turn(player_move=EMBER, presses={0: ("a", 3), 1: ("b", 3)})
    expect_scaled(r, 0, NONE, unchanged, "double: missing the second A loses the first")
    expect_scaled(r, 1, NONE, unchanged, "double: missing the second B loses the first")

    # A perfect Ember always burns, where it would burn one time in ten.
    burns = 0
    for _ in range(3):
        r = turn(player_move=EMBER, presses={0: two("a", 3)})
        burns += bool(p.memory[at["wEnemyMonStatus"]] & BRN) and r.results.get(0) == PERFECT
    check(burns == 3, f"a perfect Ember burned {burns} time(s) out of 3")

    print("Ramp:")
    for tier, badges in enumerate(BADGES):
        perfect, good = RAMP[tier][:2]
        name = f"{bin(badges).count('1')} badge(s)"
        r = turn(badges=badges, presses={0: ("a", 3), 1: ("b", 3)})
        expect_scaled(r, 0, PERFECT, boosted, f"{name}: A on the cue")
        expect_scaled(r, 1, PERFECT, braced, f"{name}: B on the cue")
        r = turn(badges=badges, presses={0: ("a", perfect + 3), 1: ("b", perfect + 3)})
        expect_scaled(r, 0, GOOD, boosted, f"{name}: A {perfect + 3} frames on is good")
        expect_scaled(r, 1, GOOD, braced, f"{name}: B {perfect + 3} frames on is good")
        r = turn(badges=badges, presses={0: ("a", good + 3), 1: ("b", good + 3)})
        expect_scaled(r, 0, NONE, unchanged, f"{name}: A {good + 3} frames on is too late")
        expect_scaled(r, 1, NONE, unchanged, f"{name}: B {good + 3} frames on is too late")
    # the longest inputs, left unanswered, still fit the budget on the last row
    for move in (CONFUSION, WATER_GUN, EMBER):
        turn(player_move=move, badges=BADGES[-1])
    turn_landing(player_move=SUBMISSION, badges=BADGES[-1])

    print("Pattern gating:")
    r = turn(player_move=WATER_GUN, badges=BADGES[0], presses={0: ("a", 3), 1: ("b", 3)})
    expect_scaled(r, 0, PERFECT, boosted, "no badges: Water Gun is a plain tap")
    expect_scaled(r, 1, PERFECT, braced, "no badges: so is the brace against it")
    late = RAMP[0][0] - 3
    r = turn(player_move=CONFUSION, badges=BADGES[0], presses={0: ("a", late)})
    expect_scaled(r, 0, PERFECT, boosted, f"no badges: Confusion taps, so {late} frames on is perfect")
    r = turn(player_move=EMBER, badges=BADGES[1], presses={0: ("a", 3), 1: ("b", 3)})
    expect_scaled(r, 0, PERFECT, boosted, "one badge: Ember is still a tap")
    expect_scaled(r, 1, PERFECT, braced, "one badge: so is the brace against it")
    snap = RAMP[1][0] - SNAP_PERFECT + 1
    r = turn(player_move=CONFUSION, badges=BADGES[1], presses={0: ("a", snap)})
    expect_scaled(r, 0, GOOD, boosted, f"one badge: Confusion snaps, so {snap} frames on is only good")

    print("Feints:")
    r = turn(foe={1: FEINT}, presses={1: ("b", "feint", 0, 3)})
    check(1 in r.feinted, "the feint is shown before the cue to brace")
    expect_scaled(r, 1, EARLY, unchanged, "B on the feint is locked out")
    r = turn(foe={1: FEINT}, presses={1: ("b", 3)}, shot=prefix and f"{prefix}_feint")
    check(1 in r.feinted, "the feint is shown again")
    expect_scaled(r, 1, PERFECT, braced, "B on the real cue after a feint is perfect")

    print("Trainer timing:")
    r = turn(foe={0: TIMED, 1: TIMED}, presses={0: ("a", 19)})
    expect_scaled(r, 0, GOOD, unchanged, "a good hit on a trainer that braced gets no bonus")
    check(r.badge.get(0) == BADGE_FOE_BRACED, f"the badge says FOE BRACED ({r.badge.get(0)})")
    expect_scaled(r, 1, NONE, boosted, "a timed attack left unbraced hits x1.5")
    check(r.badge.get(1) == BADGE_FOE_GREAT, f"the badge says FOE GREAT ({r.badge.get(1)})")
    r = turn(foe={0: TIMED, 1: TIMED}, presses={0: ("a", 3), 1: ("b", 3)})
    expect_scaled(r, 0, PERFECT, boosted, "a perfect hit goes through a trainer's brace")
    expect_scaled(r, 1, PERFECT, lambda d: braced(boosted(d)),
                  "a perfect brace halves a timed attack")

    # Rolled for real on the last row: half of a trainer's attacks, never a
    # wild Pokemon's, and a feint only ever before the cue to brace.
    def roll(turns, badges=BADGES[-1]):
        timed, feinted = [0, 0], [0, 0]
        for _ in range(turns):
            r = turn(badges=badges)
            for side in (0, 1):
                timed[side] += bool(r.foe.get(side, 0) & TIMED)
                feinted[side] += side in r.feinted
        return timed, feinted

    rec.trainer = True
    timed, feinted = roll(16)
    check(all(2 <= t <= 14 for t in timed), f"a trainer timed {timed} of 16 attacks each way")
    rec.trainer = False
    wild, wild_feints = roll(8)
    check(wild == [0, 0], f"a wild Pokemon never times an attack ({wild})")
    feints = [a + b for a, b in zip(feinted, wild_feints)]
    check(feints[0] == 0 and feints[1] >= 1,
          f"feints came before {feints[1]} of 24 braces and {feints[0]} attacks")
    timed, feinted = roll(8, badges=BADGES[2])
    check(feinted == [0, 0], f"no feints before five badges ({feinted})")

    print("Streak:")
    r = turn(streak=3, presses={0: ("a", 3), 1: ("b", 3)})
    expect_scaled(r, 0, PERFECT, doubled, "a perfect hit after three in a row doubles")
    check(r.badge.get(0) == BADGE_DOUBLE, f"the badge says PERFECT x2 ({r.badge.get(0)})")
    streak = p.memory[at["wActionCommandStreak"]]
    check(streak == 5, f"both presses add to the streak ({streak}, want 5)")
    r = turn(streak=2, presses={0: ("a", 3)})
    expect_scaled(r, 0, PERFECT, boosted, "two in a row is not yet a streak")
    streak = p.memory[at["wActionCommandStreak"]]
    check(streak == 0, f"an unanswered brace ends the streak ({streak})")

    print("Assist:")
    set_action_commands(p, at, "assist")
    r = turn(presses={0: ("a", 17), 1: ("b", 28)})
    expect_scaled(r, 0, PERFECT, boosted, "A 17 frames after the cue is still perfect")
    expect_scaled(r, 1, GOOD, braced, "B 28 frames after the cue is still good")

    rec.trainer = True
    timed, feinted = roll(6)
    rec.trainer = False
    check(timed == [0, 0] and feinted == [0, 0],
          f"on the last row, Assist still has no timing ({timed}) or feints ({feinted})")

    print("Animations off:")
    set_action_commands(p, at, "on")
    p.memory[at["wOptions"]] |= BIT_BATTLE_ANIMATION
    r = turn(presses={0: ("a", 19)})
    expect_scaled(r, 0, GOOD, boosted, "the window runs during the fixed pause")
    p.memory[at["wOptions"]] &= ~BIT_BATTLE_ANIMATION

    print("Off:")
    set_action_commands(p, at, "off")
    off_extra_before = len(extra)
    r = turn()
    for side, label in ((0, "your attack"), (1, "their attack")):
        before, applied, _ = half(r, side)
        check(r.states.get(side) == 0 and before is not None and applied[:1] == [before],
              f"off: {label} is never armed and deals {applied[:1]} (want [{before}])")
    off_extra = extra[off_extra_before:]
    check(not any(off_extra), f"off adds no frames to any attack ({off_extra})")

    print("Battle length:")
    worst = max(extra) if extra else None
    check(worst is not None and worst <= MAX_EXTRA_FRAMES,
          f"the window added at most {worst} frames to any of {len(extra)} attacks "
          f"(budget {MAX_EXTRA_FRAMES})")

    p.stop(save=False)
    if failures:
        print(f"FAIL: {len(failures)} check(s) failed")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
