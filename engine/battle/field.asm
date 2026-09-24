; Battle environments and Field States: moves change the battlefield.
;
; Every battle takes place somewhere (wFieldEnv, worked out from the map when
; the battle starts). A move can leave a Field State behind for a few turns
; that changes what other moves do, and the next field-changing move replaces
; it, so a battle becomes a tug-of-war over the arena:
;
;   SOAK  a damaging Water move           Electric x1.5, Fire x1/2
;   ICE!  an Ice move on SOAK, or in snow Ice x1.5, physical moves may slip
;   FIRE  a Fire move in grass            Fire x1.5, non-Fire Pokemon singe each
;                                         turn; a Water move puts it out
;   DUG!  Dig                             the next Ground or Rock move x1.5
;   RUBL  Earthquake or Rock Slide in a cave  the next attack on the side that
;                                         made it may be blocked
;   DUST  Sand-Attack or Gust on sand     non-Rock, non-Ground attacks may miss
;   ZAP!  an Electric move in the Power Plant  the next Electric move x2, with
;                                         recoil
;   DARK  Smokescreen or Night Shade in the Pokemon Tower  every attack may
;                                         miss, but Ghost attacks always hit
;
; The strengths grow with badges (FieldRamp). Nothing prints a message: the
; environment and state are a four-letter label in the empty tiles of the
; enemy's HUD (lowercase for the place, capitals for a state). Link battles
; have no field, since the two players stand in different places.
; See docs/field-states-design.md.

DEF FIELD_LABEL_X EQU 8 ; right of the enemy's level
DEF FIELD_LABEL_Y EQU 1
DEF FIELD_LABEL_LENGTH EQU 4
DEF FIELD_RUBBLE_BLOCK EQU 50 percent
DEF FIELD_SINGE_SHIFT EQU 4 ; a burning field takes 1/16 of max HP a turn
DEF FIELD_JUST_USED EQU 7 ; wFieldOwner: the move now being used spent a state

; a row of FieldRamp
	rsreset
DEF FIELD_RAMP_BOOST rb ; quarters a boosted move deals: 5 is x1.25, 6 x1.5
DEF FIELD_RAMP_MISS  rb ; chance a slip, dust or the dark makes a move miss
DEF FIELD_RAMP_TURNS rb ; turns a Field State lasts
DEF FIELD_RAMP_WIDTH EQU _RS

; Called at the end of InitBattleVariables: where is this battle?
InitBattleField::
	ld a, [wWalkBikeSurfState]
	cp 2 ; surfing
	ld b, ENV_WATER
	jr z, .store
	ld a, [wCurMap]
	cp POWER_PLANT
	ld b, ENV_PLANT
	jr z, .store
	cp POKEMON_TOWER_1F
	jr c, .notTower
	cp POKEMON_TOWER_7F + 1
	ld b, ENV_TOWER
	jr c, .store
.notTower
	cp SEAFOAM_ISLANDS_1F
	ld b, ENV_SNOW
	jr z, .store
	cp SEAFOAM_ISLANDS_B1F
	jr c, .notSeafoam
	cp SEAFOAM_ISLANDS_B4F + 1
	jr c, .store
.notSeafoam
	cp ROUTE_17 ; Cycling Road
	ld b, ENV_SAND
	jr z, .store
	ld a, [wCurMapTileset]
	cp CAVERN
	ld b, ENV_CAVE
	jr z, .store
	cp OVERWORLD
	ld b, ENV_GRASS
	jr z, .store
	cp FOREST
	jr z, .store
	ld b, ENV_INDOOR
.store
	ld a, b
	ld [wFieldEnv], a
	xor a
	ld [wFieldState], a
	ld [wFieldTurns], a
	ret

; nz in a link battle
IsLinkBattle:
	ld a, [wLinkState]
	cp LINK_STATE_BATTLING
	jr nz, .notLinked
	and a ; nz
	ret
.notLinked
	xor a
	ret

; hl = the row of FieldRamp for the badges you have
GetFieldRamp:
	call GetBadgeRow
	ld hl, FieldRamp
	ld bc, FIELD_RAMP_WIDTH
	jp AddNTimes

; d = the attacking move's type, e = its number, b = its power
GetFieldMove:
	ld hl, wPlayerMoveNum
	ldh a, [hWhoseTurn]
	and a
	jr z, .gotMove
	ld hl, wEnemyMoveNum
