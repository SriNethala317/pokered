; Action commands: a timed input during every damaging move.
; A on your own attack for more damage, B on the enemy's attack to brace.
;
; ArmActionCommand runs straight after a fresh damage calculation, so the
; bonus is applied once even for multi-hit and trapping moves. The window then
; runs frame by frame from DelayFrame while the move animation plays, is closed
; by FinishActionCommand at the moment of impact, and ApplyActionCommand scales
; wDamage just before it is dealt.
;
; The move's type picks the input (ActionPatterns), and its power sets the
; tempo: stronger moves take longer to wind up and are harder to land perfectly.

DEF ACTION_LEAD_IN_MIN     EQU 4  ; frames from arming to the cue, plus 0-7 random
DEF ACTION_HOLD_LEAD_IN    EQU 16 ; extra time to see HOLD and press before the cue
DEF ACTION_DOUBLE_GAP      EQU 6  ; frames between the beats of a double, plus 0-3
DEF ACTION_RAPID_PRESSES   EQU 3
DEF ACTION_RAPID_EXTRA     EQU 12 ; extra frames to fit the presses of a rapid pattern
DEF ACTION_HEAVY_POWER     EQU 100 ; moves this strong have a tighter perfect window
DEF ACTION_HEAVY_PENALTY   EQU 2
DEF ACTION_MAX_EXTRA       EQU 20 ; most frames a window may add to an attack
DEF ACTION_BADGE_FRAMES    EQU 60
DEF ACTION_PERFECT_ON      EQU 15 ; frames after the cue, exclusive
DEF ACTION_GOOD_ON         EQU 24
DEF ACTION_PERFECT_ASSIST  EQU 20
DEF ACTION_GOOD_ASSIST     EQU 32

; stands for the button to press, A or B, in the cue strings
DEF ACTION_BUTTON_CHAR     EQU '<NULL>'

; badge indexes kept in wActionCommandResult once the attack is applied
	const_def 1
	const ACTION_BADGE_EARLY   ; 1
	const ACTION_BADGE_GREAT   ; 2
	const ACTION_BADGE_PERFECT ; 3
	const ACTION_BADGE_BRACED  ; 4
	const ACTION_BADGE_COUNTER ; 5

; wActionCommandCue
	const_def 1
	const ACTION_CUE_TAP     ; 1
	const ACTION_CUE_SNAP    ; 2
	const ACTION_CUE_HOLD    ; 3
	const ACTION_CUE_LET_GO  ; 4
	const ACTION_CUE_RAPID_3 ; 5
	const ACTION_CUE_RAPID_2 ; 6
	const ACTION_CUE_RAPID_1 ; 7
	const ACTION_CUE_SECOND  ; 8

ArmActionCommand:
	xor a
	ld [wActionCommandForceEffect], a
	ld a, [wMoveMissed]
	and a
	ret nz
	ld a, [wLinkState]
	cp LINK_STATE_BATTLING
	ret z
	ld a, [wOptions]
	and ACTION_COMMANDS_MASK
	cp ACTION_COMMANDS_OFF
	ret nc
	ld a, [wDamage]
	ld b, a
	ld a, [wDamage + 1]
	or b
	ret z
	ld a, [wPlayerMoveEffect]
	ld b, a
	ldh a, [hWhoseTurn]
	and a
	jr z, .gotEffect
	ld a, [wEnemyMoveEffect]
	ld b, a
.gotEffect
	ld a, b
	cp OHKO_EFFECT ; damage is replaced when it lands, so a bonus would do nothing
	ret z
	ld a, [wActionCommandState]
	cp ACTION_COMMAND_BADGE
	call z, ClearActionBadge
	xor a
	ld [wActionCommandResult], a
	ld [wActionCommandFrame], a
	ld [wActionCommandStep], a

; b = move power, c = move type
	ld hl, wPlayerMovePower
	ldh a, [hWhoseTurn]
	and a
	jr z, .gotMove
	ld hl, wEnemyMovePower
.gotMove
	ld a, [hli]
	ld b, a
	ld c, [hl]
	push bc
	ld hl, ActionPatterns
	ld b, 0
	add hl, bc
	ld a, [hl]
	ld [wActionCommandPattern], a
	cp ACTION_PATTERN_RAPID
	jr nz, .gotStep
	ld a, ACTION_RAPID_PRESSES
	ld [wActionCommandStep], a
.gotStep

