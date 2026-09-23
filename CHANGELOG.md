# Changelog

All changes are against the vanilla Pokemon Red disassembly. The unmodified
build has sha1 `ea9bcae617fdf159b045185467ae58b2e4a48b9a`.

## Unreleased

Integration build sha1 `0fa85fc865313514b859e2015ed70b33f8459def`.

### Battle mechanics

- **Each move now has its own damage category.** In vanilla a move's type alone
  decides whether it uses Attack or Special: every Fire, Water, Grass, Electric,
  Psychic, Ice and Dragon move is special and everything else is physical. That
  is why Hitmonchan's elemental punches ignore its enormous Attack and why
  Kingler gets nothing out of Crabhammer. Moves are now looked up individually
  against the categories the series settled on from Generation 4 onward.

  Sixteen moves change hands. Fire Punch, Ice Punch, Thunder Punch, Vine Whip,
  Razor Leaf, Waterfall, Clamp and Crabhammer become physical; Razor Wind, Gust,
  Acid, Hyper Beam, Smog, Sludge, Swift and Tri Attack become special.

  Only the choice of attacking and defending stat changes. A move's type still
  decides same-type attack bonus and type effectiveness, so nothing about the
  type chart moves. Moves that deal fixed damage or are one-hit knockouts are
  left out, because they never consult these stats in the first place.

### Battle engine fixes

- **Focus Energy and Dire Hit now raise the critical hit rate.** In vanilla they
  divide the critical hit chance by four instead of multiplying it, so using
  them made a Pokemon *less* likely to land a critical hit. Both items and the
  move now work as their descriptions claim.
- **Fully accurate moves no longer miss.** Vanilla rolls against accuracy with a
  comparison that leaves a 1/256 chance of failure even at 100% accuracy. Swift
  and friends are now genuinely unmissable.
- **Badge stat boosts no longer stack.** Vanilla reapplies the badge bonus every
  time a stat changes in battle, so a long fight quietly inflated the player's
  stats well past their real values. The bonus is now applied once.
- **Psywave has a sane damage range.** The vanilla routine can roll damage far
  outside its intended band. It now produces damage between 1 and 1.5x the
  user's level on both the player's and the opponent's side.
- **Substitute uses the correct HP threshold and no longer bleeds damage
  through.** Vanilla lets Substitute be created at an HP value it should not
  allow, and damage past the substitute's HP leaked onto the user.

### Balance

- **Ghost is super-effective against Psychic.** Vanilla lists this matchup as an
  immunity, which is almost certainly a bug and which left Psychic with no
  counterplay at all.
- **Lick was raised from 20 to 50 base power.** Without this the Ghost change
  would have been cosmetic: Night Shade ignores the type chart entirely and
  Confuse Ray has no power, so Lick was the only move that could carry the
  matchup. See `BUGS.md` for the Night Shade limitation.
- **The weakest Bug moves were buffed** so Bug is a usable offensive type rather
  than a type the player never attacks with.
- **Nine unusable Pokemon received modest base stat increases:** Beedrill,
  Butterfree, Ditto, Dugtrio, Farfetch'd, Lickitung, Parasect, Raticate and
  Wigglytuff. The goal is to widen the set of viable teams, not to create new
  top-tier Pokemon.
- **The four trade evolutions now evolve by level instead.** Kadabra, Machoke,
  Graveler and Haunter can no longer be evolved at all in a single-player game,
  which cuts four Pokemon out of the roster for most players.

### Quality of life

- **Text speed defaults to fast.** The Options menu still works exactly as
  before, and existing saves keep whatever speed they had.
- **Hold B to walk at double speed.** This reuses the vanilla bicycle speedup, so
  step counting, encounter rates, warps and scripted movement are all unchanged.
  It is deliberately limited to walking on foot; surfing is not affected.
- **TMs are reusable.** They now behave like HMs and are never consumed. This
  removes the "permanently lost a TM" failure mode at the cost of the TM
  economy; the trade-off is deliberate.

### Testing

New checks under `test/`, all run against each build:

- `smoke.py` - the ROM boots and draws a screen.
- `romspace.py` - ROM and RAM headroom per region, with a delta against
  `baseline_space.json`, and a warning when a critical region runs low.
- `playable.py` - drives the intro with real inputs and confirms the player ends
  up in the world and responds to the D-pad.
- `battle.py` - enters the debug build's test battle and plays fourteen turns,
  confirming damage resolves, a Pokemon can faint, and the battle ends without
  crashing.
- `datacheck.py` - reads the built ROM back and checks the tables we edited: all
  190 evolution and learnset entries parse, and the damage category table
  decodes to exactly the moves intended.
- `splitcheck.py` - stages a matchup in the debug battle and measures damage
  with the attacker's Attack and Special swapped, proving that a move's damage
  follows the stat its category selects rather than its type.
- `navigate.py`, `rominspect.py`, `debugbattle.py` - shared helpers for scripted
  input, for reading the ROM through the linker's own symbol names, and for
  dropping straight into the debug build's test battle.

Current headroom: ROM0 138 bytes free (-18), ROMX 161,578 free (-121), WRAM0 30
free (unchanged), HRAM 0 free (unchanged), SRAM 7,646 free (unchanged). No
change in this release consumes any RAM.
