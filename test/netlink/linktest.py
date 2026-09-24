"""Two RESONANCE consoles joined by the link_shim lockstep cable.

Each console boots pokered.gbc, clears the intro, gets one Pokémon and the
Pokédex flag, flies to Pewter City and walks up to the Cable Club receptionist.
The two are then joined by a simulated network cable that delays every link
message by --delay harness ticks (one tick ~ one frame of wall time, so the
default 3 is ~50 ms each way). The test then runs the vanilla flow:

  1. host talks to the receptionist; the idle guest is armed on the external
     clock by the Pokémon Center map script, so the host ends up on the
     internal clock and the guest on the external one (checked);
  2. guest talks, both save, sync (Serial_SyncAndExchangeNybble) and reach the
     link menu (checked on both);
  3. host picks TRADE CENTER; both enter the Trade Center (checked);
  4. both use the table: random numbers, names and parties are exchanged with
     Serial_ExchangeBytes and each side sees the other's party (checked);
  5. both trade their only Pokémon and each ends up with the other's (checked).

Usage: python test/netlink/linktest.py [--delay N] [--stage N]
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

from rominspect import load_symbols  # noqa: E402
from shim import FRAME, ROOT, Console, asm_constants  # noqa: E402

ROM = os.path.join(ROOT, "pokered.gbc")
SYM = os.path.join(ROOT, "pokered.sym")

K = asm_constants(
    "REDS_HOUSE_2F", "PEWTER_CITY", "PEWTER_POKECENTER", "TRADE_CENTER",
    "EVENT_GOT_POKEDEX", "BIT_FLY_WARP", "USING_INTERNAL_CLOCK",
    "USING_EXTERNAL_CLOCK", "RATTATA", "PIDGEY",
)
SYMS = load_symbols(SYM)


def A(name):
    return SYMS[name][1]


def BA(name):
    return SYMS[name]


class Player:
    """A console plus a scripted driver that yields once per emulated frame."""

    def __init__(self, name, species):
        self.name = name
        self.c = Console(open(ROM, "rb").read())
        self.species = species
        bank, addr = BA("LinkMenu")
        self.h_linkmenu = self.c.hook(addr, bank)
        self.h_overworld = self.c.hook(A("OverworldLoop"))
        self.seen = set()
        self.driver = None

    # ---- helpers usable before linking (run frames directly) ----
    def frames(self, n):
        for _ in range(n):
            self.c.run_frame()
            self._collect()

    def _collect(self):
        for h in self.c.hooks_fired():
            self.seen.add(h)

    def mem(self, name, off=0):
        return self.c.read(A(name) + off)

    def pos(self):
        return self.mem("wYCoord"), self.mem("wXCoord")

    def press_now(self, key, hold=3, rel=24):
        self.c.set_keys([key])
        self.frames(hold)
        self.c.set_keys([])
        self.frames(rel)

    def goto(self, y, x):
        for _ in range(80):
            py, px = self.pos()
            if (py, px) == (y, x):
                return
            self.press_now("up" if py > y else "down" if py < y else "left" if px > x else "right")
        raise AssertionError(f"{self.name}: stuck walking to {(y, x)} at {self.pos()}")

    def setup(self):
        """Boot to the overworld and stand in front of Pewter's receptionist."""
        c = self.c
        for i in range(1, 4000):
            c.set_keys(["start" if i % 10 == 0 else "a"])
            self.frames(3)
            c.set_keys([])
            self.frames(6)
            if self.h_overworld in self.seen and self.mem("wCurMap") == K["REDS_HOUSE_2F"]:
                break
        else:
            raise AssertionError("never reached the overworld")
        self.frames(60)
        self.give_mon(self.species, 10)
        e = K["EVENT_GOT_POKEDEX"]
        c.write(A("wEventFlags") + e // 8, self.mem("wEventFlags", e // 8) | (1 << (e % 8)))
        c.write(A("wDestinationMap"), K["PEWTER_CITY"])
        c.write(A("wStatusFlags6"), self.mem("wStatusFlags6") | (1 << K["BIT_FLY_WARP"]))
        self.frames(400)
        assert self.mem("wCurMap") == K["PEWTER_CITY"], "fly warp failed"
        self.press_now("up", hold=20, rel=100)
        assert self.mem("wCurMap") == K["PEWTER_POKECENTER"], "did not enter the Pokémon Center"
        self.goto(3, 11)
        assert self.mem("wPartyCount") == 1

    def give_mon(self, species, level):
        """Call AddPartyMon from the overworld loop by faking a call frame."""
        c = self.c
        c.write(A("wCurPartySpecies"), species)
        c.write(A("wCurEnemyLevel"), level)
        c.write(A("wMonDataLocation"), 0x10)  # player party, skip the nickname prompt
        c.hook(A("OverworldLoop"), -1, brk=True)
        # OverworldLoop starts with `call DelayFrame`; once it has run, PC is
        # DelayFrame's entry and no caller registers are live. Push that as
        # the return address and enter AddPartyMon (ROM0; it farcalls).
        while c.run_frame() != 2:
            pass
        pc = c.L.shim_reg(c.s, 5)
        sp = c.L.shim_reg(c.s, 4) - 2
        c.write(sp, pc & 0xFF)
        c.write(sp + 1, pc >> 8)
        c.L.shim_set_reg(c.s, 4, sp)
        c.L.shim_set_reg(c.s, 5, A("AddPartyMon"))
        c.L.shim_hook_clear(c.s)
        self.h_linkmenu = c.hook(BA("LinkMenu")[1], BA("LinkMenu")[0])
        self.h_overworld = c.hook(A("OverworldLoop"))
        self.frames(30)

    # ---- driver primitives (generators) ----
    def hold(self, keys, n):
        self.c.set_keys(keys)
        for _ in range(n):
            yield
        self.c.set_keys([])

    def wait(self, n):
        self.c.set_keys([])
        for _ in range(n):
            yield

    def tap(self, key, rel=20):
        yield from self.hold([key], 4)
        yield from self.wait(rel)


class Wire:
    """Carries link messages between two consoles with a fixed delay."""

    def __init__(self, a, b, delay):
        self.a, self.b, self.delay = a, b, delay
        self.q = []  # (deliver_tick, dest, kind, byte)
        self.tick = 0
        self.messages = 0

    def collect(self):
        for src, dst in ((self.a, self.b), (self.b, self.a)):
            for kind, byte in src.c.pop():
                self.q.append((self.tick + self.delay, dst, kind, byte))
                self.messages += 1

    def deliver(self):
        keep = []
        for item in self.q:
            t, dst, kind, byte = item
            if t <= self.tick:
                dst.c.push(kind, byte)
            else:
                keep.append(item)
        self.q = keep


def run_linked(a, b, wire, until, budget, must=True):
    """Advance both drivers until until() is true. Stalled consoles wait."""
    stall = {a.name: 0, b.name: 0}
    for _ in range(budget):
        wire.deliver()
        for p in (a, b):
            for _ in range(4):  # with zero delay, a reply can land within this tick
                r = p.c.run_frame()
                p._collect()
                wire.collect()
                if r == FRAME:
                    next(p.driver, None)
                    break
                stall[p.name] += 1
                wire.deliver()
        wire.tick += 1
        if until():
            return stall
    if not must:
        return stall
    if os.environ.get("NETLINK_SHOTS"):
        from PIL import Image
        for p in (a, b):
            Image.frombytes("RGBA", (160, 144), p.c.framebuffer()).save(f"/tmp/netlink_{p.name}.png")
    raise AssertionError(
        f"timed out: {a.name} map={a.mem('wCurMap')} status={a.c.read(0xFFAA):#x}, "
        f"{b.name} map={b.mem('wCurMap')} status={b.c.read(0xFFAA):#x}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=int, default=3, help="one-way delay in frames")
    ap.add_argument("--stage", type=int, default=5, help="stop after this stage")
    args = ap.parse_args()

    t0 = time.time()
    host = Player("host", K["RATTATA"])
    guest = Player("guest", K["PIDGEY"])
    host.setup()
    guest.setup()
    print(f"setup done in {time.time() - t0:.1f}s; both at the Pewter receptionist")

    wire = Wire(host, guest, args.delay)
    host.c.plug(True)
    guest.c.plug(True)
    HS = 0xFFAA  # hSerialConnectionStatus
    assert A("hSerialConnectionStatus") == HS

    def mash_until(p, cond, key="a", every=24):
        while not cond():
            yield from p.tap(key, rel=every)

    # Stage 1+2: host talks first, guest a little later; both mash through.
    in_menu = lambda p: p.h_linkmenu in p.seen  # noqa: E731

    def host_talk():
        yield from host.wait(20)
        yield from host.tap("up")  # face the receptionist
        yield from mash_until(host, lambda: in_menu(host))
        yield from host.wait(100000)

    def guest_talk():
        yield from guest.wait(20)
        yield from guest.tap("up")
        # wait until the host has claimed the cable before talking
        while host.c.read(HS) != K["USING_INTERNAL_CLOCK"]:
            yield
        yield from guest.wait(30)
        yield from mash_until(guest, lambda: in_menu(guest))
        yield from guest.wait(100000)

    host.driver, guest.driver = host_talk(), guest_talk()
    run_linked(host, guest, wire, lambda: host.c.read(HS) == K["USING_INTERNAL_CLOCK"], 3000)
    hs_h, hs_g = host.c.read(HS), guest.c.read(HS)
    print(f"stage 1: host status={hs_h:#x} guest status={hs_g:#x} after {wire.tick} ticks")
    assert hs_h == K["USING_INTERNAL_CLOCK"] and hs_g == K["USING_EXTERNAL_CLOCK"]
    if args.stage <= 1:
        return 0

    stall = run_linked(host, guest, wire, lambda: in_menu(host) and in_menu(guest), 20000)
    print(f"stage 2: both at the link menu after {wire.tick} ticks, {wire.messages} messages, stalls {stall}")
    if args.stage <= 2:
        return 0

    # Stage 3: host picks TRADE CENTER (the first entry); guest follows.
    def host_pick():
        yield from host.wait(60)
        yield from host.tap("a")
        yield from host.wait(100000)

    host.driver, guest.driver = host_pick(), guest.wait(100000)
    tc = K["TRADE_CENTER"]
    run_linked(host, guest, wire, lambda: host.mem("wCurMap") == tc and guest.mem("wCurMap") == tc, 20000)
    run_linked(host, guest, wire, lambda: False, 120, must=False)  # let the room settle
    print(f"stage 3: both in the Trade Center after {wire.tick} ticks; host at {host.pos()}, guest at {guest.pos()}")
    if args.stage <= 3:
        return 0

    # Stage 4: use the table (host faces right, guest faces left).
    def use_table(p, face):
        yield from p.tap(face)
        yield from p.tap("a")
        yield from p.wait(100000)

    host.driver, guest.driver = use_table(host, "right"), use_table(guest, "left")

    def parties_swapped():
        return (
            host.mem("wEnemyPartyCount") == 1 and guest.mem("wEnemyPartyCount") == 1
            and host.mem("wEnemyPartySpecies") == guest.species
            and guest.mem("wEnemyPartySpecies") == host.species
        )

    stall = run_linked(host, guest, wire, parties_swapped, 60000)
    print(f"stage 4: parties exchanged after {wire.tick} ticks, {wire.messages} messages, stalls {stall}")
    if args.stage <= 4:
        return 0

    # Stage 5: select mon 1, choose TRADE, confirm. Keep pressing A on both.
    def trade(p):
        yield from p.wait(120)
        yield from p.tap("a", rel=40)  # pick the first mon
        yield from p.tap("right", rel=20)  # STATS -> TRADE
        while True:
            yield from p.tap("a", rel=40)

    host.driver, guest.driver = trade(host), trade(guest)

    shots = [0]

    def traded():
        if os.environ.get("NETLINK_SHOTS") and wire.tick % 300 == 0:
            from PIL import Image
            for p in (host, guest):
                Image.frombytes("RGBA", (160, 144), p.c.framebuffer()).save(f"/tmp/nl_{p.name}_{shots[0]:03d}.png")
            print(wire.tick, hex(host.c.L.shim_reg(host.c.s, 5)), hex(guest.c.L.shim_reg(guest.c.s, 5)), host.c.stalled(), wire.messages)
            shots[0] += 1
        return (
            host.mem("wPartySpecies") == guest.species and guest.mem("wPartySpecies") == host.species
        )

    stall = run_linked(host, guest, wire, traded, 30000)
    print(f"stage 5: trade complete after {wire.tick} ticks, {wire.messages} messages, stalls {stall}")
    print(f"total {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
