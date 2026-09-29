"""Fail on any text line that won't fit a Gen 1 text box (18 tiles).

Usage: python3 test/textlint.py [files...]   (default: text/*.asm changed
against master, i.e. vanilla). Lines vanilla already has are skipped: a few
vanilla lines run long. <PLAYER> and <RIVAL> count as 7, # as 4 (POKé), other
<...> control tokens as 0.

A line printed just before a wait (the next command is `para` or `prompt`)
gets only 17: the wait arrow is drawn over the 18th tile, and the box is
cleared before the player sees the letter under it.

The rival's defeated text is printed after his name ("<RIVAL>: "), so its
first line has 9 fewer tiles.
"""
import re
import subprocess
import sys

WIDTH = 18
BASE = "master"  # vanilla pret/pokered: lines it already has are not ours to lint
NAMED = re.compile(r"^_\w*Rival\w*DefeatedText::")  # printed after "<RIVAL>: "
LINE = re.compile(r'^\s*(text|line|cont|para|next)\s+"(.*)"')


def width(s):
    s = s.replace("<PLAYER>", "x" * 7).replace("<RIVAL>", "x" * 7)
    s = re.sub(r"<[^>]*>", "", s)
    return len(s.rstrip("@").replace("#", "POKé"))


def main():
    files = sys.argv[1:] or subprocess.run(
        ["git", "diff", "--name-only", BASE, "--", "text/", "data/text/"],
        capture_output=True, text=True, check=True).stdout.split()
    bad = 0
    for f in files:
        old = set(subprocess.run(["git", "show", f"{BASE}:{f}"],
                                 capture_output=True, text=True).stdout.splitlines())
        lines = open(f, encoding="utf-8").read().splitlines()
        named = False
        for n, l in enumerate(lines, 1):
            m = LINE.match(l)
            if NAMED.match(l):
                named = True
            if not m or l.rstrip("\n") in old:
                named = named and not m
                continue
            nxt = next((x.split()[0] for x in lines[n:] if x.strip()), "")
            limit = WIDTH - 1 if nxt in ("para", "prompt") else WIDTH
            if named:
                limit -= width("<RIVAL>: ")
                named = False
            if width(m.group(2)) > limit:
                print(f"{f}:{n}: {width(m.group(2))} > {limit}: {m.group(2)}")
                bad += 1
    print(f"{len(files)} files, {bad} over-long lines")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
