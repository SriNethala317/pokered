# Battle environments and Field States (build step 6, first part)

Combat layer E of the brief. Written 2026-09-24 during an unattended session;
**provisional** marks calls made without the user.

## Environments

Worked out when a battle starts (`InitBattleField`), from where it happens:

| Place | Label |
|---|---|
| Surfing | `sea ` |
| The Power Plant | `wire` |
| The Pokemon Tower | `tomb` |
| The Seafoam Islands | `snow` |
| Cycling Road | `sand` |
| The cave tileset | `cave` |
| The overworld and forest tilesets | `leaf` |
| Anywhere else | `room` |

The label sits in the four empty tiles right of the enemy's level: lowercase
for the place, capitals for a Field State. There is no palette tint yet
(**provisional**): Gen 1 on a DMG has one BG palette, and the battle code
rewrites it during transitions.

## Field States

| State | Made by | Effect |
|---|---|---|
| SOAK | any damaging Water move; also puts out FIRE | Electric boosted, Fire x1/2 |
| ICE! | an Ice move on SOAK, or any Ice move in the snow | Ice boosted; Gen 1 physical types may slip (miss) |
| FIRE | a damaging Fire move on grass | Fire boosted; each turn non-Fire Pokemon lose 1/16 of max HP |
| DUG! | Dig (the attack turn) | the next Ground or Rock move boosted, then used up |
| RUBL | Earthquake or Rock Slide in a cave | the next attack on the side that made it is blocked half the time, then used up |
| DUST | Sand-Attack or Gust on sand | non-Rock, non-Ground attackers may miss |
| ZAP! | a damaging Electric move in the Power Plant | the next Electric move x2, a quarter back as recoil (never a knockout), then used up |
| DARK | Smokescreen or Night Shade in the tower | every attack may miss, and Ghost attacks always hit |

- A move that uses up a state never makes a new one in the same breath.
- The next field-changing move replaces the state, so battles become a
  tug-of-war over the arena.
- Link battles have no field, because the two players stand in different
  places.

## Ramp (`FieldRamp`, by badges)

| Badges | Boost | Slip, dust or dark miss chance | Turns |
|---|---|---|---|
| 0 | x1.25 | 10% | 5 |
| 1-2 | x1.25 | 15% | 5 |
| 3-4 | x1.5 | 20% | 5 |
| 5-6 | x1.5 | 25% | 4 |
| 7-8 | x1.5 | 25% | 4 |

## Battle length

- No text is printed: the label changes, and the HP bars move for the singe.
- `fieldcheck.py` checks a turn with a state prints no more texts than one
  without.

## RAM

Four bytes: `wFieldEnv`, `wFieldState`, `wFieldTurns`, `wFieldOwner`. They are
cleared with the battle data, and they took WRAM0 from 30 bytes free to 26.

## Known limits

- The countdown runs at the top of the battle loop, which is entered again
  after a Pokemon faints and is replaced, so a faint mid-turn costs the state an
  extra turn.
- Still to build: the anime-style techniques, and gym arenas redesigned around
  the states.

## Improvise

- **How:** press START instead of A on a move in the move menu. **Provisional:**
  the brief asks for an IMPROVISE option next to FIGHT, but the battle menu's
  four slots are full and START was unused in the move menu.
- **What it does:** the move is spent (PP included) and deals no damage.
  Instead it leaves the Field State its type goes with, wherever the battle is:

  | Types | State | Picture |
  |---|---|---|
  | Water | SOAK | |
  | Ice | ICE! | |
  | Fire | FIRE | |
  | Electric, Dragon | ZAP! | |
  | Ground | DUG! | |
  | Normal, Fighting, Rock, Grass | RUBL | cover, or vines to swing clear on |
  | Flying, Bug | DUST | |
  | Poison, Ghost, Psychic | DARK | |

- **Limits:** it needs Bond 100 with the Pokemon out, and there are 3 turns
  between uses. A resonant Bond (200) makes the state last 2 turns longer.
- **Where not:** link battles, the Safari Zone and the old man's tutorial.
- **Feedback:** an IMPROV! badge shows and the label changes; no text. The
  button is explained once, in Brock's badge scene.
- **RAM:** 1 byte, `wImprovise`, leaving WRAM0 with 25 bytes free.

