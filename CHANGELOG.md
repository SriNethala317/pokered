# Changelog

All changes are against the vanilla Pokemon Red disassembly. The unmodified
build has sha1 `ea9bcae617fdf159b045185467ae58b2e4a48b9a`.

## Unreleased

Integration build sha1 `493aea78c62e631b76d3973f106f9ffcabf722aa`.

### Action commands

- **Every damaging move now has a timing window.** While a move's animation
  plays, a cue appears under the opponent's HP box: "A!" when you are
  attacking, "B!" when you are being hit. Pressing the right button in time
  changes the damage:

  | Press | Your attack (A) | Their attack (B) |
  |---|---|---|
  | Within the perfect window | PERFECT: x1.5 damage | COUNTER: x0.5 damage, and a quarter of the damage blocked is dealt back |
  | Within the good window | GREAT: x1.5 damage | BRACED: x0.5 damage |
  | Too late, or not at all | normal damage | normal damage |
  | Before the cue, or the wrong button | TOO SOON: normal damage | TOO SOON: normal damage |

  The cue comes a random 4 to 11 frames after the move starts, so it cannot be
  learned as a fixed beat, and pressing early locks you out for that attack so
  mashing never pays. How wide the windows are depends on your badges (see the
  difficulty ramp below). A counter can never knock the attacker out; it stops at
  1 HP. The result is shown as a badge for one second instead of a message, so
  nothing waits for a button.

  **Battles do not get longer.** The window runs during the animation that was
  already playing. If an animation finishes first, the window is held open for
  at most 20 frames; across the test's 205 staged attacks, at every badge
  count, the most it ever added was 13. With battle animations off, it runs inside the existing half-second
  pause.

  The bonus is applied once per attack, just before the damage is dealt, so
  multi-hit moves reuse it on every hit rather than compounding it, and moves
  that deal fixed damage or knock out outright are left alone. Link battles
  never use it.

- **Easy at the start, hard toward the end.** Your badge count picks one row
  of a single table (`ActionRamp` in `engine/battle/action_commands.asm`):

  | Badges | Perfect / good window | Inputs in use | Trainers time an attack | Feints before a brace |
  |---|---|---|---|---|
  | 0 | 18 / 30 frames | Tap only: every type taps | never | never |
  | 1-2 | 16 / 26 | Tap, Snap, Rapid | 10% | never |
  | 3-4 | 15 / 24 | all five | 20% | never |
  | 5-6 | 14 / 21 | all five | 35% | 1 in 6 |
  | 7-8 | 13 / 19 | all five | 50% | 1 in 4 |

  A type whose input is not in use yet taps instead. Even the last row stays
  within human reaction time, so most of the extra difficulty comes from the
  inputs, the feints and the trainers rather than from windows too short to
  hit.

- **Trainers time their attacks too.** In trainer battles only (never against
  wild Pokemon), each attack rolls against the row's chance. Gym leaders,
  Giovanni, your rival and the Elite Four get an extra 15%.
  - On their attack, a timed hit does x1.5 (FOE GREAT). Bracing still halves
    it, so a perfect brace brings it back to about x0.75.
  - On your attack, a trainer that times it braces: a GOOD hit gets no bonus
    (FOE BRACED). A PERFECT hit goes through as usual.

  A trainer's timing only ever adds to their damage or takes away your bonus,
  so battles never get longer than vanilla because of it.

- **Feints.** From 5 badges, the cue to brace can be faked. A `B?` shows first,
  and the real `B!` follows 6 to 9 frames later. Pressing on the feint is TOO
  SOON. Feints never come before your own attacks or a Hold.

- **Streaks.** Every GOOD or PERFECT, attacking or bracing, adds to a streak for
  the battle. Anything else resets it. With 3 or more in a row, a PERFECT
  attack does x2 instead of x1.5 (PERFECT×2).

- **Oak explains it once.** At the start of the rival battle in Oak's lab, one
  text box says what the cues mean. It never shows again, and it is skipped
  when the option is Off.

- **The move's type picks the input.** Each type has its own pattern, so the
  same press is not asked for every turn:

  | Pattern | Types | Cue | Input |
  |---|---|---|---|
  | Tap | Normal, Flying, Bug, Ghost, Dragon | `A!` | one press |
  | Snap | Electric, Psychic | `A!!` | one press in less time: 3 frames off the perfect window and 6 off the good one |
  | Hold | Water, Ice | `HOLD A`, then `LET GO!` | hold the button once HOLD shows, and let go on the cue. Letting go early is TOO SOON; not holding when the cue comes does nothing |
  | Rapid | Fighting, Rock, Ground | `A×3`, counting down | three presses; judged on the third, with 12 extra frames to fit them |
  | Double | Fire, Grass, Poison | `A!`, then `   A!` | a press on each of two cues 6 to 9 frames apart; the result is the worse of the two, and missing the second loses the first |

  When you are being hit, the same patterns ask for B.

  Gen 1 quirk: Karate Chop is Normal-type, so it taps.

- **A move's power sets its tempo.** The lead-in grows by a frame for every 32
  power, so big moves wind up visibly longer, and moves of 100 power or more
  lose 2 frames from the perfect window.

- **A perfect hit makes sure of the secondary effect.** A PERFECT attack always
  lands its move's secondary effect: Ember always burns, Confusion always
  confuses, Bite always flinches, Acid always lowers Defense. A perfect brace
  (COUNTER) stops the attacker's secondary effect entirely.

  These still block the effect as before:
  - Substitute;
  - a target that already has a status;
  - a target of the same type as the move.

  Good results roll as usual.