; the windows: tighter for heavy moves and snaps, longer for rapid presses
	call GetActionWindow
	pop bc
	push bc
	ld a, b
	cp ACTION_HEAVY_POWER
	jr c, .notHeavy
	ld a, d
	sub ACTION_HEAVY_PENALTY
	ld d, a
.notHeavy
	ld a, [wActionCommandPattern]
	cp ACTION_PATTERN_SNAP
	jr nz, .notSnap
	srl d
	srl e
.notSnap
	cp ACTION_PATTERN_RAPID
	jr nz, .gotWindow
	ld a, d
	add ACTION_RAPID_EXTRA
	ld d, a
	ld a, e
	add ACTION_RAPID_EXTRA
	ld e, a
.gotWindow
	ld a, d
	ld [wActionCommandPerfect], a
	ld a, e
	ld [wActionCommandGood], a

; the lead-in: a frame more for every 32 power, so big moves wind up
	pop bc
	ld a, b
	swap a
	srl a
	and %111
	ld b, a
	call Random
	and %111
	add b
	add ACTION_LEAD_IN_MIN
	ld b, a
	ld a, [wActionCommandPattern]
	cp ACTION_PATTERN_HOLD
	jr nz, .gotLeadIn
	ld a, b
	add ACTION_HOLD_LEAD_IN
	ld b, a
.gotLeadIn
	ld a, b
	ld [wActionCommandTimer], a

	; a button already held (from picking the move) is not a press
	ldh a, [hJoyInput]
	and PAD_A | PAD_B
	ld [wActionCommandLastInput], a
	ld a, ACTION_COMMAND_LEAD_IN
	ld [wActionCommandState], a
	ld a, [wActionCommandPattern]
	cp ACTION_PATTERN_HOLD
	ret nz
	ld a, ACTION_CUE_HOLD ; hold shows from the start: the cue is when to let go
	jp ShowActionCue

; called by DelayFrame once a frame while wActionCommandState is nonzero
ActionCommandTick::
	ld a, [wIsInBattle]
	and a
	jp z, .reset
	; b = buttons held, e = buttons held last frame, c = newly pressed
	ldh a, [hJoyInput]
	and PAD_A | PAD_B
	ld b, a
	ld a, [wActionCommandLastInput]
	ld e, a
	cpl
	and b
	ld c, a
	ld a, b
	ld [wActionCommandLastInput], a
	ld a, [wActionCommandState]
	cp ACTION_COMMAND_BADGE
	jp z, .badge
	cp ACTION_COMMAND_CLOSED
	ret nc
	; d = this side's button; the other one is always a mistake
	call GetActionButton
	ld d, a
	cpl
	and c
	jp nz, .early
	ld a, [wActionCommandState]
	cp ACTION_COMMAND_WINDOW
	jr z, .window

; lead-in
	ld a, [wActionCommandPattern]
	cp ACTION_PATTERN_HOLD
	jr z, .holdLeadIn
	ld a, c
	and a
	jp nz, .early ; pressed before the cue: locked out, so mashing never pays
	jr .leadInTimer

.holdLeadIn
	ld a, c
	and d
	jr z, .checkRelease
	ld a, 1 ; pressed since the cue to hold
	ld [wActionCommandStep], a
.checkRelease
	ld a, [wActionCommandStep]
	and a
	jr z, .leadInTimer
	ld a, b
	cpl
	and e
	and d
	jp nz, .early ; let go before the cue

.leadInTimer
	ld hl, wActionCommandTimer
	dec [hl]
	ret nz
	ld a, [wActionCommandPattern]
	cp ACTION_PATTERN_HOLD
	jr nz, .openWindow
	ld a, b
	and d
	jp z, .missed ; not holding when the cue came
.openWindow
	xor a
	ld [wActionCommandFrame], a
	ld a, ACTION_COMMAND_WINDOW
	ld [wActionCommandState], a
	call GetPatternCue
	call ShowActionCue
	ld a, SFX_PRESS_AB
	jp PlaySound

.window
	ld a, [wActionCommandPattern]
	cp ACTION_PATTERN_HOLD
	ld a, c
	jr nz, .gotInput
	; the input for a hold is letting go
	ld a, b
	cpl
	and e
.gotInput
	and d
	jr z, .noPress
	ld a, [wActionCommandPattern]
	cp ACTION_PATTERN_RAPID
	jr nz, .judge
	ld hl, wActionCommandStep
	dec [hl]
	jr z, .judge
	ld a, [wActionCommandCue]
	inc a ; count the cue down
	call ShowActionCue
	jr .noPress

