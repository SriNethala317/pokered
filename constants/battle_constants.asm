DEF MAX_LEVEL EQU 100

; maximum moves known per mon
DEF NUM_MOVES EQU 4

; significant stat values
DEF BASE_STAT_LEVEL EQU 7
DEF MAX_STAT_LEVEL EQU 13

; VitaminStats indexes (see data/battle/stat_names.asm)
	const_def 1
	const STAT_HEALTH
	const STAT_ATTACK
	const STAT_DEFENSE
	const STAT_SPEED
	const STAT_SPECIAL
DEF NUM_STATS EQU const_value - 1

; StatModTextStrings indexes (see data/battle/stat_mod_names.asm)
	const_def
	const MOD_ATTACK
	const MOD_DEFENSE
	const MOD_SPEED
	const MOD_SPECIAL
	const MOD_ACCURACY
	const MOD_EVASION
	const_skip 2
DEF NUM_STAT_MODS EQU const_value

; Moves struct fields (see data/moves/moves.asm)
rsreset
DEF MOVE_ANIM   rb
DEF MOVE_EFFECT rb
DEF MOVE_POWER  rb
DEF MOVE_TYPE   rb
DEF MOVE_ACC    rb
DEF MOVE_PP     rb
DEF MOVE_LENGTH EQU _RS

; battle classes (wIsInBattle values)
	const_def 1
	const WILD_BATTLE
	const TRAINER_BATTLE
DEF LOST_BATTLE EQU $FF

; battle type constants (wBattleType values)
	const_def
	const BATTLE_TYPE_NORMAL  ; 0
	const BATTLE_TYPE_OLD_MAN ; 1
	const BATTLE_TYPE_SAFARI  ; 2

; damage limits before type effectiveness
DEF MIN_NEUTRAL_DAMAGE EQU 2
DEF MAX_NEUTRAL_DAMAGE EQU 999

; fixed damage constants
DEF SONICBOOM_DAMAGE   EQU 20
DEF DRAGON_RAGE_DAMAGE EQU 40

; type effectiveness factors, scaled by 10
DEF SUPER_EFFECTIVE    EQU 20
DEF MORE_EFFECTIVE     EQU 15
DEF EFFECTIVE          EQU 10
DEF NOT_VERY_EFFECTIVE EQU 05
DEF NO_EFFECT          EQU 00

; non-volatile statuses
DEF SLP_MASK EQU %111 ; 0-7 turns
	const_def 3
	const PSN ; 3
	const BRN ; 4
	const FRZ ; 5
	const PAR ; 6

DEF MAX_STAT_VALUE EQU 999

; which half of a species' entry in SpecialSplitFactors to read
; (see data/pokemon/special_split.asm)
DEF SPECIAL_ATTACK_FACTOR EQU 0
DEF SPECIAL_DEFENSE_FACTOR EQU 1

; trainer dvs
DEF ATKDEFDV_TRAINER EQU $98
DEF SPDSPCDV_TRAINER EQU $88

; wDamageMultipliers
DEF BIT_STAB_DAMAGE EQU 7
DEF EFFECTIVENESS_MASK EQU %01111111

; wPlayerBattleStatus1 or wEnemyBattleStatus1 bit flags
	const_def
	const STORING_ENERGY           ; 0 ; Bide
	const THRASHING_ABOUT          ; 1 ; Thrash, Petal Dance
	const ATTACKING_MULTIPLE_TIMES ; 2 ; e.g. Double Kick, Fury Attack
	const FLINCHED                 ; 3
	const CHARGING_UP              ; 4 ; e.g. Solar Beam, Fly
	const USING_TRAPPING_MOVE      ; 5 ; e.g. Wrap
	const INVULNERABLE             ; 6 ; charging up Fly/Dig
	const CONFUSED                 ; 7

