# Changelog

All changes are against the vanilla Pokemon Red disassembly. The unmodified
build has sha1 `ea9bcae617fdf159b045185467ae58b2e4a48b9a`.

## Unreleased

Integration build sha1 `12c5666d59843b83594a294667e63b7e5d69d39c`.

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

- **Special attack and special defence are now separate in practice.** Vanilla
  stores one Special stat that a Pokemon both attacks and defends with, which is
  why Alakazam is at once the best special attacker in the game and an excellent
  special wall, and why Chansey hits as hard as it takes hits.

  Each species now carries two factors taken from its genuine Generation 2
  Special Attack and Special Defence, and the stored Special is scaled by
  whichever role it is playing at the moment damage is worked out. The pair is
  normalised to average out, so a species whose two Generation 2 values match is
  left exactly as it was; 110 of the 190 species are reshaped.

  This is a scaling layer rather than a seventh stat: stat experience, DVs and
  the badge boost still feed one stored Special. That limitation is recorded in
  `BUGS.md`. A real stored stat needs about 68 bytes of working RAM and there
  are 30.

- **The status screen shows special attack and special defence separately.**
  It used to show one SPECIAL row holding the unscaled stored value, which was
  wrong for every species whose two roles differ. It now shows SPA and SPD
  worked out with the same per-species factor the damage code uses. To fit a
  fifth row into the same box, each label now sits on the same row as its value
  and the labels are shortened to ATK, DEF, SPE, SPA and SPD. The level-up stats
  box uses the same layout.

- **Wrap, Bind, Fire Spin and Clamp no longer take the target's turns away.**
  In vanilla a trapping move removes the opponent's move menu entirely for the
  whole two to five turn duration, and a second trapping move started on the
  turn the first ends chains straight into another lockout. Against a faster
  Pokemon this can end a battle without the other side ever acting.

  The move now only does what its name suggests: it repeats and deals its
  damage each turn, and the target chooses a move every turn as normal. The
  duration, the damage and the user's own commitment to the move are unchanged.
  This is the Generation 2 treatment of the same move, with one difference
  recorded in `BUGS.md`: the target may also switch out, which Generation 2
  does not allow.

- **Hyper Beam always has to recharge.** In vanilla the recharge is applied by a
  move effect that runs after the engine has already returned early for a
  fainted target, so knocking a Pokemon out with Hyper Beam skips the recharge
  turn completely. That single omission is what makes Hyper Beam the defining
  move of Generation 1 competitive play. The recharge is now applied before the
  check for a fainted target, so it costs a turn whatever the outcome.

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
  190 evolution and learnset entries parse, the damage category table decodes to
  exactly the moves intended, and no special split factor is zero or leaves a
  species stronger overall.
- `splitcheck.py` - stages matchups in the debug battle and measures damage with
  one thing changed at a time, proving that a move's damage follows the stat its
  category selects rather than its type, and that each side's special split
  factor is really applied.
- `trapcheck.py` - stages a Wrap in the debug battle and confirms the opponent
  still acts while trapped, then knocks a target out with Hyper Beam and
  confirms the recharge is still applied. Both changes are deletions of a
  branch, which is the kind of change that fails silently.
- `statuscheck.py` - opens the status screen from the debug build's test battle,
  saves a screenshot, and decodes the stats box straight out of `wTileMap` so the
  labels and numbers can be asserted rather than eyeballed. The party Pokemon is
  turned into an Alakazam first, because its two special factors differ, so a
  swapped or unscaled SPA/SPD row fails. It then wins a battle one experience
  point short of a level and checks the level-up stats box the same way.
- `navigate.py`, `rominspect.py`, `debugbattle.py` - shared helpers for scripted
  input, for reading the ROM through the linker's own symbol names, and for
  dropping straight into the debug build's test battle.

Current headroom: ROM0 138 bytes free (-18), ROMX 161,097 free (-602), WRAM0 30
free (unchanged), HRAM 0 free (unchanged), SRAM 7,646 free (unchanged). No
change in this release consumes any RAM.
