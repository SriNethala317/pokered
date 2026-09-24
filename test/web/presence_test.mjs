// Checks presence.js against the running game (WASM core, pokered.gbc):
//  - the player's own sprite, redrawn by the overlay code at the position the
//    overlay would give a friend standing exactly where the player is, matches
//    the real screen pixel for pixel, every frame of several walks (this
//    checks the camera maths, the walk offsets, the frame/flip table and the
//    2bpp decoding in one go);
//  - the overlay hides in the start menu and shows again after.
// Run: node test/web/presence_test.mjs   (needs make web)
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import assert from "node:assert/strict";
import { readSelf, overlayVisible, friendScreenPos, spriteFrame, decodeFrame, SHADE } from "../../web/presence.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const manifest = JSON.parse(readFileSync(path.join(root, "web/build/manifest.json"), "utf8"));
const { default: createCore } = await import(path.join(root, "web/build/core.js"));
const M = await createCore();
const rom = new Uint8Array(readFileSync(path.join(root, "pokered.gbc")));
const s = M._shim_create();
M._shim_set_audio_enabled(s, 0);
const p = M._malloc(rom.length);
M.HEAPU8.set(rom, p);
M._shim_load_rom(s, p, rom.length);

const ram = manifest.ram;
const read = (a) => M._shim_read(s, a);
const KEY = { a: 1, b: 2, select: 4, start: 8, right: 16, left: 32, up: 64, down: 128 };
// The picture a frame shows was set up from RAM as it stood at the end of
// the previous frame (the vblank handler latches scroll and OAM), so the
// overlay draws from the previous frame's snapshot. `prev` is that snapshot.
let prev = null;
const frame = (n = 1, each) => {
  for (let i = 0; i < n; i++) {
    const snap = { self: readSelf(read, ram), visible: overlayVisible(read, ram) };
    M._shim_run_frame(s);
    prev = snap;
    each?.();
  }
};
const press = (k, hold = 3, rel = 24, each) => {
  M._shim_set_keys(s, KEY[k]);
  frame(hold, each);
  M._shim_set_keys(s, 0);
  frame(rel, each);
};

// boot through the intro to the overworld
const ow = manifest.rom.OverworldLoop;
const hook = M._shim_hook_add(s, ow.addr, -1, 0);
let inOverworld = false;
for (let i = 1; i < 4000 && !inOverworld; i++) {
  press(i % 10 === 0 ? "start" : "a", 3, 6);
  for (let h; (h = M._shim_hook_next(s)) >= 0; ) if (h === hook) inOverworld = overlayVisible(read, ram);
}
assert.ok(inOverworld, "never reached the overworld");
frame(60);
M._shim_hook_clear(s);

const off = manifest.rom.RedSprite.bank * 0x4000 + (manifest.rom.RedSprite.addr - 0x4000);
const sheet = rom.slice(off, off + 24 * 16);
const frames = [0, 1, 2, 3, 4, 5].map((f) => decodeFrame(sheet, f));

// On a mismatch, say which frame/flip/offset would have matched.
function explain(me, pos, obp, fb) {
  console.log("overlay state", JSON.stringify(me), "RAM now", JSON.stringify(readSelf(read, ram)));
  for (let f = 0; f < 6; f++)
    for (const fl of [0, 1])
      for (let dy = -4; dy <= 4; dy++)
        for (let dx = -4; dx <= 4; dx++) {
          let ok = true;
          for (let y = 0; y < 16 && ok; y++)
            for (let x = 0; x < 16; x++) {
              const c = frames[f][y * 16 + (fl ? 15 - x : x)];
              if (!c) continue;
              const i = fb + ((pos.y + dy + y) * 160 + pos.x + dx + x) * 4;
              if (M.HEAPU8[i] !== SHADE[(obp >> (c * 2)) & 3]) {
                ok = false;
                break;
              }
            }
          if (ok) console.log(`screen matches frame ${f} flip ${fl} at offset (${dx},${dy})`);
        }
}

