"""simulation.py 테스트. 실행: py -m unittest discover -s KWB/src/test/python"""
import os
import random
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from types import SimpleNamespace

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "main", "resources", "static")
sys.path.insert(0, os.path.abspath(STATIC_DIR))

import simulation as sim  # noqa: E402


def player(key, outcome="k", starter_innings=9, steal_attempt=0.0, steal_success=0.0, wp_factor=1.0,
           advance_factor=None):
    return SimpleNamespace(key=key, outcome=outcome, starter_innings=starter_innings,
                           steal_attempt=steal_attempt, steal_success=steal_success, wp_factor=wp_factor,
                           advance_factor=advance_factor or {})


class ScriptedModel:
    """타자마다 정해진 결과만 내는 모델. 타석 순서를 기록한다."""

    def __init__(self, wp_pb_rate=0.0, wp_share=0.5):
        self.plate_appearances = []
        self.wp_pb_rate = wp_pb_rate
        self.wp_share = wp_share

    def outcome_table(self, batter, pitcher, park_factor=1.0):
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

    def test_reach_on_error_rate_decides_whether_in_play_out_becomes_error(self):
        always = sim.advance_runners("out", [False, False, True], 0, random.Random(0), reach_on_error=1.0)
        never = sim.advance_runners("out", [False, False, False], 0, random.Random(0), reach_on_error=0.0)
        self.assertEqual(always, (1, [True, False, False], 0))
        self.assertEqual(never, (0, [False, False, False], 1))

    def test_runner_identity_is_preserved_across_advances(self):
        # 1루 주자가 단타로 2루 또는 3루까지 가면, 거기 남는 건 "진루 여부"가 아니라 "그 선수 본인"이어야
        # 다음 타석에서 그 선수의 advance_factor 를 찾을 수 있다 (어느 베이스로 갔는지는 확률적이라 무관).
        first_runner = player("r1")
        _runs, bases, _outs = self.advance("single", [first_runner, False, False])
        self.assertIn(first_runner, bases)

    def test_fast_runner_scores_from_second_on_a_single_more_often(self):
        fast = player("fast", advance_factor={"H24": 3.0})
        slow = player("slow", advance_factor={"H24": 0.1})
        rng = random.Random(1)
        fast_scores = sum(sim.advance_runners("single", [False, fast, False], 0, rng)[0] for _ in range(3000))
        slow_scores = sum(sim.advance_runners("single", [False, slow, False], 0, rng)[0] for _ in range(3000))
        self.assertGreater(fast_scores, slow_scores)

    def test_fast_runner_advances_from_first_to_third_on_a_single_more_often(self):
        fast = player("fast", advance_factor={"H13": 3.0})
        slow = player("slow", advance_factor={"H13": 0.1})
        rng = random.Random(1)

        def reaches_third(runner):
            _runs, bases, _outs = sim.advance_runners("single", [runner, False, False], 0, rng)
            return bases[2] is runner

        fast_thirds = sum(reaches_third(fast) for _ in range(3000))
        slow_thirds = sum(reaches_third(slow) for _ in range(3000))
        self.assertGreater(fast_thirds, slow_thirds)

    def test_fast_runner_advances_from_second_to_third_on_a_ground_out_more_often(self):
        fast = player("fast", advance_factor={"G23": 3.0})
        slow = player("slow", advance_factor={"G23": 0.1})
        rng = random.Random(1)

        def reaches_third(runner):
            _runs, bases, _outs = sim.advance_runners("out", [False, runner, False], 0, rng, reach_on_error=0.0)
            return bases[2] is runner

        fast_thirds = sum(reaches_third(fast) for _ in range(3000))
        slow_thirds = sum(reaches_third(slow) for _ in range(3000))
        self.assertGreater(fast_thirds, slow_thirds)

    def test_factor_is_capped_so_probability_cannot_exceed_one(self):
        # advance_factor 가 아주 커도(예: 데이터 입력 실수) 확률이 1을 넘어 rng 비교가 무의미해지면 안 된다
        reckless = player("r", advance_factor={"H24": 100.0})
        runs, _bases, _outs = sim.advance_runners("single", [False, reckless, False], 0, random.Random(0))
        self.assertEqual(runs, 1)  # 득점은 하되, 예외 없이 정상 동작

    def test_fielding_team_error_rate_is_used_for_opponent_half_innings(self):
        used = []
        original = sim.play_half_inning

        def recording(model, offense, pitcher, rng, runs_to_win=None, reach_on_error=None, steal_odds=None,
                     pb_factor=None, park_factor=None):
            used.append((offense.lineup[0].key[0], reach_on_error, steal_odds, pb_factor, park_factor))
            return 0

        sim.play_half_inning = recording
        try:
            home = sim.TeamPlan("h", [player("h1")], player("h-sp"), [], reach_on_error=0.01, steal_odds=0.8,
                                pb_factor=1.2, park_factor=1.1)
            away = sim.TeamPlan("a", [player("a1")], player("a-sp"), [], reach_on_error=0.05, steal_odds=1.3,
                                pb_factor=0.7, park_factor=0.9)  # 원정팀 구장 요인은 안 쓰인다 (항상 홈팀 구장)
            sim.simulate_game(ScriptedModel(), home, away, random.Random(0))
        finally:
            sim.play_half_inning = original
        # 원정 공격 = 홈 수비, 구장 요인은 둘 다 홈팀(h) 것
        self.assertEqual(set(used), {("a", 0.01, 0.8, 1.2, 1.1), ("h", 0.05, 1.3, 0.7, 1.1)})


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


