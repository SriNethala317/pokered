// Rooms over Trystero (WebRTC, Nostr relays for signaling; no server of ours).
//
// Star topology: the room creator is the host. Guests send presence and chat
// to the host only, and accept presence, chat and control only from the host,
// which relays them. The host approves every guest, can kick, and caps the room
// at MAX_PLAYERS. Link cable bytes go straight to the other player when the
// two are connected, else through the host.
//
// Before a peer counts as joined, both sides exchange {protocol, build sha1,
// host} in Trystero's handshake; a peer running another build is refused.

import {
  MAX_PLAYERS, LIMITS, RateLimiter, cleanName, validateCtl, validateChat, validateHello,
  encodePos, decodePos, decodeLink,
} from "./protocol.js";

export const TRYSTERO_URL = "https://cdn.jsdelivr.net/npm/@trystero-p2p/nostr@0.25.4/+esm";
const APP_ID = "resonance-pokered";
const STRIKES = 20; // malformed or over-limit packets before a peer is dropped

const CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
export function newRoomCode(rand = Math.random) {
  let s = "";
  for (let i = 0; i < 6; i++) s += CODE_CHARS[Math.floor(rand() * CODE_CHARS.length)];
  return s;
}
export function normalizeCode(code) {
  const c = String(code || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
  return c.length >= 4 && c.length <= 12 ? c : null;
}

export async function loadTrystero() {
  return import(/* @vite-ignore */ TRYSTERO_URL);
}

export class Net {
  // opts: { joinRoom, selfId, build, protocol, name, turn }
  constructor(opts) {
    this.joinRoom = opts.joinRoom;
    this.selfId = opts.selfId;
    this.build = opts.build;
    this.protocol = opts.protocol;
    this.name = cleanName(opts.name) || "Trainer";
    this.turn = opts.turn || null;
    this.now = opts.now || (() => performance.now());
    this.room = null;
    this.isHost = false;
    this.hostId = null;
    this.slot = -1;
    this.peers = new Map(); // peerId -> { hello, approved, slot, name, lim, strikes }
    this.roster = new Map(); // slot -> { peerId, name }
    this.handlers = {};
    this.banned = new Set();
  }

  on(ev, fn) {
    (this.handlers[ev] ||= []).push(fn);
  }
  emit(ev, ...a) {
    for (const f of this.handlers[ev] || []) {
      try {
        f(...a);
      } catch (e) {
        console.error(e);
      }
    }
  }

  // ---- lifecycle ----
  open(code, password, asHost) {
    this.isHost = asHost;
    this.slot = asHost ? 0 : -1;
    this.code = code;
    const config = { appId: APP_ID };
    if (password) config.password = password;
    if (this.turn) config.turnConfig = [this.turn];
    this.room = this.joinRoom(config, `room-${code}`, {
      onPeerHandshake: (peerId, send, receive) => this.handshake(peerId, send, receive),
      handshakeTimeoutMs: 10000,
      onJoinError: (d) => this.emit("error", `could not join: ${d.error}`),
    });
    const mk = (ns) => this.room.makeAction(ns);
    this.a = { ctl: mk("ctl"), pos: mk("pos"), chat: mk("chat"), link: mk("link"), linkR: mk("linkR") };
    this.a.ctl.onMessage = (d, { peerId }) => this.onCtl(d, peerId);
    this.a.pos.onMessage = (d, { peerId }) => this.onPos(d, peerId);
    this.a.chat.onMessage = (d, { peerId }) => this.onChat(d, peerId);
    this.a.link.onMessage = (d, { peerId }) => this.onLink(d, peerId, false);
    this.a.linkR.onMessage = (d, { peerId }) => this.onLinkRelay(d, peerId);
    this.room.onPeerJoin = (id) => this.onPeerJoin(id);
    this.room.onPeerLeave = (id) => this.onPeerLeave(id);
    if (asHost) {
      this.roster.set(0, { peerId: this.selfId, name: this.name });
      this.emit("roster", this.rosterList());
    }
  }

  async leave() {
    const r = this.room;
    this.room = null;
    this.peers.clear();
    this.roster.clear();
    this.hostId = null;
    if (r) await r.leave();
  }

  async handshake(peerId, send, receive) {
    await send({ protocol: this.protocol, build: this.build, host: this.isHost });
    const { data } = await receive();
    const hello = validateHello(data);
    if (!hello) throw new Error("bad handshake");
    if (hello.protocol !== this.protocol || hello.build !== this.build) {
      this.emit("notice", "Someone with a different game build tried to connect and was refused.");
      throw new Error("different build");
    }
    if (this.banned.has(peerId)) throw new Error("banned");
    if (this.isHost && hello.host) throw new Error("two hosts");
    if (!this.isHost && hello.host && this.hostId && this.hostId !== peerId) throw new Error("second host");
    this.peers.set(peerId, this.newPeer(hello));
  }

  newPeer(hello) {
    const lim = {};
    for (const [k, [r, b]] of Object.entries(LIMITS)) lim[k] = new RateLimiter(r, b, this.now);
    return { hello, approved: false, slot: -1, name: "", lim, strikes: 0 };
  }

  onPeerJoin(peerId) {
    const p = this.peers.get(peerId);
    if (!p) return;
    if (!this.isHost && p.hello.host && !this.hostId) {
      this.hostId = peerId;
      this.send("ctl", { t: "join", name: this.name }, peerId);
      this.emit("status", "Waiting for the host to let you in…");
    }
  }

  onPeerLeave(peerId) {
    const p = this.peers.get(peerId);
    this.peers.delete(peerId);
    if (!p) return;
    this.emit("peerLeave", peerId);
    if (!this.isHost && peerId === this.hostId) {
      this.emit("closed", "The host left the room.");
      this.leave();
      return;
    }
    if (this.isHost && p.approved) {
      this.roster.delete(p.slot);
      this.broadcastRoster();
    }
  }

  // ---- sending ----
  send(ch, data, target) {
    if (!this.room) return;
    this.a[ch].send(data, target ? { target } : undefined).catch(() => {});
  }

  approvedIds(except) {
    const ids = [];
    for (const [id, p] of this.peers) if (p.approved && id !== except) ids.push(id);
    return ids;
  }

  sendPos(p) {
    if (!this.room || this.slot < 0) return;
    const bytes = encodePos(p);
    if (this.isHost) {
      const ids = this.approvedIds();
      if (ids.length) this.send("pos", withSlot(0, bytes), ids);
    } else if (this.hostId) {
      this.send("pos", bytes, this.hostId);
    }
  }

  sendChat(text) {
    if (!this.room || this.slot < 0) return false;
    const msg = validateChat({ text }, false);
    if (!msg) return false;
    if (!this.selfChat) this.selfChat = new RateLimiter(...LIMITS.chat, this.now);
    if (!this.selfChat.take()) return false;
    if (this.isHost) {
      const out = { slot: 0, text: msg.text };
      const ids = this.approvedIds();
      if (ids.length) this.send("chat", out, ids);
      this.emit("chat", out);
    } else {
      this.send("chat", msg, this.hostId);
      this.emit("chat", { slot: this.slot, text: msg.text });
    }
    return true;
  }

  // Link control goes through the host (which checks both are in the room).
  sendLinkCtl(msg) {
    if (!this.room || this.slot < 0) return;
    const m = { ...msg, from: this.selfId };
    if (!validateCtl(m)) throw new Error("bad link ctl");
    if (this.isHost) this.send("ctl", m, m.to);
    else this.send("ctl", m, this.hostId);
  }

  // Link bytes: direct if connected to that peer, else via the host.
  sendLink(peerId, bytes) {
    if (!this.room) return;
    const direct = this.peers.get(peerId);
    if (direct && direct.hello && this.isConnected(peerId)) {
      this.send("link", bytes, peerId);
    } else if (!this.isHost && this.hostId) {
      const slot = this.slotOf(peerId);
      if (slot >= 0) this.send("linkR", withSlot(slot, bytes), this.hostId);
    }
  }

  isConnected(peerId) {
    const pcs = this.room?.getPeers?.() || {};
    const pc = pcs[peerId];
    return !!pc && (!pc.connectionState || pc.connectionState === "connected");
  }

  slotOf(peerId) {
    for (const [slot, r] of this.roster) if (r.peerId === peerId) return slot;
    return -1;
  }

  // ---- host actions ----
  approve(peerId) {
    const p = this.peers.get(peerId);
    if (!this.isHost || !p || p.approved) return;
    let slot = -1;
    for (let i = 1; i < MAX_PLAYERS; i++) if (!this.roster.has(i)) { slot = i; break; }
    if (slot < 0) return this.deny(peerId, "The room is full.");
    p.approved = true;
    p.slot = slot;
    this.roster.set(slot, { peerId, name: p.name });
    this.send("ctl", { t: "welcome", slot }, peerId);
    this.broadcastRoster();
  }

  deny(peerId, reason = "The host said no.") {
    if (!this.isHost) return;
    this.send("ctl", { t: "deny", reason }, peerId);
    this.peers.delete(peerId);
    this.banned.add(peerId);
  }

  kick(peerId) {
    const p = this.peers.get(peerId);
    if (!this.isHost || !p) return;
    this.send("ctl", { t: "kick" }, peerId);
    this.banned.add(peerId);
    this.peers.delete(peerId);
    if (p.approved) {
      this.roster.delete(p.slot);
      this.broadcastRoster();
    }
    this.emit("peerLeave", peerId);
  }

  rosterList() {
    return [...this.roster].map(([slot, r]) => [slot, r.peerId, r.name]).sort((a, b) => a[0] - b[0]);
  }

  broadcastRoster() {
    const players = this.rosterList();
    const ids = this.approvedIds();
    if (ids.length) this.send("ctl", { t: "roster", players }, ids);
    this.emit("roster", players);
  }

  // ---- receiving ----
  strike(peerId, why) {
    const p = this.peers.get(peerId);
    if (!p) return;
    if (++p.strikes >= STRIKES) {
      this.emit("notice", `Dropped a peer that sent bad data (${why}).`);
      if (this.isHost) this.kick(peerId);
      else {
        this.peers.delete(peerId);
        this.banned.add(peerId);
        if (peerId === this.hostId) {
          this.emit("closed", "The host sent bad data.");
          this.leave();
        }
      }
    }
  }

  gate(peerId, ch) {
    const p = this.peers.get(peerId);
    if (!p || this.banned.has(peerId)) return null;
    if (!p.lim[ch].take()) {
      this.strike(peerId, `${ch} rate`);
      return null;
    }
    return p;
  }

  onCtl(data, peerId) {
    const p = this.gate(peerId, "ctl");
    if (!p) return;
    const m = validateCtl(data);
    if (!m) return this.strike(peerId, "ctl");
    if (this.isHost) return this.hostCtl(m, p, peerId);
    if (peerId !== this.hostId) return this.strike(peerId, "ctl from non-host");
    switch (m.t) {
      case "welcome":
        this.slot = m.slot;
        this.emit("status", "You're in!");
        this.emit("joined", m.slot);
        break;
      case "deny":
        this.emit("closed", m.reason);
        this.leave();
        break;
      case "kick":
        this.emit("closed", "The host removed you from the room.");
        this.leave();
        break;
      case "roster":
        this.roster.clear();
        for (const [slot, id, name] of m.players) this.roster.set(slot, { peerId: id, name: cleanName(name) || "?" });
        this.emit("roster", this.rosterList());
        break;
      case "linkInvite":
      case "linkAnswer":
      case "linkEnd":
        if (m.to === this.selfId && this.slotOf(m.from) >= 0) this.emit("linkCtl", m);
        break;
      default:
        this.strike(peerId, "ctl type");
    }
  }

  hostCtl(m, p, peerId) {
    if (m.t === "join") {
      if (p.approved || p.requested) return;
      p.requested = true;
      p.name = cleanName(m.name) || "Trainer";
      if (this.roster.size >= MAX_PLAYERS) return this.deny(peerId, "The room is full.");
      this.emit("request", { peerId, name: p.name });
      return;
    }
    if (!p.approved) return this.strike(peerId, "ctl before approval");
    if (m.t === "linkInvite" || m.t === "linkAnswer" || m.t === "linkEnd") {
      if (m.from !== peerId) return this.strike(peerId, "spoofed from");
      if (m.to === this.selfId) return this.emit("linkCtl", m);
      const q = this.peers.get(m.to);
      if (q && q.approved) this.send("ctl", m, m.to);
      return;
    }
    this.strike(peerId, "ctl type");
  }

  onPos(data, peerId) {
    const p = this.gate(peerId, "pos");
    if (!p) return;
    if (this.isHost) {
      if (!p.approved) return;
      const pos = decodePos(data, false);
      if (!pos) return this.strike(peerId, "pos");
      pos.slot = p.slot;
      this.emit("pos", pos);
      const ids = this.approvedIds(peerId);
      if (ids.length) this.send("pos", withSlot(p.slot, encodePos(pos)), ids);
    } else {
      if (peerId !== this.hostId) return; // guests ignore each other's presence
      const pos = decodePos(data, true);
      if (!pos) return this.strike(peerId, "pos");
      if (pos.slot === this.slot || !this.roster.has(pos.slot)) return;
      this.emit("pos", pos);
    }
  }

  onChat(data, peerId) {
    const p = this.gate(peerId, "chat");
    if (!p) return;
    if (this.isHost) {
      if (!p.approved) return;
      const m = validateChat(data, false);
      if (!m) return this.strike(peerId, "chat");
      const out = { slot: p.slot, text: m.text };
      this.emit("chat", out);
      const ids = this.approvedIds(peerId);
      if (ids.length) this.send("chat", out, ids);
    } else {
      if (peerId !== this.hostId) return;
      const m = validateChat(data, true);
      if (!m) return this.strike(peerId, "chat");
      if (m.slot === this.slot || !this.roster.has(m.slot)) return;
      this.emit("chat", m);
    }
  }

  onLink(data, fromPeer) {
    const p = this.gate(fromPeer, "link");
    if (!p) return;
    const pkt = decodeLink(data);
    if (!pkt) return this.strike(fromPeer, "link");
    this.emit("link", fromPeer, pkt);
  }

  // [slot][link payload]. Guest -> host: slot is the destination.
  // Host -> guest: slot is the origin.
  onLinkRelay(data, peerId) {
    const p = this.gate(peerId, "link");
    if (!p) return;
    const b = data instanceof Uint8Array ? data : data instanceof ArrayBuffer ? new Uint8Array(data) : null;
    if (!b || b.length < 7) return this.strike(peerId, "linkR");
    const slot = b[0];
    const inner = b.subarray(1);
    const pkt = decodeLink(inner);
    if (!pkt) return this.strike(peerId, "linkR");
    if (this.isHost) {
      if (!p.approved) return;
      const dest = this.roster.get(slot);
      if (!dest) return;
      if (dest.peerId === this.selfId) return this.emit("link", peerId, pkt);
      this.send("linkR", withSlot(p.slot, inner), dest.peerId);
    } else {
      if (peerId !== this.hostId) return;
      const origin = this.roster.get(slot);
      if (origin) this.emit("link", origin.peerId, pkt);
    }
  }
}

function withSlot(slot, bytes) {
  const b = new Uint8Array(bytes.length + 1);
  b[0] = slot;
  b.set(bytes, 1);
  return b;
}
