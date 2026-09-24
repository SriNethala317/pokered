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
  1 HP. If the attacker has a Substitute up, the Substitute takes the counter
  instead, and a counter never breaks one. The result is shown as a badge for one second instead of a message, so
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

### Bond

- **Every Pokemon now has a Bond with you, from 0 to 255.** It is the first
  half of the Resonance system (see `docs/resonance-design.md`); Resonance
  itself is not in yet, so for now Bond only grows and falls.
  - It lives in the catch rate byte of each party and box Pokemon. Gen 1 never
    reads that byte again once a Pokemon exists (it only matters as a held item
    when trading to Gen 2), so Bond costs no RAM and survives the PC and saving.
  - Every new Pokemon starts at 0: caught, gifted, traded in the game or over
    the link cable. Your starter starts at 64.
  - It grows by 1 for the lead Pokemon every 16 steps (the first one that can
    still fight), and by 2 for every Pokemon that takes part in beating an enemy
    Pokemon. Exp. All shares experience but not Bond.
  - It falls by 10 when the Pokemon faints.
  - Saves from before this change keep the old catch rate in that byte, so
    their Pokemon start with a Bond equal to their species' catch rate.
  - A PERFECT or a COUNTER adds 1 to the Pokemon that landed it.

- **Resonance: fight as one with a Pokemon you have bonded with.**
  - **Unlock.** Brock's badge unlocks it and lifts the Pokemon you are closest
    to up to a resonant Bond of 200, so it is the first to Resonate. One text box
    in the badge scene explains the button; nothing is ever explained in battle.
  - **The meter.** Landed action commands fill a Resonance meter: PERFECT or
    COUNTER 2, GREAT or BRACED 1. It is drawn with the HP bar's own tiles in the
    empty space left of your Pokemon's level, and its cap turns into ▷ when
    Resonance is ready.
  - **Starting it.** Press SELECT on the battle menu with the meter full and a
    Pokemon with Bond 200 or more out. It takes no turn: the screen flashes
    twice (8 frames in all), the music changes to the final battle theme, and a
    RESONANCE! badge shows.
  - **While it lasts** (a few of your turns, ▶ on the cap):
    - your attacks do x1.5, on top of the action command bonus;
    - STAB moves land their secondary effect on any GREAT or PERFECT;
    - both timing windows are wider;
    - each PERFECT attack buys a turn back, up to the length it started with.
  - **Shared pain.** While it lasts the bar shows your HP as the trainer. Your
    Pokemon takes only 3/4 of each hit, and you lose a share of your bar equal
    to the share of max HP the Pokemon lost, scaled by the ramp. If your bar
    runs out, Resonance breaks (BROKEN!), the meter empties and you lose your
    next turn (STUNNED).
  - **When it ends.** It ends when its turns run out, the Pokemon faints or you
    switch out.
  - **The ramp.** Everything runs from one table by badge count
    (`ResonanceRamp`):

    | Badges | Meter | Turns | Wider windows | Pain |
    |---|---|---|---|---|
    | 0 | 6 | 3 | +6 frames | x1/2 |
    | 1-2 | 8 | 3 | +5 | x1/2 |
    | 3-4 | 9 | 3 | +4 | x3/4 |
    | 5-6 | 10 | 4 | +4 | x3/4 |
    | 7-8 | 12 | 4 | +3 | x1 |

  - **Battles do not get longer.** No text box is ever added in battle; every
    message is a badge on the action command line. The only extra frames are
    the 8 of the flash when you start it.
  - **What it costs.** The battle state is 4 bytes taken from padding that was
    already cleared with the battle data, so no RAM.
  - **Provisional choices,** made while you were away and easy to change:
    - the starter begins with 64 Bond;
    - the unlock is at Brock;
    - the final battle theme plays while it lasts.

### Play with friends in the browser (multiplayer, phases 0-3)

- **A web player** (`web/`, built with `make web`) runs the game in a phone or
  desktop browser with no app to install.
  - Each player loads their own Pokemon Red ROM. The page patches it with
    `pokered.bps` and refuses anything but this exact build.
  - It runs at 60 fps on SameBoy compiled to WebAssembly, with touch and
    keyboard controls, and saves in the browser with export and import.
- **Rooms with no server.**
  - Players join a room by code and an optional password, over WebRTC. Public
    Nostr relays introduce players to each other and see nothing else.
  - The room's creator approves every join and can kick, with up to 8 players.
    The creator relays for anyone who cannot connect directly.
  - Friends on the same map are drawn walking around, with name tags and chat.
  - Every packet is checked for shape, size and rate.
- **Trades and battles over the game's own link cable.** Two players accept a
  session in the page, and the page carries the link cable's bytes between
  them, exactly as a real cable does.
  - A session that goes quiet for 10 seconds ends. A game that was mid-link
    restarts from its last save.
  - A dropped trade leaves both saves as they were.
