"""Play every story scene the Sync rewrite touched, through its real script.

storytext.py proves each changed text box renders; this proves the scripts
around them still run: each scene is set up with only the event flags and
toggleable objects the game would have by then (see story.py), the player
walks onto the trigger tile or talks to the character, and the scene is played
out, battles and all. Then every line the scene should print has to have been
shown, the flags the scene sets have to be set, and the player has to be free
to walk again (or, for the ending, back at the title screen).

Rival battles are played twice, once won and once lost (with a party of one),
since the rival's victory line only shows when he wins.

Usage:
    python test/storyscenes.py [scene ...]
Screenshots of failing scenes go to test/out/scene_<name>.png.
"""
import sys
from pathlib import Path

from actioncheck import check, failures
from debugbattle import tap
from story import MAPS, Story

OUT = Path(__file__).resolve().parent / "out"
SQUIRTLE = 0xB1
SCENES = {}


def scene(fn):
    SCENES[fn.__name__] = fn
    return fn


def expect(st, name, labels=(), events=(), free=True):
    """The scene printed all of `labels`, set `events`, and ended free."""
    ok = True
    for label in labels:
        missing = st.missing(label)
        ok &= not missing
        check(not missing, f"{name}: {label}" + (f" missing {missing}" if missing else ""))
    for event in events:
        ok &= st.has_event(event)
        check(st.has_event(event), f"{name}: {event} set")
    if free:
        ok &= st.idle()
        check(st.idle(), f"{name}: the player can walk again")
    if not ok:
        st.p.screen.image.save(OUT / f"scene_{name}.png")
        print(f"        last text: {st.seen[-6:]}")


def party_of_one(st):
    st.p.memory[st.a("wPartyCount")] = 1
    st.p.memory[st.a("wPartySpecies") + 1] = 0xFF


def rival_setup(st, *events, lose=False, extra=None):
    def setup():
        st.p.memory[st.a("wRivalStarter")] = SQUIRTLE
        for e in events:
            st.event(e)
        if lose:
            party_of_one(st)
        if extra:
            extra()
    return setup


def play(st, name, *, go, labels, events=(), answers=(), win=True, free=True):
    try:
        go()
        st.drive(answers=answers, win=win)
    except AssertionError as e:
        check(False, f"{name}: {e}")
        st.p.screen.image.save(OUT / f"scene_{name}.png")
        return False
    expect(st, name, labels, events, free)
    return True


# --- scenes -------------------------------------------------------------------
@scene
def oaks_lab(st):
    st.reset()
    st.warp("PALLET_TOWN", 10, 2, setup=lambda: party_of_one(st))
    st.walk("up")
    st.drive()  # Oak stops you and walks you to the lab
    st.face("right")
    st.talk()
    st.drive(answers=[True, False])  # take the starter, don't nickname it
    play(st, "oaks_lab", go=lambda: st.walk("down", "down"), answers=[False],
         labels=["_OaksLabRivalIllTakeYouOnText"], events=["EVENT_BATTLED_RIVAL_IN_OAKS_LAB"])
    check(st.battles == 1, "oaks_lab: one rival battle")

    def before_the_parcel():  # the debug save is further along than this
        m = st.p.memory
        m[st.a("wNumBagItems")] = 0
        m[st.a("wBagItems")] = 0xFF
        st.event("EVENT_GOT_POKEDEX", False)
        st.event("EVENT_BEAT_ROUTE22_RIVAL_1ST_BATTLE", False)
    st.at_overworld(before_the_parcel)
    oak_x, oak_y = 5, 2
    x, y = st.pos
    st.walk(*(["left"] * (x - oak_x) + ["right"] * (oak_x - x) + ["up"] * (y - oak_y - 1)))
    st.face("up")
    play(st, "oaks_lab_oak", go=st.talk, labels=["_OaksLabOak1RaiseYourYoungPokemonText"])


def rival_scene(st, name, map_name, start, steps, labels, events, flags=(), extra=None):
    for lose in (False, True):
        st.reset()
        st.battles = 0
        st.warp(map_name, *start, setup=rival_setup(st, *flags, lose=lose, extra=extra))
        tag = f"{name}_{'lost' if lose else 'won'}"
        play(st, tag, go=lambda: st.walk(*steps), win=not lose,
             labels=labels[lose], events=events if not lose else ())
        check(st.battles == 1, f"{tag}: one rival battle")


@scene
def route22(st):
    for n, toggle in (("1ST", "TOGGLE_ROUTE_22_RIVAL_1"), ("2ND", "TOGGLE_ROUTE_22_RIVAL_2")):
        text = "1" if n == "1ST" else "2"
        labels = [f"_Route22RivalBeforeBattleText{text}", f"_Route22Rival{text}DefeatedText"]
        if n == "2ND":
            labels.append("_Route22RivalAfterBattleText2")
        rival_scene(st, f"route22_{n.lower()}", "ROUTE_22", (30, 5), ["left"],
                    (labels, [f"_Route22RivalBeforeBattleText{text}", f"_Route22Rival{text}VictoryText"]),
                    [f"EVENT_BEAT_ROUTE22_RIVAL_{n}_BATTLE"],
                    flags=("EVENT_ROUTE22_RIVAL_WANTS_BATTLE", f"EVENT_{n}_ROUTE22_RIVAL_BATTLE"),
                    extra=lambda t=toggle: st.toggle(t, True))


