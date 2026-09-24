"""Check the Trainer Dodge Phase against Brock, and that it stays short.

Uses actionedge.py's Battle, which turns the debug battle into a real trainer
battle, here against Brock (Geodude, then Onix). Both sides use Pound.
The rocks are random, so the outcomes are forced through the phase's own
routines rather than hoped for:
  - untouched: new rocks are held off by keeping the spawn timer high;
  - hit: a rock is put on the player's tile as CheckDodgeHit looks.

Checked:
  - the phase opens on the first damaging attack of each of Brock's
    Pokemon, and only then, so twice in the battle;
  - untouched: DODGED!, the attack halved, the meter +3;
  - one hit: a sixth of the trainer's bar lost, the attack in full;
  - hit until the bar is dry: BROKEN!, and the player's next turn is lost;
  - the screen is exactly as it was afterwards;
  - it never opens against wild Pokemon, an ordinary trainer, or with action
    commands Off;
  - it takes at most DODGE_FRAMES + 10 frames.

Usage:
    python test/dodgecheck.py [pokered_debug.gbc pokered_debug.sym]
"""
import sys

from actioncheck import check, failures
from actionedge import OPP_ID_OFFSET, SHIFT_OFF, Battle
from debugbattle import word

BROCK, YOUNGSTER = 0x22, 0x01
POUND = 0x01
DODGE_FRAMES = 150
DODGE_HIT_PAIN, TRAINER_MAX_HP = 6, 24
BADGE_BROKEN, BADGE_DODGED = 9, 12
CANNOT_MOVE = 0xFF
EVENT_RESONANCE_UNLOCKED = 0x6A
ROCK = 0x8E  # 'O'
OFF = 0b100000


class DodgeBattle(Battle):
    HOOKS = Battle.HOOKS + ("DodgePhase", "TryDodgePhase.gotResult", "TryDodgePhase.broken",
                            "CheckDodgeHit", "ShowActionBadge", "ExecutePlayerMove")
    force = None  # None, "none" (no rocks), "once" or "always"; kept across reset()

    def reset(self):
        super().reset()
        self.phases = []      # (frames the phase took, screen restored?)
        self.badges = []
        self.moves = []
        self._start = None
        self._screen = None
        self.forced = 0

    def on(self, name):
        p = self.p
        if name == "DodgePhase":
            self._start = p.frame_count
            base = self.a("wTileMap")
            self._screen = bytes(p.memory[base + i] for i in range(360))
        elif name in ("TryDodgePhase.gotResult", "TryDodgePhase.broken"):
            base = self.a("wTileMap")
            screen = bytes(p.memory[base + i] for i in range(360))
            self.phases.append((p.frame_count - self._start, screen == self._screen))
        elif name == "CheckDodgeHit":
            if self.force == "none":
                self.w("wActionCommandFrame", 200)  # the spawn timer
            elif self.force in ("once", "always") and (self.force == "always" or not self.forced):
                if not self.m("wActionCommandBadgeTimer"):  # no grace left
                    y, x = self.m("wDodgeY"), self.m("wDodgeX")
                    p.memory[self.a("wTileMap") + y * 20 + x] = ROCK
                    self.forced += 1
        elif name == "ShowActionBadge":
            self.badges.append(p.register_file.A)
        elif name == "ExecutePlayerMove":
            self.moves.append(self.m("wPlayerSelectedMove"))
        if name in Battle.HOOKS:
            super().on(name)


def brock(rom, sym, options=0x03 | SHIFT_OFF, opponent=OPP_ID_OFFSET + BROCK):
    b = DodgeBattle(rom, sym, opponent=opponent, options=options, event_battled_rival=True)
    flags = b.a("wEventFlags") + EVENT_RESONANCE_UNLOCKED // 8
    b.p.memory[flags] |= 1 << (EVENT_RESONANCE_UNLOCKED % 8)
    return b


