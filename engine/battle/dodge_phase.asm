; The Trainer Dodge Phase: on a gym leader's big attack, you dodge in person.
;
; The first damaging attack of each of a leader's Pokemon opens a small arena
; over the battle screen for a couple of seconds. You are the ♂, moved a tile
; at a time with the D-pad, and each leader has a pattern of their own
; (DodgeBosses). Each hit costs the trainer HP bar that Resonance uses
; (wTrainerPain), and running it dry breaks Resonance and costs your next turn.
; Getting through untouched halves the attack (DODGED!) and fills the
; Resonance meter fast.
;
; The arena is drawn over the battle screen in the tilemap only; the screen is
; saved to buffer 2 and put back. The hazards live in the tilemap itself, so the
; phase needs no RAM beyond the player's position, and the player is a sprite
; showing the font's ♂ so it never hides a warning. It stands in for the
; attack's action command, and is capped at DODGE_FRAMES.
; See docs/dodge-phase-design.md.

DEF DODGE_FRAMES      EQU 150 ; the phase itself, two and a half seconds
DEF DODGE_ARENA_X     EQU 5   ; the arena's inside, over the middle of the screen
DEF DODGE_ARENA_Y     EQU 4
DEF DODGE_ARENA_W     EQU 10
DEF DODGE_ARENA_H     EQU 8
DEF DODGE_GAP         EQU 2   ; rows left open in a wave
DEF DODGE_HIT_PAIN    EQU 6   ; of TRAINER_MAX_HP: four hits run the bar dry
DEF DODGE_GRACE       EQU 30  ; frames after a hit when nothing else can
DEF DODGE_HOLD_EVERY  EQU 4   ; frames between steps while a direction is held
DEF DODGE_METER_BONUS EQU 2   ; on top of the 1 a BRACED already gives

DEF DODGE_PLAYER EQU '♂' ; a font tile, which the sprites can show as well
DEF DODGE_ROCK   EQU 'O'
DEF DODGE_WAVE   EQU ')'
DEF DODGE_BOLT   EQU '│'
DEF DODGE_QUAKE  EQU '─'
DEF DODGE_WARN   EQU '▼' ; a rock about to fall
DEF DODGE_SURGE  EQU '▷' ; a wave about to come in
DEF DODGE_WARN1  EQU '.' ; a strike, two beats away
DEF DODGE_WARN2  EQU '×' ; a strike, one beat away

; the patterns, the low bits of each DodgeBosses entry
	const_def
	const DODGE_FALL   ; things drop a row every beat
	const DODGE_SWEEP  ; a wall with a gap moves across every beat
	const DODGE_COLUMN ; a column is warned twice, then struck
	const DODGE_ROW    ; a row is warned twice, then struck
DEF DODGE_PATTERN_MASK EQU %11
DEF DODGE_MIRRORED EQU 7 ; left and right are swapped

; The timers borrow action command bytes, which sit idle while the phase stands
; in for the window (DodgePhase sets wActionCommandState to idle first).
DEF wDodgeFallTimer  EQUS "wActionCommandTimer"
DEF wDodgeSpawnTimer EQUS "wActionCommandFrame"
DEF wDodgeGrace      EQUS "wActionCommandBadgeTimer"
DEF wDodgePattern    EQUS "wActionCommandCue" ; no cue is up during the phase

; a row of DodgeRamp
	rsreset
DEF DODGE_RAMP_BEAT  rb ; frames per beat
DEF DODGE_RAMP_SPAWN rb ; frames between new hazards
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
	call GetDodgePattern
	jr nc, .no
	; the first damaging attack of each of the leader's Pokemon
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

; a = this trainer's pattern, and carry, if they make you dodge
GetDodgePattern:
	ld a, [wTrainerClass]
	ld hl, DodgeBosses
	ld de, 2
	call IsInArray
	ret nc
	inc hl
	ld a, [hl]
	scf
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
	call GetDodgePattern
	ld [wDodgePattern], a
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
	ld [wDodgeGrace], a
	ld a, DODGE_ARENA_X + DODGE_ARENA_W / 2
	ld [wDodgeX], a
	ld a, DODGE_ARENA_Y + DODGE_ARENA_H - 1
	ld [wDodgeY], a
	ld a, DODGE_PLAYER
	ld [wShadowOAMSprite00TileID], a
	xor a
	ld [wShadowOAMSprite00Attributes], a
	call DrawDodgeBar
	call PlaceDodgePlayer
	ld a, 1
	ldh [hAutoBGTransferEnabled], a

	call GetDodgeTimers
	push de ; kept for the timers to reload from
	ld a, d
	ld [wDodgeFallTimer], a
	ld a, e
	srl a ; the first hazard comes quickly
	ld [wDodgeSpawnTimer], a
	ld b, DODGE_FRAMES

