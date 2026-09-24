# Opening up Kanto (build step 7, gates): proposal for approval

Level scaling (gyms 2-7 in any order) and Bond field abilities (no HM needed)
are built. What is **not** built is changing the map gates themselves. It
decides whether the game can still be finished, so it needs your approval.
This is the proposal.

## Where vanilla Red gates the player after Brock

| Gate | Vanilla key | Blocks |
|---|---|---|
| Cut tree east of Cerulean (Route 9) | HM01 Cut from the SS Anne, plus the Cascade Badge | Rock Tunnel, Lavender, Vermilion's gym |
| Saffron's four gate guards | a drink from the Celadon rooftop | Saffron, and a short way east |
| Snorlax on Routes 12 and 16 | the Poke Flute, after the Tower, after the Rocket Hideout | the southern routes to Fuchsia |
| Cycling Road | the Bicycle | the west route to Fuchsia |
| Water routes | HM03 Surf from the Safari Zone, plus the Soul Badge | Cinnabar, the Seafoam Islands |
| Viridian Gym door | 7 badges | Giovanni (keep as is) |

## Proposal

1. **Cut needs no badge.** A Grass or Bug partner with Bond 120 (or HM01)
   clears the Route 9 tree from the start.
2. **Saffron's guards let you through after the first badge.** The drink
   becomes a side quest reward.
3. **The Snorlax become Frenzy bosses** (build step 8). You can calm them or
   fight them to clear the road. The Poke Flute still works as a shortcut.
4. **Surf needs any 3 badges** instead of the Soul Badge. A Water partner
   with Bond 120 needs no HM.
5. **Keep:**
   - Brock first, and Giovanni last (7 badges);
   - the League gate (8);
   - the bike requirement for Cycling Road;
   - Strength for Victory Road.

With level scaling in place, gyms 2 to 7 can then be done in any order. The
Rocket Hideout, Tower and Silph Co. story beats keep their own prerequisites
(Silph Scope, Poke Flute, Card Key), so story order stays sane.

## Risk and test

Each change is a script or data edit on one map. The risk is soft-locks: a
place you can get into but not out of.

- The test I'd add walks a scripted route for each of the 6 possible second
  gyms from Pewter.
- It would reuse `test/navigate.py`, but that harness still can't get past
  the Pallet Town fence (BUGS.md). Fixing that comes first.

Say which of 1-5 to do, or change any of them.
