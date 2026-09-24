; Resonance: fight as one with a Pokemon you have bonded with.
;
; Landed action commands fill a meter. Once it is full, pressing SELECT on the
; battle menu with a resonant Pokemon out (Bond BOND_RESONANT or more) starts
; Resonance for a few of your turns: your attacks hit harder, the timing
; windows widen, STAB moves make sure of their secondary effect, and a PERFECT
; attack buys another turn. The catch is shared pain: the trainer takes part of
; every hit. If the trainer's bar runs out, Resonance breaks and you lose your
; next turn. The badge count sets how hard all of it is (ResonanceRamp).
;
; None of it prints a message: everything is shown on the action command badge
; line and in a small bar in the player's HUD, so battles do not get longer.
; See docs/resonance-design.md.

; a row of ResonanceRamp
	rsreset
DEF RESONANCE_RAMP_METER  rb ; points to fill the meter
DEF RESONANCE_RAMP_TURNS  rb ; your turns of Resonance
DEF RESONANCE_RAMP_WINDOW rb ; frames added to both timing windows
DEF RESONANCE_RAMP_PAIN   rb ; quarters of the Pokemon's lost HP the trainer feels
DEF RESONANCE_RAMP_WIDTH  EQU _RS

DEF RESONANCE_FLASH_FRAMES EQU 2 ; per half of each of the two flashes
DEF RESONANCE_HUD_X EQU 9 ; the bar's left cap, in the empty space of the
DEF RESONANCE_HUD_Y EQU 8 ; player's HUD left of the level

; hl = the row of ResonanceRamp for the badges you have
GetResonanceRamp:
	call GetBadgeRow
	ld hl, ResonanceRamp
	ld bc, RESONANCE_RAMP_WIDTH
	jp AddNTimes

; a = 0 to 4: the row of a ramp table for the badges you have. Rows cover 0,
; 1-2, 3-4, 5-6 and 7-8 badges.
; Keeps de, which ArmActionCommand holds its windows in.
GetBadgeRow:
	push de
	ld hl, wObtainedBadges
	ld b, 1
	call CountSetBits
	pop de
	inc a
	srl a
	ret

; nz once Brock has unlocked Resonance
IsResonanceUnlocked:
	CheckEvent EVENT_RESONANCE_UNLOCKED
	ret

; a = the Bond of the Pokemon you have out
GetBattleMonBond:
	ld hl, wPartyMon1Bond
	ld a, [wPlayerMonNumber]
	ld bc, PARTYMON_STRUCT_LENGTH
	call AddNTimes
	ld a, [hl]
	ret

; Called by ApplyActionCommand with the attack's result in wActionCommandResult.
; A landed command fills the meter; a PERFECT or COUNTER also brings the
; Pokemon closer. During Resonance a PERFECT attack keeps it going a turn
; longer instead, as many times as it lasts to begin with.
FillResonance:
	ld a, [wActionCommandResult]
	cp ACTION_RESULT_GOOD
	ret c
	ld b, 1
	cp ACTION_RESULT_PERFECT
	jr nz, .gotPoints
	inc b
	push bc
	ld a, [wPlayerMonNumber]
	ld e, a
	ld d, BOND_LANDED
	call ChangeBond
	pop bc
.gotPoints
	call IsResonanceUnlocked
	ret z
	ld a, [wResonanceFlags]
	bit RESONANCE_ACTIVE, a
	jr nz, .chain
	push bc
	call GetResonanceRamp
	pop bc
	ld c, [hl] ; RESONANCE_RAMP_METER
	ld a, [wResonanceMeter]
	add b
	cp c
	jr c, .storeMeter
	ld a, c
.storeMeter
	ld [wResonanceMeter], a
	jp UpdateResonanceHUD

.chain
	dec b
	ret z ; only a PERFECT
	ldh a, [hWhoseTurn]
	and a
	ret nz ; and only on your own attack
	call GetResonanceRamp
	inc hl
	ld b, [hl] ; RESONANCE_RAMP_TURNS
	ld a, [wResonanceFlags]
	and RESONANCE_REFUNDS_MASK
	cp b
	ret nc
	ld hl, wResonanceFlags
	inc [hl]
	ld hl, wResonanceTurns
	inc [hl]
	ret

