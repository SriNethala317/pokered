# Pokémon Red ROM Hack — Design Brief for Claude Code

## Goal
Build a unique, immersive Pokémon game from the Pokémon Red source code. Big changes are welcome: story, maps, mechanics, trainers, and combat can all change. It should feel like a new game, not a patch.

## Starting point
- I own a ROM of: **Pokémon Red** [FILL IN region, e.g. US/English]
- Source project: **pret/pokered** — https://github.com/pret/pokered
- Game Boy assembly (not C), built with **RGBDS**. Follow the repo's INSTALL.md for the correct RGBDS version.
- Build the unmodified project first and confirm it matches my ROM before changing anything.
- Test in mGBA (or another Game Boy emulator).

---

# CONCEPT: "RESONANCE" (working title)

**Pitch:** You're not just a trainer giving orders — you fight *with* your Pokémon. The better you know your partner, the more the line between you blurs, until you're moving as one (inspired by Ash & Greninja's Bond Phenomenon). Kanto is open to explore in almost any order, and every region hides bosses, challenges, and mini-games.

## 1. Combat systems

The game uses **several combat layers**, not just standard Pokémon battles. Build them in this order (simplest first).

### A. Action Commands — for every battle (from Super Mario RPG / Paper Mario / Clair Obscur)
- When your Pokémon attacks, a timing cue appears; press A on the beat for a **"Great!" bonus** (extra damage or a guaranteed secondary effect).
- When the enemy attacks, press B at the right moment to **brace** (reduce damage). A perfect brace = **"Counter!"** chip damage back.
- Each move type has its own timing pattern (e.g. Fighting = rapid taps, Water = hold and release, Electric = one sharp press) so battles never become "mash A."
- Must be toggleable in Options (Off / Assist / On) so it never feels mandatory.

### B. Resonance Meter — the Bond system (Ash-Greninja inspired)
- Each Pokémon has a hidden **Bond** value that grows by walking together, winning, landing Action Commands, and not letting it faint.
- In battle, a **Resonance Meter** fills from perfect Action Commands.
- When full, activate **Resonance Mode** for a few turns:
  - Your Pokémon gets a stat surge and a special "Resonance" version of one of its moves.
  - Action Command windows get wider and chain into combos.
  - **The catch — shared pain:** the trainer gets their own small HP bar. While in Resonance, the trainer takes a share of damage your Pokémon takes. If trainer HP hits 0, Resonance breaks and you're stunned for a turn.
  - Only Pokémon with max Bond can Resonate; your starter unlocks it first as a story moment.
- Show Resonance with a palette flash / screen effect and a unique battle theme.

### C. Trainer Dodge Phase — boss-only (from Undertale and Pokémon Legends: Arceus)
- During certain boss attacks, the battle switches to a **small arena where you control the trainer** (a heart/cursor or trainer sprite) and dodge projectiles for a few seconds.
- Each boss has a unique pattern themed on its type (Brock: falling rocks, Misty: wave sweeps, Lt. Surge: lightning grids, Sabrina: mirrored movement).
- Getting hit damages the trainer's HP bar (the same one used by Resonance).
- Fully dodging a pattern builds Resonance quickly.

### D. Frenzy Bosses — overworld encounters (from Legends: Arceus Noble battles)
- Giant, rampaging Pokémon fought on the overworld map, not in the battle screen.
- Their attacks are telegraphed tile patterns; you move to dodge, then interact with a stunned boss to **throw a lure/item** at it (lowering its Frenzy gauge) or **send out your Pokémon** for a short standard battle.
- Deplete the gauge to calm it — then it can join you or reward you.
- Candidates: Snorlax, Onix, the three legendary birds, Mewtwo as the final one.

### E. Creative Moves & Battle Environments (inspired by how the anime uses moves)
In the anime, moves aren't just damage — Pokémon use them to reshape the battlefield, defend, and set up combos. This system brings that in.

**Battle environments**
- Every battle has an **environment** based on where it happens: Grass, Water/Shore, Cave/Rock, Indoor/Gym, Tower (dark), Snow (Seafoam), Sand (routes/Cycling Road), Power Plant.
- Gym and boss arenas have **interactive features**: rocks, water pools, pipes, tall grass, pillars, electric panels.
- Show the environment and its current state with a small icon/label and palette tint (Gen 1 has no battle backgrounds).

**Moves change the field (Field States)**
A move can leave a lasting effect for a few turns that changes what other moves do. Examples:
- **Surf / Water Gun → Soaked field:** Electric moves hit harder and can hit both sides; Fire moves weaker.
- **Ice Beam on a Soaked field → Frozen field:** everyone's speed drops, physical moves may slip (miss chance), Ice moves stronger.
- **Ember / Flamethrower on Grass → Burning field:** chip damage each turn to non-Fire types until it's put out with a Water move.
- **Dig → Tunnels:** the next Ground or Rock move gets bonus power; the user can hide again faster.
- **Earthquake / Rock Slide in a Cave → Rubble:** creates cover — the next incoming attack has a chance to be blocked.
- **Sand-Attack / Gust on Sand → Sandstorm:** lowers accuracy for non-Rock/Ground types.
- **Thunderbolt in the Power Plant → Overcharge:** the next Electric move is boosted, but recoil hits the user.
- **Smokescreen / Night Shade in the dark Tower → Blackout:** both sides' accuracy drops; Ghost moves always hit.
- The field state can be cleared or overwritten by the next field-changing move, so battles become a tug-of-war over the arena.

**Improvise command**
- Add an **IMPROVISE** option next to FIGHT. Pick a move + a target in the environment instead of the opponent (e.g. use Rock Throw on the ceiling to drop rocks, Water Gun on the ground to create a Soaked field, Vine Whip on a pillar to swing out of the next attack).
- Improvise is limited per battle (e.g. once every few turns) and needs a minimum Bond with that Pokémon.
- High-Bond Pokémon unlock better Improvise options.

**Anime-style defensive and combo techniques** (unlocked through Bond and story moments)
- **Counter Shield:** a spinning move combined with an attack (e.g. Rapid Spin/Thrash + Thunderbolt) that attacks and blocks at the same time.
- **Move-as-shield:** use an attack to cancel an incoming one (Flamethrower vs. Water Gun clash) — with Action Commands, a perfect timing press wins the clash.
- **Mobility dodge:** use Quick Attack or Agility to dodge the next hit instead of dealing damage.
- **Combo chains:** set up a Field State with one Pokémon, switch, and exploit it with the next (e.g. Soak with Lapras → switch to Jolteon).
- These can chain into Resonance Mode for bigger effects.

**Bosses built around the environment**
- Brock: rock pillars you can smash for cover or use to crush his Onix.
- Misty: a pool arena — soak the field and electrify it, or freeze it to stop her mobility.
- Lt. Surge: electric panels that overcharge whoever stands on them.
- Erika: tall grass that can burn — or feed her Grass types.
- Koga: poison mist that has to be blown away (Gust/Whirlwind).
- Sabrina: moving mirrors that reflect special attacks.
- Blaine: a volcano arena with lava vents and cooling pools.
- Giovanni: shifting sand and earthquakes.

**Moves in the overworld**
- The same idea outside battle: Ember burns bushes, Thunderbolt powers a dead generator to open doors, Water Gun fills a dry fountain, Rock Throw knocks down a ledge to make a shortcut, Gust clears fog.
- Ties into Bond-based field abilities (section 2) — the Pokémon must know a move of the right type and have enough Bond.

### F. Stretch combat ideas (only after A–E work)
- **Tag battles:** you and an NPC ally each control one Pokémon.
- **Mercy/Calm option (Undertale):** some wild or boss Pokémon can be calmed instead of defeated, changing how they react later.
- **Visible turn order (Grandia / Octopath style):** show who moves next; some moves delay the enemy's turn.

## 2. Open-world Kanto
- After the first gym, most of Kanto opens. Gyms 2–7 can be done in **any order**.
- **Level scaling:** gym leaders, rival and key trainers scale to your badge count so any order is balanced.
- Replace hard HM gates with **field abilities** unlocked by your team's Bond (e.g. a Water-type with enough Bond can Surf — no HM needed).
- Add **shortcuts, secret caves, and alternate routes**; reward exploration with items, rare Pokémon, and optional bosses.
- **Choices matter:** the gym order and whether you calm or defeat Frenzy bosses change later dialogue, rewards, and the rival's team.
- A **journal/quest log** (Pokédex page or key item) tracks side quests and rumors about hidden bosses.

## 3. Mini-games
- **Fishing duel:** a timing/reel mini-game instead of a single button press.
- **Cycling Road race:** a side-scrolling or top-down timed race vs. a rival biker gang.
- **Safari Zone tracking:** follow footprints and sneak up on rare Pokémon.
- **Voltorb Flip–style puzzle** in the Game Corner (a card-flip logic game).
- **Pokémon Tower spirit tag:** dodge/catch ghosts in the dark with limited vision.
- **Silph Co. hacking puzzle:** a simple tile-sliding puzzle to open doors.
- **Rotating challenge dungeon** that changes layout every N steps or after each badge (no real-time clock in Red).
- Mini-games reward prizes, Bond, or rare items — never required for the main story.

## 4. Bosses and challenges
- Every gym leader gets a **boss phase** (Dodge Phase attacks + a stronger final Pokémon).
- **Hidden elite trainers** on side routes, each with a themed challenge (no items, one Pokémon only, timed battle, etc.).
- **Frenzy boss** in most major areas.
- **Post-game:** a surprise legendary boss fight at the end (like Red on Mt. Silver in HeartGold/SoulSilver), plus a rematch gauntlet.
- **Losing still counts** (Hades II): a loss gives some EXP or Bond so progress never feels wasted.

## 5. Life with your Pokémon — time, training, sports, and work
The game shouldn't only be battles. You live with your Pokémon, and time passes.

**Passage of time (Red has no real-time clock)**
- An **in-game calendar**: a day advances when you sleep at home, at a Pokémon Center, or after a set number of steps.
- Days split into **Morning / Day / Evening / Night**, shown with palette changes. Different Pokémon, NPCs, and events appear at different times.
- **Four seasons**, each lasting a set number of in-game days: spring flowers, summer surfing events, autumn harvest, winter snow on some routes (new paths open or close).
- **Weekly schedule:** each day of the week has something special (market day, gym training day, Game Corner tournament, sports league night).
- **Festivals** once per season (e.g. a Celadon summer festival, Lavender lantern night, Saffron winter championship).
- NPCs age and change over the game: kids you meet early show up later as trainers; shops expand; towns grow as the story progresses.

**Daily life with your team**
- A **home in Pallet Town** you can return to: feed, groom, and play with your Pokémon.
- Pokémon have a visible **mood** (happy, tired, bored, hungry) that affects Bond growth and battle performance. Rest days matter.
- A lead **partner Pokémon follows you** in the overworld (like Yellow and HeartGold/SoulSilver) and reacts to places, weather, and events. Talk to it anytime.
- **Bond moments:** small scenes that trigger at milestones — first win together, evolving, visiting its home route, a rainy night at camp.
- **Camping** on routes: rest, cook a meal, and have short scenes with your team.

**Training beyond battling**
- **Training activities** that raise specific stats (Stat Experience) instead of grinding wild battles:
  - Sprints on Cycling Road → Speed
  - Rock-carrying on Route 3 / Mt. Moon → Attack/Defense
  - Swimming laps off Cinnabar → HP
  - Meditation in Saffron or the Tower → Special
- Each is a short mini-game; better performance = bigger gains. Pokémon can get **tired** if overtrained.
- **Dojo lessons** (Saffron Fighting Dojo, gym trainers): learn techniques and unlock Improvise options.

**Sports** (inspired by HeartGold/SoulSilver's Pokéathlon)
- A **Pokémon Sports League** in Celadon or Saffron with a weekly schedule:
  - **Race:** running/flying course — Speed and Action Command timing.
  - **Ball game:** a simple soccer/dodgeball mini-game with 2–3 of your Pokémon.
  - **Swimming relay:** Water types against the clock.
  - **Strength contest:** push boulders the furthest.
  - **Obstacle course:** jump/dodge sequence (reuses the Dodge Phase engine).
- A season-long **league standings** table, rival teams, and a championship at the end of each season with unique prizes.

**Work and jobs** (Pokémon as partners in the world)
- Take **part-time jobs** with your Pokémon for money, items, and Bond:
  - Fire types help the Cinnabar glassmaker or bakery
  - Water types help put out fires, water crops, or rescue swimmers
  - Electric types power the Power Plant or Silph Co.
  - Strong Pokémon help build new areas in town (these areas then actually appear on the map)
  - Delivery runs between towns using Fly or bikes (timed)
  - Farm work on Route 6/7 across seasons
- Jobs change with the seasons and unlock new town features over time, so the world visibly grows because of what you did.

## 6. Quality of life (always on)
- Fast text, faster animations, run indoors (hold B)
- Whole-party Exp Share option
- Reusable TMs, move relearner
- DV / stat-experience viewer
- Bigger bag and easier PC management
- Trade evolutions changed to level-up or item evolutions
- All 151 catchable in one game
- Fix Gen 1 bugs (Focus Energy, 1/256 miss, Psywave/Substitute bugs, badge stat-boost stacking)
- Balance fixes: Ghost beats Psychic, stronger Bug moves, buffs for weak Pokémon
- Difficulty switchable anytime in Options

---

## Gen 1 / Game Boy limits (tell me before fighting them)
- No real-time clock → use the in-game calendar (sleep/step-based days) for time of day, seasons, and rotating content.
- Save RAM is limited: keep the calendar, moods, Bond, jobs, and league data compact, and check save space early.
- Limited ROM banks, RAM, and 4-color graphics. Consider Game Boy Color support if it helps readability of new effects.
- No abilities, natures, or held items — don't add them unless they're needed for a feature above.
- Stay with the original 151 Pokémon.
- The overworld is tile-based: Frenzy bosses and Dodge Phases should be designed around tile/sprite movement, not free movement.
- If a system is too heavy for the engine, propose a simpler version instead of dropping it.

## Build order
1. Set up the project, confirm a matching build.
2. Quality of life + bug fixes → playable build.
3. Action Commands (combat A) → playable build.
4. Bond value + Resonance Meter + trainer HP bar (combat B) → playable build.
5. Trainer Dodge Phase for one gym leader as a prototype (combat C) → playable build; then roll out to all bosses.
6. Battle environments + Field States (combat E), then the Improvise command, then anime-style techniques; redesign gym arenas around them.
7. Open-world changes, level scaling, Bond-based field abilities and overworld move uses.
8. One Frenzy boss prototype (combat D), then the rest.
9. Mini-games, one at a time.
10. In-game calendar (days, time of day, seasons), home base, moods, follower Pokémon.
11. Training activities, Sports League, and jobs — one at a time.
12. Story remix, hidden trainers, post-game boss.

## Story (propose options to me before building)
- Remix Red's story around the Resonance theme — e.g. Team Rocket wants to force Resonance through machines (connects to Mewtwo and Silph Co.).
- A rival who resonates with the *opposite* approach (power over bond).
- Pitch 2–3 concepts and let me pick.

## Working rules
- After each step in the build order, build the ROM and give me a playable test build.
- Keep a CHANGELOG.md of every change.
- Commit to git after each working step so anything can be rolled back.
- Also produce a .bps patch against my original ROM.
- Ask me before any change that would force a big rewrite of earlier work.
