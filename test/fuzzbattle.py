"""Fuzz the debug battle with action commands on, and check it never breaks.

Plays many turns with a random move on each side, drawn from every move that
keeps the battle going: multi-hit, charging, trapping, recoil, Explosion, one
hit knockouts, fixed damage, Counter, Bide, Metronome, Mirror Move and the
rest. Each turn also picks random badges, a random option and animation
setting, a random low HP and sometimes a long streak, and the buttons are
mashed on almost every frame. With --trainer, every attack is armed as if in a
trainer battle, so the trainer's timing and feints are fuzzed as well.

At every battle menu it checks that:
  - the game has not crashed (executing rst $38);
  - no window is still open: the state is idle or showing a badge;
  - no cue is left on screen or in the saved copy of the screen;
  - no badge is left on screen with nothing to clear it;
  - HP is never above max on either side;
  - the text speed bits of wOptions are untouched;
and that the battle menu keeps coming back (no softlock). A battle that ends
is started again.

Usage:
    python test/fuzzbattle.py SEED TURNS [--trainer]
"""
import random
import sys

from debugbattle import enter, word, write_word
from rominspect import load_symbols

ROM = "pokered_debug.gbc"
SYM = "pokered_debug.sym"

# Moves are numbered from POUND = 1 in constants/move_constants.asm.
# Roar, Whirlwind and Teleport end a wild battle, and Mimic opens a menu the
# fuzzer cannot drive, so they are left out.
SKIP = {18, 46, 100, 102}  # WHIRLWIND, ROAR, TELEPORT, MIMIC
NUM_ATTACKS = 165
POOL = [m for m in range(1, NUM_ATTACKS + 1) if m not in SKIP]

IDLE, BADGE = 0, 4
OPTION_BITS = 0b10110000  # battle animation and action commands
ACTION_MODES = (0b000000, 0b000000, 0b010000, 0b100000)  # on twice as often
STALL_FRAMES = 20000
OUT_OF_BATTLE_FRAMES = 300

EXTRA = (
    "wEnemyMonMoves", "wEnemyMonPP", "wObtainedBadges", "wTileMap",
    "wTileMapBackup", "wActionCommandCue", "wActionCommandStreak",
    "wIsInBattle", "wResonanceMeter", "wResonanceTurns", "wTrainerPain",
    "wResonanceFlags", "wPartyMon1Bond", "wEventFlags",
    "wFieldEnv", "wFieldState", "wFieldTurns", "wImprovise",
)
NUM_ENVS, NUM_FIELD_STATES, FIELD_TURNS = 8, 9, 5
EVENT_RESONANCE_UNLOCKED = 0x6A
RESONANCE_ACTIVE = 1 << 7
TRAINER_MAX_HP = 24
MAX_METER, MAX_TURNS = 12, 8  # ResonanceRamp's largest meter, and turns x 2


def text(s):
    """The ROM's charmap for the characters the cues and badges use."""
    out = bytearray()
    for ch in s:
        if "A" <= ch <= "Z":
            out.append(0x80 + ord(ch) - ord("A"))
        else:
            out.append({"!": 0xE7, "?": 0xE6, " ": 0x7F, "×": 0xF1}[ch])
    return bytes(out)


CUES = [text(s) for s in ("A!", "B!", "A?", "B?", "HOLD", "LET GO", "A×", "B×")]
BADGES = [text(s) for s in ("GREAT!", "PERFECT", "BRACED", "COUNTER", "TOO SOON", "FOE ")]


