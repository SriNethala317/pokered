// Wire formats and validation for everything peers send each other.
// Every incoming packet goes through here before anything else looks at it:
// wrong type, wrong size, unknown fields or too many per second -> dropped,
// and a peer that keeps sending junk is disconnected by net.js.
// Nothing received from a peer is ever written into game memory, except link
// cable bytes during a session both players accepted (linkhost.js).

export const MAX_PLAYERS = 8;
export const NAME_MAX = 12;
export const CHAT_MAX = 120;

// ---- token-bucket rate limiter ----
export class RateLimiter {
  constructor(perSecond, burst, now = () => performance.now()) {
    this.rate = perSecond / 1000;
    this.burst = burst;
    this.tokens = burst;
    this.now = now;
    this.last = now();
  }
  take(n = 1) {
    const t = this.now();
    this.tokens = Math.min(this.burst, this.tokens + (t - this.last) * this.rate);
    this.last = t;
    if (this.tokens < n) return false;
    this.tokens -= n;
    return true;
  }
}

// Per-peer limits by channel: [per second, burst]
export const LIMITS = {
  ctl: [10, 20],
  pos: [25, 30],
  chat: [0.5, 3],
  link: [4000, 4000],
};

// ---- names and chat text ----
// Printable characters only; no control, bidi-override or zero-width chars.
const BAD_CHARS = /[\u0000-\u001f\u007f-\u009f​-‏‪-‮⁠-⁯﻿]/g;

export function cleanText(s, max) {
  if (typeof s !== "string") return null;
  const t = s.replace(BAD_CHARS, "").replace(/\s+/g, " ").trim();
  if (!t) return null;
  return Array.from(t).slice(0, max).join("");
}

export const cleanName = (s) => cleanText(s, NAME_MAX);

// ---- control messages (JSON) ----
const isStr = (v, max) => typeof v === "string" && v.length <= max;
const isInt = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;
const isId = (v) => typeof v === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(v);

// type -> { field: check }. Unknown fields or types are rejected.
const CTL = {
  // guest -> host: ask to join
  join: { name: (v) => isStr(v, 64) },
  // host -> guest: accepted; slot is the guest's roster index
  welcome: { slot: (v) => isInt(v, 0, MAX_PLAYERS - 1) },
  deny: { reason: (v) => isStr(v, 80) },
  kick: {},
  // host -> all: the roster [ [slot, peerId, name], ... ]
  roster: {
    players: (v) =>
      Array.isArray(v) &&
      v.length <= MAX_PLAYERS &&
      v.every(
        (p) => Array.isArray(p) && p.length === 3 && isInt(p[0], 0, MAX_PLAYERS - 1) && isId(p[1]) && isStr(p[2], 64)
      ),
  },
  // link sessions: invite / answer / end, between two players
  linkInvite: { to: isId, from: isId, sid: (v) => isInt(v, 1, 2 ** 31), mode: (v) => v === "battle" || v === "trade" },
  linkAnswer: { to: isId, from: isId, sid: (v) => isInt(v, 1, 2 ** 31), ok: (v) => typeof v === "boolean" },
  linkEnd: { to: isId, from: isId, sid: (v) => isInt(v, 1, 2 ** 31), reason: (v) => isStr(v, 80) },
};

export function validateCtl(msg) {
  if (!msg || typeof msg !== "object" || Array.isArray(msg)) return null;
  const spec = CTL[msg.t];
  if (!spec) return null;
  const keys = Object.keys(msg);
  if (keys.length > Object.keys(spec).length + 1) return null;
  for (const k of keys) {
    if (k === "t") continue;
    if (!spec[k] || !spec[k](msg[k])) return null;
  }
  for (const k of Object.keys(spec)) if (!(k in msg)) return null;
  return msg;
}

// ---- chat (JSON): { text } from a player; host relays { slot, text } ----
export function validateChat(msg, fromHost) {
  if (!msg || typeof msg !== "object" || Array.isArray(msg)) return null;
  const keys = Object.keys(msg).sort().join(",");
  if (fromHost ? keys !== "slot,text" : keys !== "text") return null;
  if (fromHost && !isInt(msg.slot, 0, MAX_PLAYERS - 1)) return null;
  if (typeof msg.text !== "string" || msg.text.length > CHAT_MAX * 4) return null;
  const text = cleanText(msg.text, CHAT_MAX);
  if (!text) return null;
  return fromHost ? { slot: msg.slot, text } : { text };
}

