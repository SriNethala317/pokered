/* link_shim.c: see link_shim.h for the API and the link cable model. */
#include "link_shim.h"

#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

#include "Core/gb.h"

#include "dmg_boot.h" /* generated: static const unsigned char dmg_boot[256] */

#define LINK_QUEUE 1024  /* messages; a trade is ~650 bytes each way */
#define HOOK_MAX 64
#define HOOK_QUEUE 64
#define AUDIO_FRAMES 16384 /* stereo frames buffered, ~0.34 s at 48 kHz */
/* A frame is 70224 dots = 140448 ticks of SameBoy's 8 MHz clock. If the LCD is
 * off and no artificial vblank arrives, stop anyway after a few frames' worth. */
#define FRAME_TICK_CAP (140448 * 4)

typedef struct {
    uint8_t kind, byte;
} link_msg_t;

typedef struct {
    link_msg_t buf[LINK_QUEUE];
    unsigned head, tail; /* head: next to pop; tail: next free */
} link_queue_t;

typedef struct {
    uint16_t addr;
    int16_t bank;
    uint8_t brk;
} hook_t;

struct shim {
    GB_gameboy_t *gb;
    uint8_t *rom;
    size_t rom_size;
    uint32_t pixels[SHIM_WIDTH * SHIM_HEIGHT];
    bool vblank;
    uint64_t frames;
    uint8_t keys;

    /* audio ring */
    int16_t audio[AUDIO_FRAMES * 2];
    unsigned audio_head, audio_tail;
    bool audio_on;

    /* link */
    bool plugged;
    bool stalled;         /* waiting for REPLY to our XFER */
    bool reply_ready;     /* REPLY arrived for the transfer in flight */
    uint8_t reply;
    bool in_transfer;     /* our internal-clock transfer is clocking */
    bool expect_next_bit; /* the next bit_start continues the same byte */
    unsigned bits;
    link_queue_t out, in;
    uint32_t sent, received;

    /* hooks */
    hook_t hooks[HOOK_MAX];
    int nhooks;
    uint8_t hook_map[0x10000 / 8];
    int hook_fired[HOOK_QUEUE];
    unsigned hf_head, hf_tail;
    bool hook_break;

    bool sram_dirty;
};

/* ---------- queues ---------- */

static bool q_push(link_queue_t *q, uint8_t kind, uint8_t byte)
{
    unsigned next = (q->tail + 1) % LINK_QUEUE;
    if (next == q->head) return false;
    q->buf[q->tail].kind = kind;
    q->buf[q->tail].byte = byte;
    q->tail = next;
    return true;
}

static bool q_pop(link_queue_t *q, link_msg_t *m)
{
    if (q->head == q->tail) return false;
    *m = q->buf[q->head];
    q->head = (q->head + 1) % LINK_QUEUE;
    return true;
}

/* ---------- SameBoy callbacks ---------- */

static shim_t *S(GB_gameboy_t *gb) { return (shim_t *)GB_get_user_data(gb); }

static void on_vblank(GB_gameboy_t *gb, GB_vblank_type_t type)
{
    (void)type;
    S(gb)->vblank = true;
}

static uint32_t on_rgb(GB_gameboy_t *gb, uint8_t r, uint8_t g, uint8_t b)
{
    (void)gb;
    /* little-endian RGBA in memory */
    return (uint32_t)r | ((uint32_t)g << 8) | ((uint32_t)b << 16) | 0xFF000000u;
}

static void on_sample(GB_gameboy_t *gb, GB_sample_t *sample)
{
    shim_t *s = S(gb);
    if (!s->audio_on) return;
    unsigned next = (s->audio_tail + 1) % AUDIO_FRAMES;
    if (next == s->audio_head) return; /* full: drop */
    s->audio[s->audio_tail * 2] = sample->left;
    s->audio[s->audio_tail * 2 + 1] = sample->right;
    s->audio_tail = next;
}

static uint8_t io_read(shim_t *s, uint8_t reg)
{
    uint8_t *io = GB_get_direct_access(s->gb, GB_DIRECT_ACCESS_IO, NULL, NULL);
    return io[reg];
}

static void io_write_raw(shim_t *s, uint8_t reg, uint8_t v)
{
    uint8_t *io = GB_get_direct_access(s->gb, GB_DIRECT_ACCESS_IO, NULL, NULL);
    io[reg] = v;
}

#define IO_SB 0x01
#define IO_SC 0x02