class Fuzzer:
    def __init__(self, seed, trainer):
        self.rng = random.Random(seed)
        self.trainer = trainer
        self.symbols = load_symbols(SYM)
        self.failures = []
        self.menu = False
        self.crashed = False
        self.sessions = 0
        self.text_speed = None
        self.start()

    def start(self):
        self.p, self.at = enter(ROM, SYM, action_commands="on")
        for k in EXTRA:
            self.at[k] = self.symbols[k][1]
        self.p.hook_register(*self.symbols["DisplayBattleMenu"], self.on, "menu")
        self.p.hook_register(0, 0x38, self.on, "crash")
        if self.trainer:
            self.p.hook_register(*self.symbols["ArmActionCommand"], self.on, "arm")
            # A trainer battle only for as long as it takes to arm the attack:
            # straight after it, it is a wild one again, even when arming
            # returned early and no window ever runs.
            for name in ("HandleIfPlayerMoveMissed", "HandleIfEnemyMoveMissed"):
                self.p.hook_register(*self.symbols[name], self.on, "restore")
        self.sessions += 1
        self.text_speed = None

    def on(self, what):
        m, at = self.p.memory, self.at
        if what == "menu":
            self.menu = True
            if self.trainer and m[at["wIsInBattle"]] == 2:
                m[at["wIsInBattle"]] = 1
        elif what == "crash":
            self.crashed = True
        elif what == "arm":
            m[at["wIsInBattle"]] = 2  # roll as if against a trainer
        elif what == "restore":
            if m[at["wIsInBattle"]] == 2:
                m[at["wIsInBattle"]] = 1

    def row(self, tilemap):
        base = self.at[tilemap] + 4 * 20 + 1
        return bytes(self.p.memory[base + i] for i in range(10))

    def fail(self, turn, message):
        self.failures.append(f"turn {turn}: {message}")

    def check(self, turn):
        m, at = self.p.memory, self.at
        state = m[at["wActionCommandState"]]
        if state not in (IDLE, BADGE):
            self.fail(turn, f"window state {state} still live at the battle menu")
        if m[at["wActionCommandCue"]]:
            self.fail(turn, f"cue {m[at['wActionCommandCue']]} recorded at the battle menu")
        for tilemap in ("wTileMap", "wTileMapBackup"):
            row = self.row(tilemap)
            for cue in CUES:
                if row.startswith(cue):
                    self.fail(turn, f"cue {cue.hex()} left in {tilemap}")
        if state == IDLE:
            row = self.row("wTileMap")
            for badge in BADGES:
                if row.startswith(badge):
                    self.fail(turn, f"badge {badge.hex()} on screen with nothing to clear it")
        for side in ("Battle", "Enemy"):
            hp, top = word(self.p, at[f"w{side}MonHP"]), word(self.p, at[f"w{side}MonMaxHP"])
            if hp > top:
                self.fail(turn, f"{side} HP {hp} above max {top}")
        meter, turns = m[at["wResonanceMeter"]], m[at["wResonanceTurns"]]
        pain, flags = m[at["wTrainerPain"]], m[at["wResonanceFlags"]]
        if meter > MAX_METER:
            self.fail(turn, f"Resonance meter {meter} above {MAX_METER}")
        if pain >= TRAINER_MAX_HP:
            self.fail(turn, f"trainer pain {pain} not below {TRAINER_MAX_HP}")
        if flags & RESONANCE_ACTIVE and not 0 < turns <= MAX_TURNS:
            self.fail(turn, f"Resonance active with {turns} turns")
        if not flags & RESONANCE_ACTIVE and turns:
            self.fail(turn, f"Resonance over but {turns} turns left")
        env, field, left = m[at["wFieldEnv"]], m[at["wFieldState"]], m[at["wFieldTurns"]]
        if env >= NUM_ENVS or field >= NUM_FIELD_STATES or left > FIELD_TURNS:
            self.fail(turn, f"field out of range: env {env}, state {field}, turns {left}")
        if m[at["wImprovise"]] & 0x7F > 3:
            self.fail(turn, f"Improvise wait {m[at['wImprovise']] & 0x7F} above 3")
        if field and not left:
            self.fail(turn, f"Field State {field} with no turns left")
        speed = m[at["wOptions"]] & 0x0F
        if self.text_speed is not None and speed != self.text_speed:
            self.fail(turn, f"text speed bits changed to {speed:x}")

    def stage(self):
        m, at, rng = self.p.memory, self.at, self.rng
        move = rng.choice(POOL)
        m[at["wTestBattlePlayerSelectedMove"]] = move
        for i in range(4):
            m[at["wBattleMonMoves"] + i] = move if i == 0 else rng.choice(POOL)
            m[at["wBattleMonPP"] + i] = 30
            m[at["wEnemyMonMoves"] + i] = rng.choice(POOL)
            m[at["wEnemyMonPP"] + i] = 30
        for side in ("Battle", "Enemy"):
            write_word(self.p, at[f"w{side}MonMaxHP"], 500)
            write_word(self.p, at[f"w{side}MonHP"], rng.choice((500, 500, 300, 40, 5, 1)))
        m[at["wObtainedBadges"]] = rng.randrange(256)
        options = m[at["wOptions"]] & ~OPTION_BITS
        options |= rng.choice(ACTION_MODES)
        if rng.random() < 0.3:
            options |= 0x80  # animations off
        m[at["wOptions"]] = options
        self.text_speed = options & 0x0F
        if rng.random() < 0.2:
            m[at["wActionCommandStreak"]] = rng.choice((2, 3, 254, 255))
        # Resonance: unlocked most of the time, often with the Bond and a full meter
        event = at["wEventFlags"] + EVENT_RESONANCE_UNLOCKED // 8
        bit = 1 << (EVENT_RESONANCE_UNLOCKED % 8)
        m[event] = (m[event] | bit) if rng.random() < 0.8 else (m[event] & ~bit)
        if rng.random() < 0.3:
            m[at["wPartyMon1Bond"]] = rng.choice((99, 100, 199, 200, 255))
        if rng.random() < 0.2:
            m[at["wResonanceMeter"]] = MAX_METER
        # the battle stands somewhere random, and sometimes on a random field
        m[at["wFieldEnv"]] = rng.randrange(NUM_ENVS)
        if rng.random() < 0.3:
            m[at["wFieldState"]] = rng.randrange(1, NUM_FIELD_STATES)
            m[at["wFieldTurns"]] = rng.randint(1, FIELD_TURNS)

    def run(self, turns):
        rng = self.rng
        turn = frames = stalled = away = 0
        held = None
        while turn < turns:
            if self.crashed:
                self.fail(turn, "crashed into rst $38")
                break
            if self.menu:
                self.menu = False
                if self.p.memory[self.at["wIsInBattle"]] and word(self.p, self.at["wBattleMonHP"]):
                    self.check(turn)
                    self.stage()
                    turn += 1
                    stalled = 0
            if held is None and rng.random() < 0.25:
                held = [rng.choice("aabbb") if rng.random() < 0.9 else rng.choice(("up", "down", "select", "start")),
                        rng.randrange(1, 10)]
                self.p.button_press(held[0])
            elif held is not None:
                held[1] -= 1
                if held[1] <= 0:
                    self.p.button_release(held[0])
                    held = None
            self.p.tick()
            frames += 1
            stalled += 1
            away = 0 if self.p.memory[self.at["wIsInBattle"]] else away + 1
            if away > OUT_OF_BATTLE_FRAMES:
                # the battle ended: start another one
                self.p.stop(save=False)
                self.start()
                held = None
                stalled = away = 0
            elif stalled > STALL_FRAMES:
                self.fail(turn, f"no battle menu for {STALL_FRAMES} frames")
                self.p.screen.image.save(f"test/out/fuzz_stuck_{turn}.png")
                break
        self.p.stop(save=False)
        return turn, frames


def main():
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    turns = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    fuzzer = Fuzzer(seed, "--trainer" in sys.argv)
    played, frames = fuzzer.run(turns)
    print(f"seed {seed}: {played} turns in {frames} frames over "
          f"{fuzzer.sessions} battles, {len(fuzzer.failures)} failures")
    for f in fuzzer.failures[:30]:
        print("  FAIL", f)
    sys.exit(1 if fuzzer.failures else 0)


if __name__ == "__main__":
    main()
