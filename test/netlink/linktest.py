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
        self.add_hooks()
        self.seen = set()
        self.driver = None
        self.snaps = {}

    def add_hooks(self):
        c = self.c
        self.h_linkmenu = c.hook(BA("LinkMenu")[1], BA("LinkMenu")[0])
        self.h_overworld = c.hook(A("OverworldLoop"))
        # fires when the trade menu opens, after the exchange and
        # unpatching, so the parsed link data can be read at a fixed point
        self.h_select = c.hook(BA("TradeCenter_SelectMon")[1], BA("TradeCenter_SelectMon")[0])

    def snapshot(self):
        """What the game made of the link exchange: the other player's name,
        the shared random numbers, the other party and our own party."""
        def block(start, end):
            return bytes(self.c.read(a) for a in range(A(start), A(end)))
        return {
            "enemy name": bytes(self.c.read(A("wLinkEnemyTrainerName") + i) for i in range(11)),
            "random numbers": bytes(self.c.read(A("wLinkBattleRandomNumberList") + i) for i in range(10)),
            "enemy party": block("wEnemyPartyCount", "wTrainerHeaderPtr"),
            "party": block("wPartyDataStart", "wPartyDataEnd"),
        }

    # ---- helpers usable before linking (run frames directly) ----
    def frames(self, n):
        for _ in range(n):
            self.c.run_frame()
            self._collect()

    def _collect(self):
        for h in self.c.hooks_fired():
            self.seen.add(h)
            if h == self.h_select:
                # the trade menu opens after each exchange: once before the
                # trade and once after it, when the game re-exchanges
                if "exchange" not in self.snaps:
                    self.snaps["exchange"] = self.snapshot()
                elif "after trade" not in self.snaps and self.mem("wPartySpecies") != self.species:
                    self.snaps["after trade"] = self.snapshot()

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
        # Skipping the nickname prompt leaves the nickname unwritten, and the
        # ROM now refuses a traded Pokemon whose name has no terminator (as
        # glitch trades use), so give it the name the game would have.
        for i, ch in enumerate(b"\x8f\x80\x8b\x50"):  # "PAL@"
            c.write(A("wPartyMonNicks") + i, ch)
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
        self.add_hooks()
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
        f"{b.name} map={b.mem('wCurMap')} status={b.c.read(0xFFAA):#x}; "
        + "; ".join(f"{p.name} pc={p.c.L.shim_reg(p.c.s, 5):#06x} stalled={p.c.stalled()} blocks={p.c.blocks()}"
                    for p in (a, b))
    )


def enable_fast(c):
    """What linkhost.js does for a session: block and nybble-sync fast paths."""
    c.fast(A("Serial_ExchangeBytes"), A("hSerialConnectionStatus"), A("hSerialIgnoringInitialData"))
    c.fast_sync(A("Serial_SyncAndExchangeNybble"), A("wSerialExchangeNybbleSendData"),
                A("wSerialExchangeNybbleReceiveData"), A("wSerialSyncAndExchangeNybbleReceiveData"),
                A("wUnknownSerialCounter"))


def saved_species(p):
    """First party species in the battery save (not in WRAM)."""
    bank, addr = BA("sPartyData")
    return p.c.sram()[bank * 0x2000 + (addr - 0xA000) + 1]


def drop_mid_trade(host, guest, wire):
    """Cut the cable partway through the trade, as a dropped connection would,
    then do what linkhost.js does on its timeout (unplug, reset) and check
    neither battery save changed."""
    before = {p.name: saved_species(p) for p in (host, guest)}
    assert before == {"host": host.species, "guest": guest.species}, before
    start = wire.messages
    # cut while both are choosing in the trade menu, before anything is saved
    run_linked(host, guest, wire, lambda: all("exchange" in p.snaps for p in (host, guest)), 30000)
    run_linked(host, guest, wire, lambda: False, 150, must=False)
    assert host.mem("wPartySpecies") == host.species, "cut too late: the trade already happened"
    wire.q.clear()
    wire.deliver = lambda: None  # the network is gone
    wire.collect = lambda: [p.c.pop() for p in (host, guest)]
    run_linked(host, guest, wire, lambda: False, 700, must=False)  # the 10 s timeout
    print(f"drop: cable cut in the trade menu ({wire.messages - start} messages in); host stalled={host.c.stalled()}")
    for p in (host, guest):
        p.c.plug(False)
        p.c.L.shim_reset(p.c.s)
        p.frames(600)
    after = {p.name: saved_species(p) for p in (host, guest)}
    assert after == before, f"a save changed: {before} -> {after}"
    print(f"drop: both saves unchanged after reset ({after})")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="exchange Serial_ExchangeBytes blocks in one message")
    ap.add_argument("--compare", action="store_true",
                    help="trade once byte by byte and once with the fast path; the parsed data must match")
    ap.add_argument("--delay", type=int, default=3, help="one-way delay in frames")
    ap.add_argument("--stage", type=int, default=5, help="stop after this stage")
    ap.add_argument("--hostile", choices=("species", "name", "move", "count"),
                    help="the guest sends a party no real game could have; the host must refuse it")
    ap.add_argument("--drop", action="store_true", help="cut the cable mid-trade and check the saves")
    ap.add_argument("--together", action="store_true",
                    help="both talk to the receptionist at once; the guest is gated as the web page does")
    args = ap.parse_args()
    if not args.compare:
        r = run(args)
        return 0 if r == 0 or isinstance(r, dict) else r
    args.stage = 5
    results = {}
    for fast in (False, True):
        args.fast = fast
        print(f"--- {'fast path' if fast else 'byte lockstep'} ---")
        results[fast] = run(args)
    slow, quick = results[False], results[True]
    for side in ("host", "guest"):
        for when in ("exchange", "saved", "after trade"):
            if when not in slow[side]:
                continue
            for field, value in slow[side][when].items():
                # After the trade the game draws a fresh random list from the
                # divider register; the fast path changes the timing, so that
                # list differs by design. What matters is that the two
                # consoles agree, checked below.
                if when == "after trade" and field == "random numbers":
                    continue
                other = quick[side][when][field]
                assert value == other, f"{side} {when} {field} differs:\n  lockstep {value.hex()}\n  fast     {other.hex()}"
    for name, r in (("lockstep", slow), ("fast", quick)):
        # the clocking side's list is the one both use
        for when in ("exchange", "after trade"):
            if when not in r["host"] or when not in r["guest"]:
                continue
            assert r["host"][when]["random numbers"] == r["guest"][when]["random numbers"], \
                f"{name} {when}: the consoles hold different random lists"
    print(f"compare: both consoles' parsed link data and parties match with and without the fast path "
          f"(trade {slow['frames']} -> {quick['frames']} frames at {args.delay} frames delay)")
    return 0


