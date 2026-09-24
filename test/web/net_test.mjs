// net.js + protocol.js against a fake Trystero. Run: node test/web/net_test.mjs
import assert from "node:assert/strict";
import { Net, newRoomCode, normalizeCode } from "../../web/net.js";
import {
  validateCtl, validateChat, decodePos, encodePos, encodeLink, decodeLink, cleanName, RateLimiter,
} from "../../web/protocol.js";
import { FakeNet, settle } from "./fake_trystero.mjs";

const BUILD = "493aea78c62e631b76d3973f106f9ffcabf722aa";
const OTHER = "0".repeat(40);

// ---------- protocol unit checks ----------
assert.equal(cleanName("  Ash‮\u0000Ketchum is here  "), "AshKetchum i");
assert.equal(cleanName("   "), null);
assert.equal(validateChat({ text: "hi", extra: 1 }, false), null);
assert.equal(validateChat({ text: "x".repeat(1000) }, false), null);
assert.deepEqual(validateChat({ text: "a".repeat(300) }, false), { text: "a".repeat(120) });
assert.equal(validateChat({ slot: 9, text: "hi" }, true), null);
assert.equal(validateCtl({ t: "welcome", slot: 3, evil: 1 }), null);
assert.equal(validateCtl({ t: "welcome" }), null);
assert.equal(validateCtl({ t: "nope" }), null);
assert.equal(validateCtl(null), null);
assert.equal(validateCtl({ t: "roster", players: [[0, "a b", "x"]] }), null);
assert.ok(validateCtl({ t: "linkInvite", to: "abc", from: "def", sid: 5, mode: "trade" }));
assert.equal(validateCtl({ t: "linkInvite", to: "abc", from: "def", sid: 5, mode: "hack" }), null);
const pos = { map: 58, x: 11 * 16 + 6, y: 3 * 16, sprite: 9, flags: 2, seq: 200 };
assert.deepEqual({ ...decodePos(encodePos(pos), false), slot: undefined }, { ...pos, slot: undefined });
assert.equal(decodePos(new Uint8Array(7), false), null);
assert.equal(decodePos(new Uint8Array(9), false), null);
assert.equal(decodePos("hello", false), null);
assert.equal(decodePos({ length: 8 }, false), null);
const bad = encodePos(pos);
bad[5] = 0x40;
assert.equal(decodePos(bad, false), null);
assert.deepEqual(decodeLink(encodeLink(77, [0x101, 0x2fe])), { sid: 77, records: [0x101, 0x2fe] });
assert.equal(decodeLink(new Uint8Array([1, 0, 0, 0, 3, 0])), null);
assert.equal(decodeLink(new Uint8Array(4 + 65 * 2)), null);
{
  let t = 0;
  const r = new RateLimiter(2, 3, () => t);
  assert.ok(r.take() && r.take() && r.take());
  assert.ok(!r.take());
  t = 500;
  assert.ok(r.take());
  assert.ok(!r.take());
}
assert.equal(normalizeCode("ab-cd 12"), "ABCD12");
assert.equal(normalizeCode("a"), null);
assert.match(newRoomCode(), /^[A-Z2-9]{6}$/);
console.log("protocol: ok");

// ---------- rooms ----------
const fake = new FakeNet();
let clock = 0;
const mk = (id, name, build = BUILD) => {
  const n = new Net({ joinRoom: fake.joinRoomFor(id), selfId: id, build, protocol: 1, name, now: () => clock });
  const ev = { chat: [], pos: [], roster: [], closed: [], request: [], notice: [], joined: [], link: [] };
  for (const k of Object.keys(ev)) n.on(k, (...a) => ev[k].push(a));
  return { n, ev };
};

const host = mk("H", "Red");
host.n.open("ROOM1", "pw", true);
const g1 = mk("G1", "Blue");
const g2 = mk("G2", "Green");
const g3 = mk("G3", "Oak");
const wrong = mk("W", "Old", OTHER);
const nopw = mk("NP", "NoPass");
fake.block("G1", "G2"); // two phones that cannot reach each other
g1.n.open("ROOM1", "pw", false);
g2.n.open("ROOM1", "pw", false);
wrong.n.open("ROOM1", "pw", false);
nopw.n.open("ROOM1", "", false);
await settle(20);

