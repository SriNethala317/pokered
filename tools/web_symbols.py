#!/usr/bin/env python3
"""Write web/build/manifest.json for the browser player.

The page needs a handful of RAM addresses (to draw friends over the screen),
where the player sprite's tiles sit in the ROM (so friends are drawn with the
player's own cartridge graphics, never shipped by us), the link hook address,
and the sha1s of the retail base ROM and of this build (so the page refuses
any other ROM and peers refuse other builds).

Usage: python3 tools/web_symbols.py [pokered]
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "test"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from make_bps import VANILLA  # noqa: E402
from rominspect import load_symbols  # noqa: E402

# Bumped whenever the page-to-page protocol changes.
PROTOCOL = 2  # 2: link fast paths (block and nybble-sync messages)

RAM = [
    "wCurMap", "wYCoord", "wXCoord", "wWalkCounter", "wPlayerMovingDirection",
    "wPlayerDirection", "wSpritePlayerStateData1FacingDirection",
    "wSpritePlayerStateData1ImageIndex", "wSpritePlayerStateData1AnimFrameCounter",
    "wSpritePlayerStateData1YPixels", "wSpritePlayerStateData1XPixels",
    "wSpritePlayerStateData1YStepVector", "wSpritePlayerStateData1XStepVector",
    "wShadowOAM",
    "wSpritePlayerStateData2GrassPriority",
    "wIsInBattle", "wLinkState", "wWalkBikeSurfState", "wCurMapTileset",
    "wJoyIgnore", "wFontLoaded", "wPlayerName",
    "hWY", "hSCX", "hSCY", "hSerialConnectionStatus", "hSerialIgnoringInitialData",
    "wSerialExchangeNybbleSendData", "wSerialExchangeNybbleReceiveData",
    "wSerialSyncAndExchangeNybbleReceiveData", "wUnknownSerialCounter",
]
ROM = ["RedSprite", "RedBikeSprite", "SeelSprite", "OverworldLoop",
       "Serial_ExchangeBytes", "Serial_SyncAndExchangeNybble",
       "Serial_TryEstablishingExternallyClockedConnection"]


def main(argv):
    name = (argv or ["pokered"])[0]
    if name != "pokered":
        raise SystemExit("the web player targets pokered only")
    syms = load_symbols(os.path.join(ROOT, f"{name}.sym"))
    with open(os.path.join(ROOT, f"{name}.gbc"), "rb") as f:
        rom = f.read()
    missing = [s for s in RAM + ROM if s not in syms]
    if missing:
        raise SystemExit(f"missing symbols: {', '.join(missing)}")
    manifest = {
        "game": name,
        "protocol": PROTOCOL,
        "romSha1": hashlib.sha1(rom).hexdigest(),
        "baseSha1": VANILLA[name][1],
        "romSize": len(rom),
        "ram": {s: syms[s][1] for s in RAM},
        "rom": {s: {"bank": syms[s][0], "addr": syms[s][1]} for s in ROM},
    }
    out_dir = os.path.join(ROOT, "web", "build")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print(f"web/build/manifest.json: {manifest['romSha1']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
