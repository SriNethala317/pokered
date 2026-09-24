; Frenzy bosses: Pokemon the Tower's broadcast has driven frantic (docs/story.md).
;
; Talking to one starts a Frenzy on the spot: it thrashes, and a Dodge Phase
; arena opens over the map. Each round you get through untouched calms it a
; little (FRENZY_GAUGE rounds calm it for good); after each round you can keep
; calming it or fight it in the usual battle. Once calm, it can join you, or
; you leave it be and it gives you something. Either way the road is clear, and
; calming it sets its own event so people can remember which you chose. The
; Poke Flute still wakes it straight into the battle. Getting hit costs the
; trainer HP bar; running it dry sends you away to try again.
;
; The phase borrows battle-only RAM (the Dodge Phase's position and timers,
; wTrainerPain). Outside battle those bytes share a union with overworld
; scripting buffers, which is safe here: a talk script runs, nothing else moves.

DEF FRENZY_GAUGE      EQU 3
DEF FRENZY_JOIN_LEVEL EQU 30
DEF FRENZY_GIFT       EQU RARE_CANDY

	const_def
	const FRENZY_RETREAT ; you were worn out
	const FRENZY_FIGHT   ; you chose to fight it
	const FRENZY_CALMED  ; it is calm

Route12Frenzy::
	call RunFrenzy
	cp FRENZY_FIGHT
	jr z, .fight
	cp FRENZY_CALMED
	ret nz
	SetEvent EVENT_BEAT_ROUTE12_SNORLAX
	SetEvent EVENT_CALMED_ROUTE12_SNORLAX
	ld a, TOGGLE_ROUTE_12_SNORLAX
	ld [wToggleableObjectIndex], a
	predef HideObject
	jp FrenzyReward
.fight
	; Route 12's map script starts the usual battle, as the Poke Flute does
	SetEvent EVENT_FIGHT_ROUTE12_SNORLAX
	ret

Route16Frenzy::
	call RunFrenzy
	cp FRENZY_FIGHT
	jr z, .fight
	cp FRENZY_CALMED
	ret nz
	SetEvent EVENT_BEAT_ROUTE16_SNORLAX
	SetEvent EVENT_CALMED_ROUTE16_SNORLAX
	ld a, TOGGLE_ROUTE_16_SNORLAX
	ld [wToggleableObjectIndex], a
	predef HideObject
	jp FrenzyReward
.fight
	SetEvent EVENT_FIGHT_ROUTE16_SNORLAX
	ret

; a = FRENZY_RETREAT, FRENZY_FIGHT or FRENZY_CALMED
RunFrenzy:
	xor a
	ld [wTrainerPain], a
	ld hl, FrenzyStartsText
	call PrintText
	ld b, FRENZY_GAUGE
.round
	push bc
	call FrenzyDodge
	pop bc
	ld a, [wTrainerPain]
	cp TRAINER_MAX_HP
	jr nc, .exhausted
	ld a, [wDodgeHits]
	and a
	jr nz, .raging
	dec b
	jr z, .calmed
	ld hl, FrenzyCalmerText
	jr .ask
.raging
	ld hl, FrenzyRagingText
.ask
	push bc
	call PrintText
	ld hl, FrenzyKeepCalmingText
	call PrintText
	call YesNoChoice
	pop bc
	ld a, [wCurrentMenuItem]
	and a
	jr z, .round
	ld a, FRENZY_FIGHT
	ret
.exhausted
	ld hl, FrenzyExhaustedText
	call PrintText
	ld a, FRENZY_RETREAT
	ret
.calmed
	ld hl, FrenzyCalmedText
	call PrintText
	ld a, FRENZY_CALMED
	ret

; one round: the arena over the map, with the map's sprites put away
; In the overworld the map is the background and wTileMap is shown through the
; window, which is only up while text is: bring it up for the arena.
FrenzyDodge:
	ld a, $ff
	ld [wUpdateSpritesEnabled], a
	call ClearSprites
	ldh a, [hWY]
	push af
	xor a
	ldh [hWY], a
	call ClearScreen ; a plain field around the arena; the map below is untouched
	call LoadFontTilePatterns ; the letters share tiles with the map's sprites
	ld a, DODGE_COLUMN ; body slams, warned twice
	call DodgePhaseWithPattern
	pop af
	ldh [hWY], a
	ld a, 1
	ld [wUpdateSpritesEnabled], a
	jp UpdateSprites

; A calmed Pokemon can come with you, or give you something and stay.
FrenzyReward:
	ld hl, FrenzyJoinText
	call PrintText
	call YesNoChoice
	ld a, [wCurrentMenuItem]
	and a
	jr nz, .gift
	lb bc, SNORLAX, FRENZY_JOIN_LEVEL
	jp GivePokemon
.gift
	lb bc, FRENZY_GIFT, 1
	call GiveItem
	ld hl, FrenzyGiftText
	jp PrintText

FrenzyStartsText:
	text "The #MON is"
	line "thrashing about!"
	cont "Calm it down!"
	prompt

FrenzyCalmerText:
	text "It's calming"
	line "down a little..."
	prompt

FrenzyRagingText:
	text "It's still"
	line "raging!"
	prompt

FrenzyKeepCalmingText:
	text "Keep trying to"
	line "calm it?"
	done

FrenzyExhaustedText:
	text "<PLAYER> is worn"
	line "out, and backs"
	cont "away for now..."
	prompt

FrenzyCalmedText:
	text "The #MON calmed"
	line "down! The signal"
	cont "lost its grip."
	prompt

FrenzyJoinText:
	text "It wants to come"
	line "with you! Take"
	cont "it along?"
	done

FrenzyGiftText:
	text "It left a gift"
	line "and wandered off!"
	prompt
