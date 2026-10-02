"""scenario.py 테스트 (저장소 기본 2025 데이터 사용). 실행: py -m unittest discover -s KWB/src/test/python"""
import csv
import os
import shutil
import sys
import tempfile
import unittest

STATIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "main", "resources", "static"))
sys.path.insert(0, STATIC_DIR)

import scenario as sc  # noqa: E402
import simulation as sim  # noqa: E402

LG = [("홍창기", "우익수"), ("신민재", "2루수"), ("오스틴", "1루수"), ("문보경", "3루수"), ("김현수", "지명타자"),
      ("박동원", "포수"), ("오지환", "유격수"), ("송찬의", "좌익수"), ("박해민", "중견수")]
KT = [("김민혁", "좌익수"), ("강백호", "지명타자"), ("허경민", "3루수"), ("로하스", "우익수"), ("장성우", "포수"),
      ("황재균", "1루수"), ("배정대", "중견수"), ("김상수", "2루수"), ("권동진", "유격수")]


def team(name, lineup, starter):
    return {"team": name, "starter": starter, "lineup": [{"name": n, "pos": p} for n, p in lineup]}


def args(**overrides):
    base = {"home": team("LG", LG, "임찬규"), "away": team("KT", KT, "고영표"), "seed": 3}
    base.update(overrides)
    return base


class ValidationTest(unittest.TestCase):

    def assert_rejected(self, lineup, message):
        with self.assertRaises(ValueError) as ctx:
            sc.validate_lineup("home", team("LG", lineup, "임찬규"))
        self.assertIn(message, str(ctx.exception))

    def test_lineup_needs_nine_distinct_players_covering_every_field_position(self):
        self.assert_rejected(LG[:8], "9명")
        self.assert_rejected(LG[:8] + [("홍창기", "지명타자")], "같은 선수")
        self.assert_rejected(LG[:8] + [("구본혁", "2루수")], "수비 포지션이 비었습니다: 중견수")
        self.assert_rejected(LG[:8] + [("구본혁", "투수")], "알 수 없는 포지션")

    def test_starter_is_required(self):
        with self.assertRaises(ValueError):
            sc.validate_lineup("home", team("LG", LG, ""))


class RosterTest(unittest.TestCase):

    def test_default_bullpen_excludes_starter_and_uses_relievers(self):
        roster = sc.Roster(STATIC_DIR)
        closer, middle = roster.default_bullpen("LG", "임찬규")
        self.assertIsNotNone(closer)
        self.assertEqual(len(middle), sc.MIDDLE_RELIEVERS)
        self.assertNotIn("임찬규", [closer] + middle)
        self.assertNotIn(closer, middle)

    def test_candidates_follow_positions_when_available(self):
        folder = tempfile.mkdtemp()
        for name in ("hitters.csv", "pitchers.csv"):
            shutil.copy(os.path.join(STATIC_DIR, name), folder)
        with open(os.path.join(folder, "positions.csv"), "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Year", "Team", "Player", "POS", "G", "GS", "INN"])
            writer.writerows([[2025, "LG", "박동원", "포수", 40, 38, "300.0"],
                              [2025, "LG", "이주헌", "포수", 12, 6, "60.0"],
                              [2025, "LG", "구본혁", "유격수", 20, 10, "90.0"]])
        roster = sc.Roster(folder)
        lineup_names = {n for n, _ in LG}

        self.assertEqual([n for n, _ in roster.candidates("LG", "포수", lineup_names)], ["이주헌"])
        self.assertEqual([n for n, _ in roster.candidates("LG", "유격수", lineup_names)], ["구본혁"])
        # 지명타자 자리는 포지션과 무관하게 타석 수 순
        dh = roster.candidates("LG", sc.DH, lineup_names)
        self.assertEqual(len(dh), sc.CANDIDATES_PER_SLOT)
        self.assertTrue(all(n not in lineup_names for n, _ in dh))

    def test_rest_probability_is_bounded(self):
        roster = sc.Roster(STATIC_DIR)
        for name, _ in LG:
            p = roster.rest_probability("LG", name)
            self.assertGreaterEqual(p, sc.REST_PROB_RANGE[0])
            self.assertLessEqual(p, sc.REST_PROB_RANGE[1])


class AnalyzeTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.result = sc.analyze(args())

    def test_result_shape_and_bounds(self):
        r = self.result
        self.assertEqual(len(r["slots"]), 18)
        self.assertTrue(0 < r["base"]["home"] < 1)
        low, high = r["range_home"]
        self.assertLessEqual(low, r["expected_home"])
        self.assertLessEqual(r["expected_home"], high)
        for slot in r["slots"]:
            if slot["replacements"]:
                self.assertAlmostEqual(sum(o["share"] for o in slot["replacements"]), 1.0)
        self.assertEqual(r["warnings"], [])

    def test_is_reproducible_with_seed(self):
        again = sc.analyze(args())
        self.assertEqual(again["base"], self.result["base"])
        self.assertEqual(again["range_home"], self.result["range_home"])

    def test_swap_effect_signs_follow_team_side(self):
        # 같은 교체라도 홈팀이면 홈 승률에 +, 원정팀이면 - 로 반영된다
        for slot in self.result["slots"]:
            for o in slot["replacements"]:
                sign = 1 if slot["side"] == "home" else -1
                self.assertAlmostEqual(o["delta_home"], sign * o["runs"] * self.result["win_per_run"])

    def test_calculated_swap_effect_matches_large_simulation(self):
        # 효과가 가장 큰 교체를 골라 4만 경기씩 시뮬레이션한 차이와 비교 (시뮬레이션 오차 약 ±0.35%p)
        slot, option = max(((s, o) for s in self.result["slots"] for o in s["replacements"]),
                           key=lambda so: abs(so[1]["delta_home"]))
        spec = args()
        model = sim.Model(sim.DATA_DIR)
        roster = sc.Roster(sim.DATA_DIR)
        plans = {side: sc.build_plan(model, roster, spec[side]) for side in ("home", "away")}
        swapped = sc.swap_lineup(plans[slot["side"]], slot["order"] - 1, model.batter(slot["team"], option["name"]))
        home, away = (swapped, plans["away"]) if slot["side"] == "home" else (plans["home"], swapped)

        base = sc.win_probability(model, plans["home"], plans["away"], 40000, 11)["home"]
        changed = sc.win_probability(model, home, away, 40000, 12)["home"]
        self.assertAlmostEqual(changed - base, option["delta_home"], delta=0.009)


class OptimizeTest(unittest.TestCase):

    def test_result_shape(self):
        r = sc.optimize(args(target="home"))
        self.assertEqual(r["mode"], "optimize")
        self.assertEqual(r["target"], "home")
        self.assertEqual(len(r["recommended"]["lineup"]), 9)
        self.assertEqual(r["games"], sc.GAMES_OPTIMIZE)

    def test_rejects_unknown_target(self):
        with self.assertRaises(ValueError):
            sc.optimize(args(target="bogus"))

    def test_without_position_data_only_dh_is_recommended(self):
        # 저장소 기본 테스트 데이터엔 positions.csv 가 없다 (has_positions=False). 이 상태에서는
        # "그 포지션을 뛰어본 적 있는지"를 확인할 수 없으므로, 수비 자리(DH 제외)는 추천하면 안 된다.
        for target in ("home", "away"):
            r = sc.optimize(args(target=target))
            self.assertFalse(r["positions_available"])
            for c in r["changes"]:
                self.assertEqual(c["pos"], sc.DH,
                    f"포지션 데이터 없이 수비 자리({c['pos']})에 {c['to']} 를 추천함")

    def test_with_position_data_fielding_changes_require_a_recorded_start(self):
        folder = tempfile.mkdtemp()
        for name in ("hitters.csv", "pitchers.csv"):
            shutil.copy(os.path.join(STATIC_DIR, name), folder)
        with open(os.path.join(folder, "positions.csv"), "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Year", "Team", "Player", "POS", "G", "GS", "INN"])
            # 주전은 각자 자기 자리만 뛴 것으로 기록하고, 벤치 후보 "구본혁"은 1루수만 뛰어본 것으로 기록한다
            # (유격수·3루수 등 다른 자리로는 단 한 번도 선발 출장한 적이 없다)
            writer.writerows([2025, "LG", n, p, 100, 100, "900.0"] for n, p in LG)
            writer.writerow([2025, "LG", "구본혁", "1루수", 20, 15, "120.0"])
        roster = sc.Roster(folder)
        self.assertTrue(roster.has_positions)

        r = sc.optimize(args(data_dir=folder, target="home"))
        for c in r["changes"]:
            if c["to"] == "구본혁":
                self.assertEqual(c["pos"], "1루수", "1루수만 뛰어본 선수를 다른 수비 자리로 추천함")

    def test_changes_are_always_positive_for_the_target_side(self):
        # target 이 원정팀이어도 추천된 교체는 "원정팀 자신" 기준으로 득점·승률에 도움이 되어야 한다
        for target in ("home", "away"):
            r = sc.optimize(args(target=target))
            for c in r["changes"]:
                self.assertGreater(c["delta_runs"], 0)
                self.assertGreater(c["delta_win"], 0)

    def test_recommended_lineup_does_not_hurt_either_side(self):
        # 홈/원정 어느 쪽을 최적화하든, 검증 시뮬레이션에서 추천 라인업이 기존보다 뚜렷이 나빠지면 안 된다
        # (부호를 반대로 적용하면 원정팀 추천이 오히려 승률을 깎는 회귀가 생길 수 있다)
        for target in ("home", "away"):
            r = sc.optimize(args(target=target))
            self.assertGreaterEqual(r["recommended"]["win"], r["current"]["win"] - 0.03)

    def test_reapplying_recommendation_does_not_regress(self):
        first = sc.optimize(args(target="home"))
        second_args = args(target="home")
        second_args["home"]["lineup"] = first["recommended"]["lineup"]
        second = sc.optimize(second_args)
        self.assertGreaterEqual(second["recommended"]["win"], second["current"]["win"] - 0.03)


class BattingOrderOptimizeTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.model = sim.Model(STATIC_DIR)
        roster = sc.Roster(STATIC_DIR)
        cls.plans = {side: sc.build_plan(cls.model, roster, team(name, lineup, starter))
                     for side, (name, lineup, starter) in
                     {"home": ("LG", LG, "임찬규"), "away": ("KT", KT, "고영표")}.items()}
        cls.lineup = [{"name": n, "pos": p} for n, p in LG]
        cls.opponent = cls.plans["away"]

    def values(self, lineup):
        return [sc.run_value(self.model, self.model.batter("LG", s["name"]), self.opponent) for s in lineup]

    def test_result_keeps_same_nine_players_sorted_by_run_value_descending(self):
        new_lineup, _changes = sc.optimize_batting_order(self.model, "LG", self.lineup, self.opponent, 0.001)
        self.assertEqual({s["name"] for s in new_lineup}, {n for n, _ in LG})
        values = self.values(new_lineup)
        self.assertEqual(values, sorted(values, reverse=True))

    def test_changes_sum_to_the_total_run_value_shift(self):
        win_per_run = 0.001
        new_lineup, changes = sc.optimize_batting_order(self.model, "LG", self.lineup, self.opponent, win_per_run)
        before = self.values(self.lineup)
        after = self.values(new_lineup)
        expected_total = (sum(v * pa for v, pa in zip(after, sc.PA_BY_ORDER))
                          - sum(v * pa for v, pa in zip(before, sc.PA_BY_ORDER)))
        self.assertAlmostEqual(sum(c["delta_runs"] for c in changes), expected_total)
        for c in changes:
            self.assertAlmostEqual(c["delta_win"], c["delta_runs"] * win_per_run)

    def test_already_sorted_lineup_produces_no_changes(self):
        sorted_lineup, _ = sc.optimize_batting_order(self.model, "LG", self.lineup, self.opponent, 0.001)
        _again, changes = sc.optimize_batting_order(self.model, "LG", sorted_lineup, self.opponent, 0.001)
        self.assertEqual(changes, [])

    def test_optimize_reports_order_changes_with_valid_slots(self):
        r = sc.optimize(args(target="home"))
        self.assertIn("order_changes", r)
        for c in r["order_changes"]:
            self.assertNotEqual(c["from_order"], c["to_order"])
            self.assertIn(c["from_order"], range(1, 10))
            self.assertIn(c["to_order"], range(1, 10))

    def test_reapplying_recommendation_leaves_batting_order_unchanged(self):
        first = sc.optimize(args(target="home"))
        second_args = args(target="home")
        second_args["home"]["lineup"] = first["recommended"]["lineup"]
        second = sc.optimize(second_args)
        self.assertEqual(second["order_changes"], [])


class PredictTest(unittest.TestCase):

    def test_predict_returns_single_probability(self):
        r = sc.predict(args(mode="predict"))
        self.assertEqual(r["mode"], "predict")
        self.assertTrue(0 < r["home"] < 1)
        self.assertEqual(r["games"], sc.GAMES_PREDICT)


if __name__ == "__main__":
    unittest.main()