/* Called when this console clocks a bit out on the internal clock. The first
 * call of a byte comes from the SC write itself, before any bit has moved. */
static void on_bit_start(GB_gameboy_t *gb, bool bit)
{
    (void)bit;
    shim_t *s = S(gb);
    if (s->expect_next_bit) {
        s->expect_next_bit = false;
        return;
    }
    /* a new byte (or the game restarted one mid-flight) */
    s->in_transfer = true;
    s->bits = 0;
    if (!s->plugged) {
        s->stalled = false;
        return;
    }
    uint8_t out = io_read(s, IO_SB);
    s->reply_ready = false;
    s->stalled = true;
    q_push(&s->out, SHIM_LINK_XFER, out);
    s->sent++;
}

/* Returns the bit shifted in. We only care about the byte as a whole: on the
 * eighth bit, overwrite SB with the peer's byte. */
static bool on_bit_end(GB_gameboy_t *gb)
{
    shim_t *s = S(gb);
    if (!s->in_transfer) return true;
    s->bits++;
    if (s->bits < 8) {
        s->expect_next_bit = true;
        return true;
    }
    s->in_transfer = false;
    s->expect_next_bit = false;
    if (!s->plugged || !s->reply_ready) return true; /* no cable: reads $FF */
    s->reply_ready = false;
    /* SB has already been shifted left; replace it so the result is exact */
    io_write_raw(s, IO_SB, s->reply & 0xFE);
    return s->reply & 1;
}

static void on_exec(GB_gameboy_t *gb, uint16_t addr, uint8_t opcode)
{
    (void)opcode;
    shim_t *s = S(gb);
    if (!(s->hook_map[addr >> 3] & (1 << (addr & 7)))) return;
    int bank = -1;
    if (addr >= 0x4000 && addr < 0x8000) {
        uint16_t b;
        GB_get_direct_access(gb, GB_DIRECT_ACCESS_ROM, NULL, &b);
        bank = b;
    }
    for (int i = 0; i < s->nhooks; i++) {
        hook_t *h = &s->hooks[i];
        if (h->addr != addr) continue;
        if (h->bank >= 0 && bank >= 0 && h->bank != bank) continue;
        unsigned next = (s->hf_tail + 1) % HOOK_QUEUE;
        if (next != s->hf_head) {
            s->hook_fired[s->hf_tail] = i;
            s->hf_tail = next;
        }
        if (h->brk) s->hook_break = true;
    }
}

/* ---------- lifecycle ---------- */

SHIM_API shim_t *shim_create(void)
{
    shim_t *s = calloc(1, sizeof(*s));
    if (!s) return NULL;
    s->gb = GB_alloc();
    GB_init(s->gb, GB_MODEL_DMG_B);
    GB_set_user_data(s->gb, s);
    GB_load_boot_rom_from_buffer(s->gb, dmg_boot, sizeof(dmg_boot));
    GB_set_pixels_output(s->gb, s->pixels);
    GB_set_rgb_encode_callback(s->gb, on_rgb);
    GB_set_vblank_callback(s->gb, on_vblank);
    GB_apu_set_sample_callback(s->gb, on_sample);
    GB_set_sample_rate(s->gb, 48000);
    GB_set_highpass_filter_mode(s->gb, GB_HIGHPASS_ACCURATE);
    GB_set_serial_transfer_bit_start_callback(s->gb, on_bit_start);
    GB_set_serial_transfer_bit_end_callback(s->gb, on_bit_end);
    GB_set_execution_callback(s->gb, on_exec);
    GB_set_palette(s->gb, &GB_PALETTE_GREY);
    GB_set_color_correction_mode(s->gb, GB_COLOR_CORRECTION_DISABLED);
    s->audio_on = true;
    return s;
}

SHIM_API void shim_destroy(shim_t *s)
{
    if (!s) return;
    GB_free(s->gb);
    GB_dealloc(s->gb);
    free(s->rom);
    free(s);
}

static void reset_link_state(shim_t *s)
{
    s->stalled = s->reply_ready = s->in_transfer = s->expect_next_bit = false;
    s->bits = 0;
    s->out.head = s->out.tail = 0;
    s->in.head = s->in.tail = 0;
}

SHIM_API void shim_reset(shim_t *s)
{
    GB_reset(s->gb);
    reset_link_state(s);
    s->hook_break = false;
    s->hf_head = s->hf_tail = 0;
}

