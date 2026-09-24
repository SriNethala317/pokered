# Builds link_shim + the SameBoy core.
#   make native   -> ../build/native/liblinkshim.so (for test/netlink)
#   make wasm     -> ../build/core.js + ../build/core.wasm (needs emcc on PATH)
# Run ../fetch_core.sh first to fetch SameBoy at the pinned commit.

SAMEBOY ?= ../vendor/SameBoy
OUT ?= ../build
GEN := $(OUT)/gen

CORE_FILES := gb sgb apu memory mbc timing display camera sm83_cpu joypad save_state random rumble
CORE_SRC := $(addprefix $(SAMEBOY)/Core/,$(addsuffix .c,$(CORE_FILES)))

DEFS := -DGB_DISABLE_TIMEKEEPING -DGB_DISABLE_REWIND -DGB_DISABLE_DEBUGGER \
	-DGB_DISABLE_CHEATS -DGB_DISABLE_CHEAT_SEARCH -D_GNU_SOURCE \
	-DGB_VERSION='"resonance"' -DGB_COPYRIGHT_YEAR='"2026"'
WARN := -Wno-multichar -Wno-unused-result -Wno-missing-braces -Wno-int-in-bool-context \
	-Wno-unknown-warning-option -Wno-format-truncation -Wno-nonnull
CFLAGS ?= -O2
EMCC ?= emcc
ALL_CFLAGS := $(CFLAGS) -std=gnu11 $(DEFS) $(WARN) -I$(SAMEBOY) -I$(GEN)

EXPORTS := shim_create shim_destroy shim_load_rom shim_reset shim_sram_size shim_sram_save \
	shim_sram_load shim_sram_dirty shim_run_frame shim_frame_count shim_set_keys shim_framebuffer \
	shim_set_sample_rate shim_audio_read shim_set_audio_enabled shim_read shim_write \
	shim_read_block shim_rom_bank shim_link_plug shim_link_plugged shim_link_stalled \
	shim_link_pop shim_link_pop_packed shim_link_push shim_link_bytes_sent \
	shim_link_bytes_received shim_hook_add shim_hook_clear shim_hook_next shim_reg \
	shim_set_reg malloc free
comma := ,
empty :=
space := $(empty) $(empty)
EM_EXPORTS := [$(subst $(space),$(comma),$(foreach f,$(EXPORTS),'_$(f)'))]

.PHONY: native wasm clean
native: $(OUT)/native/liblinkshim.so
wasm: $(OUT)/core.js

$(GEN)/dmg_boot.h: $(SAMEBOY)/build/bin/BootROMs/dmg_boot.bin
	@mkdir -p $(GEN)
	python3 -c "import sys; d=open(sys.argv[1],'rb').read(); \
print('static const unsigned char dmg_boot[%d] = {%s};' % (len(d), ','.join(str(b) for b in d)))" $< > $@

$(OUT)/native/liblinkshim.so: link_shim.c link_shim.h $(GEN)/dmg_boot.h $(CORE_SRC)
	@mkdir -p $(dir $@)
	$(CC) $(ALL_CFLAGS) -fPIC -shared -DGB_INTERNAL -o $@ link_shim.c $(CORE_SRC) -lm

# The core is compiled with GB_INTERNAL, as SameBoy's own Makefile does.
$(OUT)/obj/%.o: $(SAMEBOY)/Core/%.c
	@mkdir -p $(dir $@)
	$(EMCC) $(ALL_CFLAGS) -O3 -DGB_INTERNAL -c $< -o $@

$(OUT)/obj/link_shim.o: link_shim.c link_shim.h $(GEN)/dmg_boot.h
	@mkdir -p $(dir $@)
	$(EMCC) $(ALL_CFLAGS) -O3 -c $< -o $@

$(OUT)/core.js: $(OUT)/obj/link_shim.o $(addprefix $(OUT)/obj/,$(addsuffix .o,$(CORE_FILES)))
	$(EMCC) -O3 -o $@ $^ \
		-sMODULARIZE=1 -sEXPORT_NAME=createCore -sEXPORT_ES6=1 -sENVIRONMENT=web,worker,node \
		-sALLOW_MEMORY_GROWTH=1 -sFILESYSTEM=0 \
		-sEXPORTED_FUNCTIONS="$(EM_EXPORTS)" \
		-sEXPORTED_RUNTIME_METHODS="['HEAPU8','HEAP16','HEAPU32']"

clean:
	rm -rf $(OUT)/native $(OUT)/obj $(OUT)/gen $(OUT)/core.js $(OUT)/core.wasm
