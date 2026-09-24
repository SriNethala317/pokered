#!/bin/sh
# Fetch the SameBoy core (Expat licence) at a pinned commit into web/vendor/
# and build its free DMG boot ROM. Needs git, make, a C compiler and RGBDS.
set -eu
SAMEBOY_REPO=https://github.com/LIJI32/SameBoy.git
SAMEBOY_COMMIT=213a12ce93d66b105a113debd9396306066a7cfc

here=$(cd "$(dirname "$0")" && pwd)
dest="$here/vendor/SameBoy"

if [ ! -d "$dest/.git" ]; then
	mkdir -p "$dest"
	git -C "$dest" init -q
	git -C "$dest" remote add origin "$SAMEBOY_REPO"
fi
if [ "$(git -C "$dest" rev-parse HEAD 2>/dev/null || true)" != "$SAMEBOY_COMMIT" ]; then
	git -C "$dest" fetch -q --depth 1 origin "$SAMEBOY_COMMIT"
	git -C "$dest" checkout -q --detach FETCH_HEAD
fi
make -C "$dest" bootroms CONF=release >/dev/null 2>&1 || make -C "$dest" bootroms CONF=release
test -f "$dest/build/bin/BootROMs/dmg_boot.bin"
echo "SameBoy $SAMEBOY_COMMIT ready in $dest"