def run_turn(b, force=None, enemy_hp=900, badges=0, player_fast=False):
    def stage():
        b.stage(player_move=POUND, enemy_move=POUND, player_fast=player_fast,
                badges=badges, enemy_hp=enemy_hp)
    b.force = force
    b.turn(stage=stage)
    return b


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else "pokered_debug.gbc"
    sym = sys.argv[2] if len(sys.argv) > 2 else "pokered_debug.sym"

    print("Untouched:")
    b = brock(rom, sym)
    check(b.m("wIsInBattle") == 2 and b.m("wTrainerClass") == BROCK, "a trainer battle against Brock")
    b.w("wResonanceMeter", 0)
    run_turn(b, force="none")
    phases = list(b.phases)
    check(len(phases) == 1, f"Geodude's first attack opens the arena ({len(phases)} phases)")
    if phases:
        took, restored = phases[0]
        check(took <= DODGE_FRAMES + 10, f"the phase took {took} frames (at most {DODGE_FRAMES + 10})")
        check(restored, "the screen is exactly as it was afterwards")
    check(BADGE_DODGED in b.badges, f"DODGED! shows (badges {b.badges})")
    before, dealt = b.before.get(1), b.dealt.get(1)
    check(before is not None and dealt == max(before // 2, 1), f"the attack is halved: {before} -> {dealt}")
    check(b.m("wResonanceMeter") == 3, f"the meter gains 3: {b.m('wResonanceMeter')}")
    check(b.m("wTrainerPain") == 0, "no pain")
    run_turn(b, force="none")
    check(not b.phases, "Geodude's second attack does not open it again")

    print("The next Pokemon:")
    run_turn(b, force="none", enemy_hp=1, player_fast=True)  # Geodude faints
    for _ in range(3):
        if b.phases:
            break
        run_turn(b, force="none")
    check(len(b.phases) == 1, f"Onix's first attack opens it again ({len(b.phases)} phases)")
    b.p.stop(save=False)

    print("One hit:")
    b = brock(rom, sym)
    run_turn(b, force="once")
    check(len(b.phases) == 1, "the arena opens")
    check(b.m("wTrainerPain") == DODGE_HIT_PAIN, f"one hit costs {DODGE_HIT_PAIN}: pain {b.m('wTrainerPain')}")
    before, dealt = b.before.get(1), b.dealt.get(1)
    check(before is not None and dealt == before, f"the attack lands in full: {before} -> {dealt}")
    check(BADGE_DODGED not in b.badges and BADGE_BROKEN not in b.badges, f"no badge ({b.badges})")
    b.p.stop(save=False)

    print("Hit until the bar is dry:")
    b = brock(rom, sym)
    run_turn(b, force="always")
    check(BADGE_BROKEN in b.badges, f"BROKEN! shows (badges {b.badges})")
    check(b.m("wTrainerPain") == 0, "the trainer's bar is refilled for next time")
    before, dealt = b.before.get(1), b.dealt.get(1)
    check(before is None or dealt == before, f"the attack lands in full: {before} -> {dealt}")
    check(CANNOT_MOVE in b.moves, f"the player's next turn is lost: moves {b.moves}")
    b.p.stop(save=False)

    print("Never:")
    b = DodgeBattle(rom, sym, options=0x03 | SHIFT_OFF)
    run_turn(b)
    run_turn(b)
    check(not b.phases and b.m("wIsInBattle") == 1, "not against a wild Pokemon")
    b.p.stop(save=False)
    b = brock(rom, sym, opponent=OPP_ID_OFFSET + YOUNGSTER)
    run_turn(b)
    check(not b.phases and b.m("wTrainerClass") == YOUNGSTER, "not against an ordinary trainer")
    b.p.stop(save=False)
    b = brock(rom, sym, options=0x03 | SHIFT_OFF | OFF)
    run_turn(b)
    check(not b.phases, "not with action commands Off")
    b.p.stop(save=False)

    print()
    print("FAILED" if failures else "all Dodge Phase checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
