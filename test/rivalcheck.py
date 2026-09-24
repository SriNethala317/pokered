"""Check Rival Sync: the rival's collar forces a Resonance below half HP.

Fights the real SS Anne rival (actionedge.py's Battle swaps the debug battle's
wild Pokemon for a trainer party) with action commands Off, eight badges (a
99.6% chance) and both sides using Pound. The rival's Pokemon is put below half
HP, then turns are played and read through hooks:
  - FOE SYNC! shows at the start of the next turn;
  - for exactly two of the rival's attacks the damage is x1.5 (read as it
    enters the field code and as it is dealt);
  - then FOE STUN shows and the rival's move that turn is CANNOT_MOVE;
  - the same Pokemon is never forced twice;
  - no extra text is printed;
  - a Youngster is never forced.

Usage:
    python test/rivalcheck.py [pokered_debug.gbc pokered_debug.sym]
"""
import sys

from actioncheck import check, failures
from actionedge import OPP_ID_OFFSET, SHIFT_OFF, Battle
from debugbattle import word, write_word

RIVAL2, YOUNGSTER = 0x2A, 0x01
POUND = 0x01
BADGE_FOE_SYNC, BADGE_FOE_STUN = 16, 17
CANNOT_MOVE = 0xFF
OFF = 0b100000


class RivalBattle(Battle):
    HOOKS = Battle.HOOKS + ("ApplyFieldToAttack", "ShowActionBadge", "ExecuteEnemyMove")

    def reset(self):
        super().reset()
        self.field_in = {}
        self.badges_seen = []
        self.enemy_moves = []
        self.texts = 0

    def on(self, name):
        side = self.m("hWhoseTurn")
        if name == "ApplyFieldToAttack":
            self.field_in.setdefault(side, word(self.p, self.a("wDamage")))
        elif name == "ShowActionBadge":
            self.badges_seen.append(self.p.register_file.A)
        elif name == "ExecuteEnemyMove":
            self.enemy_moves.append(self.m("wEnemySelectedMove"))
        if name == "PrintText":
            self.texts += 1
        if name in Battle.HOOKS:
            super().on(name)


def play(b, enemy_hp):
    def stage():
        b.stage(player_move=POUND, enemy_move=POUND, player_fast=True, badges=0xFF,
                enemy_hp=enemy_hp)
        write_word(b.p, b.a("wEnemyMonMaxHP"), 999)
    b.turn(stage=stage)


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else "pokered_debug.gbc"
    sym = sys.argv[2] if len(sys.argv) > 2 else "pokered_debug.sym"

    b = RivalBattle(rom, sym, opponent=OPP_ID_OFFSET + RIVAL2, trainer_no=1,
                    options=0x03 | SHIFT_OFF | OFF, event_battled_rival=True)
    check(b.m("wTrainerClass") == RIVAL2, "a battle against the SS Anne rival")
    play(b, 900)
    check(BADGE_FOE_SYNC not in b.badges_seen, "above half HP nothing happens")
    plain_texts = b.texts
    # below half: the next turn starts with the collar
    play(b, 400)
    boosted, stunned, syncs = 0, False, 0
    log = []
    for _ in range(4):
        play(b, 400)
        syncs += b.badges_seen.count(BADGE_FOE_SYNC)
        before, dealt = b.field_in.get(1), b.dealt.get(1)
        if before and dealt == min(before + before // 2, 0xFFFF):
            boosted += 1
        log.append((before, dealt, list(b.badges_seen), list(b.enemy_moves)))
    # FOE STUN shows as the next turn starts, which is the end of the turn before
    for i in range(1, len(log)):
        if BADGE_FOE_STUN in log[i - 1][2] and CANNOT_MOVE in log[i][3]:
            stunned = True
    check(boosted == 2, f"two of the rival's attacks were x1.5 (log {log})")
    check(stunned, "then FOE STUN, and the rival's move that turn is CANNOT_MOVE")
    play(b, 400)
    check(BADGE_FOE_SYNC not in b.badges_seen, "the same Pokemon is never forced twice")
    check(b.texts <= plain_texts + 1, f"no extra text ({b.texts} vs {plain_texts})")
    b.p.stop(save=False)

    b = RivalBattle(rom, sym, opponent=OPP_ID_OFFSET + YOUNGSTER,
                    options=0x03 | SHIFT_OFF | OFF, event_battled_rival=True)
    for _ in range(3):
        play(b, 400)
    check(BADGE_FOE_SYNC not in b.badges_seen and b.m("wRivalSync") == 0, "a Youngster is never forced")
    b.p.stop(save=False)

    print()
    print("FAILED" if failures else "all Rival Sync checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