.gotMove
	ASSERT wPlayerMovePower == wPlayerMoveNum + 2
	ASSERT wPlayerMoveType == wPlayerMoveNum + 3
	ASSERT wEnemyMovePower == wEnemyMoveNum + 2
	ASSERT wEnemyMoveType == wEnemyMoveNum + 3
	ld e, [hl] ; number
	inc hl
	inc hl ; skip the effect
	ld b, [hl] ; power
	inc hl
	ld d, [hl] ; type
	ret

; Called by the damage code once a fresh attack's damage and hit test are in:
; the field can change the damage, or make the attack miss.
ApplyFieldToAttack::
	call IsLinkBattle
	ret nz
	call ApplyTechniques
	ld a, [wFieldState]
	and a
	ret z
	call GetFieldMove
	ld a, [wFieldState]
	cp FIELD_SOAKED
	jr z, .soaked
	cp FIELD_FROZEN
	jr z, .frozen
	cp FIELD_BURNING
	jr z, .burning
	cp FIELD_TUNNELS
	jr z, .tunnels
	cp FIELD_RUBBLE
	jr z, .rubble
	cp FIELD_SANDSTORM
	jr z, .sandstorm
	cp FIELD_OVERCHARGE
	jr z, .overcharge
	; FIELD_BLACKOUT: Ghost attacks always find their mark, anything else may miss
	ld a, d
	cp GHOST
	jp nz, FieldMissRoll
	xor a
	ld [wMoveMissed], a
	ret

.soaked
	ld a, d
	cp ELECTRIC
	jp z, FieldBoost
	cp FIRE
	ret nz
	jp FieldHalve

.frozen
	ld a, d
	cp ICE
	jp z, FieldBoost
	cp SPECIAL ; the types that were physical in Gen 1 are the ones that slip
	ret nc
	jp FieldMissRoll

.burning
	ld a, d
	cp FIRE
	ret nz
	jp FieldBoost

.tunnels
	ld a, d
	cp GROUND
	jr z, .useTunnels
	cp ROCK
	ret nz
.useTunnels
	call UseUpField
	jp FieldBoost

.rubble
	; the side that made the rubble shelters behind it, once
	ldh a, [hWhoseTurn]
	ld b, a
	ld a, [wFieldOwner]
	and 1 ; the side
	cp b
	ret z ; your own attack
	call UseUpField
	ld a, [wMoveMissed]
	and a
	ret nz
	call Random ; BattleRandom is in another bank, and fields are never linked
	cp FIELD_RUBBLE_BLOCK
	ret nc
	ld a, 1
	ld [wMoveMissed], a
	ret

.sandstorm
	ld hl, wBattleMonType1
	ldh a, [hWhoseTurn]
	and a
	jr z, .gotAttackerTypes
	ld hl, wEnemyMonType1
.gotAttackerTypes
	ld a, [hli]
	cp ROCK
	ret z
	cp GROUND
	ret z
	ld a, [hl]
	cp ROCK
	ret z
	cp GROUND
	ret z
	jp FieldMissRoll

.overcharge
	ld a, d
	cp ELECTRIC
	ret nz
	call UseUpField
	ld a, [wMoveMissed]
	and a
	ret nz
	; x2, and the user takes a quarter of it, but never faints from it
	ld hl, wDamage
	ld a, [hli]
	ld c, [hl]
	ld b, a
	srl b
	rr c
	srl b
	rr c ; bc = the recoil, a quarter of the damage
	ld hl, wDamage
	ld a, [hli]
	ld l, [hl]
	ld h, a
	add hl, hl
	jr nc, .doubled
	ld hl, $ffff
.doubled
	ld a, h
	ld [wDamage], a
	ld a, l
	ld [wDamage + 1], a
	ld hl, wBattleMonHP
	ldh a, [hWhoseTurn]
	and a
	jr z, .gotUserHP
	ld hl, wEnemyMonHP
.gotUserHP
	inc hl
	ld a, [hl]
	sub c
	ld e, a
	dec hl
	ld a, [hl]
	sbc b
	ld d, a
	jr c, .leaveOne
	or e
	jr nz, .storeHP
.leaveOne
	ld de, 1
.storeHP
	ld a, d
	ld [hli], a
	ld [hl], e
	ret