def run(args):
    t0 = time.time()
    host = Player("host", K["RATTATA"])
    guest = Player("guest", K["PIDGEY"])
    host.setup()
    guest.setup()
    print(f"setup done in {time.time() - t0:.1f}s; both at the Pewter receptionist")

    wire = Wire(host, guest, args.delay)
    host.c.plug(True)
    guest.c.plug(True)
    if args.together:
        # linkhost.js: the session guest only drives the clock once connected
        guest.c.gate(A("hSerialConnectionStatus"), K["USING_EXTERNAL_CLOCK"])
    HS = 0xFFAA  # hSerialConnectionStatus
    assert A("hSerialConnectionStatus") == HS

    if args.fast:
        for p in (host, guest):
            enable_fast(p.c)

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
        while not args.together and host.c.read(HS) != K["USING_INTERNAL_CLOCK"]:
            yield
        if not args.together:
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

    debug = {}
    if args.hostile:
        # The guest sends a party no real game could have; the host must refuse
        # it and go back to the Cable Club room without using any of it.
        g = guest.c
        if args.hostile == "species":
            g.write(A("wPartySpecies"), 0x1F)  # a MissingNo. index
            g.write(A("wPartyMon1Species"), 0x1F)
        elif args.hostile == "name":
            for i in range(11):
                g.write(A("wPartyMonNicks") + i, 0x80)  # no terminator
        elif args.hostile == "move":
            g.write(A("wPartyMon1Moves"), 0xFF)
        elif args.hostile == "count":
            g.write(A("wPartyCount"), 7)
        refused = host.c.hook(BA("ReturnToCableClubRoom")[1], BA("ReturnToCableClubRoom")[0])
    if os.environ.get("LINKDEBUG"):
        for p in (host, guest):
            for label in os.environ["LINKDEBUG"].split(","):
                bank, addr = BA(label)
                debug[(p.name, p.c.hook(addr, bank))] = label
    if args.hostile:
        def refused_it():
            return refused in host.seen
        run_linked(host, guest, wire, refused_it, 60000)
        print(f"hostile {args.hostile}: the host refused the party and went back to the Cable Club room")
        return 0
    table_tick = wire.tick
    stall = run_linked(host, guest, wire, parties_swapped, 60000)
    print(f"stage 4: parties exchanged after {wire.tick} ticks, {wire.messages} messages, stalls {stall}")
    for p in (host, guest):
        fired = sorted(label for (name, h), label in debug.items() if name == p.name and h in p.seen)
        if debug:
            print(f"  {p.name} passed: {fired}")
            for field in ("wEnemyMonOT", "wEnemyMonNicks", "wLinkEnemyTrainerName"):
                print(f"    {field}: {[hex(p.mem(field, i)) for i in range(11)]}")
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

    if args.drop:
        return drop_mid_trade(host, guest, wire)

    stall = run_linked(host, guest, wire, traded, 30000)
    print(f"stage 5: trade complete after {wire.tick} ticks, {wire.messages} messages, stalls {stall}")
    # hands off (more presses could start a second trade); wait for the save
    host.driver, guest.driver = host.wait(10**9), guest.wait(10**9)
    run_linked(host, guest, wire,
               lambda: saved_species(host) == guest.species and saved_species(guest) == host.species, 20000)
    frames = wire.tick - table_tick
    print(f"trade saved on both: {frames} frames (~{frames / 60:.0f} s at {args.delay} frames one-way delay) "
          f"from using the table; fast path blocks {host.c.blocks()}+{guest.c.blocks()}, "
          f"syncs {host.c.syncs()}+{guest.c.syncs()}")
    print(f"total {time.time() - t0:.1f}s")
    for p in (host, guest):
        p.snaps["saved"] = {"party": p.snapshot()["party"]}
        assert "exchange" in p.snaps, f"{p.name}: trade menu hook never fired"
    # the game re-exchanges after the trade and reopens the trade menu
    # (byte by byte at long delays the original sync can miss the other
    # side's nybble here and never finish: one reason for the fast path)
    run_linked(host, guest, wire, lambda: all("after trade" in p.snaps for p in (host, guest)), 20000,
               must=args.fast)
    if not all("after trade" in p.snaps for p in (host, guest)):
        print("the post-trade re-exchange did not finish byte by byte at this delay")
    return {"host": host.snaps, "guest": guest.snaps, "frames": frames}


if __name__ == "__main__":
    sys.exit(main())
