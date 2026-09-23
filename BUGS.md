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

### The status screen still shows a single SPECIAL

**Severity:** wrong information shown to the player
**Found:** while splitting Special into an attacking and a defending role
**Status:** open, needs a screen layout change

Damage now scales one stored Special stat by a per-species factor, so a
Pokemon's real special attack and special defence differ. The status screen
still shows one SPECIAL row holding the unscaled stored value, which is the
truth for no species whose two factors differ, and that is 110 of them.

Fixing it means finding room for a fifth stat row. The stats box is eight rows
tall starting at row 8 and the four existing rows are spaced two rows apart, so
a fifth row does not fit without reworking the spacing and the box height. That
is a visual change, and there is currently no harness that can open the status
screen and take a screenshot, so it would ship unverified. It is deliberately
left for the Pallet-to-Brock tuning pass, where the screen gets looked at.

### Special split is applied at damage time, not stored

**Severity:** balance
**Status:** accepted for now, recorded so it is not mistaken for a real stat

Stat experience, DVs and the badge boost all still feed the one stored Special
stat. The split is a scaling layer applied when damage is worked out, not a
seventh stat. In play it gives the intended result, and it costs no RAM, which
a real stat cannot: a stored special defence needs roughly 68 bytes of WRAM0
across the party, the box cache, `wBattleMon` and `wEnemyMon`, and 30 are free.

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

- **Battles run, but most changed matchups have still not been observed.**
  `test/battle.py` plays a real fourteen-turn battle in the debug build: damage
  resolves, a Pokemon faints, and the battle ends and restarts cleanly. That
  rules out a crash in the battle loop. `test/splitcheck.py` goes further for
  one change only, the physical/special split, by staging a specific matchup and
  measuring damage. Lick connecting with an Alakazam, a Focus Energy critical
  hit and a Substitute absorbing a hit are all still unobserved.
- **The damage category test cannot observe critical hits.** On a critical hit
  the engine deliberately discards the in-battle stats and recalculates from the
  party Pokemon's stored stats, so the stat values `test/splitcheck.py` writes
  are ignored and the turn proves nothing. The test detects and discards these
  turns. A move's category on a critical hit is therefore untested, although it
  runs through exactly the same lookup.
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
