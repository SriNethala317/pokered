// Friends drawn over the game screen. The ROM is never touched: this reads a
// few RAM addresses (from web/build/manifest.json), works out where each
// friend would be on this player's screen, and draws the player sprite from
// this player's own cartridge onto an overlay canvas, with name tags in HTML.

import { FLAG } from "./protocol.js";

const S8 = (v) => (v << 24) >> 24;
const OBP0 = 0xff48;
const FRAMES_PER_SEND = 4; // at most 15 packets a second
const KEEPALIVE = 60;
const STALE_MS = 10000;

// ---- pure helpers (tested in test/web/presence_test.mjs) ----

// This player's state from RAM. read(addr) -> byte.
export function readSelf(read, ram) {
  const wc = read(ram.wWalkCounter);
  const vy = S8(read(ram.wSpritePlayerStateData1YStepVector));
  const vx = S8(read(ram.wSpritePlayerStateData1XStepVector));
  // coordinates change when a step ends; in between, the step so far is
  // (8 - counter) * 2 pixels along the step vector
  const prog = wc > 0 ? (8 - wc) * 2 : 0;
  const img = read(ram.wSpritePlayerStateData1ImageIndex);
  let flags = 0;
  if (read(ram.wIsInBattle)) flags |= FLAG.BATTLE;
  if (read(ram.wSpritePlayerStateData2GrassPriority) & 0x80) flags |= FLAG.GRASS;
  if (img === 0xff) flags |= FLAG.HIDDEN;
  return {
    map: read(ram.wCurMap),
    x: read(ram.wXCoord) * 16 + prog * vx,
    y: read(ram.wYCoord) * 16 + prog * vy,
    sprite: img === 0xff ? 0 : img & 0x0f,
    flags,
    // where this player's own sprite is drawn on screen
    anchorX: read(ram.wSpritePlayerStateData1XPixels),
    anchorY: read(ram.wSpritePlayerStateData1YPixels),
  };
}

// Can friends be drawn right now? Not in battle, menus, text boxes or with
// the LCD off: the overlay would sit on top of them.
export function overlayVisible(read, ram) {
  if (read(ram.wIsInBattle)) return false;
  if (read(ram.hWY) < 144) return false;
  if (read(ram.wFontLoaded) & 1) return false;
  if (!(read(0xff40) & 0x80)) return false;
  return true;
}

// Top-left screen pixel of a friend at map pixel (fx, fy).
export function friendScreenPos(self, fx, fy) {
  return { x: self.anchorX + (fx - self.x), y: self.anchorY + (fy - self.y) };
}

// Sprite frame for an image index: which 16x16 frame of the sheet, and flip.
// Sheet order: stand down, stand up, stand left, walk down, walk up, walk left.
export function spriteFrame(img) {
  const facing = (img >> 2) & 3; // 0 down, 1 up, 2 left, 3 right
  const anim = img & 3; // 1 and 3 are the walking frames
  const walking = anim === 1 || anim === 3;
  let frame, flip = false;
  if (facing === 0 || facing === 1) {
    frame = (walking ? 3 : 0) + facing;
    flip = anim === 3;
  } else {
    frame = walking ? 5 : 2;
    flip = facing === 3;
  }
  return { frame, flip };
}

// Decode a 16x16 frame (4 tiles, TL TR BL BR) of 2bpp data to colour indices.
export function decodeFrame(sheet, frame) {
  const out = new Uint8Array(256);
  for (let t = 0; t < 4; t++) {
    const base = (frame * 4 + t) * 16;
    const ox = (t & 1) * 8, oy = (t >> 1) * 8;
    for (let row = 0; row < 8; row++) {
      const lo = sheet[base + row * 2], hi = sheet[base + row * 2 + 1];
      for (let bit = 0; bit < 8; bit++) {
        const c = ((lo >> (7 - bit)) & 1) | (((hi >> (7 - bit)) & 1) << 1);
        out[(oy + row) * 16 + ox + bit] = c;
      }
    }
  }
  return out;
}

// shade 0..3 (white..black) -> grey level, matching the core's grey palette
export const SHADE = [0xff, 0xaa, 0x55, 0x00];

// ---- the overlay ----

export class Presence {
  // rom: patched ROM bytes; manifest: web/build/manifest.json
  constructor({ emu, rom, manifest, canvas, tags, nameOf }) {
    this.emu = emu;
    this.ram = manifest.ram;
    const at = manifest.rom.RedSprite;
    const off = at.bank * 0x4000 + (at.addr - 0x4000);
    this.sheet = rom.slice(off, off + 24 * 16);
    this.frames = [0, 1, 2, 3, 4, 5].map((f) => decodeFrame(this.sheet, f));
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.img = this.ctx.createImageData(16, 16);
    this.tags = tags;
    this.nameOf = nameOf;
    this.friends = new Map(); // slot -> { target, shown, map, sprite, flags, seen, tag, bubble }
    this.seq = 0;
    this.sinceSend = 0;
    this.last = null;
  }

  read = (a) => this.emu.read(a);

