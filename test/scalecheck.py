"""Check open-world level scaling on real trainer battles.

Uses actionedge.py's Battle to fight real trainer parties, with the badge
count written as the battle is set up, and reads the enemy team's levels.

  - Sabrina (designed for 5 badges) fought with 2 drops by 43 - 24 = 19;
  - Sabrina fought with 5 is exactly as in the original game;
  - Misty (designed for 1) fought with 6 rises by 47 - 21 = 26;
  - the SS Anne rival (designed for 2) fought with 5 rises by 43 - 24 = 19;
  - Brock and a Youngster never change, whatever the badges;
  - a trainer inside a gym follows that gym's leader.

Usage:
    python test/scalecheck.py [pokered_debug.gbc pokered_debug.sym]
"""
import sys

from actioncheck import check, failures
from actionedge import OPP_ID_OFFSET, SHIFT_OFF, Battle

PARTYMON_STRUCT_LENGTH = 44
MON_LEVEL = 33
BADGES = {0: 0, 1: 0b1, 2: 0b11, 5: 0b11111, 6: 0b111111, 8: 0xFF}
BROCK, MISTY, SABRINA, RIVAL2, YOUNGSTER = 0x22, 0x23, 0x28, 0x19 + 0, 0x01
RIVAL2 = 0x2A  # trainer_const RIVAL2
CERULEAN_GYM = 0x41
# the original teams' levels
SABRINA_LEVELS = [38, 37, 38, 43]
MISTY_LEVELS = [18, 21]
RIVAL_SS_ANNE = [19, 16, 18, 20]
BROCK_LEVELS = [12, 14]


class ScaledBattle(Battle):
    badges = 0
    where = None

    def on(self, name):
        if name == "InitOpponent":
            self.w("wObtainedBadges", BADGES[self.badges])
            if self.where is not None:
                self.w("wCurMap", self.where)
        super().on(name)

    def levels(self):
        n = self.m("wEnemyPartyCount")
        base = self.a("wEnemyMons") + MON_LEVEL
        return [self.p.memory[base + i * PARTYMON_STRUCT_LENGTH] for i in range(n)]


def fight(rom, sym, cls, badges, trainer_no=1, where=None):
    ScaledBattle.badges = badges
    ScaledBattle.where = where
    b = ScaledBattle(rom, sym, opponent=OPP_ID_OFFSET + cls, trainer_no=trainer_no,
                     options=0x03 | SHIFT_OFF | 0b100000)
    got = b.levels()
    b.p.stop(save=False)
    return got


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else "pokered_debug.gbc"
    sym = sys.argv[2] if len(sys.argv) > 2 else "pokered_debug.sym"

    got = fight(rom, sym, SABRINA, 2)
    want = [lv - 19 for lv in SABRINA_LEVELS]
    check(got == want, f"Sabrina at 2 badges: {got} (want {want})")
    got = fight(rom, sym, SABRINA, 5)
    check(got == SABRINA_LEVELS, f"Sabrina at 5 badges, on schedule: {got}")
    got = fight(rom, sym, MISTY, 6)
    want = [lv + 26 for lv in MISTY_LEVELS]
    check(got == want, f"Misty at 6 badges: {got} (want {want})")
    got = fight(rom, sym, RIVAL2, 5, trainer_no=1)
    want = [lv + 19 for lv in RIVAL_SS_ANNE]
    check(got == want, f"the SS Anne rival at 5 badges: {got} (want {want})")
    got = fight(rom, sym, BROCK, 8)
    check(got == BROCK_LEVELS, f"Brock never scales: {got}")
    got = fight(rom, sym, YOUNGSTER, 8)
    base = fight(rom, sym, YOUNGSTER, 0)
    check(got == base, f"a Youngster never scales: {got}")
    got = fight(rom, sym, YOUNGSTER, 6, where=CERULEAN_GYM)
    want = [lv + 26 for lv in base]
    check(got == want, f"a trainer in Misty's gym at 6 badges follows her: {got} (want {want})")

    print()
    print("FAILED" if failures else "all scaling checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