class StealTest(unittest.TestCase):

    def test_runner_who_reaches_first_steals_second(self):
        runner = player("r", "single", steal_attempt=1.0, steal_success=1.0)
        model = ScriptedModel()
        offense = sim.Offense([runner] + [player(f"k{i}") for i in range(8)])
        sim.play_half_inning(model, offense, player("p"), random.Random(0))
        # 단타 → 도루 성공 → 삼진 3개로 이닝 종료 (도루 실패였다면 삼진 2개로 끝남)
        self.assertEqual(len(model.plate_appearances), 4)

    def test_caught_stealing_adds_an_out(self):
        runner = player("r", "bb", steal_attempt=1.0, steal_success=0.0)
        bases, outs = sim.attempt_steal(runner, [runner, False, True], 1, random.Random(0))
        self.assertEqual((bases, outs), ([False, False, True], 2))

    def test_no_attempt_when_second_base_is_occupied(self):
        runner = player("r", "single", steal_attempt=1.0, steal_success=0.0)
        model = ScriptedModel()
        # 두 번째 타자 단타 때는 2루가 비지만, 첫 타자가 이미 실패했다면 아웃이 늘어난다
        offense = sim.Offense([runner] * 9)
        sim.play_half_inning(model, offense, player("p"), random.Random(0))
        self.assertEqual(len(model.plate_appearances), 3)  # 단타 후 매번 도루 실패 → 3타석에 3아웃

    def test_defense_odds_change_success_rate(self):
        runner = player("r", steal_attempt=1.0, steal_success=0.75)
        rng = random.Random(1)
        strong = sum(sim.attempt_steal(runner, [runner, False, False], 0, rng, 0.5)[1] == 0 for _ in range(4000))
        weak = sum(sim.attempt_steal(runner, [runner, False, False], 0, rng, 2.0)[1] == 0 for _ in range(4000))
        self.assertAlmostEqual(strong / 4000, 0.6, delta=0.03)   # odds 3 × 0.5 = 1.5 → 0.6
        self.assertAlmostEqual(weak / 4000, 6 / 7, delta=0.03)   # odds 3 × 2 = 6 → 0.857

    def test_team_steal_factors_are_regressed_odds_ratios(self):
        factors = sim._team_steal_factors([{"Team": "A", "SB": "60", "CS": "40"},
                                           {"Team": "B", "SB": "90", "CS": "10"}])
        self.assertLess(factors["A"], 1)
        self.assertGreater(factors["B"], 1)
        self.assertGreater(factors["A"], sim._odds(0.6) / sim._odds(0.75))  # 회귀로 관측값보다 1 에 가깝다


class TeamFieldingTest(unittest.TestCase):

    def test_error_factors_are_regressed_and_average_to_league(self):
        rows = [{"Team": "A", "E": "120", "INN": "1200.0"}, {"Team": "B", "E": "80", "INN": "1200.0"}]
        factors = sim._team_rate_factors(rows, "E", sim.ERROR_REG_INN)

        self.assertGreater(factors["A"], 1)
        self.assertLess(factors["A"], 1.2)  # 관측 배수 1.2 보다 리그 평균 쪽으로
        self.assertAlmostEqual((factors["A"] + factors["B"]) / 2, 1.0)

    def test_model_reads_fielding_csv_and_warns_for_missing_team(self):
        folder = tempfile.mkdtemp()
        for name in ("hitters.csv", "pitchers.csv"):
            shutil.copy(os.path.join(STATIC_DIR, name), folder)
        with open(os.path.join(folder, "fielding.csv"), "w", encoding="utf-8") as f:
            f.write("Year,Team,E,INN\n2026,LG,70,1200.0\n2026,KT,110,1200.0\n")
        model = sim.Model(folder)

        self.assertLess(model.reach_on_error("LG"), sim.P_REACH_ON_ERROR)
        self.assertGreater(model.reach_on_error("KT"), sim.P_REACH_ON_ERROR)
        self.assertEqual(model.reach_on_error("두산"), sim.P_REACH_ON_ERROR)
        self.assertEqual(len(model.warnings), 1)

    def test_without_fielding_csv_every_team_uses_league_rate(self):
        model = sim.Model()
        self.assertEqual(model.reach_on_error("LG"), sim.P_REACH_ON_ERROR)
        self.assertEqual(model.warnings, [])


