"""Prove the two halves of the battle rework actually change damage.

The read-back checks in datacheck.py only show that the tables hold the values
we meant to write. They say nothing about whether the battle code reads them.
This does, for both tables, from inside a live battle.

The method avoids having to know the damage formula. Everything except the one
thing under test is held fixed, and damage is compared between two readings.

For the per-move damage category, the player is given Fire Punch -- a move
vanilla treats as special and we now treat as physical -- and takes turns with
the attacker's Attack and Special swapped. Same move, same level, same
defender, same type chart multiplier, so the only thing that differs is which
stat the engine read.

For the special split, both sides keep Rhydon's stats and types and only the
species index that the factor table is read with changes. Damage against a
species with a high special defence factor must be lower than against one with
a low factor, and the same for the attacking side.

Usage:
    python test/splitcheck.py pokeblue_debug.gbc pokeblue_debug.sym
"""
import statistics
import sys

from debugbattle import NotReached, enter, tap, word, write_word

FIRE_PUNCH = 7
SURF = 57

# Species indexes, and the special split factors they carry in sixteenths.
RHYDON = 0x01    # 16 and 16, the same either way
CHANSEY = 0x28   # 8 attacking, 24 defending
ALAKAZAM = 0x95  # 20 attacking, 12 defending

HIGH = 250
LOW = 10
SAMPLES = 5

# The debug battle restarts from scratch the moment either side faints, which
# throws away the move and stats we installed. A high-Special Surf against a
# 73 HP Rhydon is a clean one-hit knockout, so the enemy is given far more HP
# than any single hit can remove and both sides are topped up every turn.
ENEMY_HP = 999

# Frames to let one turn play out. A turn is two attacks plus their animations
# and message boxes, so this is generous on purpose; the loop below stops early
# once the enemy's HP moves.
TURN_FRAMES = 900


# Which species each side is treated as, for the special split factor lookup.
# Only the species index changes, so types, stats and everything else stay as
# they were and the type chart multiplier is the same whatever is selected.
# Rewritten every turn along with everything else, because a restart would put
# the real Rhydon back.
SPECIES = {"attacker": RHYDON, "defender": RHYDON}

# A fixed special defence for the opponent, so the only thing moving between
# readings is the factor the species lookup supplies.
ENEMY_SPECIAL = 100


def setup(p, at, move_id, attack, special, enemy_max):
    """Heal both sides and install the move and stats for the coming turn.

    GetCurrentMove takes the player's move from wTestBattlePlayerSelectedMove
    in a test battle and ignores the menu choice entirely, so that is the byte
    to write; the move list is set to match only so the menu and the PP counter
    agree with what actually happens.

    Everything is rewritten before every single turn rather than once per
    phase. The battle engine owns this memory and rewrites parts of it as the
    turn resolves, and the debug build restarts the battle from scratch if
    either side faints, which would quietly restore the real moveset.
    """
    write_word(p, at["wEnemyMonMaxHP"], enemy_max)
    write_word(p, at["wEnemyMonHP"], enemy_max)
    write_word(p, at["wBattleMonHP"], word(p, at["wBattleMonMaxHP"]))
    p.memory[at["wTestBattlePlayerSelectedMove"]] = move_id
    p.memory[at["wBattleMonMoves"]] = move_id
    p.memory[at["wBattleMonPP"]] = 40
    write_word(p, at["wBattleMonAttack"], attack)
    write_word(p, at["wBattleMonSpecial"], special)
    write_word(p, at["wEnemyMonSpecial"], ENEMY_SPECIAL)
    p.memory[at["wBattleMonSpecies"]] = SPECIES["attacker"]
    p.memory[at["wEnemyMonSpecies"]] = SPECIES["defender"]
    # Outrunning the opponent means the first damage of the turn is ours.
    write_word(p, at["wBattleMonSpeed"], 250)
    write_word(p, at["wDamage"], 0)


def take_turn(p, at, move_id, attack, special, enemy_max):
    """Attack with move 1 and return the damage dealt, or None if unusable.

    The reading comes from wDamage rather than from the enemy's HP. Watching HP
    means racing the HP bar animation and the fainting and restart logic, which
    produces occasional wild readings; wDamage is the number the damage formula
    just produced, which is exactly what this test is about.

    None means the turn did not give a clean reading. The caller retries rather
    than averaging a meaningless number in.
    """
    setup(p, at, move_id, attack, special, enemy_max)

    # FIGHT, then the first move in the list.
    tap(p, "a", hold=6, release=20)
    tap(p, "a", hold=6, release=20)

    # wDamage is written several times as a move resolves: CalculateDamage
    # produces a raw figure, AdjustDamageForMoveType applies the type chart and
    # RandomizeDamage applies the 217-255 spread. Only the last of those is the
    # damage the move really deals, so watch the whole of our half of the turn
    # and keep the final value, which is the one standing when hWhoseTurn flips
    # to the opponent.
    damage = None
    for frame in range(TURN_FRAMES):
        if frame % 8 == 0:
            p.button_press("a")
        elif frame % 8 == 2:
            p.button_release("a")
        p.tick()
        if p.memory[at["hWhoseTurn"]] == 0:
            current = word(p, at["wDamage"])
            if current:
                damage = current
        elif damage:
            break
    p.button_release("a")

    if damage is None:
        return None
    # A restart would have reverted both of these to the real values.
    if p.memory[at["wPlayerMoveNum"]] != move_id:
        return None
    if word(p, at["wBattleMonAttack"]) != attack:
        return None
    # On a critical hit the engine deliberately throws away the in-battle stats
    # and recalculates from the party Pokemon's own, so a crit ignores the
    # stats we wrote and tells us nothing.
    if p.memory[at["wCriticalHitOrOHKO"]]:
        return None
    return damage