; SELECT on the battle menu: start Resonance if everything is ready.
TryResonance::
	ld a, [wLinkState]
	cp LINK_STATE_BATTLING
	ret z
	call IsResonanceUnlocked
	ret z ; nothing to try yet
	ld a, [wBattleType]
	and a
	jr nz, .denied ; the old man's tutorial and the Safari Zone
	ld a, [wResonanceFlags]
	bit RESONANCE_ACTIVE, a
	jr nz, .denied
	call GetResonanceRamp
	ld a, [wResonanceMeter]
	cp [hl] ; RESONANCE_RAMP_METER
	jr c, .denied
	push hl
	call GetBattleMonBond
	pop hl
	cp BOND_RESONANT
	jr c, .denied
	inc hl
	ld a, [hl] ; RESONANCE_RAMP_TURNS
	ld [wResonanceTurns], a
	ld hl, wResonanceFlags
	ld a, [hl]
	and 1 << RESONANCE_STUNNED
	or 1 << RESONANCE_ACTIVE
	ld [hl], a
	xor a
	ld [wResonanceMeter], a
	call ResonanceFlash
	call PlayResonanceMusic
	call UpdateResonanceHUD
	ld a, ACTION_BADGE_RESONANCE
	jp ShowActionBadge
.denied
	ld a, SFX_DENIED
	jp PlaySound

; Called at the start of every turn. Counts down Resonance, and takes the turn
; of a trainer who was stunned by a break: carry if the player loses this turn.
ResonanceNewTurn::
	ld hl, wResonanceFlags
	bit RESONANCE_STUNNED, [hl]
	jr z, .notStunned
	res RESONANCE_STUNNED, [hl]
	ld a, ACTION_BADGE_STUNNED
	call ShowActionBadge
	scf
	ret
.notStunned
	bit RESONANCE_ACTIVE, [hl]
	jr z, .done
	ld hl, wResonanceTurns
	dec [hl]
	call z, EndResonance
.done
	and a
	ret

; Resonance ends when its turns run out, the Pokemon faints or it is switched out.
EndResonance::
	ld hl, wResonanceFlags
	bit RESONANCE_ACTIVE, [hl]
	ret z
	ld a, [hl]
	and 1 << RESONANCE_STUNNED
	ld [hl], a
	xor a
	ld [wResonanceTurns], a
	callfar PlayBattleMusic
	jp UpdateResonanceHUD

; Called by ApplyActionCommand just before the badge is shown, with the badge
; in a. Your attacks hit harder and STAB moves make sure of their effect; the
; enemy's hit is shared with the trainer, and may break Resonance. Returns the
; badge to show in a.
ResonanceAttack:
	ld c, a
	ld a, [wResonanceFlags]
	bit RESONANCE_ACTIVE, a
	ld a, c
	ret z
	push af
	ldh a, [hWhoseTurn]
	and a
	jr nz, .theirAttack

; your attack: x1.5, and a STAB move lands its effect on any hit that landed
	call BoostDamage
	ld a, [wActionCommandResult]
	cp ACTION_RESULT_GOOD
	jr c, .done
	ld a, [wPlayerMoveType]
	ld b, a
	ld a, [wBattleMonType1]
	cp b
	jr z, .stab
	ld a, [wBattleMonType2]
	cp b
	jr nz, .done
.stab
	ld a, ACTION_EFFECT_FORCED
	ld [wActionCommandForceEffect], a
.done
	pop af
	ret

; their attack: the Pokemon takes 3/4, and the trainer feels the rest
.theirAttack
	ld hl, wDamage
	ld a, [hli]
	ld d, a
	ld e, [hl]
	or e
	jr z, .done
	ld b, d
	ld c, e
	srl b
	rr c
	srl b
	rr c
	ld a, e
	sub c
	ld [hld], a
	ld a, d
	sbc b
	ld [hl], a
	ld d, a
	ld a, [hl+]
	ld e, [hl]
	; de = the damage the Pokemon takes. The trainer loses the same share of
	; their bar as the Pokemon loses of its max HP, scaled by the ramp.
	ld hl, wBattleMonMaxHP
	ld a, [hli]
	ld b, a
	ld c, [hl]
	ld a, d
	cp b
	jr c, .scale
	jr nz, .wholeBar
	ld a, e
	cp c
	jr nc, .wholeBar