.judge
	ld a, [wActionCommandPerfect]
	ld b, a
	ld a, [wActionCommandFrame]
	cp b
	ld b, ACTION_RESULT_PERFECT
	jr c, .gotResult
	ld b, ACTION_RESULT_GOOD
.gotResult
	ld a, [wActionCommandPattern]
	cp ACTION_PATTERN_DOUBLE
	jr nz, .setResult
	ld a, [wActionCommandStep]
	and a
	jr nz, .secondBeat
	; the first beat of a double: remember it, and cue the second shortly
	inc a
	ld [wActionCommandStep], a
	ld a, b
	ld [wActionCommandResult], a
	call ClearActionCue
	call Random
	and %11
	add ACTION_DOUBLE_GAP
	ld [wActionCommandTimer], a
	ld a, ACTION_COMMAND_LEAD_IN
	ld [wActionCommandState], a
	ret

.secondBeat
	; a double is only as good as its worse beat
	ld a, [wActionCommandResult]
	cp b
	jr nc, .setResult
	ld b, a
.setResult
	ld a, b
	ld [wActionCommandResult], a
	jr .close

.noPress
	ld hl, wActionCommandFrame
	inc [hl]
	ld a, [wActionCommandGood]
	cp [hl]
	ret nz
.missed
	xor a ; too late: no bonus, even for a double whose first beat landed
	ld [wActionCommandResult], a
	jr .close

.early
	ld a, ACTION_RESULT_EARLY
	ld [wActionCommandResult], a
.close
	ld a, ACTION_COMMAND_CLOSED
	ld [wActionCommandState], a
	jp ClearActionCue

.reset
	xor a
	ld [wActionCommandState], a
	ret

.badge
	ld hl, wActionCommandBadgeTimer
	dec [hl]
	ret nz
	call ClearActionBadge
	xor a
	ld [wActionCommandState], a
	ret

; Called from MoveAnimation at the moment of impact. If the window is still
; open, wait for it, but never more than ACTION_MAX_EXTRA frames.
FinishActionCommand:
	ld a, [wActionCommandState]
	cp ACTION_COMMAND_LEAD_IN
	jr z, .wait
	cp ACTION_COMMAND_WINDOW
	ret nz
.wait
	ld c, ACTION_MAX_EXTRA
.loop
	call DelayFrame ; ticks the window
	ld a, [wActionCommandState]
	cp ACTION_COMMAND_CLOSED
	ret nc
	dec c
	jr nz, .loop
	xor a ; out of time counts as no press
	ld [wActionCommandResult], a
	ld a, ACTION_COMMAND_CLOSED
	ld [wActionCommandState], a
	jp ClearActionCue

; Called just before the attack is applied. Scales wDamage by the result and
; shows the result badge. A perfect attack also makes sure of the move's
; secondary effect, and a perfect brace shrugs it off.
ApplyActionCommand:
	ld a, [wActionCommandState]
	and a
	ret z
	cp ACTION_COMMAND_BADGE
	ret z
	call ClearActionCue
	ld a, [wActionCommandResult]
	cp ACTION_RESULT_GOOD
	jp c, .showBadge
	cp ACTION_RESULT_PERFECT
	jr nz, .scale
	ldh a, [hWhoseTurn]
	inc a ; ACTION_EFFECT_FORCED on your attack, ACTION_EFFECT_BLOCKED on theirs
	ld [wActionCommandForceEffect], a
.scale
	ldh a, [hWhoseTurn]
	and a
	jr nz, .brace
; your attack: damage x1.5
	ld hl, wDamage
	ld a, [hli]
	ld d, a
	ld e, [hl]
	ld h, d
	ld l, e
	srl d
	rr e
	add hl, de
	jr nc, .storeAttack
	ld hl, $ffff
.storeAttack
	ld a, h
	ld [wDamage], a
	ld a, l
	ld [wDamage + 1], a
	ld a, [wActionCommandResult]
	jr .showBadge

; enemy attack: damage x0.5, and a perfect brace hits back
.brace
	ld hl, wDamage
	ld a, [hli]
	ld b, a
	ld c, [hl]
	ld d, b
	ld e, c
	srl d
	rr e
	ld a, d
	or e
	jr nz, .storeBrace
	inc e
