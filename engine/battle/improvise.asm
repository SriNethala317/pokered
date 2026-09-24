; Improvise: use a move on the arena instead of the opponent.
;
; Press START instead of A on a move in the move menu. The move is spent (its
; PP too) but deals no damage: it leaves the Field State that goes with its
; type, wherever the battle is, so a Water Gun soaks the ground, a Rock Throw
; brings down cover, and a Thunderbolt charges the air. It needs a Bond of at
; least IMPROVISE_MIN_BOND with the Pokemon out, and it can be used once every
; IMPROVISE_COOLDOWN turns. A resonant Bond makes the state last longer.
; Nothing prints: an IMPROV! badge shows and the field label changes.
; See docs/field-states-design.md.

DEF IMPROVISE_MIN_BOND   EQU 100
DEF IMPROVISE_COOLDOWN   EQU 3  ; turns before the next Improvise
DEF IMPROVISE_BOND_TURNS EQU 2  ; extra turns with a resonant Bond
DEF IMPROVISE_CHOSEN     EQU 7  ; wImprovise: this turn's move is improvised
DEF IMPROVISE_WAIT_MASK  EQU %11 ; wImprovise: turns until the next one

; Called by the move menu when START picks a move. Carry if it may be
; improvised, and then it is; otherwise a buzz, and the menu stays.
TryImprovise::
	ld a, [wLinkState]
	cp LINK_STATE_BATTLING
	jr z, .no
	ld a, [wBattleType]
	and a
	jr nz, .no
	ld a, [wImprovise]
	and IMPROVISE_WAIT_MASK
	jr nz, .no
	call GetBattleMonBond
	cp IMPROVISE_MIN_BOND
	jr c, .no
	ld hl, wImprovise
	set IMPROVISE_CHOSEN, [hl]
	scf
	ret
.no
	ld a, SFX_DENIED
	call PlaySound
	and a
	ret

; Called at the start of the player's move. Carry if the move was improvised,
; and the rest of the move is skipped.
ImproviseMove::
	ld hl, wImprovise
	bit IMPROVISE_CHOSEN, [hl]
	ret z ; and carry is clear
	res IMPROVISE_CHOSEN, [hl]
	ld a, [hl]
	or IMPROVISE_COOLDOWN
	ld [hl], a
	; the move is spent as if it had been used
	ld de, wPlayerSelectedMove
	ld hl, DecrementPP
	ld b, BANK(DecrementPP)
	call Bankswitch
	; the Field State that goes with the move's type
	ld a, [wPlayerMoveType]
	ld hl, ImproviseStates
	ld e, a
	ld d, 0
	add hl, de
	ld a, [hl]
	ld [wFieldState], a
	cp FIELD_RUBBLE
	jr nz, .notCover
	xor a ; cover for the player's side
	ld [wFieldOwner], a
.notCover
	call GetFieldRamp
	inc hl
	inc hl
	ld a, [hl] ; FIELD_RAMP_TURNS
	push af
	call GetBattleMonBond ; clobbers bc
	pop bc ; b = the turns
	cp BOND_RESONANT
	jr c, .gotTurns
	ld a, b
	add IMPROVISE_BOND_TURNS
	ld b, a
.gotTurns
	ld a, b
	ld [wFieldTurns], a
	call DrawFieldLabel
	ld a, SFX_PRESS_AB
	call PlaySound
	ld a, ACTION_BADGE_IMPROVISE
	call ShowActionBadge
	scf
	ret

; Called with the Field States each turn: the wait until the next Improvise
; runs down, and an Improvise that never happened (the Pokemon could not move)
; is forgotten.
ImproviseNewTurn:
	ld hl, wImprovise
	res IMPROVISE_CHOSEN, [hl]
	ld a, [hl]
	and IMPROVISE_WAIT_MASK
	ret z
	dec [hl]
	ret

; the Field State an improvised move of each type leaves
ImproviseStates:
	table_width 1
	db FIELD_RUBBLE     ; NORMAL: smash the ground into cover
	db FIELD_RUBBLE     ; FIGHTING
	db FIELD_SANDSTORM  ; FLYING: whip up dust
	db FIELD_BLACKOUT   ; POISON: a cloud of smog
	db FIELD_TUNNELS    ; GROUND: dig in
	db FIELD_RUBBLE     ; ROCK: bring down cover
	db FIELD_SANDSTORM  ; BIRD
	db FIELD_SANDSTORM  ; BUG: a swarm kicks up dust
	db FIELD_BLACKOUT   ; GHOST: put out the light
	ds UNUSED_TYPES_END - UNUSED_TYPES, FIELD_RUBBLE
	db FIELD_BURNING    ; FIRE: set the ground alight
	db FIELD_SOAKED     ; WATER: soak it
	db FIELD_RUBBLE     ; GRASS: vines to swing clear on
	db FIELD_OVERCHARGE ; ELECTRIC: charge the air
	db FIELD_BLACKOUT   ; PSYCHIC_TYPE: bend the light
	db FIELD_FROZEN     ; ICE: freeze the ground
	db FIELD_OVERCHARGE ; DRAGON
	assert_table_length NUM_TYPES
