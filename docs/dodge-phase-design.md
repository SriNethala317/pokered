# Trainer Dodge Phase (build step 5)

Combat layer C of the brief, prototyped on Brock and then rolled out to all
eight gym leaders. Written 2026-09-24 during an
unattended session; **provisional** marks calls made without the user.

- **When:** the first damaging attack of each of a boss's Pokemon, in trainer
  battles, with action commands On or Assist. Brock (two Pokemon) makes you
  dodge twice per battle at most. It stands in for that attack's brace.
- **The arena:** a 10x8 box drawn over the middle of the battle screen, in the
  tilemap only. The screen is saved to buffer 2 and restored exactly. You are
  the ♂ and move one tile per press, or one every 4 frames held.
  **Provisional:** the ♂ and O glyphs stand in until real sprites exist.
- **Brock's pattern:** a ▼ warns where a rock will fall; it becomes an O, and
  every rock drops a row at a fixed beat. The state lives in the tilemap itself.
- **Length:** 150 frames (2.5 s). Measured at 151 including setup; the test
  allows at most 160.
- **Hits:**
  - Each costs 6 of the 24-point trainer bar that Resonance uses, with 30
    frames of grace after one.
  - Running the bar dry breaks Resonance (BROKEN!) and costs your next turn,
    exactly like a Resonance break.
  - A hit lets the attack land in full.
- **Untouched:** DODGED!, the attack is halved like a brace, and the Resonance
  meter gains 3.
- **Ramp (`DodgeRamp`, by badges):**

  | Badges | Frames per row a rock falls | Frames between rocks |
  |---|---|---|
  | 0 | 9 | 16 |
  | 1-2 | 8 | 14 |
  | 3-4 | 7 | 12 |
  | 5-6 | 6 | 10 |
  | 7-8 | 5 | 9 |

  Assist always uses the first row.
- **Fairness:** a bot that steps toward the nearest clear column took 0 hits
  in 6 real phases with random rocks at 0 badges.
- **Every leader has a pattern** (`DodgeBosses`, trainer class to pattern):

  | Leader | Pattern | Hazard |
  |---|---|---|
  | Brock | fall | rocks drop a row a beat after a ▼ warning |
  | Misty | sweep | a wave with a 2-row gap moves right a column a beat |
  | Lt. Surge | column | lightning: `.` then `×` warnings, then a strike |
  | Erika | sweep | lashing vines |
  | Koga | row | poison gas across a row |
  | Sabrina | fall, mirrored | left and right are swapped |
  | Blaine | column | fire pillars |
  | Giovanni | row | earthquakes |

  Strikes get two beats of warning and twice the beat length. Waves come a
  third as often as rocks. The player is sprite 0 showing the font's ♂, so it
  never hides a warning, and the hazards live in the tilemap.
- **Fairness:** a bot that only looks 3 tiles around it took 0 hits in one real
  phase against each leader, except Erika (3, because a random gap can be far
  away). Brock alone: 0 hits in 6 phases.
- **Provisional:** the ASCII-style glyphs; real sprites later.