.storeBrace
	ld a, d
	ld [wDamage], a
	ld a, e
	ld [wDamage + 1], a
	ld a, [wActionCommandResult]
	cp ACTION_RESULT_PERFECT
	jr nz, .braceBadge
; counter: a quarter of the damage blocked, at least 1, never a knockout
	ld a, c
	sub e
	ld c, a
	ld a, b
	sbc d
	ld b, a
	srl b
	rr c
	srl b
	rr c
	ld a, b
	or c
	jr nz, .gotCounter
	inc c
.gotCounter
	ld hl, wEnemyMonHP
	ld a, [hli]
	ld d, a
	ld a, [hl]
	sub c
	ld e, a
	ld a, d
	sbc b
	ld d, a
	jr c, .leaveOne
	or e
	jr nz, .storeHP
.leaveOne
	ld de, 1
.storeHP
	ld a, e
	ld [hld], a
	ld [hl], d
	callfar DrawEnemyHUDAndHPBar
.braceBadge
	ld a, [wActionCommandResult]
	add ACTION_BADGE_BRACED - ACTION_RESULT_GOOD
.showBadge
	and a
	jr z, .done ; no press: nothing to show
	ld [wActionCommandResult], a
	call GetActionBadgeString
	call PlaceActionString
	ld a, ACTION_BADGE_FRAMES
	ld [wActionCommandBadgeTimer], a
	ld a, ACTION_COMMAND_BADGE
.done
	ld [wActionCommandState], a
	ret

; d = frames for a perfect press, e = frames for a good one
GetActionWindow:
	ld a, [wOptions]
	and ACTION_COMMANDS_MASK
	cp ACTION_COMMANDS_ASSIST
	lb de, ACTION_PERFECT_ON, ACTION_GOOD_ON
	ret nz
	lb de, ACTION_PERFECT_ASSIST, ACTION_GOOD_ASSIST
	ret

; a = PAD_A on your attack, PAD_B on theirs
GetActionButton:
	ldh a, [hWhoseTurn]
	and a
	ld a, PAD_A
	ret z
	ld a, PAD_B
	ret

; a = the cue that opens the window for this pattern
GetPatternCue:
	ld a, [wActionCommandPattern]
	cp ACTION_PATTERN_DOUBLE
	jr nz, .first
	ld a, [wActionCommandStep]
	and a
	ld a, ACTION_CUE_SECOND
	ret nz
	ld a, ACTION_PATTERN_DOUBLE
.first
	ld hl, PatternCues
	add l
	ld l, a
	jr nc, .noCarry
	inc h
.noCarry
	ld a, [hl]
	ret

; show cue a in place of the one on screen
ShowActionCue:
	push af
	call ClearActionCue
	pop af
	ld [wActionCommandCue], a
	call GetActionCueString
	jr PlaceActionString

ClearActionCue:
	ld a, [wActionCommandCue]
	and a
	ret z
	call GetActionCueString
	xor a
	ld [wActionCommandCue], a
	jr ClearActionString

ClearActionBadge:
	ld a, [wActionCommandResult]
	call GetActionBadgeString
	; fallthrough

; Blank the string at de from the screen, but only where it is still showing.
; The battle saves the screen to wTileMapBackup at the end of every turn, while
; a badge can still be up, and restores it for the battle menu; the saved copy
; is cleaned as well, or restoring it would bring the badge back for good.
ClearActionString:
	hlcoord 1, 4, wTileMapBackup
	call IsActionStringAt
	jr nz, .screen
	push de
.blankBackup
	ld a, [de]
	cp '@'
	jr z, .screenPop
	ld [hl], ' '
	inc hl
	inc de
	jr .blankBackup
.screenPop
	pop de
.screen
	hlcoord 1, 4
	call IsActionStringAt
	ret nz
	call GetActionBGMapAddress
.blank
	ld a, [de]
	cp '@'
	ret z
	ld a, ' '
	ld [hli], a
	call PutActionVRAMTile
	inc de
	jr .blank

; z if the string at de is showing at hl
IsActionStringAt:
	push de
	push hl
.loop
	call GetActionChar
	cp '@'
	jr z, .done
	cp [hl]
	jr nz, .done
	inc de
	inc hl
	jr .loop
.done
	pop hl
	pop de
	ret

PlaceActionString:
	hlcoord 1, 4
	call GetActionBGMapAddress
.loop
	call GetActionChar
	cp '@'
	ret z
	ld [hli], a
	call PutActionVRAMTile
	inc de
	jr .loop

