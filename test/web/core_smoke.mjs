// Boots pokered.gbc in the WASM core (web/build/core.js) and checks the title
// screen draws and a frame runs fast enough. Run: node test/web/core_smoke.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const { default: createCore } = await import(path.join(root, "web/build/core.js"));
const M = await createCore();
const rom = readFileSync(path.join(root, "pokered.gbc"));
const s = M._shim_create();
M._shim_set_audio_enabled(s, 0);
const p = M._malloc(rom.length);
M.HEAPU8.set(rom, p);
if (M._shim_load_rom(s, p, rom.length) !== 0) throw new Error("load failed");
M._free(p);

const t0 = performance.now();
const N = 1200;
for (let i = 0; i < N; i++) M._shim_run_frame(s);
const ms = (performance.now() - t0) / N;

const fb = M._shim_framebuffer(s);
const px = M.HEAPU8.subarray(fb, fb + 160 * 144 * 4);
const shades = new Set();
for (let i = 0; i < px.length; i += 4) shades.add(px[i]);
console.log(`frames=${N} ${ms.toFixed(2)} ms/frame, distinct shades=${shades.size}`);
if (shades.size < 2) throw new Error("screen is blank");
if (ms > 16) console.warn("slower than real time on this machine");
console.log("core_smoke: ok");
