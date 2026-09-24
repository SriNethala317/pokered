; The Trainer Dodge Phase: on a boss's big attack, you dodge in person.
;
; The first damaging attack of each of a boss's Pokemon opens a small arena
; over the battle screen for a couple of seconds. You are the ♂ and move it a
; tile at a time with the D-pad; the boss's pattern throws things at you. Each
; hit costs the trainer HP bar that Resonance uses (wTrainerPain), and running
; it dry breaks Resonance and costs your next turn. Getting through untouched
; halves the attack (DODGED!) and fills the Resonance meter fast.
;
; The arena is drawn over the battle screen in the tilemap only (the screen is
; saved to buffer 2 and put back), and everything in it is a tile: the state
; lives in the tilemap itself, so the phase needs no RAM beyond the position.
; It stands in for the attack's action command, and is capped at DODGE_FRAMES.
; Brock's falling rocks are the first pattern. See docs/dodge-phase-design.md.

DEF DODGE_FRAMES     EQU 150 ; the phase itself, two and a half seconds
DEF DODGE_ARENA_X    EQU 5   ; the arena's inside, over the middle of the screen
DEF DODGE_ARENA_Y    EQU 4
DEF DODGE_ARENA_W    EQU 10
DEF DODGE_ARENA_H    EQU 8
DEF DODGE_HIT_PAIN   EQU 6   ; of TRAINER_MAX_HP: four hits run the bar dry
DEF DODGE_GRACE      EQU 30  ; frames after a hit when nothing else can
DEF DODGE_HOLD_EVERY EQU 4   ; frames between steps while a direction is held
DEF DODGE_METER_BONUS EQU 2  ; on top of the 1 a BRACED already gives

DEF DODGE_PLAYER EQU '♂'
DEF DODGE_ROCK   EQU 'O'
DEF DODGE_WARN   EQU '▼' ; where a rock is about to fall

; The timers borrow action command bytes, which sit idle while the phase stands
; in for the window (DodgePhase sets wActionCommandState to idle first).
DEF wDodgeFallTimer  EQUS "wActionCommandTimer"
DEF wDodgeSpawnTimer EQUS "wActionCommandFrame"
DEF wDodgeGrace      EQUS "wActionCommandBadgeTimer"

; a row of DodgeRamp
	rsreset
DEF DODGE_RAMP_FALL  rb ; frames per row a rock falls
DEF DODGE_RAMP_SPAWN rb ; frames between new rocks
DEF DODGE_RAMP_WIDTH EQU _RS

; Called by ArmActionCommand on the enemy's damaging attack, once the move is
; known to hit. Carry if a Dodge Phase ran and stands in for the window.
TryDodgePhase:
	ldh a, [hWhoseTurn]
	and a
	ret z ; only their attacks
	ld a, [wIsInBattle]
	cp 2
	jr nz, .no ; trainers only
	ld a, [wTrainerClass]
	ld hl, DodgeBosses
	ld de, 1
	call IsInArray
	jr nc, .no
	; the first damaging attack of each of the boss's Pokemon
	ld a, [wEnemyMonPartyPos]
	ld c, a
	ld b, FLAG_TEST
	ld hl, wDodgeDone
	predef FlagActionPredef
	ld a, c
	and a
	jr nz, .no
	ld a, [wEnemyMonPartyPos]
	ld c, a
	ld b, FLAG_SET
	ld hl, wDodgeDone
	predef FlagActionPredef

	call DodgePhase
	; wDodgeHits = how many times you were hit
	xor a
	ld [wActionCommandFoe], a
	ld a, ACTION_COMMAND_CLOSED
	ld [wActionCommandState], a
	ld a, [wTrainerPain]
	cp TRAINER_MAX_HP
	jr nc, .broken
	ld a, [wDodgeHits]
	and a
	ld a, ACTION_RESULT_NONE
	jr nz, .gotResult
	; untouched: the attack is halved like a brace, and the meter fills fast
	ld a, 1 << ACTION_FOE_DODGED
	ld [wActionCommandFoe], a
	call AddDodgeMeterBonus
	ld a, ACTION_RESULT_GOOD
.gotResult
	ld [wActionCommandResult], a
	scf
	ret