class BaserunningDataTest(unittest.TestCase):

    def folder_with(self, baserunning_csv):
        folder = tempfile.mkdtemp()
        for name in ("hitters.csv", "pitchers.csv"):
            shutil.copy(os.path.join(STATIC_DIR, name), folder)
        with open(os.path.join(folder, "baserunning.csv"), "w", encoding="utf-8") as f:
            f.write(baserunning_csv)
        return folder

    def test_player_with_data_gets_a_factor_regressed_toward_league_average(self):
        # 리그 평균 H24 = (10*0.80 + 10*0.20) / 20 = 0.50. 발 빠른 선수(관측 0.80, 기회 10회)는
        # 표본이 적어 회귀되지만, 그래도 느린 선수보다는 배수가 커야 한다.
        folder = self.folder_with(
            "Year,Team,Player,H24_n,H24_pct\n"
            "2026,LG,박동원,10,80.0\n"
            "2026,LG,오스틴,10,20.0\n")
        model = sim.Model(folder)
        fast = model.batter("LG", "박동원")
        slow = model.batter("LG", "오스틴")
        self.assertGreater(fast.advance_factor["H24"], 1.0)
        self.assertLess(slow.advance_factor["H24"], 1.0)
        self.assertGreater(fast.advance_factor["H24"], slow.advance_factor["H24"])

    def test_player_without_a_row_gets_the_default_factor(self):
        folder = self.folder_with("Year,Team,Player,H24_n,H24_pct\n2026,LG,박동원,10,80.0\n")
        model = sim.Model(folder)
        self.assertEqual(model.batter("LG", "오스틴").advance_factor, {})

    def test_without_baserunning_csv_every_batter_uses_the_fixed_probability(self):
        model = sim.Model()  # 저장소 기본 데이터엔 baserunning.csv 없음
        self.assertEqual(model.batter("LG", "박동원").advance_factor, {})
        self.assertEqual(model.league_baserunning, {})


class WildPitchTest(unittest.TestCase):

    def test_wild_pitch_advance_moves_every_runner_and_scores_third(self):
        self.assertEqual(sim.wild_pitch_advance([True, True, True]), (1, [False, True, True]))
        self.assertEqual(sim.wild_pitch_advance([True, False, False]), (0, [False, True, False]))
        self.assertEqual(sim.wild_pitch_advance([False, False, False]), (0, [False, False, False]))

    def test_play_half_inning_rolls_wp_pb_only_when_runners_on_base(self):
        # 리그 확률 100% 로 두면 주자가 있을 때마다 무조건 발동해, 투수가 아웃을 하나도 못 잡으면
        # (첫 타자 볼넷 이후 나머지는 삼진) 폭투·포일로만 득점이 나야 한다
        model = ScriptedModel(wp_pb_rate=1.0)
        offense = sim.Offense([player("1", "bb")] + [player(f"k{i}", "k") for i in range(8)])
        runs = sim.play_half_inning(model, offense, player("p"), random.Random(0))
        self.assertGreater(runs, 0)

    def test_play_half_inning_never_rolls_when_league_rate_is_zero(self):
        model = ScriptedModel(wp_pb_rate=0.0)
        offense = sim.Offense([player("1", "bb")] + [player(f"k{i}", "k") for i in range(8)])
        runs = sim.play_half_inning(model, offense, player("p"), random.Random(0))
        self.assertEqual(runs, 0)  # 볼넷 한 번으로는 득점 없음 (0아웃 1루) → 폭투·포일 없이는 무득점

    def test_wp_factor_defaults_to_one_without_wp_column(self):
        model = sim.Model()  # 2025 기본 데이터에는 WP 열이 없음 → 폭투 기능 꺼짐
        self.assertEqual(model.pitcher("KT", "고영표").wp_factor, 1.0)
        self.assertEqual(model.wp_pb_rate, 0.0)

    def test_league_pitcher_computes_wp_rate_when_wp_column_present(self):
        rows = [{"IP": "100.0", "TBF": "400", "SO": "80", "BB": "30", "HBP": "5", "H": "90", "HR": "8",
                "WHIP": "1.20", "WP": "6"},
                {"IP": "100.0", "TBF": "400", "SO": "80", "BB": "30", "HBP": "5", "H": "90", "HR": "8",
                "WHIP": "1.20", "WP": "2"}]
        league = sim._league_pitcher(rows)
        self.assertAlmostEqual(league["wp_rate"], 8 / 800)

    def test_wp_pb_baseline_is_zero_without_wp_or_pb_data(self):
        league_pitcher = {"wp": 0.0, "bf": 1000.0}
        rate, share = sim._wp_pb_baseline(league_pitcher, [])
        self.assertEqual(rate, 0.0)

    def test_wp_pb_baseline_combines_pitcher_and_team_totals(self):
        league_pitcher = {"wp": 40.0, "bf": 20000.0}
        fielding = [{"Team": "A", "PB": "10"}, {"Team": "B", "PB": "10"}]
        rate, share = sim._wp_pb_baseline(league_pitcher, fielding)
        self.assertAlmostEqual(rate, (40 + 20) / 20000 * sim.WP_PB_SCALE)
        self.assertAlmostEqual(share, 40 / 60)


