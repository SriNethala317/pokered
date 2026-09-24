"""Find plain calls and jumps that cross into another switchable ROM bank.

A `call`, `jp` or `jr` only reaches the bank that is switched in, so from code
in one ROMX bank it cannot reach a label in another: the CPU runs whatever sits
at that address in the current bank, usually straight into a crash. Such calls
have to go through callfar, farcall, predef or homecall. The linker cannot see
the mistake, and it only shows when that exact path runs, which is how the
Field States' first draft crashed on a Rubble block (BattleRandom lives in
bank $0F, the field code in $2D).

Every instruction is attributed to the global label above it, whose bank the
linker's .sym file gives, and compared with the bank of its target.

Usage:
    python test/bankcheck.py [pokered.sym]
"""
import glob
import re
import sys

LABEL = re.compile(r"^([A-Za-z_][\w]*)::?")
JUMP = re.compile(r"^\s+(call|jp|jr)\s+(?:(?:n?z|n?c),\s*)?([A-Za-z_][\w.]*)\s*(?:;.*)?$")


def load(sym_path):
    syms = {}
    for line in open(sym_path, encoding="utf-8", errors="replace"):
        if line.startswith(";") or ":" not in line:
            continue
        loc, name = line.split()
        bank, addr = loc.split(":")
        syms[name] = (int(bank, 16), int(addr, 16))
    return syms


def main():
    sym_path = sys.argv[1] if len(sys.argv) > 1 else "pokered.sym"
    syms = load(sym_path)
    problems = []
    files = [f for f in glob.glob("**/*.asm", recursive=True)
             if not f.startswith((".claude", "graphify-out", "tools"))]
    for path in files:
        here = None
        for n, line in enumerate(open(path, encoding="utf-8", errors="replace"), 1):
            m = LABEL.match(line)
            if m:
                here = syms.get(m.group(1))
                continue
            m = JUMP.match(line)
            if not m or here is None:
                continue
            target = m.group(2)
            if target.startswith(".") or target not in syms:
                continue
            bank, addr = syms[target]
            if addr >= 0x4000 and addr < 0x8000 and here[1] >= 0x4000 and here[1] < 0x8000 \
                    and bank != here[0]:
                problems.append(f"{path}:{n}: {line.strip()} (from bank ${here[0]:02x} "
                                f"to ${bank:02x})")
            elif addr >= 0x4000 and addr < 0x8000 and here[1] < 0x4000:
                pass  # home code switching banks itself around the call is its own business
    for p in problems:
        print("  FAIL  " + p)
    print(f"{len(files)} files checked, {len(problems)} cross-bank plain calls")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
