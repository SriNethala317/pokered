// Emulator wrapper over web/build/core.js (link_shim compiled to WASM).
// Runs the game at 59.73 fps from requestAnimationFrame with a fixed-step
// accumulator, draws to a canvas, and streams audio through Web Audio.

export const KEY = { a: 1, b: 2, select: 4, start: 8, right: 16, left: 32, up: 64, down: 128 };
export const RUN = { FRAME: 0, STALLED: 1, HOOK: 2 };
export const LINK = { XFER: 1, REPLY: 2 };

const FRAME_MS = 1000 / 59.7275;
const SAMPLE_RATE = 48000;

export class Emulator {
  static async create(canvas) {
    const { default: createCore } = await import("./build/core.js");
    const M = await createCore();
    return new Emulator(M, canvas);
  }

  constructor(M, canvas) {
    this.M = M;
    this.s = M._shim_create();
    this.canvas = canvas;
    // canvas may be null (tests): then nothing is drawn
    this.ctx = canvas ? canvas.getContext("2d", { alpha: false }) : null;
    this.image = this.ctx ? this.ctx.createImageData(160, 144) : null;
    this.keys = 0;
    this.running = false;
    this.acc = 0;
    this.last = 0;
    this.listeners = { frame: [], stall: [], draw: [] };
    this.audio = null;
    this.audioBuf = M._malloc(4096 * 4);
    this.scratch = M._malloc(64);
    M._shim_set_sample_rate(this.s, SAMPLE_RATE);
  }

  on(ev, fn) {
    this.listeners[ev].push(fn);
  }

  loadRom(bytes) {
    const p = this.M._malloc(bytes.length);
    this.M.HEAPU8.set(bytes, p);
    const r = this.M._shim_load_rom(this.s, p, bytes.length);
    this.M._free(p);
    if (r !== 0) throw new Error("core rejected the ROM");
  }

  sramSize() {
    return this.M._shim_sram_size(this.s);
  }

  sramDirty() {
    return !!this.M._shim_sram_dirty(this.s);
  }

  saveSram() {
    const n = this.sramSize();
    const p = this.M._malloc(n);
    this.M._shim_sram_save(this.s, p, n);
    const out = this.M.HEAPU8.slice(p, p + n);
    this.M._free(p);
    return out;
  }

  loadSram(bytes) {
    const p = this.M._malloc(bytes.length);
    this.M.HEAPU8.set(bytes, p);
    this.M._shim_sram_load(this.s, p, bytes.length);
    this.M._free(p);
  }

  reset() {
    this.M._shim_reset(this.s);
  }

  read(addr) {
    return this.M._shim_read(this.s, addr);
  }

  readBlock(addr, n) {
    const out = new Uint8Array(n);
    for (let i = 0; i < n; i++) out[i] = this.M._shim_read(this.s, (addr + i) & 0xffff);
    return out;
  }

  setKeys(mask) {
    this.keys = mask & 0xff;
    this.M._shim_set_keys(this.s, this.keys);
  }

  // ---- link cable (used only by linkhost.js during an accepted session) ----
  linkPlug(on) {
    this.M._shim_link_plug(this.s, on ? 1 : 0);
  }
  linkGate(addr, value) {
    this.M._shim_link_gate(this.s, addr, value);
  }
  linkPop() {
    const out = [];
    for (;;) {
      const v = this.M._shim_link_pop_packed(this.s);
      if (v < 0) return out;
      out.push(v);
    }
  }
  linkPush(kind, byte) {
    return this.M._shim_link_push(this.s, kind, byte) === 0;
  }
  linkStalled() {
    return !!this.M._shim_link_stalled(this.s);
  }

  // ---- audio ----
  async enableAudio() {
    if (this.audio) return this.audio.ctx.resume();
    const AC = globalThis.AudioContext || globalThis.webkitAudioContext;
    if (!AC) return;
    const ctx = new AC({ sampleRate: SAMPLE_RATE, latencyHint: "interactive" });
    this.audio = { ctx, next: 0, muted: false };
    await ctx.resume();
  }

  setMuted(m) {
    if (this.audio) this.audio.muted = m;
    this.M._shim_set_audio_enabled(this.s, m ? 0 : 1);
  }

  pumpAudio() {
    const n = this.M._shim_audio_read(this.s, this.audioBuf, 4096);
    const a = this.audio;
    if (!a || a.muted || n === 0 || a.ctx.state !== "running") return;
    const pcm = new Int16Array(this.M.HEAPU8.buffer, this.audioBuf, n * 2);
    const buf = a.ctx.createBuffer(2, n, SAMPLE_RATE);
    const l = buf.getChannelData(0), r = buf.getChannelData(1);
    for (let i = 0; i < n; i++) {
      l[i] = pcm[i * 2] / 32768;
      r[i] = pcm[i * 2 + 1] / 32768;
    }
    const src = a.ctx.createBufferSource();
    src.buffer = buf;
    src.connect(a.ctx.destination);
    const now = a.ctx.currentTime;
    // keep ~60 ms queued; resync if we fell behind or ran far ahead
    if (a.next < now + 0.02 || a.next > now + 0.25) a.next = now + 0.06;
    src.start(a.next);
    a.next += n / SAMPLE_RATE;
  }

  // ---- frame loop ----
  draw() {
    if (!this.ctx) return;
    const fb = this.M._shim_framebuffer(this.s);
    this.image.data.set(this.M.HEAPU8.subarray(fb, fb + 160 * 144 * 4));
    this.ctx.putImageData(this.image, 0, 0);
    for (const f of this.listeners.draw) f();
  }

  step() {
    const r = this.M._shim_run_frame(this.s);
    if (r === RUN.FRAME) {
      for (const f of this.listeners.frame) f();
      return true;
    }
    for (const f of this.listeners.stall) f(r);
    return false;
  }

  start() {
    if (this.running) return;
    this.running = true;
    this.last = performance.now();
    this.acc = 0;
    const tick = (now) => {
      if (!this.running) return;
      this.acc += Math.min(now - this.last, 100);
      this.last = now;
      let ran = 0;
      while (this.acc >= FRAME_MS && ran < 4) {
        this.acc -= FRAME_MS;
        if (this.step()) ran++;
        else break; // stalled on the link: wait for the peer
      }
      if (this.acc > FRAME_MS * 4) this.acc = 0;
      if (ran) {
        this.draw();
        this.pumpAudio();
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  // Called by linkhost.js when the peer's reply lands: finish the stalled
  // frame now instead of waiting for the next animation frame, so a transfer
  // costs one round trip rather than one round trip plus up to 16 ms.
  kick() {
    if (!this.running || this.linkStalled()) return;
    let n = 0;
    while (n < 8 && this.acc > -FRAME_MS * 2) {
      this.acc -= FRAME_MS;
      n++;
      if (!this.step()) return;
      this.draw();
      this.pumpAudio();
    }
  }

  stop() {
    this.running = false;
  }
}