- **The ROM no longer trusts what the other Game Boy sends.** Gen 1 link
  trades are a known way to run arbitrary code, through glitch species and
  names with no terminator. Before the game uses a received party it now
  checks:
  - the count is 1 to 6, and the species list is terminated;
  - every species is real and matches its struct;
  - every move exists, every level is 1 to 100, and no HP is above its max;
  - every OT name and nickname ends inside 11 bytes.
  A party that fails any of these is never used: the player goes straight
  back to the Cable Club room.
- **The patch list is bounded.** The received patch list is walked for at most
  its 200 bytes, and a patch may only land inside the enemy party's data.
  Before, both were open-ended.
- **Not yet:**
  - GitHub Pages publishing (the deploy job is switched off until you approve
    it);
  - testing on real phones;
  - link battles, where only trades are tested;
  - faster trades. Every byte costs a round trip, so a trade takes about 2
    minutes at 100 ms.

### Battle environments and Field States

- **Every battle happens somewhere.** It can be grass, sea (surfing), a cave,
  a room, the Pokemon Tower, the snow of Seafoam, the sand of Cycling Road, or
  the wires of the Power Plant. The place shows as a small lowercase label
  right of the enemy's level.
- **Moves change the field for a few turns.** The label turns to capitals:
  - SOAK: Water. Electric is boosted and Fire halved.
  - ICE!: Ice on SOAK, or Ice in the snow. Ice is boosted, and physical moves
    may slip.
  - FIRE: Fire on grass. Fire is boosted, everyone else singes 1/16 a turn,
    and Water puts it out.
  - DUG!: Dig. The next Ground or Rock move is boosted.
  - RUBL: Earthquake or Rock Slide in a cave. It gives cover from the next
    attack half the time.
  - DUST: Sand-Attack or Gust on sand. Anyone but Rock and Ground types may
    miss.
  - ZAP!: Electric in the Power Plant. The next Electric move does x2, with
    recoil.
  - DARK: Smokescreen or Night Shade in the tower. Anything may miss, but
    Ghost moves always hit.
- **Improvise: press START on a move to use it on the battlefield.** The move
  deals no damage but leaves the state its type goes with, anywhere:
  - Water soaks the ground and Fire sets it alight;
  - Rock, Normal, Fighting and Grass bring down cover;
  - Electric charges the air;
  - and so on (`docs/field-states-design.md`).
  It needs Bond 100, can be used once every 3 turns, and a resonant Bond makes
  the state last 2 turns longer. It prints no text: an IMPROV! badge shows.
  Brock's badge scene explains the button.
- **Anime-style techniques, unlocked by Bond.**
  - Improvising Quick Attack, Agility or Double Team dodges the next attack.
  - Improvising while resonating is a Counter Shield: the attack goes ahead
    and the next hit on you is halved.
  - With Bond 150, a perfect brace against an attack your last move beats
    (Water on Fire, Electric on Water...) cancels it outright (CLASH!).
  - A Field State survives switching, so one Pokemon can set up a combo for
    the next.
- **The next field-changing move replaces the state.** Boosts, miss chances
  and durations grow with badges (`FieldRamp`). There is no text, so battles
  are no longer, and link battles have no field.
- **RAM.** It uses 4 bytes of RAM, which leaves 26 free. See
  `docs/field-states-design.md`.

### Trainer Dodge Phase

- **Gym leaders make you dodge in person.** The first damaging attack of each
  of a leader's Pokemon opens a small DODGE! arena over the battle screen for two and a
  half seconds.
  - You are the ♂, moved a tile at a time with the D-pad. A ▼ warns where a
    rock will fall, and then it falls row by row.
  - Each rock that hits you costs a quarter of your trainer HP bar, the one
    Resonance uses. Running it dry breaks Resonance and costs your next turn.
  - Getting through untouched halves the attack (DODGED!) and adds 3 to the
    Resonance meter.
  - It happens twice at most in Brock's battle, never against wild Pokemon or
    ordinary trainers, and never with action commands Off. Assist always uses
    the gentlest speed.
  - Rocks fall faster with more badges (`DodgeRamp`). The screen comes back
    exactly as it was.
  - It needs no new RAM beyond 4 bytes of padding, because the rocks live in
    the tilemap itself.
  - Every leader has a pattern of their own:
    - Brock: falling rocks.
    - Misty and Erika: waves and vines that sweep across with a gap.
    - Lt. Surge and Blaine: lightning and fire columns, warned twice before
      they strike.
    - Koga and Giovanni: poison and quake rows.
    - Sabrina: rocks with your left and right swapped.
  - See `docs/dodge-phase-design.md`.

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

