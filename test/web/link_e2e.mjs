// End-to-end link session through the page's own modules, in node:
// two WASM consoles (web/emu.js), each with web/net.js + web/linkhost.js, in
// a room hosted by a third player, over the in-memory Trystero stand-in. The
// two traders cannot reach each other directly (like two phones on mobile
// data), so every link byte is relayed through the room host.
//
// Both walk up to Pewter's Cable Club receptionist and talk at the same time
// (the invitee is gated, so the inviter always drives the clock), go through
// the link menu into the Trade Center, trade, and each ends up with the
// other's Pokémon, saved. Then the room host goes silent-free but the link
// times out on a fake clock: both sessions end, the cable is unplugged and
// the games reset, keeping the saved trade. Stray bytes with the wrong
// session id are ignored.
//
// Run: node test/web/link_e2e.mjs   (needs make web; ~1 min)
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import assert from "node:assert/strict";
import { Emulator, KEY } from "../../web/emu.js";
import { Net } from "../../web/net.js";
import { LinkHost } from "../../web/linkhost.js";
import { FakeNet, settle } from "./fake_trystero.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const manifest = JSON.parse(readFileSync(path.join(root, "web/build/manifest.json"), "utf8"));
const { default: createCore } = await import(path.join(root, "web/build/core.js"));
const M = await createCore();
const rom = new Uint8Array(readFileSync(path.join(root, "pokered.gbc")));

const sym = {};
for (const line of readFileSync(path.join(root, "pokered.sym"), "utf8").split("\n")) {
  const m = /^([0-9a-f]{2}):([0-9a-f]{4}) (\S+)/i.exec(line);
  if (m) sym[m[3]] = { bank: parseInt(m[1], 16), addr: parseInt(m[2], 16) };
}
const A = (n) => sym[n].addr;
const K = (() => {
  const names = ["REDS_HOUSE_2F", "PEWTER_CITY", "PEWTER_POKECENTER", "TRADE_CENTER", "EVENT_GOT_POKEDEX",
    "BIT_FLY_WARP", "RATTATA", "PIDGEY", "USING_INTERNAL_CLOCK", "USING_EXTERNAL_CLOCK"];
  const src = 'INCLUDE "includes.asm"\n' + names.map((n) => `PRINTLN "${n}=", ${n}\n`).join("");
  const out = execFileSync("rgbasm", ["-o", "/dev/null", "-"], { cwd: root, input: src }).toString();
  return Object.fromEntries(out.trim().split("\n").map((l) => l.split("=")).map(([k, v]) => [k, parseInt(v.replace("$", ""), 16)]));
})();

let clock = 0;
const now = () => clock;

