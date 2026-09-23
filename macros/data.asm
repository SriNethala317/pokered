; Value macros

DEF percent EQUS "* $ff / 100"

MACRO? bcd2
	dn ((\1) / 1000) % 10, ((\1) / 100) % 10
	dn ((\1) / 10) % 10, (\1) % 10
ENDM

MACRO? bcd3
	dn ((\1) / 100000) % 10, ((\1) / 10000) % 10
	dn ((\1) / 1000) % 10, ((\1) / 100) % 10
	dn ((\1) / 10) % 10, (\1) % 10
ENDM

; used in data/pokemon/base_stats/*.asm
MACRO? tmhm
	; initialize bytes to 0
	FOR n, (NUM_TM_HM + 7) / 8
		DEF _tm{d:n} = 0
	ENDR
	; set bits of bytes
	REPT _NARG
		ASSERT FATAL, STRFIND("\1", " ") == -1, "Invalid move: \1"
		IF DEF(\1_TMNUM)
			DEF n = (\1_TMNUM - 1) / 8
			DEF i = (\1_TMNUM - 1) % 8
			DEF _tm{d:n} |= 1 << i
		ELSE
			FAIL "\1 is not a TM or HM move"
		ENDC
		SHIFT
	ENDR
	; output bytes
	FOR n, (NUM_TM_HM + 7) / 8
		db _tm{d:n}
	ENDR
ENDM

; used in engine/battle/core.asm
MACRO? special_moves
	; initialize bytes to 0
	FOR n, (NUM_ATTACKS + 7) / 8
		DEF _sp{d:n} = 0
	ENDR
	; set bits of bytes
	REPT _NARG
		ASSERT FATAL, STRFIND("\1", " ") == -1, "Invalid move: \1"
		DEF n = ((\1) - 1) / 8
		DEF i = ((\1) - 1) % 8
		DEF _sp{d:n} |= 1 << i
		SHIFT
	ENDR
	; output bytes
	FOR n, (NUM_ATTACKS + 7) / 8
		db _sp{d:n}
	ENDR
ENDM

; used in data/pokemon/special_split.asm
; \1 = Generation 2 Special Attack, \2 = Generation 2 Special Defence
;
; Emits the two as factors in sixteenths of the species' stored Special stat,
; scaled so the pair averages 16. A species whose Generation 2 values match
; therefore comes out as 16 and 16, which leaves it exactly as it is today.
; Both halves round to nearest so the pair keeps its shape at small values.
MACRO? special_split
	db (32 * (\1) + ((\1) + (\2)) / 2) / ((\1) + (\2))
	db (32 * (\2) + ((\1) + (\2)) / 2) / ((\1) + (\2))
ENDM


; Constant data (db, dw, dl) macros

MACRO? dbw
	db \1
	dw \2
ENDM

MACRO? dwb
	dw \1
	db \2
ENDM

MACRO? dn ; nybbles
	REPT _NARG / 2
		db ((\1) << 4) | (\2)
		SHIFT 2
	ENDR
ENDM

MACRO? dc ; "crumbs"
	REPT _NARG / 4
		db ((\1) << 6) | ((\2) << 4) | ((\3) << 2) | (\4)
		SHIFT 4
	ENDR
ENDM

MACRO? bigdw ; big-endian word
	db HIGH(\1), LOW(\1)
ENDM

MACRO? dba ; dbw bank, address
	REPT _NARG
		dbw BANK(\1), \1
		SHIFT
	ENDR
ENDM

MACRO? dab ; dwb address, bank
	REPT _NARG
		dwb \1, BANK(\1)
		SHIFT
	ENDR
ENDM

MACRO? dname
	IF _NARG == 2
		DEF n = \2
	ELSE
		DEF n = NAME_LENGTH - 1
	ENDC
	ASSERT STRFIND(\1, "@") == -1, "String terminator \"@\" in name: \1"
	ASSERT CHARLEN(\1) <= n, "Name longer than {d:n} characters: \1"
	db \1
	ds n - CHARLEN(\1), '@'
ENDM
