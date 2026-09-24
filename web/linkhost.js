// Link cable sessions between two players in a room.
//
// A session starts only when one player invites and the other accepts in the
// page UI. Until then the cable is unplugged and the game sees no cable, and
// no remote byte can reach the console. During a session the shim's lockstep
// serial bytes (see web/core/link_shim.h) are carried over the room's data
// channel: direct between the two players, or through the host.
//
// The inviter is the session host and drives the clock; the invitee is gated
// (shim_link_gate) so it only ever answers until it is connected on the
// external clock. Both players then walk to any Pokémon Center 2F and talk to
// the Cable Club receptionist, as in the original game.
//
// Safety: bytes are accepted only for the live session id and only from the
// session peer; a 10 s silence ends the session, unplugs the cable and, if the
// game was mid-link, resets it to the last save (the receptionist saves before
// every link, and a trade only saves once both sides have finished).

import { LINK } from "./emu.js";
import { encodeLink, LINK_MAX_RECORDS } from "./protocol.js";

const TIMEOUT_MS = 10000;
const HEARTBEAT_MS = 1000;
const INVITE_MS = 30000;
const USING_EXTERNAL_CLOCK = 1;

export class LinkHost {
  constructor({ emu, net, manifest, ui, now = () => performance.now(), timers = true }) {
    this.now = now;
    this.emu = emu;
    this.net = net;
    this.ram = manifest.ram;
    this.ui = ui; // { state(text), incoming(invite) -> Promise<bool>, ended(reason, reset) }
    this.session = null;
    this.pending = null; // our outgoing invite
    net.on("linkCtl", (m) => this.onCtl(m));
    net.on("link", (from, pkt) => this.onLink(from, pkt));
    net.on("peerLeave", (id) => {
      if (this.session && this.session.peer === id) this.end("Your friend left the room.", false);
      if (this.pending && this.pending.to === id) this.pending = null;
    });
    net.on("closed", () => this.session && this.end("You left the room.", false));
    emu.on("frame", () => this.pump());
    emu.on("stall", () => this.pump());
    if (timers) this.timer = setInterval(() => this.pump(), 250); // heartbeats and timeouts while paused
  }

  dispose() {
    if (this.session) this.end("Left the room.", true);
    clearInterval(this.timer);
    this.disposed = true;
  }

  get active() {
    return !!this.session;
  }

  invite(peerId, mode) {
    if (this.session || this.pending) return false;
    const sid = 1 + Math.floor(Math.random() * 0x7ffffffe);
    this.pending = { to: peerId, sid, mode, at: this.now() };
    this.net.sendLinkCtl({ t: "linkInvite", to: peerId, sid, mode });
    this.ui.state(`Waiting for an answer…`);
    return true;
  }

  async onCtl(m) {
    if (m.t === "linkInvite") {
      if (this.session || this.pending) {
        this.net.sendLinkCtl({ t: "linkAnswer", to: m.from, sid: m.sid, ok: false });
        return;
      }
      const ok = await this.ui.incoming(m);
      if (ok && !this.session && !this.pending) {
        this.net.sendLinkCtl({ t: "linkAnswer", to: m.from, sid: m.sid, ok: true });
        this.start(m.from, m.sid, m.mode, "guest");
      } else {
        this.net.sendLinkCtl({ t: "linkAnswer", to: m.from, sid: m.sid, ok: false });
      }
    } else if (m.t === "linkAnswer") {
      const p = this.pending;
      if (!p || p.to !== m.from || p.sid !== m.sid) return;
      this.pending = null;
      if (m.ok) this.start(m.from, m.sid, p.mode, "host");
      else this.ui.state("Your friend said no.");
    } else if (m.t === "linkEnd") {
      if (this.session && this.session.peer === m.from && this.session.sid === m.sid)
        this.end(`Your friend ended the link (${m.reason}).`, false);
    }
  }

  start(peer, sid, mode, role) {
    const now = this.now();
    this.session = { peer, sid, mode, role, lastRx: now, lastTx: now };
    // the guest only drives the clock once it is connected as external
    if (role === "guest") this.emu.linkGate(this.ram.hSerialConnectionStatus, USING_EXTERNAL_CLOCK);
    else this.emu.linkGate(0, 0);
    this.emu.linkPlug(true);
    this.ui.started?.(this.session);
    this.ui.state(
      `Linked for a ${mode}. Both of you: go to a Pokémon Center 2F and talk to the Cable Club receptionist.`
    );
  }

  onLink(from, pkt) {
    const s = this.session;
    if (!s || from !== s.peer || pkt.sid !== s.sid) return; // not our session: ignore
    s.lastRx = this.now();
    for (const v of pkt.records) {
      if (!this.emu.linkPush(v >> 8, v & 0xff)) return this.end("Link overflow.", true);
    }
    if (pkt.records.length) this.emu.kick();
  }

  pump() {
    if (this.disposed) return;
    const now = this.now();
    if (this.pending && now - this.pending.at > INVITE_MS) {
      this.pending = null;
      this.ui.state("No answer.");
    }
    const s = this.session;
    if (!s) return;
    const out = this.emu.linkPop();
    for (let i = 0; i < out.length; i += LINK_MAX_RECORDS) {
      this.net.sendLink(s.peer, encodeLink(s.sid, out.slice(i, i + LINK_MAX_RECORDS)));
      s.lastTx = now;
    }
    if (now - s.lastTx > HEARTBEAT_MS) {
      this.net.sendLink(s.peer, encodeLink(s.sid, []));
      s.lastTx = now;
    }
    if (now - s.lastRx > TIMEOUT_MS) this.end("The link timed out.", true);
  }

  // Is the game in the middle of something that needs the cable?
  midLink() {
    const st = this.emu.read(this.ram.hSerialConnectionStatus);
    return this.emu.linkStalled() || this.emu.read(this.ram.wLinkState) !== 0 || st === 1 || st === 2;
  }

  end(reason, notify = true) {
    const s = this.session;
    if (!s) return;
    this.session = null;
    if (notify) this.net.sendLinkCtl({ t: "linkEnd", to: s.peer, sid: s.sid, reason: reason.slice(0, 80) });
    const reset = this.midLink();
    this.emu.linkPlug(false);
    this.emu.linkGate(0, 0);
    this.emu.linkPop(); // discard anything queued
    if (reset) this.emu.reset();
    this.ui.ended(reason, reset);
  }
}

export { LINK };
