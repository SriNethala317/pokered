#!/usr/bin/env python3
"""Make .bps patches of the built ROMs against the vanilla games.

A .bps patch is how a ROM hack is shared: players apply it to their own copy of
the retail game with any patcher (Floating IPS, Rom Patcher JS, or the one
built into most emulators), so no ROM is ever handed around.

The base for each patch is the unmodified game. A `baserom_red.gbc` or
`baserom_blue.gbc` next to the Makefile is used if present; otherwise the
vanilla disassembly is built from VANILLA_COMMIT in a temporary git worktree,
checked against its known sha1, and kept as that baserom for next time.

Every patch is checked before it is kept: it is decoded again, applied to the
base, and the result must match the built ROM byte for byte.

Usage:
    python3 tools/make_bps.py pokered
    python3 tools/make_bps.py --apply base.gbc patch.bps out.gbc
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import zlib

# The last upstream commit before any change of ours; master is kept on it.
VANILLA_COMMIT = "a1a22aaf"
VANILLA = {
    # rom name -> (baserom file, sha1 of the retail game)
    "pokered": ("baserom_red.gbc", "ea9bcae617fdf159b045185467ae58b2e4a48b9a"),
    "pokeblue": ("baserom_blue.gbc", "d7037c83e1ae5b39bde3c30787637ba1d4c48ce2"),
}

SOURCE_READ, TARGET_READ, SOURCE_COPY, TARGET_COPY = range(4)
KEY = 6            # bytes hashed to find a match in the source
MIN_COPY = 8       # shorter matches cost more than the literal bytes
MAX_CANDIDATES = 32


def sha1(data):
    return hashlib.sha1(data).hexdigest()


def number(n):
    """BPS variable-length number."""
    out = bytearray()
    while True:
        x = n & 0x7F
        n >>= 7
        if n == 0:
            out.append(0x80 | x)
            return bytes(out)
        out.append(x)
        n -= 1


def read_number(data, pos):
    n, shift = 0, 1
    while True:
        x = data[pos]
        pos += 1
        n += (x & 0x7F) * shift
        if x & 0x80:
            return n, pos
        shift <<= 7
        n += shift


def encode(source, target):
    """Greedy encoder: copy in place where the bytes still line up, copy from
    elsewhere in the source where code has moved, and store the rest."""
    index = {}
    for i in range(len(source) - KEY + 1):
        index.setdefault(source[i:i + KEY], []).append(i)

    out = bytearray(b"BPS1")
    out += number(len(source)) + number(len(target)) + number(0)
    literal = bytearray()
    source_offset = 0  # where the last SourceCopy left off

    def flush():
        if literal:
            out.extend(number(((len(literal) - 1) << 2) | TARGET_READ))
            out.extend(literal)
            literal.clear()

    pos = 0
    while pos < len(target):
        # the same bytes in the same place
        n = 0
        while pos + n < len(target) and pos + n < len(source) and source[pos + n] == target[pos + n]:
            n += 1
        if n >= 4 or (n and not literal):
            flush()
            out.extend(number(((n - 1) << 2) | SOURCE_READ))
            pos += n
            continue

        # the same bytes somewhere else
        best, best_at = 0, 0
        for at in index.get(target[pos:pos + KEY], ())[-MAX_CANDIDATES:]:
            m = 0
            while pos + m < len(target) and at + m < len(source) and source[at + m] == target[pos + m]:
                m += 1
            if m > best:
                best, best_at = m, at
        if best >= MIN_COPY:
            flush()
            out.extend(number(((best - 1) << 2) | SOURCE_COPY))
            delta = best_at - source_offset
            out.extend(number((abs(delta) << 1) | (delta < 0)))
            source_offset = best_at + best
            pos += best
            continue

        literal.append(target[pos])
        pos += 1
    flush()

    out += zlib.crc32(source).to_bytes(4, "little")
    out += zlib.crc32(target).to_bytes(4, "little")
    out += zlib.crc32(out).to_bytes(4, "little")
    return bytes(out)


def apply(source, patch):
    """A full decoder, written from the format rather than from encode(), so
    a mistake in one is not repeated in the other."""
    if patch[:4] != b"BPS1":
        raise ValueError("not a BPS patch")
    if zlib.crc32(patch[:-4]) != int.from_bytes(patch[-4:], "little"):
        raise ValueError("patch checksum mismatch")
    pos = 4
    source_size, pos = read_number(patch, pos)
    target_size, pos = read_number(patch, pos)
    metadata_size, pos = read_number(patch, pos)
    pos += metadata_size
    if source_size != len(source):
        raise ValueError(f"source is {len(source)} bytes, patch wants {source_size}")
    if zlib.crc32(source) != int.from_bytes(patch[-12:-8], "little"):
        raise ValueError("source checksum mismatch: wrong base ROM")

    target = bytearray()
    source_rel = target_rel = 0
    end = len(patch) - 12
    while pos < end:
        data, pos = read_number(patch, pos)
        command, length = data & 3, (data >> 2) + 1
        if command == SOURCE_READ:
            start = len(target)
            target += source[start:start + length]
        elif command == TARGET_READ:
            target += patch[pos:pos + length]
            pos += length
        else:
            data, pos = read_number(patch, pos)
            delta = -(data >> 1) if data & 1 else data >> 1
            if command == SOURCE_COPY:
                source_rel += delta
                target += source[source_rel:source_rel + length]
                source_rel += length
            else:
                target_rel += delta
                for _ in range(length):  # may overlap what it is writing
                    target.append(target[target_rel])
                    target_rel += 1
    if len(target) != target_size:
        raise ValueError(f"patch made {len(target)} bytes, expected {target_size}")
    if zlib.crc32(target) != int.from_bytes(patch[-8:-4], "little"):
        raise ValueError("target checksum mismatch")
    return bytes(target)


def build_vanilla(root, names):
    """Build the vanilla ROMs from VANILLA_COMMIT in a throwaway worktree."""
    tmp = tempfile.mkdtemp(prefix="pokered-vanilla-")
    tree = os.path.join(tmp, "tree")
    subprocess.run(["git", "-C", root, "worktree", "add", "--detach", tree, VANILLA_COMMIT],
                   check=True, stdout=subprocess.DEVNULL)
    try:
        subprocess.run(["make", "-C", tree, f"-j{os.cpu_count() or 2}",
                        *(f"{name}.gbc" for name in names)],
                       check=True, stdout=subprocess.DEVNULL)
        built = {}
        for name in names:
            with open(os.path.join(tree, f"{name}.gbc"), "rb") as f:
                built[name] = f.read()
        return built
    finally:
        subprocess.run(["git", "-C", root, "worktree", "remove", "--force", tree], check=False)
        shutil.rmtree(tmp, ignore_errors=True)


def base_roms(root, names):
    bases, missing = {}, []
    for name in names:
        path = os.path.join(root, VANILLA[name][0])
        if os.path.exists(path):
            with open(path, "rb") as f:
                bases[name] = f.read()
        else:
            missing.append(name)
    if missing:
        print(f"building vanilla {', '.join(missing)} from {VANILLA_COMMIT}")
        for name, data in build_vanilla(root, missing).items():
            bases[name] = data
            with open(os.path.join(root, VANILLA[name][0]), "wb") as f:
                f.write(data)
    for name, data in bases.items():
        want = VANILLA[name][1]
        if sha1(data) != want:
            raise SystemExit(f"{VANILLA[name][0]} has sha1 {sha1(data)}, "
                             f"not the retail game's {want}")
    return bases


def main(argv):
    if argv[:1] == ["--apply"]:
        base, patch, out = argv[1:4]
        with open(base, "rb") as f, open(patch, "rb") as g:
            try:
                result = apply(f.read(), g.read())
            except ValueError as e:
                raise SystemExit(f"{patch}: {e}")
        with open(out, "wb") as f:
            f.write(result)
        print(f"{out}: sha1 {sha1(result)}")
        return 0

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    names = argv or list(VANILLA)
    for name in names:
        if name not in VANILLA:
            raise SystemExit(f"no vanilla base known for {name}")
    bases = base_roms(root, names)
    for name in names:
        with open(os.path.join(root, f"{name}.gbc"), "rb") as f:
            rom = f.read()
        patch = encode(bases[name], rom)
        if apply(bases[name], patch) != rom:
            raise SystemExit(f"{name}.bps does not rebuild {name}.gbc")
        with open(os.path.join(root, f"{name}.bps"), "wb") as f:
            f.write(patch)
        print(f"{name}.bps: {len(patch):,} bytes, rebuilds sha1 {sha1(rom)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
