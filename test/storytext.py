"""Print every story text box the Sync rewrite changed, and read it back.

Each changed label is printed through the game's own text engine (Story's
print_text), with B pressed to page through it, and every line the source
says it prints has to appear in the text box, spelled exactly as written:
nothing cut off, wrapped or garbled.

Usage:
    python test/storytext.py [pokered_debug.gbc pokered_debug.sym]
"""
import sys

from actioncheck import check, failures
from debugbattle import tap
from story import Story

# Every label the story rewrite changed (git diff c87e89e8 a77f6996 -- text).
LABELS = """
_CeruleanCityRivalPreBattleText _CeruleanCityRivalDefeatedText _CeruleanCityRivalVictoryText
_ChampionsRoomRivalIntroText _ChampionsRoomRivalAfterBattleText _ChampionsRoomOakDisappointedWithRivalText
_MrFujisHouseMrFujiIThinkThisMayHelpYourQuestText _MrFujisHouseMrFujiPokeFluteExplanationText
_MtMoonB2FRocket1BattleText _MtMoonB2FRocket3AfterBattleText
_OaksLabOak1RaiseYourYoungPokemonText _OaksLabRivalIllTakeYouOnText
_PokemonTower2FRivalWhatBringsYouHereText _PokemonTower2FRivalDefeatedText _PokemonTower2FRivalVictoryText
_PokemonTower7FMrFujiRescueText _PokemonTower7FRocket2BattleText _PokemonTower7FRocket2AfterBattleText
_RocketHideoutB4FGiovanniHopeWeMeetAgainText
_Route12SnorlaxWokeUpText _Route16SnorlaxWokeUpText
_Route22RivalBeforeBattleText1 _Route22RivalBeforeBattleText2 _Route22RivalAfterBattleText2
_SSAnne2FRivalText _SSAnne2FRivalDefeatedText _SSAnne2FRivalVictoryText
_SaffronGymSabrinaText
_SilphCo11FGiovanniText _SilphCo11FGiovanniYouRuinedOurPlansText _SilphCo11FSilphPresidentMasterBallDescriptionText
_SilphCo5FPokemonReport1Text
_SilphCo7FRivalWaitedHereText _SilphCo7FRivalDefeatedText _SilphCo7FRivalVictoryText
_ViridianGymGiovanniPreBattleText _ViridianGymGiovanniPostBattleAdviceText
""".split()


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else "pokered_debug.gbc"
    sym = sys.argv[2] if len(sys.argv) > 2 else "pokered_debug.sym"
    st = Story(rom, sym)
    print(f"player {st.player!r}, rival {st.rival!r}")
    for label in LABELS:
        st.reset()
        st.print_text(label)
        for _ in range(40):
            tap(st.p, "b", hold=4, release=12)
            st.tick(4)
        missing = st.missing(label)
        check(not missing, f"{label}: {len(st.expected(label))} lines"
              + (f", missing {missing}" if missing else ""))
    st.p.stop(save=False)
    if failures:
        print(f"\n{len(failures)} FAILED")
        sys.exit(1)
    print("\nall story text checks passed")


if __name__ == "__main__":
    main()
