; Bond: how close each Pokemon is to you, 0-255.
;
; It lives in the party and box struct's catch rate byte (MON_BOND), which Gen 1
; never reads again once a Pokemon exists: it only becomes the held item when a
; Pokemon is traded to Gen 2. So Bond costs no RAM, and it survives the PC and
; saving. See docs/resonance-design.md.

; Change the Bond of party Pokemon e by d, a signed amount, stopping at 0 and 255.
ChangeBond::
	ld hl, wPartyMon1Bond
	ld a, e
	push de
	ld bc, PARTYMON_STRUCT_LENGTH
	call AddNTimes
	pop de
	ld a, d
	bit 7, a
	jr nz, .lose
	add [hl]
	jr nc, .store
	ld a, MAX_BOND
	jr .store
.lose
	add [hl] ; no carry means it went below 0
	jr c, .store
	xor a
.store
	ld [hl], a
	ret

; Called once a step. Every BOND_STEPS steps, the lead Pokemon that can still
; fight grows a little closer.
StepBond::
	ld a, [wStepCounter]
	and BOND_STEPS - 1
	ret nz
	ld a, [wPartyCount]
	and a
	ret z
	ld hl, wPartyMon1HP
	ld bc, PARTYMON_STRUCT_LENGTH
	ld e, 0
.findLead
	ld a, [hli]
	or [hl]
	jr nz, .gotLead
	dec hl
	add hl, bc
	inc e
	ld a, [wPartyCount]
	cp e
	jr nz, .findLead
	ret ; nobody can fight
.gotLead
	ld d, BOND_WALK
	jr ChangeBond

; Losing still counts: a blackout means the whole team went down fighting, and
; every Pokemon in it comes out closer to you (BOND_LOSS), so a loss is never
; wasted. (The fainted ones have already lost their "took part" flags.)
LosingStillCounts::
	ld e, 0
.loop
	ld a, [wPartyCount]
	cp e
	ret z
	push de
	ld d, BOND_LOSS
	call ChangeBond
	pop de
	inc e
	jr .loop