.scale
	; damage < max HP <= 999, so damage x 24 fits in 16 bits
	ld h, d
	ld l, e
	add hl, hl
	add hl, de ; x3
	add hl, hl
	add hl, hl
	add hl, hl ; x24
	xor a
.countLoop
	; a = how many whole max HPs fit in hl
	push af
	ld a, l
	sub c
	ld l, a
	ld a, h
	sbc b
	ld h, a
	jr c, .counted
	pop af
	inc a
	jr .countLoop
.counted
	pop af
	jr .gotLoss
.wholeBar
	ld a, TRAINER_MAX_HP
.gotLoss
	; x the ramp's quarters, at least 1
	push af
	call GetResonanceRamp
	ld de, RESONANCE_RAMP_PAIN
	add hl, de
	ld b, [hl]
	pop af
	ld c, a
	xor a
.painLoop
	add c
	dec b
	jr nz, .painLoop
	srl a
	srl a
	jr nz, .gotPain
	inc a
.gotPain
	ld hl, wTrainerPain
	add [hl]
	cp TRAINER_MAX_HP
	jr nc, .break
	ld [hl], a
	call UpdateResonanceHUD
	pop af
	ret

; The trainer can take no more: Resonance breaks and the next turn is lost.
.break
	xor a
	ld [hl], a ; the trainer gets their breath back by the next Resonance
	ld [wResonanceMeter], a
	call EndResonance
	ld hl, wResonanceFlags
	set RESONANCE_STUNNED, [hl]
	pop af
	ld a, ACTION_BADGE_BROKEN
	ret

; Called with ApplyActionCommand's window arguments: widen both windows, d
; (perfect) and e (good), during Resonance.
ResonanceWindowBonus:
	ld a, [wResonanceFlags]
	bit RESONANCE_ACTIVE, a
	ret z
	push hl
	call GetResonanceRamp
	ld bc, RESONANCE_RAMP_WINDOW
	add hl, bc
	ld a, [hl]
	pop hl
	ld b, a
	add d
	ld d, a
	ld a, b
	add e
	ld e, a
	ret

; Two quick flashes of the whole screen.
ResonanceFlash:
	ld b, 2
.loop
	push bc
	ldh a, [rBGP]
	cpl
	ldh [rBGP], a
	ld c, RESONANCE_FLASH_FRAMES
	call DelayFrames
	ldh a, [rBGP]
	cpl
	ldh [rBGP], a
	ld c, RESONANCE_FLASH_FRAMES
	call DelayFrames
	pop bc
	dec b
	jr nz, .loop
	ret

; The final battle theme, or the gym leader theme against the champion, where
; the final battle theme is already playing.
PlayResonanceMusic:
	xor a
	ld [wAudioFadeOutControl], a
	dec a ; SFX_STOP_ALL_MUSIC
	ld [wNewSoundID], a
	call PlaySound
	ld c, BANK(Music_FinalBattle)
	ld a, [wCurOpponent]
	cp OPP_RIVAL3
	ld a, MUSIC_FINAL_BATTLE
	jr nz, .play
	ld a, MUSIC_GYM_LEADER_BATTLE
.play
	jp PlayMusic

; Draw the bar in the player's HUD: the meter filling up, or during Resonance
; the trainer's HP. The cap turns into ▷ when Resonance is ready and ▶ while it
; lasts. Nothing is drawn until Resonance is unlocked.
; DrawPlayerHUDAndHPBar calls it with the automatic tilemap copy off; during an
; attack the copy is off as well, so it also goes straight to VRAM.
DrawResonanceHUD::
	call IsResonanceUnlocked
	ret z
	ld a, [wLinkState]
	cp LINK_STATE_BATTLING
	ret z
	; a = pixels to fill, c = the cap
	ld a, [wResonanceFlags]
	bit RESONANCE_ACTIVE, a
	jr z, .meter
	ld a, [wTrainerPain]
	cpl
	add TRAINER_MAX_HP + 1 ; = TRAINER_MAX_HP - pain
	ld c, '▶'
	jr .draw
