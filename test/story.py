"""Harness for story tests: drop the player into any scene and read its text.

Playing the whole game to reach Silph Co. is not practical for a test, and
nothing in a scene depends on how the player got there, only on the event
flags, toggleable objects and map script indices it reads. So a Story boots
the debug new game once, keeps a save state of the overworld, and for each
scene reloads it, writes that scene's flags and "warps" the player: wCurMap
and the coordinates are set, wDestinationWarpID is $ff (so the map loader keeps
them), and the overworld loop is sent to EnterMap, as a real warp does.

Everything shown in the text box (rows 14 and 16) is recorded as the game
draws it, and Story.expected() reads the lines a text label should print out
of text/*.asm, so a test can check that the game printed exactly those lines.
"""
import io
import re
from pathlib import Path

from pyboy import PyBoy

from debugbattle import boot_to_debug_menu, tap, word, write_word
from rominspect import load_symbols

ROOT = Path(__file__).resolve().parent.parent
SCREEN_WIDTH = 20
TX_FAR, TX_END = 0x17, 0x50
INTRO_TAPS = 300


def _charmap():
    """byte -> string, from constants/charmap.asm (the English entries win)."""
    table = {}
    for line in open(ROOT / "constants/charmap.asm", encoding="utf-8"):
        m = re.match(r'\s*charmap\s+"([^"]*)",\s*\$([0-9a-fA-F]+)', line)
        if m and not m.group(1).startswith("<"):
            table.setdefault(int(m.group(2), 16), m.group(1))
    table[0x7F] = " "
    return table


CHARS = _charmap()


def decode(data):
    return "".join(CHARS.get(b, "?") for b in data)


def _constants(path, first=0):
    """NAME -> value for a file of `const`s (const_def / const_next aware)."""
    def number(expr):  # e.g. "$F0 - 2"
        return eval(re.sub(r"\$([0-9a-fA-F]+)", r"0x\1", expr), {})

    values, v = {}, first
    for line in open(ROOT / path, encoding="utf-8"):
        line = line.split(";")[0].strip()
        if m := re.match(r"const_def\b\s*(.*)", line):
            v = number(m.group(1)) if m.group(1) else 0
        elif m := re.match(r"const_(next|skip)\b\s*(.*)", line):
            if m.group(1) == "next":
                v = number(m.group(2))
            else:
                v += number(m.group(2)) if m.group(2) else 1
        elif m := re.match(r"const\s+(\w+)", line):
            values[m.group(1)] = v
            v += 1
    return values


EVENTS = _constants("constants/event_constants.asm")
TOGGLES = _constants("constants/toggle_constants.asm")


def _maps():
    """NAME -> (id, width in blocks) from constants/map_constants.asm."""
    maps, v = {}, 0
    for line in open(ROOT / "constants/map_constants.asm", encoding="utf-8"):
        line = line.split(";")[0].strip()
        if m := re.match(r"map_const\s+(\w+),\s*(\d+),\s*(\d+)", line):
            maps[m.group(1)] = (v, int(m.group(2)))
            v += 1
        elif m := re.match(r"const_def", line):
            v = 0
    return maps


MAPS = _maps()


def text_entries():
    """_Label -> list of printed strings, for every label in text/*.asm."""
    entries = {}
    for f in sorted((ROOT / "text").glob("*.asm")):
        label = None
        for line in open(f, encoding="utf-8"):
            if m := re.match(r"^(_\w+)::", line):
                label = m.group(1)
                entries[label] = []
            elif label and (m := re.match(r'\s*(text|line|cont|para|next)\s+"(.*)"', line)):
                entries[label].append(m.group(2))
    return entries