class Player {
  constructor(name, species) {
    this.name = name;
    this.species = species;
    this.emu = new Emulator(M, null);
    this.emu.setMuted(true);
    this.emu.loadRom(rom);
    this.emu.kick = () => {}; // the test drives frames itself
    this.s = this.emu.s;
    this.seen = new Set();
    this.hookIds = {};
  }
  read = (a) => this.emu.read(a);
  write = (a, v) => M._shim_write(this.s, a, v);
  hooks() {
    this.hookIds.ow = M._shim_hook_add(this.s, A("OverworldLoop"), -1, 0);
    this.hookIds.lm = M._shim_hook_add(this.s, sym.LinkMenu.addr, sym.LinkMenu.bank, 0);
  }
  collect() {
    for (let h; (h = M._shim_hook_next(this.s)) >= 0; ) this.seen.add(h);
  }
  frames(n) {
    for (let i = 0; i < n; i++) {
      M._shim_run_frame(this.s);
      this.collect();
    }
  }
  press(k, hold = 3, rel = 24) {
    this.emu.setKeys(KEY[k]);
    this.frames(hold);
    this.emu.setKeys(0);
    this.frames(rel);
  }
  pos() {
    return [this.read(A("wYCoord")), this.read(A("wXCoord"))];
  }
  goto(y, x) {
    for (let i = 0; i < 80; i++) {
      const [py, px] = this.pos();
      if (py === y && px === x) return;
      this.press(py > y ? "up" : py < y ? "down" : px > x ? "left" : "right");
    }
    throw new Error(`${this.name} stuck at ${this.pos()}`);
  }
  setup() {
    this.hooks();
    for (let i = 1; ; i++) {
      assert.ok(i < 4000, "never reached the overworld");
      this.press(i % 10 === 0 ? "start" : "a", 3, 6);
      if (this.seen.has(this.hookIds.ow) && this.read(A("wCurMap")) === K.REDS_HOUSE_2F) break;
    }
    this.frames(60);
    // give a Pokémon by calling AddPartyMon from the top of the overworld loop
    M._shim_hook_clear(this.s);
    M._shim_hook_add(this.s, A("OverworldLoop"), -1, 1);
    this.write(A("wCurPartySpecies"), this.species);
    this.write(A("wCurEnemyLevel"), 10);
    this.write(A("wMonDataLocation"), 0x10);
    while (M._shim_run_frame(this.s) !== 2);
    const pc = M._shim_reg(this.s, 5), sp = M._shim_reg(this.s, 4) - 2;
    this.write(sp, pc & 0xff);
    this.write(sp + 1, pc >> 8);
    M._shim_set_reg(this.s, 4, sp);
    M._shim_set_reg(this.s, 5, A("AddPartyMon"));
    M._shim_hook_clear(this.s);
    this.seen.clear();
    this.hooks();
    this.frames(30);
    const e = K.EVENT_GOT_POKEDEX;
    this.write(A("wEventFlags") + (e >> 3), this.read(A("wEventFlags") + (e >> 3)) | (1 << (e & 7)));
    this.write(A("wDestinationMap"), K.PEWTER_CITY);
    this.write(A("wStatusFlags6"), this.read(A("wStatusFlags6")) | (1 << K.BIT_FLY_WARP));
    this.frames(400);
    assert.equal(this.read(A("wCurMap")), K.PEWTER_CITY);
    this.press("up", 20, 100);
    assert.equal(this.read(A("wCurMap")), K.PEWTER_POKECENTER);
    this.goto(3, 11);
    assert.equal(this.read(A("wPartyCount")), 1);
  }
  // driver primitives (generators, one yield per emulated frame)
  *wait(n) {
    this.emu.setKeys(0);
    for (let i = 0; i < n; i++) yield;
  }
  *tap(k, rel = 20) {
    this.emu.setKeys(KEY[k]);
    for (let i = 0; i < 4; i++) yield;
    yield* this.wait(rel);
  }
  savedSpecies() {
    const at = sym.sPartyData;
    return this.emu.saveSram()[at.bank * 0x2000 + (at.addr - 0xa000) + 1];
  }
}

const t0 = Date.now();
const alice = new Player("alice", K.RATTATA);
const bob = new Player("bob", K.PIDGEY);
alice.setup();
bob.setup();
console.log(`setup ${((Date.now() - t0) / 1000).toFixed(1)}s`);

// ---- room: host H (just a room host, no game), alice and bob can't connect
const fake = new FakeNet();
fake.block("alice", "bob");
const mkNet = (id, host) => {
  const n = new Net({ joinRoom: fake.joinRoomFor(id), selfId: id, build: manifest.romSha1, protocol: manifest.protocol, name: id, now });
  n.open("LINKTEST", "", host);
  return n;
};
const H = mkNet("H", true);
H.on("request", ({ peerId }) => H.approve(peerId));
const nets = { alice: mkNet("alice", false), bob: mkNet("bob", false) };
await settle(30);
assert.equal(nets.alice.slot >= 1 && nets.bob.slot >= 1, true, "both approved");

const ended = {};
const states = [];
for (const p of [alice, bob]) {
  p.net = nets[p.name];
  p.link = new LinkHost({
    emu: p.emu, net: p.net, manifest, now, timers: false,
    ui: {
      state: (t) => states.push(`${p.name}: ${t}`),
      incoming: async (m) => m.mode === "trade",
      ended: (reason, reset) => (ended[p.name] = { reason, reset }),
    },
  });
}
alice.link.invite("bob", "trade");
await settle(30);
assert.ok(alice.link.active && bob.link.active, `session not started: ${states.join(" | ")}`);
assert.equal(alice.link.session.role, "host");
assert.equal(bob.link.session.role, "guest");

// a stray packet with the wrong session id is ignored
const rx0 = M._shim_link_bytes_received(bob.s);
bob.link.onLink("alice", { sid: bob.link.session.sid ^ 1, records: [0x155] });
bob.link.onLink("H", { sid: bob.link.session.sid, records: [0x155] });
M._shim_run_frame(bob.s);
assert.equal(M._shim_link_bytes_received(bob.s), rx0, "stray link bytes reached the console");

