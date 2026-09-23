"""Read the built ROM back and check the data tables we edited.

Assembling without an error does not mean a table is right. Two of ours are
easy to break silently: the evolution and learnset table is reached through a
pointer table, so one malformed entry shifts the meaning of every later
species, and the damage category table is a bit array where an off-by-one
would quietly move every move into the wrong column.

Usage:
    python test/datacheck.py pokered.gbc pokered.sym
"""
import sys

from rominspect import load_symbols, rom_offset

NUM_POKEMON_INDEXES = 190
NUM_ATTACKS = 165

# Moves whose damage category we deliberately changed away from vanilla. In
# vanilla the move's type decides this: Fire, Water, Grass, Electric, Psychic,
# Ice and Dragon moves are special and everything else is physical.
NOW_PHYSICAL = {
    7: "FIRE_PUNCH", 8: "ICE_PUNCH", 9: "THUNDERPUNCH", 22: "VINE_WHIP",
    75: "RAZOR_LEAF", 127: "WATERFALL", 128: "CLAMP", 152: "CRABHAMMER",
}
NOW_SPECIAL = {
    13: "RAZOR_WIND", 16: "GUST", 51: "ACID", 63: "HYPER_BEAM",
    123: "SMOG", 124: "SLUDGE", 129: "SWIFT", 161: "TRI_ATTACK",
}


def check_evos_moves(rom, sym):
    """Walk every species' evolution and learnset entry looking for desync."""
    bank, addr = sym["EvosMovesPointerTable"]
    table = rom_offset(bank, addr)
    problems = []
    for idx in range(1, NUM_POKEMON_INDEXES + 1):
        lo = rom[table + (idx - 1) * 2]
        hi = rom[table + (idx - 1) * 2 + 1]
        ptr = lo | (hi << 8)
        if not 0x4000 <= ptr < 0x8000:
            problems.append(f"index {idx}: pointer ${ptr:04x} is outside the bank window")
            continue
        p = rom_offset(bank, ptr)
        # Evolutions first, terminated by $00.
        for _ in range(10):
            kind = rom[p]
            if kind == 0:
                break
            if kind == 1:  # EV_LEVEL: kind, level, species
                if not 1 <= rom[p + 1] <= 100:
                    problems.append(f"index {idx}: evolution level {rom[p + 1]}")
                p += 3
            elif kind == 2:  # EV_ITEM: kind, item, 1, species
                p += 4
            elif kind == 3:  # EV_TRADE: kind, 1, species
                p += 3
            else:
                problems.append(f"index {idx}: evolution type {kind} is not 1, 2 or 3")
                break
        else:
            problems.append(f"index {idx}: evolution list never terminated")
            continue
        p += 1
        # Then (level, move) pairs, terminated by $00.
        for _ in range(30):
            if rom[p] == 0:
                break
            if not 1 <= rom[p] <= 100:
                problems.append(f"index {idx}: learn level {rom[p]} out of range")
            if not 1 <= rom[p + 1] <= NUM_ATTACKS:
                problems.append(f"index {idx}: move id {rom[p + 1]} out of range")
            p += 2
    return problems


def special_move_ids(rom, sym):
    """Decode the damage category bit array into the set of special move ids."""
    bank, addr = sym["SpecialMoves"]
    base = rom_offset(bank, addr)
    ids = set()
    for index in range(NUM_ATTACKS):
        byte = rom[base + index // 8]
        if byte >> (index % 8) & 1:
            ids.add(index + 1)
    return ids


def main():
    rom_path = sys.argv[1] if len(sys.argv) > 1 else "pokered.gbc"
    sym_path = sys.argv[2] if len(sys.argv) > 2 else "pokered.sym"

    with open(rom_path, "rb") as f:
        rom = f.read()
    sym = load_symbols(sym_path)

    failures = []

    problems = check_evos_moves(rom, sym)
    print(f"evos_moves      : {NUM_POKEMON_INDEXES} entries parsed, {len(problems)} problems")
    for p in problems[:10]:
        print(f"  {p}")
    failures += problems

    special = special_move_ids(rom, sym)
    print(f"damage categories: {len(special)} of {NUM_ATTACKS} moves are special")
    for move_id, name in sorted(NOW_PHYSICAL.items()):
        if move_id in special:
            failures.append(f"{name} should be physical but is marked special")
    for move_id, name in sorted(NOW_SPECIAL.items()):
        if move_id not in special:
            failures.append(f"{name} should be special but is marked physical")
    # Spot check two moves that must not have moved either way.
    if 57 not in special:  # SURF
        failures.append("SURF should still be special")
    if 89 in special:  # EARTHQUAKE
        failures.append("EARTHQUAKE should still be physical")

    # Balance edits that other checks depend on.
    bank, addr = sym["Moves"]
    lick_power = rom[rom_offset(bank, addr) + (122 - 1) * 6 + 2]
    print(f"Lick base power : {lick_power} (vanilla 20)")
    if lick_power != 50:
        failures.append(f"Lick base power is {lick_power}, expected 50")

    bank, addr = sym["TypeEffects"]
    i = rom_offset(bank, addr)
    ghost_psychic = None
    while rom[i] != 0xFF:
        if rom[i] == 0x08 and rom[i + 1] == 0x18:  # GHOST vs PSYCHIC_TYPE
            ghost_psychic = rom[i + 2]
        i += 3
    print(f"Ghost vs Psychic: {ghost_psychic} (20 = super effective, vanilla 0 = immune)")
    if ghost_psychic != 20:
        failures.append(f"Ghost vs Psychic is {ghost_psychic}, expected 20")

    print()
    if failures:
        for f in failures[:20]:
            print(f"FAIL: {f}")
        return 1
    print("PASS: every table reads back as intended")
    return 0


if __name__ == "__main__":
    sys.exit(main())
