"""Fail on any text line that won't fit a Gen 1 text box (18 tiles).

Usage: python3 test/textlint.py [files...]   (default: text/*.asm changed
against integration). Lines unchanged from integration are skipped: a few
vanilla lines run long. <PLAYER> and <RIVAL> count as 7, # as 4 (POKé), other
<...> control tokens as 0.
"""
import re
import subprocess
import sys

WIDTH = 18
LINE = re.compile(r'^\s*(text|line|cont|para|next)\s+"(.*)"')


def width(s):
    s = s.replace("<PLAYER>", "x" * 7).replace("<RIVAL>", "x" * 7)
    s = re.sub(r"<[^>]*>", "", s)
    return len(s.rstrip("@").replace("#", "POKé"))


def main():
    files = sys.argv[1:] or subprocess.run(
        ["git", "diff", "--name-only", "integration", "--", "text/", "data/text/"],
        capture_output=True, text=True, check=True).stdout.split()
    bad = 0
    for f in files:
        old = set(subprocess.run(["git", "show", f"integration:{f}"],
                                 capture_output=True, text=True).stdout.splitlines())
        for n, l in enumerate(open(f, encoding="utf-8"), 1):
            m = LINE.match(l)
            if m and l.rstrip("\n") not in old and width(m.group(2)) > WIDTH:
                print(f"{f}:{n}: {width(m.group(2))} > {WIDTH}: {m.group(2)}")
                bad += 1
    print(f"{len(files)} files, {bad} over-long lines")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