.loop
	push bc
	call DelayFrame
	call Joypad
	pop bc
	push bc
	call MoveDodgePlayer
	pop bc
	pop de
	push de
	push bc
	ld hl, wDodgeFallTimer
	dec [hl]
	jr nz, .noBeat
	ld [hl], d
	call StepDodgeHazards
.noBeat
	pop bc
	pop de
	push de
	push bc
	ld hl, wDodgeSpawnTimer
	dec [hl]
	jr nz, .noSpawn
	ld [hl], e
	call SpawnDodgeHazard
.noSpawn
	call CheckDodgeHit
	call PlaceDodgePlayer
	pop bc
	dec b
	jr nz, .loop

	pop de
	ld a, SCREEN_HEIGHT_PX + OAM_Y_OFS ; the ♂ goes away with the arena
	ld [wShadowOAMSprite00YCoord], a
	xor a
	ld [wDodgePattern], a
	call LoadScreenTilesFromBuffer2
	pop af
	ldh [hAutoBGTransferEnabled], a
	ret

; d = frames per beat, e = frames between hazards, from the ramp (Assist always
; gets the gentlest row). A strike needs two beats of warning to be fair, and a
; wave crossing the whole arena is spaced out further.
GetDodgeTimers:
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
	ld d, a
	ld e, [hl]
	ld a, [wDodgePattern]
	and DODGE_PATTERN_MASK
	cp DODGE_SWEEP
	jr z, .sweep
	cp DODGE_COLUMN
	ret c ; DODGE_FALL
	sla d ; strikes
	sla e
	ret
.sweep
	ld a, e
	add a
	add e
	ld e, a
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

; the ♂ is sprite 0, blinking while nothing can hit
PlaceDodgePlayer:
	ld a, [wDodgeGrace]
	and 2
	ld a, SCREEN_HEIGHT_PX + OAM_Y_OFS
	jr nz, .gotY
	ld a, [wDodgeY]
	add a
	add a
	add a
	add OAM_Y_OFS
.gotY
	ld [wShadowOAMSprite00YCoord], a
	ld a, [wDodgeX]
	add a
	add a
	add a
	add OAM_X_OFS
	ld [wShadowOAMSprite00XCoord], a
	ret

; One tile per press, and one every DODGE_HOLD_EVERY frames while held.
; Sabrina swaps left and right. b = frames of the phase left
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
	ld a, [wDodgePattern]
	bit DODGE_MIRRORED, a
	jr z, .notMirrored
	ld a, b
	and PAD_LEFT | PAD_RIGHT
	jr z, .notMirrored
	cp PAD_LEFT | PAD_RIGHT
	jr z, .notMirrored
	ld a, b
	xor PAD_LEFT | PAD_RIGHT
	ld b, a
.notMirrored
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

; Everything in the arena moves on a beat: rocks drop a row, waves move right,
; and strikes go from warning to warning to struck to gone. Each tile is looked
; at once, from the bottom right, so nothing moves twice.
StepDodgeHazards:
	hlcoord DODGE_ARENA_X + DODGE_ARENA_W - 1, DODGE_ARENA_Y + DODGE_ARENA_H - 1
	ld b, DODGE_ARENA_H
.row
	ld c, DODGE_ARENA_W
.column
	ld a, [hl]
	cp ' '
	call nz, StepDodgeTile
	dec hl
	dec c
	jr nz, .column
	ld de, DODGE_ARENA_W - SCREEN_WIDTH
	add hl, de
	dec b
	jr nz, .row
	ret

; hl = a tile holding a. b counts the rows down from DODGE_ARENA_H at the
; bottom, and c the columns down from DODGE_ARENA_W at the right edge.
StepDodgeTile:
	cp DODGE_WARN
	jr z, .becomesRock
	cp DODGE_ROCK
	jr z, .rock
	cp DODGE_SURGE
	jr z, .becomesWave
	cp DODGE_WAVE
	jr z, .wave
	cp DODGE_WARN1
	jr z, .secondWarning
	cp DODGE_WARN2
	jr z, .strike
	cp DODGE_BOLT
	jr z, .gone
	cp DODGE_QUAKE
	ret nz
.gone
	ld [hl], ' '
	ret
