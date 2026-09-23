"""Prove the two anti-fun battle mechanics really changed.

Both changes are deletions, and a deletion is the easiest kind of change to get
wrong without noticing: the build still succeeds and every other test still
passes whether or not the branch was actually removed.

Trapping: the player uses Wrap. On any turn where the player is mid-Wrap, the
opponent has to still act. In vanilla it printed "can't move" and did nothing
for the whole duration, so the player's HP could not fall.

Hyper Beam: the player knocks the target out with Hyper Beam and must still be
flagged to recharge. In vanilla the recharge was set by a move effect that runs
only after a check for a fainted target, so a knockout skipped it entirely.

Usage:
    python test/trapcheck.py pokeblue_debug.gbc pokeblue_debug.sym
"""
import sys

from debugbattle import NotReached, enter, tap, word, write_word

WRAP = 0x23
HYPER_BEAM = 0x3F

USING_TRAPPING_MOVE = 1 << 5  # in wPlayerBattleStatus1
NEEDS_TO_RECHARGE = 1 << 5  # in wPlayerBattleStatus2

# Wrap does very little damage, so the opponent needs enough health to survive
# the whole duration and keep hitting back.
TRAP_ENEMY_HP = 400
TURN_FRAMES = 900
TRAP_TURNS = 12

# Hyper Beam has to knock the target out in one hit for this to test anything.
KO_ENEMY_HP = 1
KO_TURNS = 6


def arm(p, at, move_id, enemy_hp, heal_player):
    """Install the move and the health both sides start the turn with."""
    write_word(p, at["wEnemyMonMaxHP"], enemy_hp)
    write_word(p, at["wEnemyMonHP"], enemy_hp)
    if heal_player:
        write_word(p, at["wBattleMonHP"], word(p, at["wBattleMonMaxHP"]))
    p.memory[at["wTestBattlePlayerSelectedMove"]] = move_id
    p.memory[at["wBattleMonMoves"]] = move_id
    p.memory[at["wBattleMonPP"]] = 40


def trapping_leaves_the_opponent_able_to_act(p, at):
    """Return (turns seen mid-Wrap, turns the opponent hit back)."""
    mid_wrap = 0
    hit_back = 0

    for _ in range(TRAP_TURNS):
        # The player is healed every turn, so any fall in health can only have
        # come from the turn just played.
        arm(p, at, WRAP, TRAP_ENEMY_HP, heal_player=True)
        before = word(p, at["wBattleMonHP"])

        tap(p, "a", hold=6, release=20)
        tap(p, "a", hold=6, release=20)

        # Wrap sets its flag early in the turn and the engine clears it once the
        # duration runs out, so watch the whole turn rather than reading the
        # flag at the end, when it may already be gone.
        trapping = False
        for frame in range(TURN_FRAMES):
            if frame % 8 == 0:
                p.button_press("a")
            elif frame % 8 == 2:
                p.button_release("a")
            p.tick()
            if p.memory[at["wPlayerBattleStatus1"]] & USING_TRAPPING_MOVE:
                trapping = True
        p.button_release("a")

        if not trapping:
            continue
        # A restart would have put the real Rhydon's moves back.
        if p.memory[at["wPlayerMoveNum"]] != WRAP:
            continue
        mid_wrap += 1
        if word(p, at["wBattleMonHP"]) < before:
            hit_back += 1

    return mid_wrap, hit_back


def hyper_beam_recharges_after_a_knockout(p, at):
    """Return (knockouts landed, knockouts that still set the recharge flag)."""
    knockouts = 0
    recharges = 0

    for _ in range(KO_TURNS):
        arm(p, at, HYPER_BEAM, KO_ENEMY_HP, heal_player=True)
        p.memory[at["wPlayerBattleStatus2"]] &= ~NEEDS_TO_RECHARGE
        # A Pokemon mid-Wrap repeats Wrap and never reaches the move it was
        # given, and a Pokemon mid-recharge does not attack at all. The Wrap
        # phase above leaves both behind, so clear them before each turn.
        p.memory[at["wPlayerBattleStatus1"]] &= ~USING_TRAPPING_MOVE

        tap(p, "a", hold=6, release=20)
        tap(p, "a", hold=6, release=20)

        # The debug battle restarts from scratch the moment either side faints,
        # and a restart clears the battle status bytes. The flag therefore has
        # to be caught while the turn is still running, not read afterwards.
        recharged = False
        fainted = False
        used_hyper_beam = False
        for frame in range(TURN_FRAMES):
            if frame % 8 == 0:
                p.button_press("a")
            elif frame % 8 == 2:
                p.button_release("a")
            p.tick()
            if p.memory[at["wPlayerBattleStatus2"]] & NEEDS_TO_RECHARGE:
                recharged = True
            if word(p, at["wEnemyMonHP"]) == 0:
                fainted = True
            if p.memory[at["wPlayerMoveNum"]] == HYPER_BEAM:
                used_hyper_beam = True
        p.button_release("a")

        # Only a knockout dealt by Hyper Beam itself says anything here, and
        # the restart wipes the move number, so it has to be read during the
        # turn rather than after it.
        if not fainted or not used_hyper_beam:
            continue
        knockouts += 1
        if recharged:
            recharges += 1

    return knockouts, recharges


def main():
    rom_path = sys.argv[1] if len(sys.argv) > 1 else "pokeblue_debug.gbc"
    sym_path = sys.argv[2] if len(sys.argv) > 2 else "pokeblue_debug.sym"

    try:
        p, at = enter(rom_path, sym_path)
    except NotReached as e:
        print(f"FAIL: {e}")
        return 1

    failures = []

    mid_wrap, hit_back = trapping_leaves_the_opponent_able_to_act(p, at)
    print("partial trapping (the player uses Wrap)")
    print(f"  turns spent mid-Wrap          {mid_wrap}")
    print(f"  of those, opponent hit back   {hit_back}")
    if mid_wrap == 0:
        failures.append("Wrap never took hold, so nothing was tested")
    elif hit_back == 0:
        failures.append(
            "the opponent never acted while trapped: the lock is still there"
        )

    knockouts, recharges = hyper_beam_recharges_after_a_knockout(p, at)
    print("Hyper Beam recharge (the player knocks the target out)")
    print(f"  knockouts landed              {knockouts}")
    print(f"  of those, recharge was set    {recharges}")
    if knockouts == 0:
        failures.append("Hyper Beam never knocked the target out, so nothing was tested")
    elif recharges < knockouts:
        failures.append(
            f"the recharge was skipped on {knockouts - recharges} of {knockouts} "
            "knockouts"
        )

    p.stop(save=False)

    print()
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("PASS: trapping no longer locks the target, and a knockout still recharges")
    return 0


if __name__ == "__main__":
    sys.exit(main())