; wPlayerBattleStatus2 or wEnemyBattleStatus2 bit flags
	const_def
	const USING_X_ACCURACY    ; 0
	const PROTECTED_BY_MIST   ; 1
	const GETTING_PUMPED      ; 2 ; Focus Energy
	const_skip                ; 3 ; unused
	const HAS_SUBSTITUTE_UP   ; 4
	const NEEDS_TO_RECHARGE   ; 5 ; Hyper Beam
	const USING_RAGE          ; 6
	const SEEDED              ; 7 ; Leech Seed

; wPlayerBattleStatus3 or wEnemyBattleStatus3 bit flags
	const_def
	const BADLY_POISONED      ; 0 ; Toxic
	const HAS_LIGHT_SCREEN_UP ; 1
	const HAS_REFLECT_UP      ; 2
	const TRANSFORMED         ; 3

; wActionCommandState
	const_def
	const ACTION_COMMAND_IDLE    ; 0
	const ACTION_COMMAND_LEAD_IN ; 1
	const ACTION_COMMAND_WINDOW  ; 2
	const ACTION_COMMAND_CLOSED  ; 3
	const ACTION_COMMAND_BADGE   ; 4

; wActionCommandResult
	const_def
	const ACTION_RESULT_NONE    ; 0
	const ACTION_RESULT_EARLY   ; 1
	const ACTION_RESULT_GOOD    ; 2
	const ACTION_RESULT_PERFECT ; 3

; wActionCommandPattern, chosen by the move's type
	const_def
	const ACTION_PATTERN_TAP    ; 0 one press on the cue
	const ACTION_PATTERN_SNAP   ; 1 one press, in half the time
	const ACTION_PATTERN_HOLD   ; 2 hold the button, let go on the cue
	const ACTION_PATTERN_RAPID  ; 3 three presses
	const ACTION_PATTERN_DOUBLE ; 4 a press on each of two cues

; wActionCommandForceEffect
	const_def
	const ACTION_EFFECT_ROLL    ; 0 the move's secondary effect rolls as usual
	const ACTION_EFFECT_FORCED  ; 1 a perfect attack: it always lands
	const ACTION_EFFECT_BLOCKED ; 2 a perfect brace: it never does

; wActionCommandFoe
	const_def
	const ACTION_FOE_FEINT ; 0 a false cue comes first
	const ACTION_FOE_TIMED ; 1 the trainer times this attack too
	const ACTION_FOE_DODGED ; 2 a Dodge Phase stood in, and you were not hit

; wResonanceFlags, see engine/battle/resonance.asm
DEF RESONANCE_REFUNDS_MASK EQU %111 ; turns the chain has given back
DEF RESONANCE_STUNNED      EQU 6
DEF RESONANCE_ACTIVE       EQU 7

; the Resonance bar in the player's HUD: a cap and 3 segments of 8 pixels
DEF RESONANCE_BAR_TILES  EQU 3
DEF TRAINER_MAX_HP       EQU RESONANCE_BAR_TILES * 8

; wFieldEnv: where the battle is, see engine/battle/field.asm
	const_def
	const ENV_INDOOR ; 0
	const ENV_GRASS  ; 1
	const ENV_WATER  ; 2 surfing
	const ENV_CAVE   ; 3
	const ENV_TOWER  ; 4 the Pokemon Tower, in the dark
	const ENV_SNOW   ; 5 the Seafoam Islands
	const ENV_SAND   ; 6 Cycling Road
	const ENV_PLANT  ; 7 the Power Plant
DEF NUM_ENVS EQU const_value

; wFieldState
	const_def
	const FIELD_NONE       ; 0
	const FIELD_SOAKED     ; 1
	const FIELD_FROZEN     ; 2
	const FIELD_BURNING    ; 3
	const FIELD_TUNNELS    ; 4
	const FIELD_RUBBLE     ; 5
	const FIELD_SANDSTORM  ; 6
	const FIELD_OVERCHARGE ; 7
	const FIELD_BLACKOUT   ; 8
DEF NUM_FIELD_STATES EQU const_value