SHIM_API int shim_load_rom(shim_t *s, const uint8_t *rom, size_t size)
{
    if (size < 0x8000 || size > 8 * 1024 * 1024) return -1;
    free(s->rom);
    s->rom = malloc(size);
    if (!s->rom) return -1;
    memcpy(s->rom, rom, size);
    s->rom_size = size;
    GB_load_rom_from_buffer(s->gb, s->rom, size);
    shim_reset(s);
    return 0;
}

/* ---------- SRAM ---------- */

SHIM_API int shim_sram_size(shim_t *s) { return GB_save_battery_size(s->gb); }

SHIM_API int shim_sram_save(shim_t *s, uint8_t *out, size_t size)
{
    GB_clear_battery_dirty(s->gb);
    return GB_save_battery_to_buffer(s->gb, out, size);
}

SHIM_API void shim_sram_load(shim_t *s, const uint8_t *in, size_t size)
{
    GB_load_battery_from_buffer(s->gb, in, size);
    GB_clear_battery_dirty(s->gb);
}

SHIM_API int shim_sram_dirty(shim_t *s) { return GB_get_battery_dirty(s->gb); }

/* ---------- link ---------- */

/* Apply one message from the peer at an instruction boundary. */
static void link_apply(shim_t *s, link_msg_t m)
{
    if (m.kind == SHIM_LINK_REPLY) {
        if (s->stalled) {
            s->reply = m.byte;
            s->reply_ready = true;
            s->stalled = false;
            s->received++;
        }
        return; /* a stray reply (e.g. after unplugging) is dropped */
    }
    if (m.kind != SHIM_LINK_XFER) return;
    s->received++;
    uint8_t sc = io_read(s, IO_SC);
    uint8_t answer;
    if (!s->plugged) {
        answer = 0xFF;
    }
    else if ((sc & 0x81) == 0x80) {
        /* armed on the external clock: take the byte, give back SB */
        answer = io_read(s, IO_SB);
        for (int i = 7; i >= 0; i--) {
            GB_serial_set_data_bit(s->gb, (m.byte >> i) & 1);
        }
    }
    else if (sc & 0x80) {
        answer = 0xFF; /* we are clocking too: the line reads high */
    }
    else {
        answer = 0x00; /* serial off: SameBoy's disabled port reads 0 */
    }
    q_push(&s->out, SHIM_LINK_REPLY, answer);
}

static void link_drain(shim_t *s)
{
    link_msg_t m;
    /* While stalled, stop right after our REPLY so the CPU runs before the
     * next XFER is applied (XFERs that precede it are still answered). */
    while (q_pop(&s->in, &m)) {
        link_apply(s, m);
        if (m.kind == SHIM_LINK_REPLY) break;
        if (m.kind == SHIM_LINK_XFER && !s->stalled) break;
    }
}

SHIM_API void shim_link_plug(shim_t *s, int plugged)
{
    s->plugged = plugged != 0;
    if (!s->plugged) {
        /* A transfer we were waiting on completes as if the cable was pulled */
        s->stalled = false;
        s->reply_ready = false;
        s->in.head = s->in.tail = 0;
    }
}

SHIM_API int shim_link_plugged(shim_t *s) { return s->plugged; }
SHIM_API int shim_link_stalled(shim_t *s) { return s->stalled; }

SHIM_API int shim_link_pop(shim_t *s, uint8_t *kind, uint8_t *byte)
{
    link_msg_t m;
    if (!q_pop(&s->out, &m)) return 0;
    *kind = m.kind;
    *byte = m.byte;
    return 1;
}

SHIM_API int shim_link_pop_packed(shim_t *s)
{
    link_msg_t m;
    if (!q_pop(&s->out, &m)) return -1;
    return (m.kind << 8) | m.byte;
}

SHIM_API int shim_link_push(shim_t *s, uint8_t kind, uint8_t byte)
{
    if (kind != SHIM_LINK_XFER && kind != SHIM_LINK_REPLY) return -1;
    return q_push(&s->in, kind, byte) ? 0 : -1;
}

SHIM_API uint32_t shim_link_bytes_sent(shim_t *s) { return s->sent; }
SHIM_API uint32_t shim_link_bytes_received(shim_t *s) { return s->received; }

/* ---------- emulation ---------- */

