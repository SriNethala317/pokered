// An in-memory stand-in for Trystero's joinRoom, for testing net.js in node.
// Peers in the same room and password connect pairwise (unless the pair is
// blocked, to model two phones behind CGNAT), run the handshake, then get
// onPeerJoin. Messages are delivered asynchronously and structured-cloned.

export class FakeNet {
  constructor() {
    this.rooms = new Map(); // key -> Set(member)
    this.blocked = new Set();
    this.log = [];
  }
  block(a, b) {
    this.blocked.add(`${a}|${b}`);
    this.blocked.add(`${b}|${a}`);
  }
  joinRoomFor(selfId) {
    return (config, roomId, callbacks = {}) => this.join(selfId, config, roomId, callbacks);
  }
  join(selfId, config, roomId, callbacks) {
    const key = `${config.appId}/${roomId}/${config.password || ""}`;
    if (!this.rooms.has(key)) this.rooms.set(key, new Set());
    const members = this.rooms.get(key);
    const net = this;
    const m = {
      selfId,
      actions: {},
      connected: new Set(),
      left: false,
      room: null,
    };
    const room = {
      onPeerJoin: null,
      onPeerLeave: null,
      makeAction(ns) {
        const a = {
          onMessage: null,
          async send(data, opts) {
            let targets = opts?.target ?? [...m.connected];
            if (!Array.isArray(targets)) targets = [targets];
            for (const t of targets) {
              if (!m.connected.has(t)) continue;
              const peer = [...members].find((x) => x.selfId === t);
              const copy = data instanceof Uint8Array ? new Uint8Array(data) : structuredClone(data);
              net.log.push([ns, selfId, t]);
              setTimeout(() => {
                if (peer && !peer.left && peer.connected.has(selfId)) peer.actions[ns]?.onMessage?.(copy, { peerId: selfId });
              }, 0);
            }
          },
        };
        m.actions[ns] = a;
        return a;
      },
      getPeers() {
        const out = {};
        for (const id of m.connected) out[id] = { connectionState: "connected" };
        return out;
      },
      async leave() {
        m.left = true;
        members.delete(m);
        for (const id of m.connected) {
          const peer = [...members].find((x) => x.selfId === id);
          if (peer) {
            peer.connected.delete(selfId);
            setTimeout(() => peer.room.onPeerLeave?.(selfId), 0);
          }
        }
        m.connected.clear();
      },
    };
    m.room = room;
    m.callbacks = callbacks;
    const others = [...members];
    members.add(m);
    for (const o of others) {
      if (this.blocked.has(`${selfId}|${o.selfId}`)) continue;
      this.connect(m, o);
    }
    return room;
  }
  async connect(a, b) {
    const box = { [a.selfId]: [], [b.selfId]: [] };
    const waiters = { [a.selfId]: [], [b.selfId]: [] };
    const mk = (me, other) => ({
      send: async (data) => {
        const q = waiters[other];
        if (q.length) q.shift()({ data: structuredClone(data) });
        else box[other].push({ data: structuredClone(data) });
      },
      receive: () => new Promise((res) => (box[me].length ? res(box[me].shift()) : waiters[me].push(res))),
    });
    const ha = mk(a.selfId, b.selfId), hb = mk(b.selfId, a.selfId);
    try {
      await Promise.all([
        a.callbacks.onPeerHandshake?.(b.selfId, ha.send, ha.receive, true),
        b.callbacks.onPeerHandshake?.(a.selfId, hb.send, hb.receive, false),
      ]);
    } catch {
      return; // refused: never connected
    }
    if (a.left || b.left) return;
    a.connected.add(b.selfId);
    b.connected.add(a.selfId);
    a.room.onPeerJoin?.(b.selfId);
    b.room.onPeerJoin?.(a.selfId);
  }
}

export const settle = (ms = 5) => new Promise((r) => setTimeout(r, ms));