// the wrong build is refused in the handshake; no password = other room
assert.ok(host.ev.notice.some(([m]) => /different game build/.test(m)));
assert.deepEqual(host.ev.request.map(([r]) => r.name).sort(), ["Blue", "Green"]);
assert.equal(g1.n.slot, -1, "not in before approval");

// nothing from an unapproved guest is relayed
g1.n.slot = 0; // pretend, to try to talk before approval
g1.n.sendChat("let me in");
g1.n.slot = -1;
await settle();
assert.equal(host.ev.chat.length, 0);

host.n.approve("G1");
host.n.approve("G2");
await settle(20);
assert.equal(g1.n.slot, 1);
assert.equal(g2.n.slot, 2);
assert.deepEqual(g2.ev.roster.at(-1)[0].map((p) => p[2]), ["Red", "Blue", "Green"]);

// chat is relayed through the host, sanitized and rate limited
g1.n.sendChat("hello\u0007 world");
await settle();
assert.deepEqual(host.ev.chat.at(-1)[0], { slot: 1, text: "hello world" });
assert.deepEqual(g2.ev.chat.at(-1)[0], { slot: 1, text: "hello world" });
for (let i = 0; i < 10; i++) g1.n.sendChat(`spam ${i}`);
await settle();
assert.ok(g2.ev.chat.length <= 3, `rate limit let ${g2.ev.chat.length} through`);

// presence: G1 -> host -> G2 even though G1 and G2 are not connected
g1.n.sendPos(pos);
await settle();
assert.equal(g2.ev.pos.at(-1)[0].slot, 1);
assert.equal(g2.ev.pos.at(-1)[0].x, pos.x);
assert.equal(host.ev.pos.at(-1)[0].slot, 1);

// a guest cannot inject presence claiming to be someone else via the host
const forged = new Uint8Array(9);
forged[0] = 0;
forged.set(encodePos(pos), 1);
g1.n.send("pos", forged, "H"); // 9 bytes: wrong size for guest->host
await settle();
assert.equal(host.ev.pos.length, 1);

// link bytes: G1 -> G2 must go via the host (blocked pair); H <-> G1 direct
g1.n.sendLink("G2", encodeLink(9, [0x155]));
host.n.sendLink("G1", encodeLink(9, [0x2aa]));
await settle(20);
assert.deepEqual(g2.ev.link.at(-1).slice(0, 1), ["G1"]);
assert.deepEqual(g2.ev.link.at(-1)[1].records, [0x155]);
assert.deepEqual(g1.ev.link.at(-1)[1].records, [0x2aa]);

// a flood of junk gets the peer dropped
for (let i = 0; i < 30; i++) g2.n.send("ctl", { t: "bogus" }, "H");
await settle(20);
assert.ok(g2.ev.closed.length === 1, "junk sender was kicked");
assert.ok(!host.n.rosterList().some((p) => p[1] === "G2"));

// kick
host.n.kick("G1");
await settle(20);
assert.match(g1.ev.closed[0][0], /removed/);
assert.equal(host.n.rosterList().length, 1);

// room cap: fill up to 8
const extra = [];
for (let i = 0; i < 8; i++) {
  const e = mk(`E${i}`, `P${i}`);
  e.n.open("ROOM1", "pw", false);
  extra.push(e);
}
await settle(30);
for (const e of extra) host.n.approve(e.n.selfId);
await settle(30);
assert.equal(host.n.rosterList().length, 8);
assert.equal(extra.filter((e) => e.n.slot > 0).length, 7);
assert.equal(extra.filter((e) => e.ev.closed.some(([m]) => /full/.test(m))).length, 1);

// host leaving closes the room for guests
await host.n.leave();
await settle(20);
assert.ok(extra.filter((e) => e.n.slot > 0).every((e) => e.ev.closed.some(([m]) => /host left/.test(m))));
console.log("net_test: ok");