class ParkFactorTest(unittest.TestCase):

    def test_hitter_park_scores_more_than_it_allows_on_road(self):
        # A 는 홈에서 원정보다 득점이 많이 남 (타자 친화적), B 는 그 반대
        games = (
            [{"status": "final", "home": "A", "away": "B", "home_score": "6", "away_score": "6"}] * 30
            + [{"status": "final", "home": "B", "away": "A", "home_score": "4", "away_score": "4"}] * 30)
        factors = sim._team_park_factors(games)

        self.assertGreater(factors["A"], 1)
        self.assertLess(factors["B"], 1)

    def test_thin_sample_is_regressed_toward_one(self):
        games = ([{"status": "final", "home": "A", "away": "B", "home_score": "10", "away_score": "10"}]
                 + [{"status": "final", "home": "B", "away": "A", "home_score": "2", "away_score": "2"}])
        factors = sim._team_park_factors(games)

        self.assertAlmostEqual(factors["A"], 1.0, delta=0.05)  # 경기 2개로는 거의 리그 평균

    def test_team_without_both_home_and_away_games_is_skipped(self):
        games = [{"status": "final", "home": "A", "away": "B", "home_score": "5", "away_score": "5"}]
        self.assertEqual(sim._team_park_factors(games), {})  # A 는 원정 경기가, B 는 홈경기가 없음

    def test_park_factor_shifts_hit_probability_without_touching_k_or_bb(self):
        model = sim.Model()
        batter, pitcher = model.batter("LG", "오스틴"), model.pitcher("KT", "고영표")
        neutral = model._build_outcome_table(batter, pitcher, park_factor=1.0)
        hitter_park = model._build_outcome_table(batter, pitcher, park_factor=1.2)

        def prob(table, outcome):
            previous = 0.0
            for cumulative, o in table:
                if o == outcome:
                    return cumulative - previous
                previous = cumulative

        self.assertGreater(prob(hitter_park, "single") + prob(hitter_park, "double")
                           + prob(hitter_park, "triple") + prob(hitter_park, "homerun"),
                           prob(neutral, "single") + prob(neutral, "double")
                           + prob(neutral, "triple") + prob(neutral, "homerun"))
        self.assertAlmostEqual(prob(hitter_park, "k"), prob(neutral, "k"))
        self.assertAlmostEqual(prob(hitter_park, "bb"), prob(neutral, "bb"))

    def test_simulate_game_uses_home_teams_park_for_both_sides(self):
        used = []
        original = sim.Model.outcome_table

        def recording(self, batter, pitcher, park_factor=1.0):
            used.append(park_factor)
            return original(self, batter, pitcher, park_factor)

        sim.Model.outcome_table = recording
        try:
            model = sim.Model()
            home = model.team_plan({"team": "LG", "lineup": ["박동원", "오스틴", "문보경", "오지환", "김현수",
                                    "박해민", "송찬의", "신민재", "구본혁"], "starter": "임찬규"})
            away = model.team_plan({"team": "KT", "lineup": ["김민혁", "강백호", "허경민", "로하스", "장성우",
                                    "황재균", "배정대", "김상수", "권동진"], "starter": "고영표"})
            home = replace(home, park_factor=1.15)
            sim.simulate_game(model, home, away, random.Random(0))
        finally:
            sim.Model.outcome_table = original
        self.assertTrue(used)
        self.assertTrue(all(p == 1.15 for p in used))


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