class Story:
    def __init__(self, rom="pokered_debug.gbc", sym="pokered_debug.sym"):
        self.s = load_symbols(sym)
        self.actions, self.seen = [], []
        self.p, _ = boot_to_debug_menu(rom, sym)
        p = self.p
        tap(p, "down", hold=8, release=24)
        tap(p, "a", hold=8, release=40)
        for n in range(INTRO_TAPS):
            tap(p, "b", hold=4, release=20)
            if n % 10 == 9:
                tap(p, "start", hold=6, release=40)
                if "ITEM" in "".join(self.rows()):
                    break
        tap(p, "b", hold=6, release=60)
        self.tick(60)
        m = p.memory
        # fast text, action commands off, SET battle style, no animations
        m[self.a("wOptions")] = 0b11100001
        self.player = self.name("wPlayerName")
        self.rival = self.name("wRivalName")
        self.seen = []
        self.asked = []  # the text box, each time a YES/NO box opened
        self.question = False
        self.loop_frame = -1
        p.hook_register(*self.s["OverworldLoop"], self._overworld, None)
        p.hook_register(*self.s["YesNoChoice"], self._yes_no, None)
        self.base = io.BytesIO()
        p.save_state(self.base)

    # --- memory ---------------------------------------------------------
    def a(self, name):
        return self.s[name][1]

    def name(self, label):
        m, at = self.p.memory, self.a(label)
        out = []
        for i in range(11):
            if m[at + i] == 0x50:
                break
            out.append(m[at + i])
        return decode(out)

    def tick(self, n=1):
        for _ in range(n):
            self.p.tick()
            self._record()

    def rows(self, which=range(18)):
        m, base = self.p.memory, self.a("wTileMap")
        return [decode(m[base + y * SCREEN_WIDTH + x] for x in range(SCREEN_WIDTH)) for y in which]

    def _record(self):
        if self.rows((12,))[0][0] != "┌":
            return
        for row in self.rows((14, 16)):
            text = row[1:19].replace("▼", " ").strip()
            if text and (not self.seen or self.seen[-1] != text):
                self.seen.append(text)

    def event(self, name, value=True):
        n = EVENTS[name]
        at = self.a("wEventFlags") + n // 8
        m = self.p.memory
        m[at] = (m[at] | (1 << (n % 8))) if value else (m[at] & ~(1 << (n % 8)))

    def has_event(self, name):
        n = EVENTS[name]
        return bool(self.p.memory[self.a("wEventFlags") + n // 8] & (1 << (n % 8)))

    def toggle(self, name, shown):
        """Show or hide a toggleable object (the flag set means hidden)."""
        n = TOGGLES[name]
        at = self.a("wToggleableObjectFlags") + n // 8
        m = self.p.memory
        m[at] = (m[at] & ~(1 << (n % 8))) if shown else (m[at] | (1 << (n % 8)))

    # --- control --------------------------------------------------------
    def reset(self):
        self.base.seek(0)
        self.p.load_state(self.base)
        self.p.memory[self.a("wRepelRemainingSteps")] = 255  # no wild battles in a scene
        self.actions = []
        self.seen = []
        self.asked = []
        self.question = False

    def _yes_no(self, _):
        self.question = True
        self.asked.append(" / ".join(r[1:19].strip() for r in self.rows((14, 16))))

    def _overworld(self, _):
        self.loop_frame = self.p.frame_count
        if self.actions:
            self.actions.pop(0)()

    def _call(self, target, **regs):
        """From the overworld loop, call `target` and come back to the loop."""
        r, m = self.p.register_file, self.p.memory
        r.SP -= 2
        m[r.SP] = r.PC & 0xFF
        m[r.SP + 1] = r.PC >> 8
        for k, v in regs.items():
            setattr(r, k, v)
        r.PC = target

    def at_overworld(self, fn, frames=120):
        """Run fn at the top of the next overworld loop."""
        self.actions.append(fn)
        for _ in range(frames):
            self.tick()
            if not self.actions:
                return
        raise AssertionError("the overworld loop never came round")

    def print_text(self, label):
        """Print a text label (e.g. _OaksLabRivalIllTakeYouOnText) in a text box."""
        bank, addr = self.s[label]
        buf = self.a("wSerialEnemyDataBlock")
        m = self.p.memory
        for i, b in enumerate((TX_FAR, addr & 0xFF, addr >> 8, bank, TX_END)):
            m[buf + i] = b
        self.at_overworld(lambda: self._call(self.s["PrintText"][1], HL=buf))

    def warp(self, map_name, x, y, last_map=None, setup=None):
        """Put the player on (x, y) of a map, as if they had walked in."""
        map_id, width = MAPS[map_name]

        def go():
            m = self.p.memory
            if setup:
                setup()
            m[self.a("wCurMap")] = map_id
            m[self.a("wDestinationWarpID")] = 0xFF
            m[self.a("wYCoord")], m[self.a("wXCoord")] = y, x
            m[self.a("wYBlockCoord")], m[self.a("wXBlockCoord")] = y & 1, x & 1
            view = self.a("wOverworldMap") + 7 + width + (width + 6) * (y >> 1) + (x >> 1)
            m[self.a("wCurrentTileBlockMapViewPointer")] = view & 0xFF
            m[self.a("wCurrentTileBlockMapViewPointer") + 1] = view >> 8
            if last_map is not None:
                m[self.a("wLastMap")] = MAPS[last_map][0]
            self.p.register_file.PC = self.s["EnterMap"][1]

        self.at_overworld(go)
        self.settle()

    def settle(self, frames=90):
        self.tick(frames)

    def idle(self):
        """The player could walk: the overworld loop ran this frame with no
        text box, no scripted movement and no input ignored."""
        m = self.p.memory
        return (self.p.frame_count - self.loop_frame <= 4
                and not m[self.a("wIsInBattle")]
                and m[self.a("wJoyIgnore")] == 0
                and m[self.a("wSimulatedJoypadStatesIndex")] == 0
                and m[self.a("wNPCMovementScriptFunctionNum")] == 0
                and self.rows((12,))[0][0] != "┌")

    def drive(self, answers=(), frames=20000, quiet=90, win=True, until=None):
        """Play a scene out: page text with B, answer YES/NO boxes from
        `answers` (then YES), and win any battle (the foe is held at 1 HP, our
        side at full), or with win=False lose it the same way. Returns once the player has been free for `quiet`
        frames, or as soon as until() is true; raises if that never happens."""
        answers = list(answers)
        m = self.p.memory
        calm = 0
        self.battles = getattr(self, "battles", 0)
        in_battle = False
        for f in range(frames):
            self.tick()
            if until and until():
                return f
            if m[self.a("wIsInBattle")]:
                if not in_battle:
                    self.battles += 1
                in_battle = True
                ours, theirs = ("wBattleMonHP", "wEnemyMonHP") if win else ("wEnemyMonHP", "wBattleMonHP")
                if word(self.p, self.a(theirs)) > 1:
                    write_word(self.p, self.a(theirs), 1)
                write_word(self.p, self.a(ours), word(self.p, self.a(ours.replace("HP", "MaxHP"))))
                if f % 8 == 0:
                    tap(self.p, "a", hold=3, release=3)
                calm = 0
                continue
            in_battle = False
            if self.question:
                self.question = False
                self.tick(30)
                if not (answers.pop(0) if answers else True):
                    tap(self.p, "down", hold=4, release=12)
                tap(self.p, "a", hold=4, release=20)
                calm = 0
                continue
            if self.idle() and not until:
                calm += 1
                if calm >= quiet:
                    return f
                continue
            calm = 0
            if f % 8 == 0:
                tap(self.p, "b", hold=3, release=3)
        raise AssertionError(f"the scene never gave control back; last text {self.seen[-4:]}")

    def walk(self, *steps):
        """Walk, e.g. walk("up", "up", "left"); a step into a wall only turns."""
        for button in steps:
            tap(self.p, button, hold=18, release=14)
            self.tick(4)

    def face(self, direction):
        tap(self.p, direction, hold=2, release=10)

    def talk(self):
        tap(self.p, "a", hold=4, release=10)

    @property
    def pos(self):
        m = self.p.memory
        return m[self.a("wXCoord")], m[self.a("wYCoord")]

    @property
    def map(self):
        return self.p.memory[self.a("wCurMap")]

    # --- text ----------------------------------------------------------
    def expected(self, label):
        out = []
        for s in text_entries()[label]:
            if "@" in s.rstrip("@"):
                continue  # a string broken up by text_ram & co.
            s = s.rstrip("@").replace("<PLAYER>", self.player).replace("<RIVAL>", self.rival)
            s = s.replace("#", "POKé")
            if not re.search(r"<[^>]*>", s) and s.strip():
                out.append(s.strip())
        return out

    def missing(self, label):
        """Lines of `label` that never appeared in the text box."""
        seen = set(self.seen)
        # a trainer's end-of-battle text follows their name: "SONY: What!?"
        seen |= {s.split(": ", 1)[1] for s in self.seen if ": " in s}
        return [line for line in self.expected(label) if line not in seen]