- **Special attacks no longer cost two extra frames a turn.** Splitting the
  Special stat scaled it with the engine's general multiply and divide, which
  took about a third of a frame per attack and added a lag frame or two to every
  special move, even with action commands off. The factor is at most 32 and a
  stat at most 999, so it is now a 16-bit shift and add, about ten times faster.
  With action commands off, battles are now frame for frame the same length as
  vanilla.

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
- `netlink/linktest.py` - two consoles joined by a delayed cable: they
  connect, reach the Trade Center, swap parties and trade. `--drop` cuts the
  cable mid-trade and checks both saves; `--together` has both players talk to
  the receptionist at once. `--hostile species|name|move|count` has the guest
  send a party no real game could have, and checks the host refuses it. Its
  fixture now names the Pokemon it gives (the prompt it skips used to leave the
  name unwritten, which the ROM rightly refuses). `test/web/*.mjs` test the
  page's own code in node, including a full trade relayed through a third
  player.
- `fieldcheck.py` - staged turns with action commands Off, reading the damage
  as it enters the field code and as it is dealt:
  - each state is made by its move in its place and not elsewhere;
  - every boost, halving and the ZAP! doubling are exact;
  - the singe is 1/16;
  - DUG!, RUBL and ZAP! are used up, and not remade by the move that used them;
  - Ghost moves always hit in the dark;
  - a state lasts 5 turns, adds no text, and never appears in a link battle;
  - Improvise: refused at Bond 99; at Bond 100, START on Water Gun soaks a room
    with no damage and one PP spent; a second Improvise inside the wait is
    refused; Rock Throw gives cover, and lasts 2 turns longer with Bond 255.
  The Improvise check caught the turn count being lost to the Bond lookup, so
  a state lasted 0 turns (then 255). It also checks:
  - an improvised Quick Attack makes the next attack miss;
  - a Counter Shield still hits and halves the next attack exactly.
  `resonancecheck.py` checks a clash cancels Ember after Water Gun at Bond
  150, and only braces below that.
  It found a crash on the first draft: see `bankcheck.py`.
- `bankcheck.py` - reads every `.asm` file against the linker's symbols and
  fails on any plain `call`/`jp`/`jr` from one switchable ROM bank into
  another. Such a call runs whatever sits at that address in the current bank.
  The first draft of the field code called `BattleRandom` (bank $0F) from bank
  $2D this way, and crashed on a Rubble block.
- `battle.py` now also watches for `rst $38` directly. It lets a blank screen
  come back for up to 10 seconds before calling it a crash, because the debug
  battle's fade-in into the next battle is black too.
- `fuzzbattle.py` now also stands the battle in a random place and on a random
  Field State, and checks the field bytes stay in range.
- `dodgecheck.py` - fights Brock (a real trainer battle) and forces each
  outcome through the phase's own routines:
  - untouched gives DODGED!, half damage and a meter of 3;
  - one hit costs 6 and the attack lands in full;
  - running the bar dry gives BROKEN! and a lost turn;
  - the arena opens exactly once per Brock Pokemon;
  - the screen is restored byte for byte;
  - it never opens against a wild Pokemon, a Youngster or with Off;
  - it takes at most 160 frames.
  - For every leader, a dodging bot plays a real phase: the arena must open,
    show that leader's hazard, and restore the screen. Sabrina's RIGHT must
    move left.
- `resonancecheck.py` - staged turns in the debug battle, with three badges.
  - Nothing fills or shows before the unlock.
  - The meter fills by 2 and 1, and Bond by 1 on PERFECT and COUNTER only.
  - SELECT is refused one point short and at Bond 199, and starts Resonance
    otherwise.
  - The cap shows ▷ and ▶.
  - x1.5 your way and x3/4 theirs, and the trainer's loss matches the formula.
  - The perfect window is 4 frames wider.
  - A PERFECT buys a turn back, 3 at most, and it ends after its turns.
  - A turn with Resonance prints exactly as many texts as one without, and
    starting it takes 8 frames.
  - The trainer's last HP breaks it: BROKEN!, the meter empties, and the
    player's next move is CANNOT_MOVE.
  `fuzzbattle.py` now also unlocks it, gives Bond and a full meter at random,
  mashes SELECT, and checks the meter, pain and turns stay in range.
- `bondcheck.py` - plays the debug build to check Bond: every Pokemon the debug
  new game adds starts at 0, the 16th step gives the lead 1 and other steps
  nothing, a fainted lead is passed over, a win gives 2 (once, even with Exp.
  All in the bag), fainting costs 10, and Bond stops at 0 and 255.
- `trapcheck.py` now allows 1,500 frames for a Hyper Beam knockout turn. The
  recharge flag is set about 150 frames after the target's HP reaches 0, so a
  knockout late in a 900-frame turn could miss it and fail the check although
  the recharge was set.
- `actionedge.py` - action command cases the staged check and the wild fuzz
  cannot reach. It swaps the debug battle's wild Rhydon for a real trainer
  party, so the genuine trainer path runs, and checks:
  - Oak's tutorial text: shown once, never with the option Off, never in a
    wild battle;
  - Brock's timing over 24 turns;
  - a trainer's Pokemon fainting with a badge up, and the next one sent out
    with no badge left behind;
  - a counter into a Substitute;
  - link battles never arming;
  - 250 fuzzed trainer turns, checking that no move arms twice.
  This caught the counter going straight through a Substitute.
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
