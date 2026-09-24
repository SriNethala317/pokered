; Action commands: a timed press during every damaging move.
; A on your own attack for more damage, B on the enemy's attack to brace.
;
; ArmActionCommand runs straight after a fresh damage calculation, so the
; bonus is applied once even for multi-hit and trapping moves. The window then
; runs frame by frame from DelayFrame while the move animation plays, is closed
; by FinishActionCommand at the moment of impact, and ApplyActionCommand scales
; wDamage just before it is dealt.

DEF ACTION_LEAD_IN_MIN     EQU 4  ; frames from arming to the cue, plus 0-7 random
DEF ACTION_MAX_EXTRA       EQU 20 ; most frames a window may add to an attack
DEF ACTION_BADGE_FRAMES    EQU 60
DEF ACTION_PERFECT_ON      EQU 15 ; frames after the cue, exclusive
DEF ACTION_GOOD_ON         EQU 24
DEF ACTION_PERFECT_ASSIST  EQU 20
DEF ACTION_GOOD_ASSIST     EQU 32

; badge indexes kept in wActionCommandResult once the attack is applied
	const_def 1
	const ACTION_BADGE_EARLY   ; 1
	const ACTION_BADGE_GREAT   ; 2
	const ACTION_BADGE_PERFECT ; 3
	const ACTION_BADGE_BRACED  ; 4
	const ACTION_BADGE_COUNTER ; 5

ArmActionCommand:
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
	call Random
	and %111
	add ACTION_LEAD_IN_MIN
	ld [wActionCommandTimer], a
	xor a
	ld [wActionCommandResult], a
	ld [wActionCommandFrame], a
	; a button already held (from picking the move) is not a press
	ldh a, [hJoyInput]
	and PAD_A | PAD_B
	ld [wActionCommandLastInput], a
	ld a, ACTION_COMMAND_LEAD_IN
	ld [wActionCommandState], a
	ret

; called by DelayFrame once a frame while wActionCommandState is nonzero
ActionCommandTick::
	ld a, [wIsInBattle]
	and a
	jr z, .reset
	; c = buttons newly pressed this frame
	ldh a, [hJoyInput]
	and PAD_A | PAD_B
	ld b, a
	ld a, [wActionCommandLastInput]
	cpl
	and b
	ld c, a
	ld a, b
	ld [wActionCommandLastInput], a
	ld a, [wActionCommandState]
	cp ACTION_COMMAND_LEAD_IN
	jr z, .leadIn
	cp ACTION_COMMAND_WINDOW
	jr z, .window
	cp ACTION_COMMAND_BADGE
	jr z, .badge
	ret

.reset
	xor a
	ld [wActionCommandState], a
	ret

.leadIn
	ld a, c
	and a
	jr nz, .early ; pressed before the cue: locked out, so mashing never pays
	ld hl, wActionCommandTimer
	dec [hl]
	ret nz
	ld a, ACTION_COMMAND_WINDOW
	ld [wActionCommandState], a
	call GetActionCueString
	jp PlaceActionString

.window
	ld a, c
	and a
	jr z, .noPress
	ldh a, [hWhoseTurn]
	and a
	ld a, PAD_A
	jr z, .gotButton
	ld a, PAD_B
.gotButton
	cp c
	jr nz, .early ; wrong button
	call GetActionWindow
	ld a, [wActionCommandFrame]
	cp d
	ld b, ACTION_RESULT_PERFECT
	jr c, .setResult
	ld b, ACTION_RESULT_GOOD
.setResult
	ld a, b
	ld [wActionCommandResult], a
	jr .close

.noPress
	call GetActionWindow
	ld hl, wActionCommandFrame
	inc [hl]
	ld a, [hl]
	cp e
	ret c
	jr .close ; too late, no bonus

.early
	ld a, ACTION_RESULT_EARLY
	ld [wActionCommandResult], a
.close
	ld a, ACTION_COMMAND_CLOSED
	ld [wActionCommandState], a
	jp ClearActionCue

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
	ld a, ACTION_COMMAND_CLOSED
	ld [wActionCommandState], a
	jp ClearActionCue

; Called just before the attack is applied. Scales wDamage by the result and
; shows the result badge.
ApplyActionCommand:
	ld a, [wActionCommandState]
	and a
	ret z
	cp ACTION_COMMAND_BADGE
	ret z
	call ClearActionCue
	ld a, [wActionCommandResult]
	cp ACTION_RESULT_GOOD
	jr c, .showBadge
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

GetActionCueString:
	ld de, ActionCueA
	ldh a, [hWhoseTurn]
	and a
	ret z
	ld de, ActionCueB
	ret

ClearActionCue:
	call GetActionCueString
	jr ClearActionString

ClearActionBadge:
	ld a, [wActionCommandResult]
	call GetActionBadgeString
	; fallthrough

; blank the string at de from the screen, but only if it is still showing there
ClearActionString:
	hlcoord 1, 4
	push de
.compare
	ld a, [de]
	cp '@'
	jr z, .clear
	cp [hl]
	jr nz, .notShowing
	inc de
	inc hl
	jr .compare
.notShowing
	pop de
	ret
.clear
	pop de
	hlcoord 1, 4
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

PlaceActionString:
	hlcoord 1, 4
	call GetActionBGMapAddress
.loop
	ld a, [de]
	cp '@'
	ret z
	ld [hli], a
	call PutActionVRAMTile
	inc de
	jr .loop

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

; de = badge string for index a
GetActionBadgeString:
	dec a
	add a
	ld e, a
	ld d, 0
	ld hl, ActionBadgeStrings
	add hl, de
	ld a, [hli]
	ld e, a
	ld d, [hl]
	ret

ActionCueA: db "A!@"
ActionCueB: db "B!@"

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
