"""Read data structures back out of a built ROM.

Assembling successfully only proves the source is syntactically valid. To prove a
data change actually reached the cartridge, we resolve the label through the
linker's symbol map and read the bytes at that address out of the ROM image.

Usage:
    python test/rominspect.py pokered.gbc pokered.sym TypeEffects 32
"""
import sys


def load_symbols(sym_path):
    """Map label -> (bank, address) from an rgblink .sym file."""
    symbols = {}
    with open(sym_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.split(";")[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 2 or ":" not in parts[0]:
                continue
            bank_str, addr_str = parts[0].split(":", 1)
            try:
                symbols[parts[1]] = (int(bank_str, 16), int(addr_str, 16))
            except ValueError:
                continue
    return symbols


def rom_offset(bank, addr):
    """Convert a Game Boy bank:address pair into a flat ROM file offset."""
    if addr < 0x4000:
        return addr
    return bank * 0x4000 + (addr - 0x4000)


def read_label(rom_path, sym_path, label, length):
    symbols = load_symbols(sym_path)
    if label not in symbols:
        raise KeyError(f"label {label!r} not found in {sym_path}")
    bank, addr = symbols[label]
    offset = rom_offset(bank, addr)
    with open(rom_path, "rb") as f:
        f.seek(offset)
        return bank, addr, f.read(length)


if __name__ == "__main__":
    rom, sym, label = sys.argv[1], sys.argv[2], sys.argv[3]
    length = int(sys.argv[4]) if len(sys.argv) > 4 else 16
    bank, addr, data = read_label(rom, sym, label, length)
    print(f"{label} @ {bank:02x}:{addr:04x} (+0x{rom_offset(bank, addr):06x})")
    print(" ".join(f"{b:02x}" for b in data))