// ---- presence (binary) ----
// 8 bytes: map, x lo, x hi, y lo, y hi, sprite, flags, seq
// x/y are map pixels + 32 (the top-left of the 16x16 sprite, before the -4
// sprite lift). The host relays it with the sender's slot in front (9 bytes).
export const POS_LEN = 8;
export const FLAG = { BATTLE: 1, GRASS: 2, HIDDEN: 4 };

export function encodePos(p) {
  const b = new Uint8Array(POS_LEN);
  const x = Math.max(0, Math.min(0xffff, p.x + 32));
  const y = Math.max(0, Math.min(0xffff, p.y + 32));
  b[0] = p.map;
  b[1] = x & 0xff;
  b[2] = x >> 8;
  b[3] = y & 0xff;
  b[4] = y >> 8;
  b[5] = p.sprite & 0x0f;
  b[6] = p.flags & 0x07;
  b[7] = p.seq & 0xff;
  return b;
}

function bytesOf(data) {
  if (data instanceof Uint8Array) return data;
  if (data instanceof ArrayBuffer) return new Uint8Array(data);
  if (ArrayBuffer.isView(data)) return new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  return null;
}

// fromHost: expect the 9-byte relayed form. Returns null if malformed.
export function decodePos(data, fromHost) {
  const b = bytesOf(data);
  if (!b || b.length !== POS_LEN + (fromHost ? 1 : 0)) return null;
  let o = 0, slot = -1;
  if (fromHost) {
    slot = b[0];
    if (slot >= MAX_PLAYERS) return null;
    o = 1;
  }
  if (b[o + 5] > 0x0f || b[o + 6] > 0x07) return null;
  const x = (b[o + 1] | (b[o + 2] << 8)) - 32;
  const y = (b[o + 3] | (b[o + 4] << 8)) - 32;
  if (x < -32 || y < -32 || x > 256 * 16 || y > 256 * 16) return null;
  return { slot, map: b[o], x, y, sprite: b[o + 5], flags: b[o + 6], seq: b[o + 7] };
}

// ---- link bytes (binary) ----
// [sid (4 bytes LE), then up to 512 records of (kind, byte)]. Kinds are the
// shim's: 1 XFER, 2 REPLY, 3 BLOCK byte, 4 BLOCK end, 5 NYBBLE sync.
// No records = a heartbeat.
export const LINK_MAX_RECORDS = 512;

export function encodeLink(sid, records) {
  const b = new Uint8Array(4 + records.length * 2);
  b[0] = sid & 0xff;
  b[1] = (sid >>> 8) & 0xff;
  b[2] = (sid >>> 16) & 0xff;
  b[3] = (sid >>> 24) & 0xff;
  records.forEach((v, i) => {
    b[4 + i * 2] = v >> 8;
    b[5 + i * 2] = v & 0xff;
  });
  return b;
}

export function decodeLink(data) {
  const b = bytesOf(data);
  if (!b || b.length < 4 || b.length % 2 || (b.length - 4) / 2 > LINK_MAX_RECORDS) return null;
  const sid = (b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24)) >>> 0;
  const records = [];
  for (let i = 4; i < b.length; i += 2) {
    if (b[i] < 1 || b[i] > 5) return null;
    records.push((b[i] << 8) | b[i + 1]);
  }
  return { sid, records };
}

// ---- same-build handshake ----
// Exchanged in Trystero's onPeerHandshake before a peer counts as joined.
export function validateHello(msg) {
  if (!msg || typeof msg !== "object") return null;
  if (!isInt(msg.protocol, 0, 1e6)) return null;
  if (typeof msg.build !== "string" || !/^[0-9a-f]{40}$/.test(msg.build)) return null;
  if (typeof msg.host !== "boolean") return null;
  return { protocol: msg.protocol, build: msg.build, host: msg.host };
}
