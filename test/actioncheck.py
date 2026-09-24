"""Prove the action command window scales damage as designed, and stays short.

Each staged turn has the player attack first and the opponent attack back, both
with Pound, so both halves of the window are exercised: A on your own attack
and B on the opponent's. Presses are timed from the moment the cue appears,
which is when wActionCommandState moves from the lead-in to the window.

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
DOUBLESLAP = 0x03
GROWL = 0x2D

# wActionCommandState / wActionCommandResult, see constants/battle_constants.asm
LEAD_IN, WINDOW, BADGE = 1, 2, 4
NONE, EARLY, GOOD, PERFECT = 0, 1, 2, 3

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
)


class Recorder:
    """Collects what the hooks see during one turn."""

    def __init__(self, p, at):
        self.p = p
        self.at = at
        self.frame = 0
        self.reset()

    def reset(self):
        self.menu = False
        self.prompt = False
        self.before = {}    # side -> damage entering ApplyActionCommand
        self.applied = {}   # side -> list of damage values dealt, one per hit
        self.hp_before = {}  # side -> enemy HP entering ApplyActionCommand
        self.hp_after = {}   # side -> enemy HP once the attack is being dealt
        self.results = {}   # side -> wActionCommandResult entering Apply
        self.states = {}    # side -> wActionCommandState entering Apply
        self.extra = []     # frames each window added to an attack
        self._finish = None

    def side(self):
        return self.p.memory[self.at["hWhoseTurn"]]

    def on(self, name):
        p, at = self.p, self.at
        if name == "DisplayBattleMenu":
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
        elif name in ("ApplyAttackToEnemyPokemon", "ApplyAttackToPlayerPokemon"):
            s = self.side()
            self.applied.setdefault(s, []).append(word(p, at["wDamage"]))
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


def stage(p, at, player_move, enemy_hp=900):
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
        p.memory[at["wEnemyMonMoves"] + i] = POUND
    write_word(p, at["wBattleMonSpeed"], 250)
    # Pound into a Rhydon does about 4, too little to see rounding go wrong.
    write_word(p, at["wBattleMonAttack"], ATTACK)
    write_word(p, at["wEnemyMonAttack"], ATTACK)
    write_word(p, at["wDamage"], 0)


def take_turn(p, at, rec, player_move=POUND, presses=None, enemy_hp=900, shot=None):
    """Play one turn. presses maps a side (0 player, 1 opponent) to a
    (button, when) pair, where when is frames after the cue, or "lead-in" to
    press before the cue appears. shot is a filename prefix: the screen is
    saved as the player's cue and result badge appear."""
    presses = presses or {}
    # The previous turn is over once the battle menu is being drawn again.
    for _ in range(TURN_FRAMES):
        if rec.menu:
            break
        p.tick()
        rec.frame += 1
    for _ in range(30):
        p.tick()
        rec.frame += 1
    stage(p, at, player_move, enemy_hp)
    tap(p, "a", hold=6, release=20)
    tap(p, "a", hold=6, release=0)
    rec.reset()

    state_at = at["wActionCommandState"]
    cue = {}
    held = None
    prev = None
    pending_shot = None
    for _ in range(TURN_FRAMES):
        state = p.memory[state_at]
        side = p.memory[at["hWhoseTurn"]]
        if state != prev:
            if state == WINDOW:
                cue[side] = rec.frame
            if shot and side == 0 and state in (WINDOW, BADGE):
                pending_shot = (rec.frame + 4, "cue" if state == WINDOW else "badge")
            prev = state
        if held is not None and rec.frame - held[1] >= 3:
            p.button_release(held[0])
            held = None
        # Some messages, such as "It's not very effective", wait for a button.
        # Answer them, and only them, so no stray press reaches a window.
        if held is None and rec.prompt:
            p.button_press("a")
            held = ("a", rec.frame)
            rec.prompt = False
        elif held is None and side in presses:
            button, when = presses[side]
            if when == "lead-in":
                fire = state == LEAD_IN
            else:
                fire = side in cue and rec.frame - cue[side] == when
            if fire:
                p.button_press(button)
                held = (button, rec.frame)
                del presses[side]
        p.tick()
        rec.frame += 1
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
    at["wEnemyMonMoves"] = symbols["wEnemyMonMoves"][1]
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

    print("Assist:")
    set_action_commands(p, at, "assist")
    r = turn(presses={0: ("a", 17), 1: ("b", 28)})
    expect_scaled(r, 0, PERFECT, boosted, "A 17 frames after the cue is still perfect")
    expect_scaled(r, 1, GOOD, braced, "B 28 frames after the cue is still good")

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