; the trainer's bar ran dry: Resonance breaks and the next turn is lost, and
; the attack lands in full
.broken
	xor a
	ld [wTrainerPain], a
	ld [wResonanceMeter], a
	call EndResonance
	ld hl, wResonanceFlags
	set RESONANCE_STUNNED, [hl]
	ld a, ACTION_BADGE_BROKEN
	call ShowActionBadge
	scf
	ret

.no
	and a
	ret

AddDodgeMeterBonus:
	call IsResonanceUnlocked
	ret z
	ld a, [wResonanceFlags]
	bit RESONANCE_ACTIVE, a
	ret nz
	call GetResonanceRamp
	ld b, [hl] ; RESONANCE_RAMP_METER
	ld a, [wResonanceMeter]
	add DODGE_METER_BONUS
	cp b
	jr c, .store
	ld a, b
.store
	ld [wResonanceMeter], a
	ret

DodgePhase:
	xor a
	ld [wActionCommandState], a ; no window ticks while the phase runs
	ldh a, [hAutoBGTransferEnabled]
	push af
	call SaveScreenTilesToBuffer2
	hlcoord DODGE_ARENA_X - 1, DODGE_ARENA_Y - 1
	lb bc, DODGE_ARENA_H, DODGE_ARENA_W
	call TextBoxBorder
	hlcoord DODGE_ARENA_X, DODGE_ARENA_Y - 1
	ld de, DodgeTitleText
	call PlaceString
	xor a
	ld [wDodgeHits], a
	ld a, DODGE_ARENA_X + DODGE_ARENA_W / 2
	ld [wDodgeX], a
	ld a, DODGE_ARENA_Y + DODGE_ARENA_H - 1
	ld [wDodgeY], a
	call DrawDodgeBar
	call PlaceDodgePlayer
	ld a, 1
	ldh [hAutoBGTransferEnabled], a

	; the ramp: Assist always gets the gentlest row
	call GetBadgeRow
	ld c, a
	call IsActionAssist
	jr nz, .gotRow
	ld c, 0
.gotRow
	ld a, c
	ld hl, DodgeRamp
	ld bc, DODGE_RAMP_WIDTH
	call AddNTimes
	ld a, [hli]
	ld d, a ; frames per row
	ld e, [hl] ; frames between rocks
	push de ; kept for the timers to reload from
	ld a, d
	ld [wDodgeFallTimer], a
	ld a, e
	srl a ; the first rock comes quickly
	ld [wDodgeSpawnTimer], a
	xor a
	ld [wDodgeGrace], a
	ld b, DODGE_FRAMES

.loop
	push bc
	call DelayFrame
	call Joypad
	call ClearDodgePlayer
	pop bc
	push bc
	call MoveDodgePlayer
	pop bc
	pop de
	push de
	push bc
	ld hl, wDodgeFallTimer
	dec [hl]
	jr nz, .noFall
	ld [hl], d
	call DropDodgeRocks
.noFall
	pop bc
	pop de
	push de
	push bc
	ld hl, wDodgeSpawnTimer
	dec [hl]
	jr nz, .noSpawn
	ld [hl], e
	call SpawnDodgeRock
.noSpawn
	call CheckDodgeHit
	call PlaceDodgePlayer
	pop bc
	dec b
	jr nz, .loop

	pop de
	call LoadScreenTilesFromBuffer2
	pop af
	ldh [hAutoBGTransferEnabled], a
	ret

; hl = the tile under the player
GetDodgePlayerTile:
	ld a, [wDodgeY]
	ld hl, wTileMap
	ld bc, SCREEN_WIDTH
	call AddNTimes
	ld a, [wDodgeX]
	ld c, a
	ld b, 0
	add hl, bc
	ret

ClearDodgePlayer:
	call GetDodgePlayerTile
	ld a, [hl]
	cp DODGE_PLAYER
	ret nz
	ld [hl], ' '
	ret

PlaceDodgePlayer:
	ld a, [wDodgeGrace]
	and 2 ; blink while nothing can hit
	ret nz
	call GetDodgePlayerTile
	ld a, [hl]
	cp ' '
	ret nz ; a rock sits there while the hit plays out
	ld [hl], DODGE_PLAYER
	ret

; One tile per press, and one every DODGE_HOLD_EVERY frames while held.
; b = frames of the phase left
MoveDodgePlayer:
	ld a, b
	and DODGE_HOLD_EVERY - 1
	ldh a, [hJoyPressed]
	jr nz, .gotInput
	ld c, a
	ldh a, [hJoyHeld]
	or c