.becomesRock
	ld [hl], DODGE_ROCK
	ret
.rock
	ld [hl], ' '
	ld a, b
	cp DODGE_ARENA_H
	ret z ; off the bottom
	push hl
	ld de, SCREEN_WIDTH
	add hl, de
	ld [hl], DODGE_ROCK
	pop hl
	ret
.becomesWave
	ld [hl], DODGE_WAVE
	ret
.wave
	ld [hl], ' '
	ld a, c
	cp DODGE_ARENA_W
	ret z ; off the right edge
	inc hl
	ld [hl], DODGE_WAVE
	dec hl
	ret
.secondWarning
	ld [hl], DODGE_WARN2
	ret
.strike
	ld a, [wDodgePattern]
	and DODGE_PATTERN_MASK
	cp DODGE_ROW
	ld a, DODGE_BOLT
	jr nz, .struck
	ld a, DODGE_QUAKE
.struck
	ld [hl], a
	ret

SpawnDodgeHazard:
	ld a, [wDodgePattern]
	and DODGE_PATTERN_MASK
	cp DODGE_SWEEP
	jr z, .wave
	cp DODGE_COLUMN
	jr z, .column
	cp DODGE_ROW
	jr z, .row
; a rock: a warning in a random column of the top row
	ld b, DODGE_ARENA_W
	call DodgeRandom
	ld c, a
	ld b, 0
	hlcoord DODGE_ARENA_X, DODGE_ARENA_Y
	add hl, bc
	ld a, [hl]
	cp ' '
	ret nz
	ld [hl], DODGE_WARN
	ret

; a wave: the left column, but for a gap somewhere
.wave
	ld b, DODGE_ARENA_H - DODGE_GAP + 1
	call DodgeRandom
	ld e, a ; the gap's top row
	hlcoord DODGE_ARENA_X, DODGE_ARENA_Y
	ld bc, SCREEN_WIDTH
	ld d, 0
.waveRow
	ld a, d
	sub e
	cp DODGE_GAP
	jr c, .inGap
	ld [hl], DODGE_SURGE
.inGap
	add hl, bc
	inc d
	ld a, d
	cp DODGE_ARENA_H
	jr nz, .waveRow
	ret

; a strike down a random column
.column
	ld b, DODGE_ARENA_W
	call DodgeRandom
	ld c, a
	ld b, 0
	hlcoord DODGE_ARENA_X, DODGE_ARENA_Y
	add hl, bc
	ld bc, SCREEN_WIDTH
	ld d, DODGE_ARENA_H
	jr .warnLine

; a strike across a random row
.row
	ld b, DODGE_ARENA_H
	call DodgeRandom
	ld hl, wTileMap + DODGE_ARENA_Y * SCREEN_WIDTH + DODGE_ARENA_X
	ld bc, SCREEN_WIDTH
	call AddNTimes
	ld bc, 1
	ld d, DODGE_ARENA_W
.warnLine
	ld a, [hl]
	cp ' '
	jr nz, .taken
	ld [hl], DODGE_WARN1
.taken
	add hl, bc
	dec d
	jr nz, .warnLine
	ret

; a = a random number from 0 to b - 1
DodgeRandom:
	call Random
.mod
	sub b
	jr nc, .mod
	add b
	ret

; A hazard on the player's tile is a hit, unless one only just landed.
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
	jr z, .hit
	cp DODGE_WAVE
	jr z, .hit
	cp DODGE_BOLT
	jr z, .hit
	cp DODGE_QUAKE
	ret nz
.hit
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

; the gym leaders who make you dodge, and how
DodgeBosses:
	db BROCK,    DODGE_FALL   ; falling rocks
	db MISTY,    DODGE_SWEEP  ; waves
	db LT_SURGE, DODGE_COLUMN ; lightning
	db ERIKA,    DODGE_SWEEP  ; lashing vines
	db KOGA,     DODGE_ROW    ; poison gas
	db SABRINA,  DODGE_FALL | 1 << DODGE_MIRRORED ; everything mirrored
	db BLAINE,   DODGE_COLUMN ; fire pillars
	db GIOVANNI, DODGE_ROW    ; earthquakes
	db -1 ; end

; frames per beat and frames between hazards, by badges
DodgeRamp:
	table_width DODGE_RAMP_WIDTH
	db 9, 16 ; 0 badges
	db 8, 14 ; 1-2
	db 7, 12 ; 3-4
	db 6, 10 ; 5-6
	db 5,  9 ; 7-8
	assert_table_length 5
