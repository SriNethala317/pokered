// BPS patch apply, ported from tools/make_bps.py (apply). Works in browsers
// and in node (both have crypto.subtle). No ROM ever leaves the player's
// device: the page patches the player's own retail cartridge dump.

const SOURCE_READ = 0, TARGET_READ = 1, SOURCE_COPY = 2, TARGET_COPY = 3;

let CRC_TABLE = null;
function crcTable() {
  if (CRC_TABLE) return CRC_TABLE;
  CRC_TABLE = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    CRC_TABLE[n] = c >>> 0;
  }
  return CRC_TABLE;
}

export function crc32(bytes, start = 0, end = bytes.length) {
  const t = crcTable();
  let c = 0xffffffff;
  for (let i = start; i < end; i++) c = t[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

export async function sha1Hex(bytes) {
  const d = new Uint8Array(await crypto.subtle.digest("SHA-1", bytes));
  return Array.from(d, (b) => b.toString(16).padStart(2, "0")).join("");
}

function u32le(b, at) {
  return (b[at] | (b[at + 1] << 8) | (b[at + 2] << 16) | (b[at + 3] << 24)) >>> 0;
}

export class BpsError extends Error {}

// Returns [n, pos]. Guarded against running off the end or overflowing.
function readNumber(data, pos, end) {
  let n = 0, shift = 1;
  for (;;) {
    if (pos >= end) throw new BpsError("truncated number");
    const x = data[pos++];
    n += (x & 0x7f) * shift;
    if (x & 0x80) return [n, pos];
    shift *= 128;
    n += shift;
    if (n > 0x7fffffff) throw new BpsError("number too large");
  }
}

// Size limit for the output: Game Boy carts top out at 8 MiB.
const MAX_TARGET = 8 * 1024 * 1024;

export function applyBps(source, patch) {
  if (!(source instanceof Uint8Array) || !(patch instanceof Uint8Array)) throw new TypeError("Uint8Array expected");
  if (patch.length < 4 + 3 + 12 || String.fromCharCode(...patch.subarray(0, 4)) !== "BPS1")
    throw new BpsError("not a BPS patch");
  if (crc32(patch, 0, patch.length - 4) !== u32le(patch, patch.length - 4))
    throw new BpsError("patch checksum mismatch");
  const end = patch.length - 12;
  let pos = 4, sourceSize, targetSize, metaSize;
  [sourceSize, pos] = readNumber(patch, pos, end);
  [targetSize, pos] = readNumber(patch, pos, end);
  [metaSize, pos] = readNumber(patch, pos, end);
  pos += metaSize;
  if (sourceSize !== source.length)
    throw new BpsError(`this ROM is ${source.length} bytes; the patch wants ${sourceSize}`);
  if (crc32(source) !== u32le(patch, patch.length - 12))
    throw new BpsError("wrong base ROM (checksum mismatch)");
  if (targetSize > MAX_TARGET) throw new BpsError("target too large");

  const target = new Uint8Array(targetSize);
  let out = 0, sourceRel = 0, targetRel = 0;
  const need = (n) => {
    if (out + n > targetSize) throw new BpsError("patch writes past the end");
  };
  while (pos < end) {
    let data;
    [data, pos] = readNumber(patch, pos, end);
    const command = data & 3, length = Math.floor(data / 4) + 1;
    need(length);
    if (command === SOURCE_READ) {
      if (out + length > source.length) throw new BpsError("source read out of range");
      target.set(source.subarray(out, out + length), out);
      out += length;
    } else if (command === TARGET_READ) {
      if (pos + length > end) throw new BpsError("truncated literal");
      target.set(patch.subarray(pos, pos + length), out);
      pos += length;
      out += length;
    } else {
      [data, pos] = readNumber(patch, pos, end);
      const delta = data & 1 ? -Math.floor(data / 2) : Math.floor(data / 2);
      if (command === SOURCE_COPY) {
        sourceRel += delta;
        if (sourceRel < 0 || sourceRel + length > source.length) throw new BpsError("source copy out of range");
        target.set(source.subarray(sourceRel, sourceRel + length), out);
        sourceRel += length;
        out += length;
      } else {
        targetRel += delta;
        if (targetRel < 0 || targetRel >= out) throw new BpsError("target copy out of range");
        for (let i = 0; i < length; i++) target[out++] = target[targetRel++]; // may overlap
      }
    }
  }
  if (out !== targetSize) throw new BpsError(`patch made ${out} bytes, expected ${targetSize}`);
  if (crc32(target) !== u32le(patch, patch.length - 8)) throw new BpsError("result checksum mismatch");
  return target;
}

// Patch the player's ROM and insist the result is exactly our build.
// manifest: { baseSha1, romSha1 } from web/build/manifest.json.
export async function patchRom(romBytes, patchBytes, manifest) {
  const base = await sha1Hex(romBytes);
  if (base === manifest.romSha1) return { rom: romBytes, already: true };
  if (base !== manifest.baseSha1)
    throw new BpsError(
      "This is not an unmodified Pokémon Red (UE) ROM. " +
        `Its sha1 is ${base}; the patch needs ${manifest.baseSha1}.`
    );
  const out = applyBps(romBytes, patchBytes);
  const got = await sha1Hex(out);
  if (got !== manifest.romSha1) throw new BpsError(`patched ROM sha1 ${got} is not this build's ${manifest.romSha1}`);
  return { rom: out, already: false };
}