- A cue now plays a short click (the A/B press sound) when it appears.

- Fixed: a result badge that was still on screen at the end of a turn was
  saved with the screen, and came back for good when the battle menu restored
  it. The badge is now cleaned from the saved copy as well.

- **An Action Commands option: On, Assist or Off.** It lives in two unused bits
  of the saved options byte. On is the default, including for existing saves.
  Assist widens the window to 20 and 32 frames at every badge count, and turns
  off trainer timing and feints; the inputs still unlock as usual. Off turns it
  off entirely, with no windows and vanilla damage. The text speed code masks
  these bits out: before this, setting either bit would have broken text speed.

- **The Options screen has an ACTION COMMANDS row** with ON, ASSIST and OFF,
  moved between with left and right like text speed. To fit it, the screen is
  now four boxes of two lines each, the label with its choices straight below,
  and CANCEL underneath; up and down wrap between the top row and CANCEL as
  before.

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

### Sharing the hack

- **`make bps` writes `pokered.bps`,** patches against the
  retail games that any BPS patcher can apply (Floating IPS, Rom Patcher JS, or
  the one built into most emulators), so the hack can be shared without handing
  out a ROM. Each is about 37 KB.
  - The base is the unmodified game. A `baserom_red.gbc` or `baserom_blue.gbc`
    is used if present. Otherwise `tools/make_bps.py` builds the vanilla
    disassembly (commit `a1a22aaf`, the tip of `master`) in a temporary git
    worktree, checks it against the retail sha1, and keeps it as the baserom
    for next time.
  - Every patch is decoded again and applied to its base before it is kept,
    and the result has to match the built ROM byte for byte.
  - `python3 tools/make_bps.py --apply base.gbc patch.bps out.gbc` applies a
    patch, and refuses a base that is not the game the patch was made from.

### Testing

New checks under `test/`, all run against each build:

- **Only Red is built.** `make` now builds `pokered.gbc` and a new
  `pokered_debug.gbc`. Blue's targets are still in the Makefile but are no
  longer built, patched or tested, and every battle check runs on the Red
  debug build. `make bps` writes `pokered.bps` only.
- `fuzzbattle.py` - plays hundreds of turns of the debug battle with a random
  move on each side (every move that keeps a wild battle going), random badges,
  option, animation setting, HP and streak, and buttons mashed on almost every
  frame. With `--trainer`, each attack is armed as if against a trainer, so
  trainer timing and feints are fuzzed too. At every battle menu it checks for
  a crash, a window left open, a cue or badge stuck on screen or in the saved
  screen, HP above max and changed text speed bits, and it fails if the battle
  menu stops coming back. About 6,000 turns over 25 seeds pass.

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
  swapped or unscaled SPA/SPD row fails. It then checks the level-up stats box
  through both of its callers: winning a battle one experience point short of a
  level, and using a Rare Candy from the debug new game's bag.
- `actioncheck.py` - stages turns in the debug battle where both sides use the
  same move, and presses A or B at exact frames after the cue. Each pattern is
  staged with a move of its type and checked both ways: its own input succeeds
  and a plain tap does not. It also checks that a perfect Ember burns three
  times out of three, and that a perfect brace blocks the burn. It hooks the engine
  to read the damage just before and just after the bonus, so the x1.5, x0.5
  and counter amounts are checked exactly. Also covers pressing late, early and
  with the wrong button, a counter against a 1 HP attacker, Doubleslap not
  compounding the bonus, Assist, animations off, and Off never arming. It also
  enforces the battle-length budget: it counts the frames each window adds to
  every attack and fails above 20. It writes `wObtainedBadges` before each turn:
  the pattern checks use three badges, and a ramp section walks every row,
  checking its perfect, good and too-late timings and that the longest inputs
  still fit the budget. It also checks that inputs not yet in use tap; that a
  press on a feint is TOO SOON and a press on the real cue after one is
  perfect; FOE GREAT and FOE BRACED with a trainer's timing forced on; the real
  roll (by making the battle look like a trainer battle only while the attack
  is armed: about half of 16 attacks timed on the last row, never against a
  wild Pokemon, no feints before five badges, none with Assist); and the
  streak doubling a perfect hit. `splitcheck.py`, `trapcheck.py` and
  `statuscheck.py` now turn action commands off, because they press A to
  advance text and measure damage, and a press that landed in a window would
  scale it. `battle.py` leaves them on, so it now plays a full battle with the
  feature live.
- `optionscheck.py` - boots the retail ROM to the main menu, opens OPTION and
  reads the screen out of `wTileMap`: every label, choice line and CANCEL must
  sit where the cursor code expects it, inside its box. It then walks the new
  row left and right past both ends, checks `wOptions` after every press, and
  changes each older row to prove none of them disturbs another. Finally it
  closes the menu, opens it again, and checks every cursor comes back from the
  saved byte.
- `navigate.py`, `rominspect.py`, `debugbattle.py` - shared helpers for scripted
  input, for reading the ROM through the linker's own symbol names, and for
  dropping straight into the debug build's test battle.

Current headroom: ROM0 118 bytes free (-20), ROMX 175,746 free (+14,047:
bank $2D, previously unused, now holds the new combat code and has 14,984
bytes left of its 16,384), WRAM0 30 free (unchanged), HRAM 0 free (unchanged),
SRAM 7,646 free (unchanged). No change in this release consumes any RAM: the
action command state lives in padding that was already there.
