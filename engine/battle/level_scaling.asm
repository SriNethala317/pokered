; Level scaling: gym leaders, their gyms and the rival follow your badges.
;
; Kanto opens up after Brock, so gyms 2 to 7 can come in any order. Each of
; those leaders keeps the place they had in the original order (their
; "designed" badge count) and their team is shifted by the difference between
; the typical ace level at your badge count and at theirs (TrainerAceLevels),
; so the shape of the team stays and only its level moves. Sabrina fought with
; two badges drops from an ace of 43 to 24; Misty fought with six rises from 21
; to 47. Gym trainers follow their gym, and the rival's mid-game battles follow
; which one it is. Everyone else is left as they were.

DEF MIN_SCALED_LEVEL EQU 2

; Called by ReadTrainer with a team member's level in wCurEnemyLevel.
ScaleTrainerLevel::
	call GetDesignedBadges
	ret nc
	push af ; the designed badge count; CountSetBits uses c
	ld hl, wObtainedBadges
	ld b, 1
	call CountSetBits
	pop bc
	ld c, b ; c = the designed badge count
	cp c
	ret z ; fought on schedule
	; e = the ace level at your badges, d = at theirs
	ld hl, TrainerAceLevels
	ld e, a
	ld d, 0
	add hl, de
	ld e, [hl]
	ld hl, TrainerAceLevels
	ld b, 0
	add hl, bc
	ld d, [hl]
	ld a, [wCurEnemyLevel]
	add e
	jr c, .tooHigh
	sub d
	jr c, .tooLow
	cp MIN_SCALED_LEVEL
	jr c, .tooLow
	cp MAX_LEVEL + 1
	jr c, .store
.tooHigh
	ld a, MAX_LEVEL
	jr .store
.tooLow
	ld a, MIN_SCALED_LEVEL
.store
	ld [wCurEnemyLevel], a
	ret

; a = the badge count this trainer was designed for, and carry, if they scale
GetDesignedBadges:
	ld a, [wTrainerClass]
	ld hl, ScaledLeaders
	ld de, 2
	call IsInArray
	jr c, .fromTable
	ld a, [wTrainerClass]
	cp RIVAL2
	jr z, .rival
	; anyone else in a gym trains there
	ld a, [wCurMap]
	ld hl, ScaledGyms
	ld de, 2
	call IsInArray
	ret nc
.fromTable
	inc hl
	ld a, [hl]
	scf
	ret
.rival
	; SS Anne, Pokemon Tower, Silph Co. and Route 22, three starters each
	ld a, [wTrainerNo]
	dec a
	ld b, -1
.third
	inc b
	sub 3
	jr nc, .third
	ld hl, RivalDesignedBadges
	ld c, b
	ld b, 0
	add hl, bc
	ld a, [hl]
	scf
	ret

; the leaders who can be fought in any order, and the badges they expect
ScaledLeaders:
	db MISTY,    1
	db LT_SURGE, 2
	db ERIKA,    3
	db KOGA,     4
	db SABRINA,  5
	db BLAINE,   6
	db -1 ; end

ScaledGyms:
	db CERULEAN_GYM,  1
	db VERMILION_GYM, 2
	db CELADON_GYM,   3
	db FUCHSIA_GYM,   4
	db SAFFRON_GYM,   5
	db CINNABAR_GYM,  6
	db -1 ; end

RivalDesignedBadges:
	db 2 ; SS Anne
	db 3 ; Pokemon Tower
	db 5 ; Silph Co.
	db 8 ; Route 22, before the League

; the level of a leader's ace at each badge count, from the original leaders
TrainerAceLevels:
	table_width 1
	db 14 ; 0: Brock
	db 21 ; 1: Misty
	db 24 ; 2: Lt. Surge
	db 29 ; 3: Erika
	db 43 ; 4: Koga
	db 43 ; 5: Sabrina
	db 47 ; 6: Blaine
	db 50 ; 7: Giovanni
	db 55 ; 8: the League
	assert_table_length NUM_BADGES + 1
