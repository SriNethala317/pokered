# RESONANCE story bible: "Sync"

This blends pitch 1 (The Forced Bond) and pitch 3 (Two Frequencies), chosen on
2026-09-24. Everything written in game follows this file.

## Premise

Every Pokemon has a **frequency**. Bond is two frequencies tuning to each
other, and Resonance is when they lock. Silph Co. found a way to fake it: the
**Sync Collar** forces a Pokemon's frequency onto whoever wears the matching
**band**, trust or no trust. It works, but the Pokemon is worn down with every
use.

Team Rocket bought the collars. To drive them across Kanto without a band
nearby, Rocket built a **broadcast** into the Pokemon Tower's old radio mast,
and powers it with the Tower's ghosts. The signal leaks. Wild Pokemon that
catch it go **frantic** (the Frenzy bosses) and block the roads.

## Cast

- **You.** You Resonate the honest way. Your starter trusts you from the first
  minute: it starts at Bond 64 and reaches Resonance at Brock.
- **Rival.** Oak's grandchild. At Cerulean they buy a Sync band from a Rocket
  "salesman". They win with it, their Pokemon Resonate on command, and they get
  worse each time: Rival Sync stuns them after.
- **Professor Oak** studied frequencies as a young man. He sees your starter
  Resonate at Brock and knows what it means.
- **Mr. Fuji** is an ex-Silph engineer. He built the first collar for one
  Pokemon, Mewtwo, and has run the Pokemon House as penance ever since.
- **Giovanni** means to put a collar on every Pokemon in Kanto: an army that
  obeys whoever holds the band.
- **Mewtwo** was the first Pokemon ever collared. It broke the collar, but kept
  the signal. The broadcast is tuned to Mewtwo's own frequency, which is why it
  drives Pokemon frantic.

## Beats by place (the maps, scripts and flags are vanilla's)

| Place | Beat |
|---|---|
| Oak's lab | Oak on Bond: "trust is a frequency." The rival: "Power beats trust." |
| Route 22 / Cerulean | The rival shows off a band; "a Rocket guy sold it to me." |
| Mt. Moon | Rocket collects fossils to test collars on old frequencies |
| Brock | You Resonate for the first time (the unlock text) |
| Saffron's gates | Guards on edge from the broadcast; after Brock they let you through |
| Rocket Hideout | Collar crates; Giovanni: "Silph makes them, I make them matter." |
| Pokemon Tower | The broadcast mast on 7F; the ghosts are worn-out collared Pokemon; Marowak's spirit is the loudest |
| Mr. Fuji | Built the first collar; gives the Poke Flute: "its tune cuts through the signal" |
| Routes 12 / 16 | Frantic Snorlax; calm it (Frenzy) or fight it |
| Silph Co. | The collar line on the Card Key floors; the Master Ball was a collar prototype's cage |
| Saffron Gym | Sabrina can hear the broadcast and hates it |
| Giovanni (Viridian) | "Your bond is a collar you chose to wear." You beat him |
| Cerulean Cave | Mewtwo, still humming with the broadcast. Calm it last |
| The League | The rival's Pokemon are near breaking; winning frees them from the band |

## Choice flags (for later dialogue)

- `EVENT_CALMED_ROUTE12_SNORLAX`, `EVENT_CALMED_ROUTE16_SNORLAX`: calmed rather
  than beaten.
- Later Frenzy bosses add their own.
- NPCs and the rival react to how many you calmed.

## Tone

Warm and hopeful, and never grim on screen: Gen 1's text boxes are short. Keep
lines within 18 characters and scenes to vanilla length.
