; Bond field abilities: a close Pokemon can Cut, Surf, Strength, Flash or Fly
; without the HM, if its type suits the job (BondFieldMoves). The party menu
; lists them after the moves it really knows; each still needs the badge the
; HM always needed. See docs/resonance-design.md.

DEF FIELD_ABILITY_BOND EQU 120

; Called by GetMonFieldMoves once the known field moves are listed.
AddBondFieldMoves::
	ld a, [wWhichPokemon]
	ld hl, wPartyMon1Bond
	ld bc, PARTYMON_STRUCT_LENGTH
	call AddNTimes
	ld a, [hl]
	cp FIELD_ABILITY_BOND
	ret c
	ASSERT MON_TYPE1 == MON_BOND - 2
	ASSERT MON_TYPE2 == MON_BOND - 1
	dec hl
	ld a, [hld]
	ld e, a ; type 2
	ld d, [hl] ; type 1
	ld hl, BondFieldMoves
.entry
	ld a, [hli]
	cp -1
	ret z
	cp d
	jr z, .suits
	cp e
	jr z, .suits
	inc hl
	inc hl
	jr .entry
.suits
	ld a, [hli] ; the FieldMoveNames index
	ld c, a
	ld a, [hli] ; its leftmost tile
	ld b, a
	push hl
	call .add
	pop hl
	jr .entry

; add name index c, drawn from column b, unless it is listed or the list is full
.add
	ld hl, wFieldMoves
	ld a, [wNumFieldMoves]
	cp NUM_MOVES
	ret nc
	and a
	jr z, .append
	push de
	ld e, a
.alreadyListed
	ld a, [hli]
	cp c
	jr z, .listed
	dec e
	jr nz, .alreadyListed
	pop de
	jr .append
.listed
	pop de
	ret
.append
	ld a, [wNumFieldMoves]
	ld hl, wFieldMoves
	push de
	ld e, a
	ld d, 0
	add hl, de
	pop de
	ld [hl], c
	inc a
	ld [wNumFieldMoves], a
	ld a, [wFieldMovesLeftmostXCoord]
	cp b
	ret c
	ld a, b
	ld [wFieldMovesLeftmostXCoord], a
	ret

; type, FieldMoveNames index, leftmost tile (as in FieldMoveDisplayData)
BondFieldMoves:
	db GRASS,    1, $0C ; CUT
	db BUG,      1, $0C
	db WATER,    4, $0C ; SURF
	db FIGHTING, 5, $0A ; STRENGTH
	db ROCK,     5, $0A
	db GROUND,   5, $0A
	db ELECTRIC, 6, $0C ; FLASH
	db FLYING,   2, $0C ; FLY
	db -1 ; end