let checked = 0;
// Position must match on every frame. The walk animation image can trail the
// RAM by a frame (the overworld loop runs every other frame), so while moving
// any frame of the sheet may match; standing still, the exact one must.
function matchesAnyFrame(pos, obp, fb) {
  for (let f = 0; f < 6; f++)
    for (const fl of [false, true]) {
      let ok = true;
      for (let y = 0; y < 16 && ok; y++)
        for (let x = 0; x < 16; x++) {
          const c = frames[f][y * 16 + (fl ? 15 - x : x)];
          if (c && M.HEAPU8[fb + ((pos.y + y) * 160 + pos.x + x) * 4] !== SHADE[(obp >> (c * 2)) & 3]) {
            ok = false;
            break;
          }
        }
      if (ok) return true;
    }
  return false;
}

function checkSelfOverlay(label, exactImage) {
  if (!prev.visible || !overlayVisible(read, ram)) return;
  const me = prev.self;
  const pos = friendScreenPos(me, me.x, me.y);
  if (!exactImage) {
    const fb = M._shim_framebuffer(s);
    if (!matchesAnyFrame(pos, read(0xff48), fb)) {
      explain(me, pos, read(0xff48), fb);
      assert.fail(`${label}: no sprite frame at the overlay position`);
    }
    checked++;
    return;
  }
  const { frame: fr, flip } = spriteFrame(me.sprite);
  const obp = read(0xff48);
  const fb = M._shim_framebuffer(s);
  let opaque = 0;
  for (let y = 0; y < 16; y++)
    for (let x = 0; x < 16; x++) {
      const c = frames[fr][y * 16 + (flip ? 15 - x : x)];
      if (!c) continue;
      const sx = pos.x + x, sy = pos.y + y;
      const got = M.HEAPU8[fb + (sy * 160 + sx) * 4];
      if (got !== SHADE[(obp >> (c * 2)) & 3]) explain(me, pos, obp, fb);
      assert.equal(got, SHADE[(obp >> (c * 2)) & 3], `${label}: pixel (${x},${y}) sprite ${me.sprite} at ${JSON.stringify(me)}`);
      opaque++;
    }
  assert.ok(opaque > 40);
  checked++;
}

// Red's bedroom: walk left, down, right, up with a check on every frame.
checkSelfOverlay("standing", true);
const each = () => checkSelfOverlay("walking", false);
const faced = new Set();
let scx0 = null, moved = 0;
for (const dir of ["left", "left", "down", "right", "right", "up"]) {
  const before = readSelf(read, ram);
  press(dir, 3, 24, () => {
    each();
    const me = readSelf(read, ram);
    const scx = read(ram.hSCX), scy = read(ram.hSCY);
    // the camera moves with the player pixel for pixel
    if (scx0 === null) scx0 = [(me.x - scx) & 0xff, (me.y - scy) & 0xff];
    assert.deepEqual([(me.x - scx) & 0xff, (me.y - scy) & 0xff], scx0, "camera and player pixel drifted");
  });
  const after = readSelf(read, ram);
  if (after.x !== before.x || after.y !== before.y) moved++;
  frame(4);
  checkSelfOverlay(`standing after ${dir}`, true);
  faced.add(spriteFrame(readSelf(read, ram).sprite).frame + (spriteFrame(readSelf(read, ram).sprite).flip ? 10 : 0));
}
assert.ok(moved >= 4, `only ${moved} steps taken`);
assert.ok(faced.size >= 4, `standing frames checked: ${[...faced]}`);

// menu hides the overlay; closing it shows it again
press("start", 3, 30);
assert.equal(overlayVisible(read, ram), false, "overlay should hide in the start menu");
press("b", 3, 30);
assert.equal(overlayVisible(read, ram), true);
console.log(`presence_test: ok (${checked} frames compared, ${moved} steps)`);