; wDamage x FIELD_RAMP_BOOST / 4, unless the attack missed
FieldBoost:
	ld a, [wMoveMissed]
	and a
	ret nz
	call GetFieldRamp
	ld a, [hl] ; FIELD_RAMP_BOOST
	sub 4
	ld b, a
	ld hl, wDamage
	ld a, [hli]
	ld l, [hl]
	ld h, a
	ld d, h
	ld e, l
	srl d
	rr e
	srl d
	rr e ; de = a quarter
.add
	add hl, de
	jr c, .capped
	dec b
	jr nz, .add
	jr .store
.capped
	ld hl, $ffff
.store
	ld a, h
	ld [wDamage], a
	ld a, l
	ld [wDamage + 1], a
	ret

; wDamage x1/2, at least 1
FieldHalve:
	ld hl, wDamage
	ld a, [hli]
	ld e, [hl]
	srl a
	rr e
	ld d, a
	or e
	jr nz, .store
	inc e
.store
	ld [hl], e
	dec hl
	ld [hl], d
	ret

; the attack misses with the ramp's chance, unless it already has
FieldMissRoll:
	ld a, [wMoveMissed]
	and a
	ret nz
	call GetFieldRamp
	inc hl
	ld b, [hl] ; FIELD_RAMP_MISS
	call Random ; BattleRandom is in another bank, and fields are never linked
	cp b
	ret nc
	ld a, 1
	ld [wMoveMissed], a
	ret

; Called once a move has been used, hit or not: it may leave a Field State.
FieldAfterMove::
	call IsLinkBattle
	ret nz
	ld hl, wFieldOwner
	bit FIELD_JUST_USED, [hl]
	res FIELD_JUST_USED, [hl]
	ret nz
	call GetFieldMove
	ld a, b
	and a
	jr z, .anyHit ; status moves change the field whether or not they land
	ld a, [wMoveMissed]
	and a
	ret nz
.anyHit
	ld a, [wFieldEnv]
	ld c, a
	ld a, e
	cp DIG
	ld a, FIELD_TUNNELS
	jr z, .setIfAttack
	ld a, e
	cp EARTHQUAKE
	jr z, .rubble
	cp ROCK_SLIDE
	jr z, .rubble
	cp SAND_ATTACK
	jr z, .sand
	cp GUST
	jr z, .sand
	cp SMOKESCREEN
	jr z, .dark
	cp NIGHT_SHADE
	jr z, .dark
	ld a, b
	and a
	ret z ; the rest need a damaging move
	ld a, d
	cp WATER
	ld a, FIELD_SOAKED ; soaks the field, and puts out a fire
	jr z, .set
	ld a, d
	cp ICE
	jr z, .ice
	cp FIRE
	jr z, .fire
	cp ELECTRIC
	ret nz
	ld a, c
	cp ENV_PLANT
	ret nz
	ld a, FIELD_OVERCHARGE
	jr .set
.ice
	ld a, c
	cp ENV_SNOW
	jr z, .freeze
	ld a, [wFieldState]
	cp FIELD_SOAKED
	ret nz
.freeze
	ld a, FIELD_FROZEN
	jr .set
.fire
	ld a, c
	cp ENV_GRASS
	ret nz
	ld a, FIELD_BURNING
	jr .set
.rubble
	ld a, c
	cp ENV_CAVE
	ret nz
	ldh a, [hWhoseTurn]
	ld [wFieldOwner], a
	ld a, FIELD_RUBBLE
	jr .setIfAttack
.sand
	ld a, c
	cp ENV_SAND
	ret nz
	ld a, FIELD_SANDSTORM
	jr .set
.dark
	ld a, c
	cp ENV_TOWER
	ret nz
	ld a, FIELD_BLACKOUT
	jr .set
.setIfAttack
	push af
	ld a, b
	and a
	pop bc
	ret z
	ld a, b
.set
	ld [wFieldState], a
	call GetFieldRamp
	inc hl
	inc hl
	ld a, [hl] ; FIELD_RAMP_TURNS
	ld [wFieldTurns], a
	jr DrawFieldLabel

; A move that spends a state does not leave a new one in the same breath:
; otherwise every Electric move in the Power Plant would recharge the next.
UseUpField:
	ld hl, wFieldOwner
	set FIELD_JUST_USED, [hl]
	; fallthrough

ClearField:
	xor a
	ld [wFieldState], a
	ld [wFieldTurns], a
	jr DrawFieldLabel

