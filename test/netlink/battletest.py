"""A link battle in the Colosseum between two consoles on the link_shim cable.

Same setup as linktest.py (Rattata vs Pidgey, level 10, at Pewter's Cable
Club), with the fast paths on unless --lockstep. The host picks COLOSSEUM,
both use the table, and each side picks its first damaging move every turn
(Tackle, Gust) until one faints.

Desync check: at the start of every turn (each entry to MainInBattleLoop)
both consoles record (own HP, other HP). Turn by turn, the host's own HP must
equal the guest's view of its opponent and the other way round, and the
battle must end the same way on both (one winner, one loser). Action
Commands, Field States, Resonance and Dodge are off in link battles by
design; a desync from any of them would show up here as a mismatch.

Usage: python test/netlink/battletest.py [--delay N] [--lockstep]
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import linktest as L  # noqa: E402
from shim import asm_constants  # noqa: E402

K = dict(L.K)
K.update(asm_constants("COLOSSEUM", "LINK_STATE_BATTLING"))
A, BA = L.A, L.BA
HS = A("hSerialConnectionStatus")


def word(p, name):
    return (p.mem(name) << 8) | p.mem(name, 1)


class Fighter(L.Player):
    def add_hooks(self):
        super().add_hooks()
        bank, addr = BA("MainInBattleLoop")
        self.h_turn = self.c.hook(addr, bank)
        self.turns = []
        self.battled = False

    def _collect(self):
        for h in self.c.hooks_fired():
            self.seen.add(h)
            if h == getattr(self, "h_turn", None):
                # between turns nothing changes HP until both have chosen
                self.turns.append((word(self, "wBattleMonHP"), word(self, "wEnemyMonHP")))
        if self.mem("wIsInBattle"):
            self.battled = True
            self.last_hp = (word(self, "wBattleMonHP"), word(self, "wEnemyMonHP"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=int, default=3, help="one-way delay in frames")
    ap.add_argument("--lockstep", action="store_true", help="byte by byte only (no fast paths)")
    args = ap.parse_args()
    t0 = time.time()
    host = Fighter("host", K["RATTATA"])
    guest = Fighter("guest", K["PIDGEY"])
    host.setup()
    guest.setup()
    wire = L.Wire(host, guest, args.delay)
    for p in (host, guest):
        p.c.plug(True)
        if not args.lockstep:
            L.enable_fast(p.c)
    guest.c.gate(HS, K["USING_EXTERNAL_CLOCK"])  # as linkhost.js does

    in_menu = lambda p: p.h_linkmenu in p.seen  # noqa: E731

    def talk(p):
        yield from p.wait(20)
        yield from p.tap("up")
        # the host talks first: while the guest idles in the Pokémon Center
        # the map script keeps it listening for the host's clock. (Talking at
        # the same moment can miss at long delays; the receptionist then says
        # the area is reserved and you simply talk again.)
        while p is guest and host.c.read(HS) != K["USING_INTERNAL_CLOCK"]:
            yield
        while not in_menu(p):
            yield from p.tap("a", rel=24)
        yield from p.wait(10**9)

    host.driver, guest.driver = talk(host), talk(guest)
    L.run_linked(host, guest, wire, lambda: in_menu(host) and in_menu(guest), 20000)
    print(f"link menu after {wire.tick} ticks")

    def pick_colosseum():
        yield from host.wait(60)
        yield from host.tap("down")
        yield from host.tap("a")
        yield from host.wait(10**9)

    host.driver, guest.driver = pick_colosseum(), guest.wait(10**9)
    col = K["COLOSSEUM"]
    L.run_linked(host, guest, wire, lambda: host.mem("wCurMap") == col and guest.mem("wCurMap") == col, 20000)
    L.run_linked(host, guest, wire, lambda: False, 120, must=False)
    print(f"both in the Colosseum after {wire.tick} ticks")

    def fight(p, face):
        yield from p.tap(face)
        yield from p.tap("a")
        # A through the intro text, FIGHT, the first move, and each turn's text
        while True:
            yield from p.tap("a", rel=30)

    host.driver, guest.driver = fight(host, "right"), fight(guest, "left")
    start = wire.tick

    def over():
        return all(p.battled and not p.mem("wIsInBattle") for p in (host, guest))

    L.run_linked(host, guest, wire, over, 60000)
    frames = wire.tick - start
    n = min(len(host.turns), len(guest.turns))
    print(f"battle over after {frames} frames (~{frames / 60:.0f} s at {args.delay} frames delay, "
          f"{'lockstep' if args.lockstep else 'fast paths'}), {n} turns")
    assert len(host.turns) == len(guest.turns), f"turn counts differ: {len(host.turns)} vs {len(guest.turns)}"
    assert n >= 3, f"only {n} turns"
    for i, (h, g) in enumerate(zip(host.turns, guest.turns), 1):
        print(f"  turn {i}: host sees {h[0]} vs {h[1]}, guest sees {g[1]} vs {g[0]}")
        assert h == (g[1], g[0]), f"desync at turn {i}: host {h}, guest {g}"
    # the battle ended the same way on both: one mon fainted, the same one
    # (link battles restore the party afterwards, so read the battle's HP)
    h, g = host.last_hp, guest.last_hp
    assert h == (g[1], g[0]), f"final HP differs: host {h}, guest {g}"
    assert (h[0] == 0) != (h[1] == 0), f"expected exactly one fainted mon: {h}"
    print(f"battle ended the same on both: host {h[0]} HP vs guest {h[1]} HP; total {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