@scene
def cerulean(st):
    rival_scene(st, "cerulean", "CERULEAN_CITY", (20, 7), ["up"],
                (["_CeruleanCityRivalPreBattleText", "_CeruleanCityRivalDefeatedText"],
                 ["_CeruleanCityRivalPreBattleText", "_CeruleanCityRivalVictoryText"]),
                ["EVENT_BEAT_CERULEAN_RIVAL"], flags=("EVENT_BEAT_CERULEAN_ROCKET_THIEF",))


@scene
def ss_anne(st):
    rival_scene(st, "ss_anne", "SS_ANNE_2F", (36, 9), ["up"],
                (["_SSAnne2FRivalText", "_SSAnne2FRivalDefeatedText"],
                 ["_SSAnne2FRivalText", "_SSAnne2FRivalVictoryText"]),
                [])


@scene
def tower2f(st):
    rival_scene(st, "tower2f", "POKEMON_TOWER_2F", (15, 6), ["up"],
                (["_PokemonTower2FRivalWhatBringsYouHereText", "_PokemonTower2FRivalDefeatedText"],
                 ["_PokemonTower2FRivalWhatBringsYouHereText", "_PokemonTower2FRivalVictoryText"]),
                ["EVENT_BEAT_POKEMON_TOWER_RIVAL"])


@scene
def silph7f(st):
    rival_scene(st, "silph7f", "SILPH_CO_7F", (4, 3), ["left"],
                (["_SilphCo7FRivalWaitedHereText", "_SilphCo7FRivalDefeatedText"],
                 ["_SilphCo7FRivalWaitedHereText", "_SilphCo7FRivalVictoryText"]),
                ["EVENT_BEAT_SILPH_CO_RIVAL"])


def talk_to(st, direction):
    """Face a character next to the player and talk to them."""
    def go():
        st.face(direction)
        st.talk()
    return go


@scene
def tower7f(st):
    st.reset()
    st.warp("POKEMON_TOWER_7F", 10, 10, setup=lambda: [
        st.event("EVENT_BEAT_POKEMONTOWER_7_TRAINER_0"), st.event("EVENT_BEAT_POKEMONTOWER_7_TRAINER_2")])
    # the Rocket at (12, 9) sees the player step into his row
    play(st, "tower7f_rocket", go=lambda: st.walk("up"),
         labels=["_PokemonTower7FRocket2BattleText", "_PokemonTower7FRocket2AfterBattleText"],
         events=["EVENT_BEAT_POKEMONTOWER_7_TRAINER_1"])
    x, y = st.pos
    st.walk(*(["up"] * (y - 4)))
    play(st, "tower7f_fuji", go=talk_to(st, "up"),
         labels=["_PokemonTower7FMrFujiRescueText"], events=["EVENT_RESCUED_MR_FUJI"])
    check(st.map == MAPS["MR_FUJIS_HOUSE"][0], "tower7f_fuji: Mr. Fuji takes you to his house")


@scene
def fujis_house(st):
    st.reset()
    st.warp("MR_FUJIS_HOUSE", 3, 2, setup=lambda: [
        st.event("EVENT_RESCUED_MR_FUJI"), st.toggle("TOGGLE_MR_FUJIS_HOUSE_MR_FUJI", True)])
    play(st, "fujis_house", go=talk_to(st, "up"),
         labels=["_MrFujisHouseMrFujiIThinkThisMayHelpYourQuestText",
                 "_MrFujisHouseMrFujiPokeFluteExplanationText"],
         events=["EVENT_GOT_POKE_FLUTE"])


@scene
def mt_moon(st):
    st.reset()
    # the Rocket at (11, 16) looks down his column
    st.warp("MT_MOON_B2F", 11, 18)
    play(st, "mt_moon_rocket1", go=lambda: None,
         labels=["_MtMoonB2FRocket1BattleText"], events=["EVENT_BEAT_MT_MOON_3_TRAINER_0"])
    st.reset()
    st.warp("MT_MOON_B2F", 29, 10, setup=lambda: st.event("EVENT_BEAT_MT_MOON_3_TRAINER_2"))
    play(st, "mt_moon_rocket3", go=talk_to(st, "down"), labels=["_MtMoonB2FRocket3AfterBattleText"])


@scene
def hideout(st):
    st.reset()
    st.warp("ROCKET_HIDEOUT_B4F", 25, 4)
    play(st, "hideout_giovanni", go=talk_to(st, "up"),
         labels=["_RocketHideoutB4FGiovanniHopeWeMeetAgainText"],
         events=["EVENT_BEAT_ROCKET_HIDEOUT_GIOVANNI"])