; Called at the top of MainInBattleLoop, before fainting is checked: a burning
; field singes, and the state runs down.
FieldNewTurn::
	call IsLinkBattle
	ret nz
	call ImproviseNewTurn
	ld a, [wFieldState]
	and a
	ret z
	cp FIELD_BURNING
	call z, SingeBothSides
	ld hl, wFieldTurns
	dec [hl]
	ret nz
	jr ClearField

SingeBothSides:
	ld hl, wBattleMonHP
	ld de, wBattleMonType1
	call Singe
	ld hl, wEnemyMonHP
	ld de, wEnemyMonType1
	call Singe
	callfar DrawHUDsAndHPBars
	ret

; hl = HP (then max HP 12 bytes on in a battle struct), de = types.
; A Pokemon that is not Fire-type loses 1/16 of its max HP, at least 1.
Singe:
	ld a, [de]
	cp FIRE
	ret z
	inc de
	ld a, [de]
	cp FIRE
	ret z
	ld a, [hli]
	or [hl]
	ret z ; already fainted
	push hl
	ld de, (wBattleMonMaxHP + 1) - (wBattleMonHP + 1)
	add hl, de
	ld a, [hld]
	ld c, a
	ld b, [hl]
	REPT FIELD_SINGE_SHIFT
	srl b
	rr c
	ENDR
	ld a, b
	or c
	jr nz, .gotAmount
	inc c
.gotAmount
	pop hl
	ld a, [hl]
	sub c
	ld [hld], a
	ld a, [hl]
	sbc b
	ld [hl], a
	ret nc
	xor a ; fainted
	ld [hli], a
	ld [hl], a
	ret

; The label in the enemy's HUD: the Field State, or the place if there is none.
; Drawn with the automatic tilemap copy off, so it goes to VRAM as well.
DrawFieldLabel::
	call IsLinkBattle
	ret nz
	ld a, [wFieldState]
	and a
	ld hl, FieldStateLabels - FIELD_LABEL_LENGTH
	jr nz, .gotLabel
	ld a, [wFieldEnv]
	ld hl, FieldEnvLabels
.gotLabel
	ld bc, FIELD_LABEL_LENGTH
	call AddNTimes
	ld d, h
	ld e, l
	ldh a, [hAutoBGTransferDest]
	add LOW(FIELD_LABEL_Y * TILEMAP_WIDTH + FIELD_LABEL_X)
	ld c, a
	ldh a, [hAutoBGTransferDest + 1]
	adc HIGH(FIELD_LABEL_Y * TILEMAP_WIDTH + FIELD_LABEL_X)
	ld b, a
	hlcoord FIELD_LABEL_X, FIELD_LABEL_Y
	ld a, FIELD_LABEL_LENGTH
.loop
	push af
	ld a, [de]
	ld [hli], a
	call PutActionVRAMTile
	inc de
	pop af
	dec a
	jr nz, .loop
	ret

; lowercase for the place
FieldEnvLabels:
	table_width FIELD_LABEL_LENGTH
	db "room" ; ENV_INDOOR
	db "leaf" ; ENV_GRASS
	db "sea " ; ENV_WATER
	db "cave" ; ENV_CAVE
	db "tomb" ; ENV_TOWER
	db "snow" ; ENV_SNOW
	db "sand" ; ENV_SAND
	db "wire" ; ENV_PLANT
	assert_table_length NUM_ENVS

; capitals for a Field State, from FIELD_SOAKED on
FieldStateLabels:
	table_width FIELD_LABEL_LENGTH
	db "SOAK" ; FIELD_SOAKED
	db "ICE!" ; FIELD_FROZEN
	db "FIRE" ; FIELD_BURNING
	db "DUG!" ; FIELD_TUNNELS
	db "RUBL" ; FIELD_RUBBLE
	db "DUST" ; FIELD_SANDSTORM
	db "ZAP!" ; FIELD_OVERCHARGE
	db "DARK" ; FIELD_BLACKOUT
	assert_table_length NUM_FIELD_STATES - 1

; boosts, the chance a slip, dust or the dark makes a move miss, and turns
FieldRamp:
	table_width FIELD_RAMP_WIDTH
	db 5, 10 percent, 5 ; 0 badges
	db 5, 15 percent, 5 ; 1-2
	db 6, 20 percent, 5 ; 3-4
	db 6, 25 percent, 4 ; 5-6
	db 6, 25 percent, 4 ; 7-8
	assert_table_length 5
