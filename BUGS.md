# Known issues and engine limitations

Tracked per the project's bug process: reproduce, isolate, fix, add a regression
check, log it here. Entries stay until they are fixed or consciously accepted.

Priority order: crashes and save corruption > softlocks > wrong game logic >
balance > visuals and text.

---

## Open

### Night Shade ignores the type chart

**Severity:** wrong game logic (affects balance)
**Found:** during the Ghost vs Psychic balance change
**Status:** open, needs an engine change

Night Shade is handled in `SetDamageEffects`, so `PlayerCalcMoveDamage`
(`engine/battle/core.asm:3134`) branches past `AdjustDamageForMoveType`
entirely. The move therefore never consults `TypeEffects` at all: it still hits
Normal types, and it gains nothing from Ghost being super-effective against
Psychic.

This matters more than it looks. Ghost has only three moves in Gen 1 — Night
Shade, Lick and Confuse Ray. Confuse Ray has 0 power and Night Shade skips the
type chart, so making Ghost super-effective against Psychic would have applied
to Lick alone. Lick was buffed from 20 to 50 base power so the matchup has a
real carrier, but Night Shade itself is still type-blind.

Fixing it properly means routing fixed-damage moves through the type chart for
the immunity and effectiveness check while keeping their damage fixed. That is
an engine change and was deliberately not attempted alongside the data change.

### Buffed Pokemon give unchanged base experience

**Severity:** balance
**Status:** open, needs a deliberate decision

Nine species received base stat increases but their `base exp` values were left
untouched, so they now give the same experience for more power. This slightly
distorts the levelling curve. Left alone on purpose rather than changed
silently, because it shifts pacing across the whole game.

---

## Accepted / won't fix

Nothing yet.

---

## Verification gaps

These are not bugs, but they are things we currently cannot prove:

- **Battles run, but no specific changed matchup has been observed.**
  `test/battle.py` now plays a real fourteen-turn battle in the debug build:
  damage resolves, a Pokemon faints, and the battle ends and restarts cleanly.
  That rules out a crash in the battle loop. It does not show Lick connecting
  with an Alakazam, a Focus Energy critical hit, or a Substitute absorbing a
  hit. Each changed mechanic still needs a matchup built for it.
- **Data changes are verified by reading the ROM, not by playing.** All 190
  evolution and learnset entries parse correctly out of the built ROM, and the
  Lick and type chart edits read back with the expected values. Nobody has
  evolved a Kadabra at level 40 in game.
- **There is no harness for calling a battle routine directly.** Setting up
  WRAM, pointing the CPU at a routine such as `AdjustDamageForMoveType` and
  reading the result back would test a changed calculation exactly, without
  needing a matchup to occur naturally. A working version of this was built and
  then removed: it returns correctly for short routines but faults into `rst38`
  as soon as the call reaches the engine's multiply and divide helpers, and the
  cause was not found. It is worth another attempt, because it is the cheapest
  way to prove the damage changes.
- **Completability is unproven.** `test/playable.py` proves the intro finishes
  and the player responds to input. It does not prove the game can be finished.
  An attempt at a full scripted opening run got as far as the bedroom, the
  stairs, the front door and Pallet Town, then stalled finding the gap in the
  fence at the north edge of Pallet, which is what triggers Oak's event and
  gates the starter. Solving that routing problem is the first step toward a
  run-to-credits harness.
