/*
 * link_shim: a thin C API over the SameBoy core for the RESONANCE web build.
 *
 * The same file builds natively (test/netlink, via ctypes) and with emscripten
 * (web/build/core.js + core.wasm). Everything the page needs goes through here:
 * ROM and SRAM, one frame of emulation, input, the framebuffer, audio, RAM
 * peeks, PC hooks and the link cable.
 *
 * Link cable model (byte-accurate, lockstep):
 *   - When this console starts a transfer on the internal clock (SC=$81) with
 *     the cable plugged in, the shim queues an outgoing XFER(byte) and stalls:
 *     shim_run_frame() returns SHIM_STALLED and the CPU does not advance until
 *     the peer's REPLY(byte) is pushed in. The 8 bits then clock out normally
 *     and the byte that arrives is the peer's reply.
 *   - When an XFER(byte) arrives from the peer, it is applied at the next
 *     instruction boundary: if this console is armed on the external clock
 *     (SC=$80) it receives the byte, raises the serial interrupt and replies
 *     with its old SB. Otherwise it replies $FF (it is itself driving the
 *     clock) or $00 (serial disabled), matching SameBoy's two-console link.
 *   - With the cable unplugged the game sees exactly what it sees with no cable:
 *     internal transfers complete on their own and read $FF.
 * Messages are opaque 2-byte records (kind, byte) for the page to carry.
 */
#ifndef LINK_SHIM_H
#define LINK_SHIM_H

#include <stddef.h>
#include <stdint.h>

#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#define SHIM_API EMSCRIPTEN_KEEPALIVE
#else
#define SHIM_API
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct shim shim_t;

/* shim_run_frame() results */
enum {
    SHIM_FRAME = 0,   /* a full frame ran; the framebuffer is fresh */
    SHIM_STALLED = 1, /* waiting on the peer's reply to our link byte */
    SHIM_HOOK = 2,    /* a hook marked "break" fired; call shim_hook_next() */
};

/* link message kinds */
enum {
    SHIM_LINK_XFER = 1,  /* we clocked a byte out on the internal clock */
    SHIM_LINK_REPLY = 2, /* our answer to the peer's XFER */
    SHIM_LINK_BLOCK = 3, /* one byte of a fast-path block */
    SHIM_LINK_BLOCK_END = 4, /* end of a block; byte = length & 0xFF */
    SHIM_LINK_NYBBLE = 5, /* our side of a fast-path nybble sync */
};

/* joypad bits, same order as the hardware nybbles */
enum {
    SHIM_KEY_A = 1 << 0,
    SHIM_KEY_B = 1 << 1,
    SHIM_KEY_SELECT = 1 << 2,
    SHIM_KEY_START = 1 << 3,
    SHIM_KEY_RIGHT = 1 << 4,
    SHIM_KEY_LEFT = 1 << 5,
    SHIM_KEY_UP = 1 << 6,
    SHIM_KEY_DOWN = 1 << 7,
};

#define SHIM_WIDTH 160
#define SHIM_HEIGHT 144

SHIM_API shim_t *shim_create(void);
SHIM_API void shim_destroy(shim_t *s);

/* ROM bytes are copied. Resets the console. Returns 0 on success. */
SHIM_API int shim_load_rom(shim_t *s, const uint8_t *rom, size_t size);
SHIM_API void shim_reset(shim_t *s);

/* Battery RAM. */
SHIM_API int shim_sram_size(shim_t *s);
SHIM_API int shim_sram_save(shim_t *s, uint8_t *out, size_t size);
SHIM_API void shim_sram_load(shim_t *s, const uint8_t *in, size_t size);
/* 1 if the game wrote SRAM since the last shim_sram_save(). */
SHIM_API int shim_sram_dirty(shim_t *s);

/* Emulation. */
SHIM_API int shim_run_frame(shim_t *s);
SHIM_API uint64_t shim_frame_count(shim_t *s);
SHIM_API void shim_set_keys(shim_t *s, uint8_t keys);
/* 160x144 RGBA8888, row-major. Valid until shim_destroy. */
SHIM_API uint8_t *shim_framebuffer(shim_t *s);

/* Audio: interleaved stereo int16 at the rate set (default 48000). */
SHIM_API void shim_set_sample_rate(shim_t *s, unsigned rate);
SHIM_API int shim_audio_read(shim_t *s, int16_t *out, int max_frames);
SHIM_API void shim_set_audio_enabled(shim_t *s, int on);

