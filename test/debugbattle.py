"""Drop straight into a real battle in the debug build.

Walking a fresh save to a wild encounter is a long and brittle route, and it
only ever exercises whatever matchup happens to occur. The debug build has a
much better door: holding SELECT as the title screen hands off opens a debug
menu whose first entry starts a level 20 Rhydon mirror match. The battle code
is identical between the release and debug builds -- only the entry differs.

Shared by the battle checks under test/.
"""
from pyboy import PyBoy

from rominspect import load_symbols

WANTED = (
    "wIsInBattle",
    "wBattleMonMoves",
    "wBattleMonPP",
    "wBattleMonHP",
    "wBattleMonMaxHP",
    "wBattleMonAttack",
    "wBattleMonDefense",
    "wBattleMonSpecial",
    "wEnemyMonHP",
    "wEnemyMonMaxHP",
    "wEnemyMonAttack",
    "wEnemyMonSpecial",
    "wPlayerSelectedMove",
    "wTestBattlePlayerSelectedMove",
    "wPlayerMoveNum",
    "wPlayerMovePower",
    "wBattleMonSpeed",
    "wBattleMonSpecies",
    "wEnemyMonSpecies",
    "wDamage",
    "hWhoseTurn",
    "wCriticalHitOrOHKO",
    "wPlayerBattleStatus1",
    "wPlayerBattleStatus2",
    "wEnemyBattleStatus1",
    "wPlayerNumAttacksLeft",
    "wPartyCount",
    "wTopMenuItemY",
    "wMaxMenuItem",
    "wOptions",
    "wActionCommandState",
    "wActionCommandResult",
)

# wOptions bits 4-5, see constants/ram_constants.asm
ACTION_COMMANDS_MASK = 0b110000
ACTION_COMMANDS = {"on": 0b000000, "assist": 0b010000, "off": 0b100000}


class NotReached(Exception):
    """The debug battle could not be entered."""


def word(p, addr):
    return (p.memory[addr] << 8) | p.memory[addr + 1]


def write_word(p, addr, value):
    p.memory[addr] = (value >> 8) & 0xFF
    p.memory[addr + 1] = value & 0xFF


def tap(p, button, hold=4, release=8):
    p.button_press(button)
    for _ in range(hold):
        p.tick()
    p.button_release(button)
    for _ in range(release):
        p.tick()


def set_action_commands(p, at, mode):
    """Switch the timed-press option. Read when each attack is armed."""
    options = p.memory[at["wOptions"]] & ~ACTION_COMMANDS_MASK
    p.memory[at["wOptions"]] = options | ACTION_COMMANDS[mode]


def boot_to_debug_menu(rom_path, sym_path):
    """Boot the debug ROM and return (pyboy, addresses) at the debug menu."""
    symbols = load_symbols(sym_path)
    at = {k: symbols[k][1] for k in WANTED if k in symbols}

    p = PyBoy(rom_path, window="null")
    p.set_emulation_speed(0)

    # The title screen reads hJoyHeld at the moment it hands off, so SELECT has
    # to still be down when START lands. How many frames the intro takes before
    # the title even appears is not worth guessing, so keep tapping START until
    # the debug menu's own cursor layout appears.
    p.button_press("select")
    reached = False
    for i in range(4000):
        p.tick()
        if i % 120 == 0 and i > 240:
            p.button_press("start")
            for _ in range(8):
                p.tick()
            p.button_release("start")
        # DebugMenu is the only menu with two entries drawn at row 7.
        if p.memory[at["wTopMenuItemY"]] == 7 and p.memory[at["wMaxMenuItem"]] == 1:
            reached = True
            break
    p.button_release("select")
    for _ in range(60):
        p.tick()
    if not reached:
        p.stop(save=False)
        raise NotReached("never reached the debug menu")
    return p, at


def enter(rom_path, sym_path, action_commands="off"):
    """Boot the debug ROM and return (pyboy, addresses) inside a live battle.

    Action commands default to off: most checks measure damage while pressing
    A, and a press that happened to land in the window would scale it.
    """
    p, at = boot_to_debug_menu(rom_path, sym_path)

    # FIGHT is the first entry and the cursor starts on it. TestBattle builds
    # the party with AddPartyMon, which stops on a "give a nickname?" prompt, so
    # keep answering B (no) until the battle itself is up.
    tap(p, "a", hold=10, release=0)
    for _ in range(80):
        if p.memory[at["wIsInBattle"]]:
            break
        tap(p, "b", hold=6, release=24)

    if not p.memory[at["wIsInBattle"]]:
        p.stop(save=False)
        raise NotReached("debug FIGHT did not start a battle")

    # wIsInBattle is set well before the battle is actually set up: the send-out
    # sequence still has to copy the party Pokemon into wBattleMon, and it waits
    # on the "Go! RHYDON!" message boxes to be dismissed first. Anything written
    # before that copy lands is silently overwritten. B advances text and does
    # nothing at the battle menu, so it is safe to hold on past the last box.
    for _ in range(60):
        if word(p, at["wBattleMonHP"]) > 0:
            break
        tap(p, "b", hold=4, release=16)
    for _ in range(120):
        p.tick()

    if word(p, at["wBattleMonHP"]) == 0:
        p.stop(save=False)
        raise NotReached("battle started but the player's Pokemon never loaded")

    set_action_commands(p, at, action_commands)
    return p, at