.meter
	call GetResonanceRamp
	ld b, [hl] ; RESONANCE_RAMP_METER
	ld a, [wResonanceMeter]
	cp b
	jr c, .partMeter
	call GetBattleMonBond
	ld c, $62 ; the HP bar's left cap
	cp BOND_RESONANT
	jr c, .fullMeter
	ld c, '▷' ; ready
.fullMeter
	ld a, TRAINER_MAX_HP
	jr .draw
.partMeter
	; pixels = meter x TRAINER_MAX_HP / meter size, in 16 bits
	ld l, a
	ld h, 0
	ld d, h
	ld e, l
	add hl, hl
	add hl, de ; x3
	add hl, hl
	add hl, hl
	add hl, hl ; x24
	ASSERT TRAINER_MAX_HP == 24
	ld c, b
	ld b, 0
	ld a, -1
.divide
	inc a ; a = how many meter sizes fit so far
	push af
	ld a, l
	sub c
	ld l, a
	ld a, h
	sbc b
	ld h, a
	jr c, .divided
	pop af
	jr .divide
.divided
	pop af
	ld c, $62 ; the HP bar's left cap
.draw
	; a = pixels, c = the cap
	ld e, a
	push de
	push bc
	call GetResonanceBGMapAddress
	pop hl
	ld a, l ; the cap
	hlcoord RESONANCE_HUD_X, RESONANCE_HUD_Y
	ld [hli], a
	call PutActionVRAMTile
	pop de
	ld d, RESONANCE_BAR_TILES
.segment
	ld a, e
	cp 8
	jr c, .partSegment
	sub 8
	ld e, a
	ld a, $63 + 8
	jr .putSegment
.partSegment
	add $63 ; the HP bar's segments, $63 empty to $6b full
	ld e, 0
.putSegment
	ld [hli], a
	call PutActionVRAMTile
	dec d
	jr nz, .segment
	ld a, $6d ; the HP bar's right cap
	ld [hl], a
	jp PutActionVRAMTile

; Redraw the bar in the middle of a battle.
UpdateResonanceHUD:
	jp DrawResonanceHUD

; bc = the BG map address of the bar's cap
GetResonanceBGMapAddress:
	ldh a, [hAutoBGTransferDest]
	add LOW(RESONANCE_HUD_Y * TILEMAP_WIDTH + RESONANCE_HUD_X)
	ld c, a
	ldh a, [hAutoBGTransferDest + 1]
	adc HIGH(RESONANCE_HUD_Y * TILEMAP_WIDTH + RESONANCE_HUD_X)
	ld b, a
	ret

; points to fill the meter, your turns of Resonance, frames added to both timing
; windows, and quarters of lost HP the trainer feels, by badges
ResonanceRamp:
	table_width RESONANCE_RAMP_WIDTH
	db  6, 3, 6, 2 ; 0 badges
	db  8, 3, 5, 2 ; 1-2
	db  9, 3, 4, 3 ; 3-4
	db 10, 4, 4, 3 ; 5-6
	db 12, 4, 3, 4 ; 7-8
	assert_table_length 5

; Brock's badge unlocks Resonance, and the Pokemon you are closest to reaches a
; resonant Bond, so it can be the first to Resonate.
UnlockResonance::
	SetEvent EVENT_RESONANCE_UNLOCKED
	ld a, [wPartyCount]
	and a
	ret z
	ld c, a
	ld hl, wPartyMon1Bond
	ld de, PARTYMON_STRUCT_LENGTH
	ld b, 0 ; highest so far
	push hl ; closest so far
.loop
	ld a, [hl]
	cp b
	jr c, .next
	ld b, a
	pop af
	push hl
.next
	add hl, de
	dec c
	jr nz, .loop
	pop hl
	ld a, [hl]
	cp BOND_RESONANT
	ret nc
	ld [hl], BOND_RESONANT
	ret
