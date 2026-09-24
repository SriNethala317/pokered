"""ctypes binding for web/core/link_shim.c (native build: web/build/native/liblinkshim.so).

Build it with `make -C web/core native` after `web/fetch_core.sh`.
"""
import ctypes
import os
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LIB_PATH = os.path.join(ROOT, "web", "build", "native", "liblinkshim.so")

FRAME, STALLED, HOOK = 0, 1, 2
XFER, REPLY = 1, 2

KEYS = {
    "a": 1 << 0,
    "b": 1 << 1,
    "select": 1 << 2,
    "start": 1 << 3,
    "right": 1 << 4,
    "left": 1 << 5,
    "up": 1 << 6,
    "down": 1 << 7,
}


def _load():
    lib = ctypes.CDLL(LIB_PATH)
    P, U8, U16, I, SZ = ctypes.c_void_p, ctypes.c_uint8, ctypes.c_uint16, ctypes.c_int, ctypes.c_size_t
    sig = {
        "shim_create": (P, []),
        "shim_destroy": (None, [P]),
        "shim_load_rom": (I, [P, ctypes.c_char_p, SZ]),
        "shim_reset": (None, [P]),
        "shim_sram_size": (I, [P]),
        "shim_sram_save": (I, [P, ctypes.c_char_p, SZ]),
        "shim_sram_load": (None, [P, ctypes.c_char_p, SZ]),
        "shim_sram_dirty": (I, [P]),
        "shim_run_frame": (I, [P]),
        "shim_frame_count": (ctypes.c_uint64, [P]),
        "shim_set_keys": (None, [P, U8]),
        "shim_framebuffer": (ctypes.POINTER(U8), [P]),
        "shim_set_audio_enabled": (None, [P, I]),
        "shim_read": (U8, [P, U16]),
        "shim_write": (None, [P, U16, U8]),
        "shim_rom_bank": (I, [P]),
        "shim_link_plug": (None, [P, I]),
        "shim_link_plugged": (I, [P]),
        "shim_link_stalled": (I, [P]),
        "shim_link_gate": (None, [P, U16, U8]),
        "shim_link_fast": (None, [P, U16, U16, U16]),
        "shim_link_blocks": (ctypes.c_uint32, [P]),
        "shim_link_fast_sync": (None, [P, U16, U16, U16, U16, U16]),
        "shim_link_syncs": (ctypes.c_uint32, [P]),
        "shim_link_pop_packed": (I, [P]),
        "shim_link_push": (I, [P, U8, U8]),
        "shim_link_bytes_sent": (ctypes.c_uint32, [P]),
        "shim_link_bytes_received": (ctypes.c_uint32, [P]),
        "shim_hook_add": (I, [P, U16, I, I]),
        "shim_hook_clear": (None, [P]),
        "shim_hook_next": (I, [P]),
        "shim_reg": (U16, [P, I]),
        "shim_set_reg": (None, [P, I, U16]),
    }
    for name, (res, args) in sig.items():
        fn = getattr(lib, name)
        fn.restype = res
        fn.argtypes = args
    return lib


_lib = None


def lib():
    global _lib
    if _lib is None:
        if not os.path.exists(LIB_PATH):
            raise SystemExit(f"{LIB_PATH} missing: run web/fetch_core.sh && make -C web/core native")
        _lib = _load()
    return _lib


class Console:
    def __init__(self, rom_bytes, sram=None):
        self.L = lib()
        self.s = self.L.shim_create()
        self.L.shim_set_audio_enabled(self.s, 0)
        if self.L.shim_load_rom(self.s, rom_bytes, len(rom_bytes)) != 0:
            raise RuntimeError("load_rom failed")
        if sram is not None:
            self.L.shim_sram_load(self.s, sram, len(sram))
        self.keys = 0

    def close(self):
        if self.s:
            self.L.shim_destroy(self.s)
            self.s = None

    def run_frame(self):
        return self.L.shim_run_frame(self.s)

    def set_keys(self, names):
        mask = 0
        for n in names:
            mask |= KEYS[n]
        self.keys = mask
        self.L.shim_set_keys(self.s, mask)

    def read(self, addr):
        return self.L.shim_read(self.s, addr)

    def write(self, addr, value):
        self.L.shim_write(self.s, addr, value)

    def sram(self):
        n = self.L.shim_sram_size(self.s)
        buf = ctypes.create_string_buffer(n)
        self.L.shim_sram_save(self.s, buf, n)
        return buf.raw

    def framebuffer(self):
        p = self.L.shim_framebuffer(self.s)
        return bytes(ctypes.cast(p, ctypes.POINTER(ctypes.c_uint8 * (160 * 144 * 4))).contents)

    # link
    def plug(self, on=True):
        self.L.shim_link_plug(self.s, 1 if on else 0)

    def gate(self, addr, value):
        self.L.shim_link_gate(self.s, addr, value)

    def fast(self, exchange_bytes, status, ignoring):
        self.L.shim_link_fast(self.s, exchange_bytes, status, ignoring)

    def blocks(self):
        return self.L.shim_link_blocks(self.s)

    def fast_sync(self, sync, send, recv, result, counter):
        self.L.shim_link_fast_sync(self.s, sync, send, recv, result, counter)

    def syncs(self):
        return self.L.shim_link_syncs(self.s)

    def stalled(self):
        return bool(self.L.shim_link_stalled(self.s))

    def pop(self):
        out = []
        while True:
            v = self.L.shim_link_pop_packed(self.s)
            if v < 0:
                return out
            out.append((v >> 8, v & 0xFF))

    def push(self, kind, byte):
        if self.L.shim_link_push(self.s, kind, byte) != 0:
            raise RuntimeError("link queue full")

    def hook(self, addr, bank=-1, brk=False):
        return self.L.shim_hook_add(self.s, addr, bank, 1 if brk else 0)

    def hooks_fired(self):
        out = []
        while True:
            h = self.L.shim_hook_next(self.s)
            if h < 0:
                return out
            out.append(h)


def asm_constants(*names):
    """Evaluate assembler constants by asking rgbasm to print them."""
    src = 'INCLUDE "includes.asm"\n' + "".join(f'PRINTLN "{n}=", {n}\n' for n in names)
    tmp = os.path.join(ROOT, "web", "build", "consts.asm")
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    with open(tmp, "w") as f:
        f.write(src)
    out = subprocess.run(["rgbasm", "-o", os.devnull, tmp], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    vals = {}
    for line in out.splitlines():
        k, v = line.split("=", 1)
        vals[k] = int(v.strip().lstrip("$"), 16)
    return vals
