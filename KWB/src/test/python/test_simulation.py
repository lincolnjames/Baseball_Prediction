"""simulation.py 테스트. 실행: py -m unittest discover -s KWB/src/test/python"""
import os
import random
import sys
import unittest
from dataclasses import replace
from types import SimpleNamespace

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "main", "resources", "static")
sys.path.insert(0, os.path.abspath(STATIC_DIR))

import simulation as sim  # noqa: E402


def player(key, outcome="k", starter_innings=9):
    return SimpleNamespace(key=key, outcome=outcome, starter_innings=starter_innings)


class ScriptedModel:
    """타자마다 정해진 결과만 내는 모델. 타석 순서를 기록한다."""

    def __init__(self):
        self.plate_appearances = []

    def outcome_table(self, batter, pitcher):
        self.plate_appearances.append(batter.key)
        return [(1.0, batter.outcome)]


def plan(prefix, outcomes, closer=None):
    lineup = [player(f"{prefix}{i + 1}", o) for i, o in enumerate(outcomes)]
    return sim.TeamPlan(team=prefix, lineup=lineup, starter=player(f"{prefix}-sp"), middle=[], closer=closer)


class GameRulesTest(unittest.TestCase):

    def test_each_team_keeps_its_own_batting_order(self):
        model = ScriptedModel()
        sim.simulate_game(model, plan("h", ["k"] * 9), plan("a", ["k"] * 9), random.Random(0))

        away = [k for k in model.plate_appearances if k.startswith("a")]
        home = [k for k in model.plate_appearances if k.startswith("h")]
        self.assertEqual(away[:4], ["a1", "a2", "a3", "a4"])
        self.assertEqual(home[:4], ["h1", "h2", "h3", "h4"])

    def test_scoreless_game_is_a_draw_after_max_innings(self):
        model = ScriptedModel()
        score = sim.simulate_game(model, plan("h", ["k"] * 9), plan("a", ["k"] * 9), random.Random(0))

        self.assertEqual(score, (0, 0))
        self.assertEqual(len(model.plate_appearances), sim.MAX_INNINGS * 2 * 3)

    def test_bottom_of_ninth_is_skipped_when_home_leads(self):
        model = ScriptedModel()
        home_score, away_score = sim.simulate_game(
            model, plan("h", ["homerun"] + ["k"] * 8), plan("a", ["k"] * 9), random.Random(0))

        self.assertGreater(home_score, away_score)
        home_outs = sum(1 for k in model.plate_appearances if k.startswith("h") and k != "h1")
        self.assertEqual(home_outs, 8 * 3)  # 1~8회말만 공격

    def test_walk_off_ends_half_inning(self):
        model = ScriptedModel()
        offense = sim.Offense([player("h1", "homerun")] * 9)
        runs = sim.play_half_inning(model, offense, player("p"), random.Random(0), runs_to_win=1)

        self.assertEqual(runs, 1)
        self.assertEqual(len(model.plate_appearances), 1)

    def test_closer_pitches_ninth_in_save_situation(self):
        closer = player("closer")
        team = sim.TeamPlan("h", [], player("sp", starter_innings=6), [player("m1"), player("m2")], closer)
        staff = sim.Staff(team, random.Random(0))

        used = [staff.pitcher_for(inning, lead=2).key for inning in range(1, 10)]
        self.assertEqual(used, ["sp"] * 6 + ["m1", "m2", "closer"])

    def test_closer_rests_when_lead_is_large(self):
        team = sim.TeamPlan("h", [], player("sp", starter_innings=8), [player("m1")], player("closer"))
        staff = sim.Staff(team, random.Random(0))

        [staff.pitcher_for(inning, lead=7) for inning in range(1, 9)]
        self.assertEqual(staff.pitcher_for(9, lead=7).key, "m1")


class BaseRunningTest(unittest.TestCase):

    def advance(self, outcome, bases, outs=0):
        return sim.advance_runners(outcome, bases, outs, random.Random(0))

    def test_walk_only_forces_runners(self):
        self.assertEqual(self.advance("bb", [False, True, False]), (0, [True, True, False], 0))
        self.assertEqual(self.advance("bb", [True, False, True]), (0, [True, True, True], 0))
        self.assertEqual(self.advance("bb", [True, True, True]), (1, [True, True, True], 0))

    def test_extra_base_hits_clear_bases(self):
        self.assertEqual(self.advance("homerun", [True, True, True]), (4, [False, False, False], 0))
        self.assertEqual(self.advance("triple", [True, True, False]), (2, [False, False, True], 0))

    def test_strikeout_adds_out_without_moving_runners(self):
        self.assertEqual(self.advance("k", [True, False, True], 1), (0, [True, False, True], 2))


class ModelTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.model = sim.Model()

    def test_innings_notation(self):
        self.assertAlmostEqual(sim.innings(58.2), 58 + 2 / 3)
        self.assertAlmostEqual(sim.innings(61.1), 61 + 1 / 3)

    def test_same_name_players_are_resolved_by_team(self):
        kt = self.model.batter("KT", "김민혁")
        doosan = self.model.batter("두산", "김민혁")

        self.assertEqual((kt.hand, doosan.hand), ("L", "R"))
        self.assertNotEqual(kt.rates, doosan.rates)
        self.assertEqual(self.model.warnings, [])

    def test_ambiguous_or_unknown_player_uses_league_average_with_warning(self):
        model = sim.Model()
        unknown = model.batter("LG", "없는선수")

        self.assertAlmostEqual(unknown.rates["h"], model.league_batter["h"])
        self.assertEqual(len(model.warnings), 1)

    def test_outcome_probabilities_sum_to_one(self):
        table = self.model.outcome_table(self.model.batter("LG", "오스틴"), self.model.pitcher("KT", "고영표"))
        self.assertAlmostEqual(table[-1][0], 1.0)
        self.assertEqual([o for _, o in table], ["k", "bb", "single", "double", "triple", "homerun", "out"])

    def test_better_hitter_gets_more_hits_against_neutral_pitcher(self):
        # 투수 유형을 모르는 가상 투수 → 플래툰 효과 없이 타자 능력만 비교
        pitcher = sim.Model().pitcher("X", "가상투수")
        good = self._probs(self.model.batter("LG", "박동원"), pitcher)   # 타율 .316
        weak = self._probs(self.model.batter("LG", "신민재"), pitcher)   # 타율 .200
        self.assertGreater(good["hit"], weak["hit"])

    def test_left_handed_batter_gains_against_submarine(self):
        submarine = self.model.pitcher("KT", "고영표")  # 우언
        self.assertEqual(submarine.ptype, "U")
        # 같은 투수에서 유형 정보만 뺀 비교 대상 (캐시 키가 겹치지 않도록 key 도 바꾼다)
        untyped = replace(submarine, key=("KT", "고영표-유형없음"), ptype=None)
        lefty = self.model.batter("LG", "신민재")  # 좌타

        self.assertGreater(self._probs(lefty, submarine)["hit"], self._probs(lefty, untyped)["hit"])

    def _probs(self, batter, pitcher):
        table = self.model.outcome_table(batter, pitcher)
        probs, previous = {}, 0.0
        for cumulative, outcome in table:
            probs[outcome] = cumulative - previous
            previous = cumulative
        probs["hit"] = sum(probs[t] for t in ("single", "double", "triple", "homerun"))
        return probs

    def test_league_average_teams_score_like_the_league(self):
        league_era = self._league_era()
        average_team = {"team": "X", "lineup": [f"평균{i}" for i in range(9)], "starter": "평균투수",
                        "middle": ["평균계투"], "closer": None}
        result = sim.run({"home": average_team, "away": average_team, "match_count": 5000, "seed": 7})

        runs_per_game = (result["home_avg_score"] + result["away_avg_score"]) / 2
        target = league_era * 1.08  # 비자책점 포함
        self.assertAlmostEqual(runs_per_game, target, delta=0.3)
        self.assertLess(result["draw_rate"], 0.06)

    def _league_era(self):
        import csv
        with open(os.path.join(STATIC_DIR, "pitchers.csv"), encoding="utf-8-sig") as f:
            rows = [r for r in csv.DictReader(f) if r["IP"] and r["ERA"]]
        ip = [sim.innings(float(r["IP"])) for r in rows]
        return sum(float(r["ERA"]) * i for r, i in zip(rows, ip)) / sum(ip)


class RunTest(unittest.TestCase):

    def test_run_is_reproducible_with_seed(self):
        lg = {"team": "LG", "lineup": ["박동원", "오스틴", "문보경", "오지환", "김현수", "박해민", "송찬의", "신민재", "구본혁"],
              "starter": "임찬규", "middle": [], "closer": None}
        kt = {"team": "KT", "lineup": ["김민혁", "강백호", "허경민", "로하스", "장성우", "황재균", "배정대", "김상수", "권동진"],
              "starter": "고영표", "middle": [], "closer": None}
        args = {"home": lg, "away": kt, "match_count": 300, "seed": 42}

        first, second = sim.run(args), sim.run(args)
        first.pop("elapsed_time"), second.pop("elapsed_time")
        self.assertEqual(first, second)
        self.assertEqual(first["home_win_count"] + first["away_win_count"] + first["draw_count"], 300)

    def test_lineup_must_have_nine_batters(self):
        bad = {"team": "LG", "lineup": ["박동원"], "starter": "임찬규"}
        with self.assertRaises(ValueError):
            sim.run({"home": bad, "away": bad, "match_count": 1})


if __name__ == "__main__":
    unittest.main()
