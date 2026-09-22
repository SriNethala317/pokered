"""Headless boot smoke test for the built ROM.

Runs the ROM in PyBoy with no window, advances past the copyright and title
screens, and reports whether the game reached a live frame without crashing.
Exits non-zero on failure so it can gate a build.
"""
import sys
from pyboy import PyBoy

rom = sys.argv[1] if len(sys.argv) > 1 else "pokered.gbc"
frames = int(sys.argv[2]) if len(sys.argv) > 2 else 1200
shot = sys.argv[3] if len(sys.argv) > 3 else None

pyboy = PyBoy(rom, window="null")
pyboy.set_emulation_speed(0)
for _ in range(frames):
    pyboy.tick()

screen = pyboy.screen.ndarray
blank = screen[:, :, :3].std() < 1.0
if shot:
    pyboy.screen.image.save(shot)
pyboy.stop(save=False)

if blank:
    print(f"FAIL: {rom} screen is blank after {frames} frames")
    sys.exit(1)
print(f"PASS: {rom} booted, {frames} frames, screen active")