  // Called once per emulated frame. Returns a presence packet to send, or null.
  tick() {
    const me = readSelf(this.read, this.ram);
    // The picture on screen was set up from RAM as it stood one frame ago
    // (the vblank handler latches scroll and OAM), so draw from that.
    this.drawn = this.self || me;
    this.drawnVisible = this.visibleNow ?? false;
    this.self = me;
    this.visibleNow = overlayVisible(this.read, this.ram);
    this.sinceSend++;
    const changed =
      !this.last || me.map !== this.last.map || me.x !== this.last.x || me.y !== this.last.y ||
      me.sprite !== this.last.sprite || me.flags !== this.last.flags;
    if ((changed && this.sinceSend >= FRAMES_PER_SEND) || this.sinceSend >= KEEPALIVE) {
      this.sinceSend = 0;
      this.last = me;
      return { map: me.map, x: me.x, y: me.y, sprite: me.sprite, flags: me.flags, seq: this.seq++ & 0xff };
    }
    return null;
  }

  update(pos) {
    let f = this.friends.get(pos.slot);
    if (!f) {
      f = { shown: null, seq: -1 };
      f.tag = document.createElement("div");
      f.tag.className = "tag";
      this.tags.append(f.tag);
      this.friends.set(pos.slot, f);
    }
    // drop reordered packets (8-bit sequence, wraps)
    if (f.seq >= 0 && ((pos.seq - f.seq) & 0xff) > 128) return;
    f.seq = pos.seq;
    if (f.map !== pos.map) f.shown = null; // snap on map change
    f.map = pos.map;
    f.target = { x: pos.x, y: pos.y };
    f.sprite = pos.sprite;
    f.flags = pos.flags;
    f.seen = performance.now();
  }

  remove(slot) {
    const f = this.friends.get(slot);
    if (!f) return;
    f.tag.remove();
    f.bubble?.remove();
    this.friends.delete(slot);
  }

  say(slot, text) {
    const f = this.friends.get(slot);
    if (!f) return;
    f.bubble?.remove();
    const b = document.createElement("div");
    b.className = "bubble";
    b.textContent = text; // never innerHTML
    this.tags.append(b);
    f.bubble = b;
    clearTimeout(f.bubbleTimer);
    f.bubbleTimer = setTimeout(() => {
      b.remove();
      if (f.bubble === b) f.bubble = null;
    }, 5000);
  }

  render() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, 160, 144);
    const me = this.drawn;
    const visible = me && this.drawnVisible && this.visibleNow;
    const now = performance.now();
    const obp = this.read(OBP0);
    for (const [slot, f] of this.friends) {
      if (now - f.seen > STALE_MS) {
        this.remove(slot);
        continue;
      }
      // glide toward the latest position; snap if far behind
      if (!f.shown || Math.abs(f.target.x - f.shown.x) + Math.abs(f.target.y - f.shown.y) > 48) {
        f.shown = { ...f.target };
      } else {
        const sp = Math.abs(f.target.x - f.shown.x) + Math.abs(f.target.y - f.shown.y) > 16 ? 4 : 2;
        f.shown.x += Math.sign(f.target.x - f.shown.x) * Math.min(sp, Math.abs(f.target.x - f.shown.x));
        f.shown.y += Math.sign(f.target.y - f.shown.y) * Math.min(sp, Math.abs(f.target.y - f.shown.y));
      }
      const on = visible && f.map === me.map && !(f.flags & FLAG.HIDDEN);
      const p = on ? friendScreenPos(me, f.shown.x, f.shown.y) : null;
      const inView = p && p.x > -16 && p.x < 160 && p.y > -16 && p.y < 144;
      if (inView) this.drawSprite(p.x, p.y, f.sprite, f.flags & FLAG.GRASS, obp);
      this.placeTag(f, inView ? p : null, slot);
    }
  }

  drawSprite(x, y, sprite, grass, obp) {
    const { frame, flip } = spriteFrame(sprite);
    const px = this.frames[frame];
    const d = this.img.data;
    d.fill(0);
    const rows = grass ? 12 : 16; // in grass the lower legs are hidden
    for (let yy = 0; yy < rows; yy++) {
      for (let xx = 0; xx < 16; xx++) {
        const c = px[yy * 16 + (flip ? 15 - xx : xx)];
        if (!c) continue; // colour 0 is transparent
        const g = SHADE[(obp >> (c * 2)) & 3];
        const i = (yy * 16 + xx) * 4;
        d[i] = d[i + 1] = d[i + 2] = g;
        d[i + 3] = 255;
      }
    }
    // putImageData ignores alpha compositing, so stage through a bitmap
    if (!this.stage) {
      this.stage = new OffscreenCanvasOr(16, 16);
      this.sctx = this.stage.getContext("2d");
    }
    this.sctx.putImageData(this.img, 0, 0);
    this.ctx.drawImage(this.stage, x, y);
  }

  placeTag(f, p, slot) {
    const name = this.nameOf(slot) || "?";
    if (f.tag.textContent !== name) f.tag.textContent = name;
    if (!p) {
      f.tag.hidden = true;
      if (f.bubble) f.bubble.hidden = true;
      return;
    }
    const left = ((p.x + 8) / 160) * 100, top = (p.y / 144) * 100;
    f.tag.hidden = false;
    f.tag.style.left = `${left}%`;
    f.tag.style.top = `${top}%`;
    if (f.bubble) {
      f.bubble.hidden = false;
      f.bubble.style.left = `${left}%`;
      f.bubble.style.top = `${top}%`;
    }
  }

  clear() {
    for (const slot of [...this.friends.keys()]) this.remove(slot);
  }
}

function OffscreenCanvasOr(w, h) {
  if (typeof OffscreenCanvas !== "undefined") return new OffscreenCanvas(w, h);
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
}
