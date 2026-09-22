"""Input-driven navigation helpers for scripted play tests.

Walking a route by hand-counting button presses is brittle: one wall in the way
and every later step is wrong. These helpers read the player's coordinates out
of WRAM after each step, so they notice when a move was blocked and route
around it.

Coordinate note: map object files write warps as `warp_event x, y`, but WRAM
stores wYCoord before wXCoord. Mixing the two orders up is the single easiest
mistake to make here, so everything in this module takes and returns (y, x).
"""
from rominspect import load_symbols

# A walk cycle is 16 frames; presses have to outlast one full step.
STEP_HOLD = 20
STEP_RELEASE = 14


class Game:
    def __init__(self, pyboy, sym_path):
        self.p = pyboy
        s = load_symbols(sym_path)
        self.addr = {
            k: s[k][1]
            for k in (
                "wYCoord",
                "wXCoord",
                "wCurMap",
                "wPartyCount",
                "wIsInBattle",
            )
        }

    def tick(self, n):
        for _ in range(n):
            self.p.tick()

    def press(self, button, hold=STEP_HOLD, release=STEP_RELEASE):
        self.p.button_press(button)
        self.tick(hold)
        self.p.button_release(button)
        self.tick(release)

    def mem(self, name):
        return self.p.memory[self.addr[name]]

    @property
    def pos(self):
        return (self.mem("wYCoord"), self.mem("wXCoord"))

    @property
    def map_id(self):
        return self.mem("wCurMap")

    @property
    def in_battle(self):
        return self.mem("wIsInBattle")

    def state(self):
        return {
            "map": self.map_id,
            "pos": self.pos,
            "party": self.mem("wPartyCount"),
            "battle": self.in_battle,
        }

    def skip_text(self, presses=8):
        """Clear an open dialogue box so movement is accepted again."""
        for _ in range(presses):
            self.press("b", hold=4, release=10)

    def goto(self, target, budget=40):
        """Greedily walk toward (y, x) on the current map.

        Returns True on arrival. Stops early if the map changes, which means we
        stepped onto a warp -- usually the point of the trip.
        """
        start_map = self.map_id
        for _ in range(budget):
            if self.map_id != start_map:
                return True
            y, x = self.pos
            if (y, x) == target:
                return True
            dy, dx = target[0] - y, target[1] - x
            # Try the axis with the greater remaining distance first, then the
            # other axis, so a wall on one side does not stall the walk.
            options = []
            if abs(dy) >= abs(dx):
                options = [("down" if dy > 0 else "up", dy), ("right" if dx > 0 else "left", dx)]
            else:
                options = [("right" if dx > 0 else "left", dx), ("down" if dy > 0 else "up", dy)]
            moved = False
            for button, delta in options:
                if delta == 0:
                    continue
                before = self.pos
                self.press(button)
                if self.pos != before or self.map_id != start_map:
                    moved = True
                    break
            if not moved:
                # Fully blocked on both useful axes.
                return self.pos == target
        return self.pos == target