SHIM_API int shim_run_frame(shim_t *s)
{
    unsigned ticks = 0;
    s->vblank = false;
    for (;;) {
        if (s->in.head != s->in.tail) link_drain(s);
        if (s->stalled) return SHIM_STALLED;
        if (s->hook_break) {
            s->hook_break = false;
            return SHIM_HOOK;
        }
        ticks += GB_run(s->gb);
        if (s->vblank || ticks >= FRAME_TICK_CAP) break;
    }
    s->frames++;
    if (GB_get_battery_dirty(s->gb)) s->sram_dirty = true;
    return SHIM_FRAME;
}

SHIM_API uint64_t shim_frame_count(shim_t *s) { return s->frames; }

SHIM_API void shim_set_keys(shim_t *s, uint8_t keys)
{
    static const GB_key_t map[8] = {GB_KEY_A,     GB_KEY_B,    GB_KEY_SELECT, GB_KEY_START,
                                    GB_KEY_RIGHT, GB_KEY_LEFT, GB_KEY_UP,     GB_KEY_DOWN};
    s->keys = keys;
    for (int i = 0; i < 8; i++) GB_set_key_state(s->gb, map[i], (keys >> i) & 1);
}

SHIM_API uint8_t *shim_framebuffer(shim_t *s) { return (uint8_t *)s->pixels; }

SHIM_API void shim_set_sample_rate(shim_t *s, unsigned rate)
{
    GB_set_sample_rate(s->gb, rate);
    s->audio_head = s->audio_tail = 0;
}

SHIM_API void shim_set_audio_enabled(shim_t *s, int on)
{
    s->audio_on = on != 0;
    if (!on) s->audio_head = s->audio_tail = 0;
}

SHIM_API int shim_audio_read(shim_t *s, int16_t *out, int max_frames)
{
    int n = 0;
    while (n < max_frames && s->audio_head != s->audio_tail) {
        out[n * 2] = s->audio[s->audio_head * 2];
        out[n * 2 + 1] = s->audio[s->audio_head * 2 + 1];
        s->audio_head = (s->audio_head + 1) % AUDIO_FRAMES;
        n++;
    }
    return n;
}

/* ---------- memory ---------- */

SHIM_API uint8_t shim_read(shim_t *s, uint16_t addr) { return GB_safe_read_memory(s->gb, addr); }

SHIM_API void shim_write(shim_t *s, uint16_t addr, uint8_t value) { GB_write_memory(s->gb, addr, value); }

SHIM_API void shim_read_block(shim_t *s, uint16_t addr, uint8_t *out, size_t n)
{
    for (size_t i = 0; i < n; i++) out[i] = GB_safe_read_memory(s->gb, (uint16_t)(addr + i));
}

SHIM_API int shim_rom_bank(shim_t *s)
{
    uint16_t b;
    GB_get_direct_access(s->gb, GB_DIRECT_ACCESS_ROM, NULL, &b);
    return b;
}

/* ---------- hooks ---------- */

SHIM_API int shim_hook_add(shim_t *s, uint16_t addr, int bank, int brk)
{
    if (s->nhooks >= HOOK_MAX) return -1;
    hook_t *h = &s->hooks[s->nhooks];
    h->addr = addr;
    h->bank = (int16_t)bank;
    h->brk = brk != 0;
    s->hook_map[addr >> 3] |= 1 << (addr & 7);
    return s->nhooks++;
}

SHIM_API void shim_hook_clear(shim_t *s)
{
    s->nhooks = 0;
    memset(s->hook_map, 0, sizeof(s->hook_map));
    s->hf_head = s->hf_tail = 0;
    s->hook_break = false;
}

SHIM_API int shim_hook_next(shim_t *s)
{
    if (s->hf_head == s->hf_tail) return -1;
    int id = s->hook_fired[s->hf_head];
    s->hf_head = (s->hf_head + 1) % HOOK_QUEUE;
    return id;
}

SHIM_API uint16_t shim_reg(shim_t *s, int which)
{
    GB_registers_t *r = GB_get_registers(s->gb);
    switch (which) {
        case 0: return r->af;
        case 1: return r->bc;
        case 2: return r->de;
        case 3: return r->hl;
        case 4: return r->sp;
        case 5: return r->pc;
    }
    return 0;
}

SHIM_API void shim_set_reg(shim_t *s, int which, uint16_t value)
{
    GB_registers_t *r = GB_get_registers(s->gb);
    switch (which) {
        case 0: r->af = value & 0xFFF0; break;
        case 1: r->bc = value; break;
        case 2: r->de = value; break;
        case 3: r->hl = value; break;
        case 4: r->sp = value; break;
        case 5: r->pc = value; break;
    }
}