def measure(p, at, move_id, attack, special, enemy_max):
    """Average damage over several turns with the given move and stats.

    Averaging matters: Gen 1 multiplies damage by a random 217-255 factor and
    can roll a critical hit, so a single turn is not a reliable reading.
    """
    samples = []
    for _ in range(SAMPLES * 6):
        if len(samples) == SAMPLES:
            break
        result = take_turn(p, at, move_id, attack, special, enemy_max)
        if result is not None:
            samples.append(result)
    return samples


def report(name, samples):
    if not samples:
        print(f"  {name:<28} no usable turns")
        return None
    mean = statistics.mean(samples)
    print(f"  {name:<28} {samples}  mean {mean:.1f}")
    return mean


def main():
    rom_path = sys.argv[1] if len(sys.argv) > 1 else "pokeblue_debug.gbc"
    sym_path = sys.argv[2] if len(sys.argv) > 2 else "pokeblue_debug.sym"

    try:
        p, at = enter(rom_path, sym_path)
    except NotReached as e:
        print(f"FAIL: {e}")
        return 1

    enemy_max = ENEMY_HP
    print(f"in battle, enemy has {enemy_max} HP")

    failures = []

    def compare(move_id, label, stat_name, expect_attack):
        print(f"{label}")
        by_attack = report(
            "Attack 250, Special 10", measure(p, at, move_id, HIGH, LOW, enemy_max)
        )
        by_special = report(
            "Attack 10, Special 250", measure(p, at, move_id, LOW, HIGH, enemy_max)
        )
        if by_attack is None or by_special is None:
            failures.append(f"{label}: could not get a clean reading")
            return
        high, low = (by_attack, by_special) if expect_attack else (by_special, by_attack)
        if high <= low * 2:
            failures.append(
                f"{label}: damage does not follow {stat_name} "
                f"({high:.1f} when {stat_name} is high, {low:.1f} when it is low)"
            )

    # Fire Punch is special in vanilla and physical after our change, so its
    # damage should now move with Attack.
    compare(FIRE_PUNCH, "FIRE_PUNCH (we made it physical)", "Attack", True)

    # Surf was special in vanilla and stays special. It is the control: if it
    # also followed Attack, the fault would be in the stat writes rather than in
    # the table lookup, and the Fire Punch result would prove nothing.
    compare(SURF, "SURF (unchanged control, still special)", "Special", False)

    # The special split. Both sides keep Rhydon's stats and types throughout;
    # only the species index the factor table is read with changes, so any
    # difference in damage can only have come from the factors.
    def with_species(attacker, defender):
        SPECIES["attacker"] = attacker
        SPECIES["defender"] = defender
        return measure(p, at, SURF, LOW, 200, enemy_max)

    print("special defence factor (defender's share of one Special stat)")
    vs_alakazam = report("defender Alakazam (12/16)", with_species(RHYDON, ALAKAZAM))
    vs_chansey = report("defender Chansey (24/16)", with_species(RHYDON, CHANSEY))
    if vs_alakazam is None or vs_chansey is None:
        failures.append("special defence factor: could not get a clean reading")
    elif vs_alakazam <= vs_chansey * 1.4:
        failures.append(
            "the defender's special defence factor is not being applied: "
            f"{vs_alakazam:.1f} against the frail defender, "
            f"{vs_chansey:.1f} against the sturdy one"
        )

    print("special attack factor (attacker's share of one Special stat)")
    as_alakazam = report("attacker Alakazam (20/16)", with_species(ALAKAZAM, RHYDON))
    as_chansey = report("attacker Chansey (8/16)", with_species(CHANSEY, RHYDON))
    if as_alakazam is None or as_chansey is None:
        failures.append("special attack factor: could not get a clean reading")
    elif as_alakazam <= as_chansey * 1.4:
        failures.append(
            "the attacker's special attack factor is not being applied: "
            f"{as_alakazam:.1f} from the strong attacker, "
            f"{as_chansey:.1f} from the weak one"
        )

    p.stop(save=False)

    print()
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("PASS: damage follows each move's category and each species' factors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