.gotInput
	ld b, a
	ld hl, wDodgeX
	bit B_PAD_LEFT, b
	jr z, .notLeft
	ld a, [hl]
	cp DODGE_ARENA_X
	jr z, .notLeft
	dec [hl]
.notLeft
	bit B_PAD_RIGHT, b
	jr z, .notRight
	ld a, [hl]
	cp DODGE_ARENA_X + DODGE_ARENA_W - 1
	jr z, .notRight
	inc [hl]
.notRight
	ld hl, wDodgeY
	bit B_PAD_UP, b
	jr z, .notUp
	ld a, [hl]
	cp DODGE_ARENA_Y
	jr z, .notUp
	dec [hl]
.notUp
	bit B_PAD_DOWN, b
	ret z
	ld a, [hl]
	cp DODGE_ARENA_Y + DODGE_ARENA_H - 1
	ret z
	inc [hl]
	ret

; Every rock falls a row, from the bottom up so none moves twice. Rocks at the
; bottom leave, and warnings in the top row become rocks.
DropDodgeRocks:
	hlcoord DODGE_ARENA_X, DODGE_ARENA_Y + DODGE_ARENA_H - 1
	ld b, DODGE_ARENA_H
.row
	push hl
	ld c, DODGE_ARENA_W
.column
	ld a, [hl]
	cp DODGE_WARN
	jr z, .warning
	cp DODGE_ROCK
	jr nz, .next
	ld [hl], ' '
	ld a, b
	cp DODGE_ARENA_H
	jr z, .next ; the bottom row: gone
	push hl
	ld de, SCREEN_WIDTH
	add hl, de
	ld [hl], DODGE_ROCK
	pop hl
	jr .next
.warning
	ld [hl], DODGE_ROCK
.next
	inc hl
	dec c
	jr nz, .column
	pop hl
	ld de, -SCREEN_WIDTH
	add hl, de
	dec b
	jr nz, .row
	ret

; A warning in a random column of the top row, a rock the next time rocks fall.
SpawnDodgeRock:
	call Random
.mod
	sub DODGE_ARENA_W
	jr nc, .mod
	add DODGE_ARENA_W
	ld c, a
	ld b, 0
	hlcoord DODGE_ARENA_X, DODGE_ARENA_Y
	add hl, bc
	ld a, [hl]
	cp ' '
	ret nz
	ld [hl], DODGE_WARN
	ret

; A rock on the player's tile is a hit, unless one only just landed.
CheckDodgeHit:
	ld hl, wDodgeGrace
	ld a, [hl]
	and a
	jr z, .check
	dec [hl]
	ret
.check
	call GetDodgePlayerTile
	ld a, [hl]
	cp DODGE_ROCK
	ret nz
	ld a, DODGE_GRACE
	ld [wDodgeGrace], a
	ld hl, wDodgeHits
	inc [hl]
	ld a, SFX_DENIED
	call PlaySound
	ld a, [wTrainerPain]
	add DODGE_HIT_PAIN
	cp TRAINER_MAX_HP
	jr c, .store
	ld a, TRAINER_MAX_HP
.store
	ld [wTrainerPain], a
	; fallthrough

; the trainer's bar, under the arena
DrawDodgeBar:
	hlcoord DODGE_ARENA_X, DODGE_ARENA_Y + DODGE_ARENA_H + 1
	ld a, [wTrainerPain]
	cpl
	add TRAINER_MAX_HP + 1 ; = TRAINER_MAX_HP - pain
	ld e, a
	ld [hl], '▶'
	inc hl
	ld d, RESONANCE_BAR_TILES
.segment
	ld a, e
	cp 8
	jr c, .part
	sub 8
	ld e, a
	ld a, $63 + 8
	jr .put
.part
	add $63
	ld e, 0
.put
	ld [hli], a
	dec d
	jr nz, .segment
	ld [hl], $6d
	ret

DodgeTitleText:
	db "DODGE!@"

; the bosses who make you dodge, and so far all of them throw rocks
DodgeBosses:
	db BROCK
	db -1 ; end

; frames per row a rock falls, and frames between rocks, by badges
DodgeRamp:
	table_width DODGE_RAMP_WIDTH
	db 9, 16 ; 0 badges
	db 8, 14 ; 1-2
	db 7, 12 ; 3-4
	db 6, 10 ; 5-6
	db 5,  9 ; 7-8
	assert_table_length 5
