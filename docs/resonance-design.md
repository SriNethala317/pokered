# Bond and Resonance (build step 4)

Design notes for combat layer B of the brief. Written 2026-09-24 during an
unattended session; anything marked **provisional** is a call made without the
user and is easy to change.

## Bond

- One byte per Pokemon, 0-255, stored in the party/box struct's catch rate slot
  (`MON_CATCH_RATE`, aliased `MON_BOND`). Gen 1 never reads that byte after a
  Pokemon is created (it is only the Gen 2 held item), so Bond costs no RAM and
  survives the PC and saving.
- Starts at 0 for every new Pokemon: caught, gifted, traded in-game or over the
  link. The starter starts at **64** (provisional): it is your partner from the
  first minute.
- Grows by:
  | Source | Amount |
  |---|---|
  | Walking with it as the lead, every 16 steps | +1 |
  | Taking part in a win (per enemy Pokemon beaten) | +2 |
  | A PERFECT or COUNTER landed while it is out | +1 |
  | Fainting | -10 |
- **Resonant** Bond is 200 or more. Only a resonant Pokemon can Resonate.
  A Pokemon walked as the lead reaches it in roughly 2,000 to 3,000 steps with
  normal battling, and the starter reaches it at about Brock.

## Unlock (story moment, provisional)

Resonance is locked until `EVENT_RESONANCE_UNLOCKED`, set when Brock hands
over the Boulder Badge. At that point the starter's Bond is raised to at least
200, so it is the first to resonate. One line of text in the badge scene
explains the SELECT button. No text in battle.

## Resonance Meter (battle-only)

- Fills from action commands: PERFECT or COUNTER +2, GREAT or BRACED +1.
  Anything else adds nothing (no penalty: missing is its own punishment).
- It is kept across the enemy trainer's Pokemon and across your switches, and
  resets at the end of the battle.
- Drawn in four tiles on row 8 of the player's HUD, left of the level,
  with the HP bar's own segment tiles (32 steps). It is hidden until Resonance
  is unlocked.

## Resonance Mode

- **Activation:** press SELECT on the battle menu when the meter is full and
  the Pokemon out is resonant. It is a free action: no turn is used and no text
  box appears. The screen flashes (BGP inverted for 4 frames, twice) and the
  music changes.
- **Duration:** a number of your turns, from the ramp. A PERFECT during
  Resonance refunds that turn (the chain), up to twice the base length.
- **Surge:** your attacks do x1.5 (they stack with the action command bonus).
- **Resonant moves:** STAB moves make sure of their secondary effect on GOOD
  as well as PERFECT.
- **Wider windows:** the perfect and good windows are wider by the ramp's
  bonus.
- **Shared pain:** a trainer HP bar replaces the meter tiles (32 steps, full at
  the start of each battle). While resonating, your Pokemon takes 3/4 of the
  damage it is dealt. The trainer loses the fraction of their bar equal to the
  fraction of max HP the Pokemon lost, times the ramp's pain factor. At 0,
  Resonance breaks: the meter empties, a BROKEN! badge shows, and your next
  turn is skipped (STUNNED badge, no text box).
- Resonance also ends when the Pokemon faints or is switched out.
- **Music (provisional):** the final battle theme, or the gym leader theme when
  the final battle theme is already playing.

## Ramp (one table by badge count, like ActionRamp)

| Badges | Meter points | Turns | Window bonus | Pain factor |
|---|---|---|---|---|
| 0 | 6 | 3 | +6 | 1/2 |
| 1-2 | 8 | 3 | +5 | 1/2 |
| 3-4 | 9 | 3 | +4 | 3/4 |
| 5-6 | 10 | 4 | +4 | 3/4 |
| 7-8 | 12 | 4 | +3 | 1 |

## Battle-length budget

- No new text boxes in battle, ever. Activation, break and stun all use the
  badge line.
- Activation flash: 8 frames, at most once per activation.
- The meter and trainer bar redraw inside existing HUD redraws, not in extra
  frames.
- **Test (`test/resonancecheck.py`):**
  - The meter fills by the table.
  - SELECT activates only when full, resonant and unlocked.
  - Damage is x1.5, and pain is shared.
  - A break stuns for one turn.
  - A PERFECT refunds a turn, capped.
  - Bond changes by the table, and Bond survives a save/reload.
  - The PrintText count in a staged battle is the same with Resonance used
    as without.
  - Activation adds at most 8 frames.

## RAM

Battle state is 4 bytes, taken from the `ds 8` padding before
`wMiscBattleDataEnd`:
- `wResonanceMeter`
- `wResonanceTurns`
- `wTrainerHP`
- `wResonanceFlags` (active, stunned, chain count bits)

That block is cleared with the rest of the battle data at the start of every
battle.