/* Memory, as the CPU sees it (current banks). */
SHIM_API uint8_t shim_read(shim_t *s, uint16_t addr);
SHIM_API void shim_write(shim_t *s, uint16_t addr, uint8_t value);
SHIM_API void shim_read_block(shim_t *s, uint16_t addr, uint8_t *out, size_t n);
/* Currently mapped ROMX bank. */
SHIM_API int shim_rom_bank(shim_t *s);

/* Link cable. */
SHIM_API void shim_link_plug(shim_t *s, int plugged);
SHIM_API int shim_link_plugged(shim_t *s);
SHIM_API int shim_link_stalled(shim_t *s);
/* Only put transfers this console clocks itself (internal clock) on the cable
 * while memory[addr] == value; otherwise they complete locally as if no cable
 * were plugged. The link session guest uses this so that only the session host
 * ever drives the clock while the connection is being set up. addr 0 = off. */
SHIM_API void shim_link_gate(shim_t *s, uint16_t addr, uint8_t value);
/* Block fast path. When the CPU enters exchange_bytes_addr
 * (Serial_ExchangeBytes) with the cable plugged and memory[status_addr]
 * (hSerialConnectionStatus) showing a connection, the whole block goes out as
 * one run of BLOCK records and the console waits for the peer's block, then
 * finishes as an ideal cable would (block_start in link_shim.c). ignoring_addr
 * is hSerialIgnoringInitialData. Both consoles must enable it; everything
 * else stays byte-by-byte lockstep. exchange_bytes_addr 0 turns it off. */
SHIM_API void shim_link_fast(shim_t *s, uint16_t exchange_bytes_addr, uint16_t status_addr, uint16_t ignoring_addr);
/* Blocks sent over the fast path so far. */
SHIM_API uint32_t shim_link_blocks(shim_t *s);
/* Nybble sync fast path: when the CPU enters sync_addr
 * (Serial_SyncAndExchangeNybble) with a connection and the 16-bit inactivity
 * counter at counter_addr (wUnknownSerialCounter) at zero, send
 * memory[send_addr] as one message, wait for the peer's, store its low nybble
 * at recv_addr and result_addr and return, as the sync loop would after
 * agreeing. With the counter running (the receptionist's timed sync) the
 * original loop runs byte by byte. Both consoles must enable it. */
SHIM_API void shim_link_fast_sync(shim_t *s, uint16_t sync_addr, uint16_t send_addr, uint16_t recv_addr,
                                  uint16_t result_addr, uint16_t counter_addr);
SHIM_API uint32_t shim_link_syncs(shim_t *s);
/* Pops one outgoing message. Returns 1 and fills kind/byte, or 0 if none. */
SHIM_API int shim_link_pop(shim_t *s, uint8_t *kind, uint8_t *byte);
/* Same, packed as (kind << 8) | byte, or -1 if none (handier from JS). */
SHIM_API int shim_link_pop_packed(shim_t *s);
/* Queues one incoming message. Returns 0, or -1 if the queue is full. */
SHIM_API int shim_link_push(shim_t *s, uint8_t kind, uint8_t byte);
/* Counters for tests and the UI. */
SHIM_API uint32_t shim_link_bytes_sent(shim_t *s);
SHIM_API uint32_t shim_link_bytes_received(shim_t *s);

/* PC hooks: fire when the instruction at addr is fetched. bank = -1 matches
 * any bank (use it for ROM0). If brk is set, shim_run_frame() returns
 * SHIM_HOOK right after that instruction has executed, so the page can act
 * on the machine state. Returns the hook id (>= 0) or -1. */
SHIM_API int shim_hook_add(shim_t *s, uint16_t addr, int bank, int brk);
SHIM_API void shim_hook_clear(shim_t *s);
/* Pops the next fired hook id, or -1. Non-break hooks queue too (bounded). */
SHIM_API int shim_hook_next(shim_t *s);
/* CPU registers for hook handlers: 0=AF 1=BC 2=DE 3=HL 4=SP 5=PC */
SHIM_API uint16_t shim_reg(shim_t *s, int which);
SHIM_API void shim_set_reg(shim_t *s, int which, uint16_t value);

#ifdef __cplusplus
}
#endif

#endif
