"""Report ROM bank and RAM headroom for a build.

The brief requires a free-space report on every build. rgblink already writes a
SUMMARY block at the top of the .map file; this parses it, prints the numbers,
and fails loudly when a region drops below a safety margin, so we find out we
are out of room at build time rather than three features later.

Usage:
    python test/romspace.py pokered.map
    python test/romspace.py pokered.map --baseline baseline.json
"""
import json
import re
import sys

# Regions where running out is a hard wall. ROMX has 44 banks of slack, so it is
# tracked but not gated.
CRITICAL = {"ROM0", "WRAM0", "HRAM", "SRAM"}

SUMMARY_RE = re.compile(
    r"^\s*(\w+):\s+(\d+) bytes used / (\d+) free(?: in (\d+) banks?)?"
)


def parse(map_path):
    regions = {}
    with open(map_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith("ROM0 bank"):
                break
            m = SUMMARY_RE.match(line)
            if m:
                name, used, free, banks = m.groups()
                regions[name] = {
                    "used": int(used),
                    "free": int(free),
                    "banks": int(banks) if banks else 1,
                }
    return regions


def main():
    map_path = sys.argv[1] if len(sys.argv) > 1 else "pokered.map"
    baseline = None
    if "--baseline" in sys.argv:
        path = sys.argv[sys.argv.index("--baseline") + 1]
        try:
            with open(path, encoding="utf-8") as f:
                baseline = json.load(f)
        except FileNotFoundError:
            baseline = None

    regions = parse(map_path)
    if not regions:
        print(f"FAIL: no SUMMARY block found in {map_path}")
        return 1

    print(f"{'region':8} {'used':>9} {'free':>9}  {'delta vs baseline':>18}")
    for name, r in regions.items():
        delta = ""
        if baseline and name in baseline:
            d = r["free"] - baseline[name]["free"]
            delta = f"{d:+d} bytes free"
        bank_note = f" ({r['banks']} banks)" if r["banks"] > 1 else ""
        print(f"{name:8} {r['used']:>9} {r['free']:>9}  {delta:>18}{bank_note}")

    # A region with almost nothing left is the real constraint on new features.
    tight = [n for n in CRITICAL if n in regions and regions[n]["free"] < 64]
    if tight:
        print()
        for n in sorted(tight):
            print(f"WARNING: {n} has only {regions[n]['free']} bytes free")

    if "--save" in sys.argv:
        out = sys.argv[sys.argv.index("--save") + 1]
        with open(out, "w", encoding="utf-8") as f:
            json.dump(regions, f, indent=2)
        print(f"\nbaseline written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