; a = the character at de, with the button to press filled in
GetActionChar:
	ld a, [de]
	cp ACTION_BUTTON_CHAR
	ret nz
	ldh a, [hWhoseTurn]
	and a
	ld a, 'A'
	ret z
	ld a, 'B'
	ret

; The animation engine turns off the automatic tilemap copy while a move
; plays, so the cue has to go straight to the BG map as well as wTileMap.
; bc = the BG map address of coord 1, 4
GetActionBGMapAddress:
	ldh a, [hAutoBGTransferDest]
	add 4 * TILEMAP_WIDTH + 1
	ld c, a
	ldh a, [hAutoBGTransferDest + 1]
	adc 0
	ld b, a
	ret

; write tile a to [bc] as soon as the PPU lets go of VRAM
PutActionVRAMTile:
	push hl
	ld h, a
.wait
	ldh a, [rSTAT]
	and STAT_BUSY
	jr nz, .wait
	ld a, h
	ld [bc], a
	inc bc
	pop hl
	ret

; de = cue string for index a
GetActionCueString:
	ld hl, ActionCueStrings
	jr GetActionString

; de = badge string for index a
GetActionBadgeString:
	ld hl, ActionBadgeStrings
	; fallthrough

; de = entry a of the 1-based string table at hl
GetActionString:
	dec a
	add a
	ld e, a
	ld d, 0
	add hl, de
	ld a, [hli]
	ld e, a
	ld d, [hl]
	ret

; the input each move type asks for
ActionPatterns:
	table_width 1
	db ACTION_PATTERN_TAP    ; NORMAL
	db ACTION_PATTERN_RAPID  ; FIGHTING
	db ACTION_PATTERN_TAP    ; FLYING
	db ACTION_PATTERN_DOUBLE ; POISON
	db ACTION_PATTERN_RAPID  ; GROUND
	db ACTION_PATTERN_RAPID  ; ROCK
	db ACTION_PATTERN_TAP    ; BIRD
	db ACTION_PATTERN_TAP    ; BUG
	db ACTION_PATTERN_TAP    ; GHOST
	ds UNUSED_TYPES_END - UNUSED_TYPES, ACTION_PATTERN_TAP
	db ACTION_PATTERN_DOUBLE ; FIRE
	db ACTION_PATTERN_HOLD   ; WATER
	db ACTION_PATTERN_DOUBLE ; GRASS
	db ACTION_PATTERN_SNAP   ; ELECTRIC
	db ACTION_PATTERN_SNAP   ; PSYCHIC_TYPE
	db ACTION_PATTERN_HOLD   ; ICE
	db ACTION_PATTERN_TAP    ; DRAGON
	assert_table_length NUM_TYPES

; the cue that opens the window, by pattern
PatternCues:
	table_width 1
	db ACTION_CUE_TAP     ; ACTION_PATTERN_TAP
	db ACTION_CUE_SNAP    ; ACTION_PATTERN_SNAP
	db ACTION_CUE_LET_GO  ; ACTION_PATTERN_HOLD
	db ACTION_CUE_RAPID_3 ; ACTION_PATTERN_RAPID
	db ACTION_CUE_TAP     ; ACTION_PATTERN_DOUBLE
	assert_table_length ACTION_PATTERN_DOUBLE + 1

ActionCueStrings:
; entries correspond to ACTION_CUE_* constants
	dw .tap
	dw .snap
	dw .hold
	dw .letGo
	dw .rapid3
	dw .rapid2
	dw .rapid1
	dw .second

.tap    db ACTION_BUTTON_CHAR, "!@"
.snap   db ACTION_BUTTON_CHAR, "!!@"
.hold   db "HOLD ", ACTION_BUTTON_CHAR, "@"
.letGo  db "LET GO!@"
.rapid3 db ACTION_BUTTON_CHAR, "×3@"
.rapid2 db ACTION_BUTTON_CHAR, "×2@"
.rapid1 db ACTION_BUTTON_CHAR, "×1@"
.second db "   ", ACTION_BUTTON_CHAR, "!@"

ActionBadgeStrings:
; entries correspond to ACTION_BADGE_* constants
	dw .early
	dw .great
	dw .perfect
	dw .braced
	dw .counter

.early   db "TOO SOON@"
.great   db "GREAT!@"
.perfect db "PERFECT!@"
.braced  db "BRACED!@"
.counter db "COUNTER!@"