// ---- linked play
let ticks = 0;
async function runLinked(until, budget) {
  for (let i = 0; i < budget; i++) {
    for (const p of [alice, bob]) {
      for (let tries = 0; tries < 4; tries++) {
        const ok = p.emu.step();
        p.collect();
        if (ok) {
          p.driver.next();
          break;
        }
        await settle(0);
      }
    }
    await settle(0);
    ticks++;
    clock += 16.7;
    if (until()) return;
  }
  throw new Error(`timed out: alice map ${alice.read(A("wCurMap"))} status ${alice.read(0xffaa)}, bob map ${bob.read(A("wCurMap"))} status ${bob.read(0xffaa)}`);
}
const inMenu = (p) => p.seen.has(p.hookIds.lm);
function* mashUntil(p, cond) {
  while (!cond()) yield* p.tap("a", 24);
}
function* talk(p) {
  yield* p.wait(20);
  yield* p.tap("up");
  yield* mashUntil(p, () => inMenu(p));
  yield* p.wait(1e9);
}
// both talk to the receptionist at the same time
alice.driver = talk(alice);
bob.driver = talk(bob);
await runLinked(() => inMenu(alice) && inMenu(bob), 20000);
assert.equal(alice.read(0xffaa), K.USING_INTERNAL_CLOCK, "the inviter drives the clock");
assert.equal(bob.read(0xffaa), K.USING_EXTERNAL_CLOCK);
console.log(`link menu reached on both after ${ticks} ticks`);

alice.driver = (function* () {
  yield* alice.wait(60);
  yield* alice.tap("a");
  yield* alice.wait(1e9);
})();
bob.driver = bob.wait(1e9);
const tc = K.TRADE_CENTER;
await runLinked(() => alice.read(A("wCurMap")) === tc && bob.read(A("wCurMap")) === tc, 20000);
let settleTicks = 0;
await runLinked(() => ++settleTicks > 120, 200);

function* useTable(p, face) {
  yield* p.tap(face);
  yield* p.tap("a");
  yield* p.wait(1e9);
}
alice.driver = useTable(alice, "right");
bob.driver = useTable(bob, "left");
const E = A("wEnemyPartySpecies");
await runLinked(() => alice.read(E) === bob.species && bob.read(E) === alice.species, 60000);
console.log(`parties exchanged after ${ticks} ticks`);

function* trade(p) {
  yield* p.wait(120);
  yield* p.tap("a", 40);
  yield* p.tap("right", 20);
  for (;;) yield* p.tap("a", 40);
}
alice.driver = trade(alice);
bob.driver = trade(bob);
const P = A("wPartySpecies");
await runLinked(() => alice.read(P) === bob.species && bob.read(P) === alice.species, 30000);
// hands off (more A presses could start a second trade) and wait for the game
// to save, after the animation and one more sync over the link
alice.driver = alice.wait(1e9);
bob.driver = bob.wait(1e9);
await runLinked(() => alice.savedSpecies() === bob.species && bob.savedSpecies() === alice.species, 6000);
const relayed = fake.log.filter(([ns]) => ns === "linkR").length;
const direct = fake.log.filter(([ns, from, to]) => ns === "link" && ((from === "alice" && to === "bob") || (from === "bob" && to === "alice"))).length;
console.log(`trade done after ${ticks} ticks; ${relayed} relayed link packets, ${direct} direct`);
assert.ok(relayed > 0 && direct === 0, "alice and bob are blocked, so the host must relay");
assert.equal(alice.savedSpecies(), bob.species, "alice's save has bob's Pokémon");
assert.equal(bob.savedSpecies(), alice.species, "bob's save has alice's Pokémon");

// ---- the link goes quiet: timeout ends both sessions and resets the games
fake.block("alice", "H"); // alice's connection drops (no leave event)
for (const r of fake.rooms.values()) for (const m of r) if (m.selfId === "alice") m.connected.delete("H");
for (const r of fake.rooms.values()) for (const m of r) if (m.selfId === "H") m.connected.delete("alice");
clock += 11000;
alice.link.pump();
bob.link.pump();
assert.ok(ended.alice && ended.bob, "both sessions ended on timeout");
assert.ok(ended.alice.reset && ended.bob.reset, "games in the Trade Center were reset");
assert.equal(M._shim_link_plugged(alice.s), 0);
assert.equal(M._shim_link_plugged(bob.s), 0);
alice.frames(300);
assert.equal(alice.savedSpecies(), bob.species, "the finished trade stays saved");
console.log(`link_e2e: ok (${((Date.now() - t0) / 1000).toFixed(1)}s)`);
process.exit(0);
