// Checks web/bps.js against tools/make_bps.py's output.
// Needs baserom_red.gbc, pokered.gbc, pokered.bps and web/build/manifest.json
// (make web). Run: node test/web/bps_test.mjs
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import assert from "node:assert/strict";
import { applyBps, patchRom, sha1Hex, crc32, BpsError } from "../../web/bps.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const read = (f) => new Uint8Array(readFileSync(path.join(root, f)));
const manifest = JSON.parse(readFileSync(path.join(root, "web/build/manifest.json"), "utf8"));

assert.equal(crc32(new TextEncoder().encode("123456789")), 0xcbf43926);

const rom = read("pokered.gbc");
const patch = read("pokered.bps");
assert.equal(await sha1Hex(rom), manifest.romSha1, "manifest is stale; run make web");

if (existsSync(path.join(root, "baserom_red.gbc"))) {
  const base = read("baserom_red.gbc");
  const out = applyBps(base, patch);
  assert.deepEqual(out, rom, "patched bytes differ from pokered.gbc");
  const r = await patchRom(base, patch, manifest);
  assert.equal(r.already, false);
  assert.equal(await sha1Hex(r.rom), manifest.romSha1);

  // A different game (one byte off) is refused with a readable message.
  const wrong = base.slice();
  wrong[0x1000] ^= 1;
  await assert.rejects(patchRom(wrong, patch, manifest), /not an unmodified Pokémon Red/);
  assert.throws(() => applyBps(wrong, patch), /wrong base ROM/);

  // A corrupted patch is refused.
  const bad = patch.slice();
  bad[100] ^= 0xff;
  assert.throws(() => applyBps(base, bad), BpsError);
  // Truncated patch.
  assert.throws(() => applyBps(base, patch.subarray(0, 50)), BpsError);
  console.log("bps: base ROM patched to the build; wrong/corrupt inputs refused");
} else {
  console.log("bps: baserom_red.gbc not present; skipping the full apply");
}

// Already-patched ROM is accepted as is.
const r2 = await patchRom(rom, patch, manifest);
assert.equal(r2.already, true);

// Garbage never throws anything but BpsError.
for (let i = 0; i < 200; i++) {
  const junk = new Uint8Array(20 + ((i * 37) % 300));
  for (let j = 0; j < junk.length; j++) junk[j] = (i * 131 + j * 17) & 0xff;
  junk.set([66, 80, 83, 49]);
  assert.throws(() => applyBps(new Uint8Array(64), junk), BpsError);
}
console.log("bps_test: ok");