@scene
def silph(st):
    st.reset()
    st.warp("SILPH_CO_5F", 22, 13)
    play(st, "silph5f_report", go=talk_to(st, "up"), labels=["_SilphCo5FPokemonReport1Text"])
    st.reset()
    st.warp("SILPH_CO_11F", 7, 13)
    play(st, "silph11f_giovanni", go=lambda: st.walk("up"),
         labels=["_SilphCo11FGiovanniText", "_SilphCo11FGiovanniYouRuinedOurPlansText"],
         events=["EVENT_BEAT_SILPH_CO_GIOVANNI"])
    st.reset()
    st.warp("SILPH_CO_11F", 7, 6, setup=lambda: st.event("EVENT_BEAT_SILPH_CO_GIOVANNI"))
    play(st, "silph11f_president", go=talk_to(st, "up"), labels=[], events=["EVENT_GOT_MASTER_BALL"])
    play(st, "silph11f_president_again", go=talk_to(st, "up"),
         labels=["_SilphCo11FSilphPresidentMasterBallDescriptionText"])


def gym_leader(st, name, map_name, at, labels, events):
    st.reset()
    st.warp(map_name, *at)
    play(st, name, go=talk_to(st, "up"), labels=labels[:1], events=events)
    play(st, f"{name}_again", go=talk_to(st, "up"), labels=labels[1:], free=False)
    st.drive()
    expect(st, f"{name}_again", free=True)


@scene
def sabrina(st):
    gym_leader(st, "sabrina", "SAFFRON_GYM", (9, 9), ["_SaffronGymSabrinaText"], ["EVENT_BEAT_SABRINA"])


@scene
def viridian_gym(st):
    gym_leader(st, "viridian_gym", "VIRIDIAN_GYM", (2, 2),
               ["_ViridianGymGiovanniPreBattleText", "_ViridianGymGiovanniPostBattleAdviceText"],
               ["EVENT_BEAT_VIRIDIAN_GYM_GIOVANNI"])


@scene
def snorlax(st):
    for route, at in (("12", (10, 63)), ("16", (27, 10))):
        st.reset()
        st.battles = 0
        # "Fight" in the frenzy (frenzycheck.py plays the frenzy itself)
        st.warp(f"ROUTE_{route}", *at, setup=lambda r=route: st.event(f"EVENT_FIGHT_ROUTE{r}_SNORLAX"))
        play(st, f"route{route}_snorlax", go=lambda: None,
             labels=[f"_Route{route}SnorlaxWokeUpText"], events=[f"EVENT_BEAT_ROUTE{route}_SNORLAX"])
        check(st.battles == 1, f"route{route}_snorlax: one battle")


@scene
def champion(st):
    """The last battle, Oak, the Hall of Fame, the credits, and the title."""
    reached = set()
    for label in ("HallOfFamePC", "Credits", "Init"):
        st.p.hook_register(*st.s[label], lambda name: reached.add(name), label)
    for lose in (False, True):
        st.reset()
        st.battles = 0
        reached.clear()

        def setup(lose=lose):
            st.p.memory[st.a("wChampionsRoomCurScript")] = 1  # SCRIPT_CHAMPIONSROOM_PLAYER_ENTERS
            st.p.memory[st.a("wRivalStarter")] = SQUIRTLE
            if lose:
                party_of_one(st)
        st.warp("CHAMPIONS_ROOM", 4, 7, last_map="LANCES_ROOM", setup=setup)
        if lose:
            play(st, "champion_lost", go=lambda: None, win=False,
                 labels=["_ChampionsRoomRivalIntroText", "_RivalVictoryText"])
            check("Credits" not in reached, "champion_lost: no credits")
            continue
        try:
            st.drive(frames=80000, until=lambda: "Init" in reached)
        except AssertionError as e:
            check(False, f"champion: {e}")
        expect(st, "champion", ["_ChampionsRoomRivalIntroText", "_RivalDefeatedText",
                                "_ChampionsRoomRivalAfterBattleText",
                                "_ChampionsRoomOakDisappointedWithRivalText", "_HallOfFameOakText"],
               free=False)
        check(st.battles == 1, "champion: one battle")
        for label in ("HallOfFamePC", "Credits", "Init"):
            check(label in reached, f"champion: reached {label}")


def main():
    names = sys.argv[1:] or list(SCENES)
    OUT.mkdir(exist_ok=True)
    st = Story()
    print(f"player {st.player!r}, rival {st.rival!r}")
    for name in names:
        print(f"-- {name}")
        SCENES[name](st)
    st.p.stop(save=False)
    if failures:
        print(f"\n{len(failures)} FAILED")
        sys.exit(1)
    print("\nall story scenes passed")


if __name__ == "__main__":
    main()
