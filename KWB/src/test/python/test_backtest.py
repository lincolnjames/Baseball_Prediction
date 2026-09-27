"""backtest.py 테스트. 실행: py -m unittest discover -s KWB/src/test/python"""
import csv
import os
import sys
import unittest

KWB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(KWB_DIR, "backtest"))

import backtest as bt  # noqa: E402


def game(date, home, away, home_score, away_score):
    return {"date": date, "home": home, "away": away, "home_score": home_score, "away_score": away_score}


class MetricsTest(unittest.TestCase):

    def test_coin_flip_has_brier_quarter_and_zero_skill(self):
        m = bt.evaluate([0.5] * 4, [1, 0, 1, 0])
        self.assertAlmostEqual(m["brier"], 0.25)
        self.assertAlmostEqual(m["brier_skill"], 0.0)

    def test_perfect_confident_predictions(self):
        m = bt.evaluate([0.9, 0.1], [1, 0])
        self.assertAlmostEqual(m["brier"], 0.01)
        self.assertEqual(m["accuracy"], 1.0)

    def test_accuracy_skips_undecided_predictions(self):
        m = bt.evaluate([0.5, 0.7, 0.3], [0, 1, 1])
        self.assertEqual(m["accuracy"], 0.5)

    def test_log5_and_home_edge(self):
        self.assertAlmostEqual(bt.log5(0.6, 0.6), 0.5)
        self.assertGreater(bt.log5(0.6, 0.4), 0.6)
        self.assertAlmostEqual(bt.with_home_edge(0.5, 0.04), 0.54)
        self.assertAlmostEqual(bt.with_home_edge(0.6, 0.0), 0.6)

    def test_calibration_buckets(self):
        rows = bt.calibration([0.2, 0.5, 0.52, 0.9], [0, 1, 0, 1])
        self.assertEqual([r["n"] for r in rows], [1, 2, 1])
        self.assertAlmostEqual(rows[1]["actual"], 0.5)


class DataSplitTest(unittest.TestCase):

    def test_snapshot_split_has_no_future_games_in_train(self):
        games = [game("2025-05-20", "LG", "KT", 3, 2), game("2025-05-21", "KT", "LG", 1, 4)]
        train, test = bt.split_games(games, "2025-05-20")
        self.assertEqual([g["date"] for g in train], ["2025-05-20"])
        self.assertEqual([g["date"] for g in test], ["2025-05-21"])

    def test_home_win_rate_ignores_draws(self):
        games = [game("d", "A", "B", 3, 1), game("d", "A", "B", 2, 2), game("d", "A", "B", 0, 1)]
        self.assertAlmostEqual(bt.home_win_rate(games), 0.5)

    def test_pythagorean_favours_team_with_better_run_differential(self):
        train = [game("d", "A", "B", 10, 2), game("d", "B", "A", 1, 8)]
        p_a_home, p_b_home = bt.pythagorean_baseline(train, [game("t", "A", "B", 0, 0), game("t", "B", "A", 0, 0)], 0.0)
        self.assertGreater(p_a_home, 0.9)
        self.assertLess(p_b_home, 0.1)


class RealDataTest(unittest.TestCase):

    def test_default_rosters_have_full_lineups(self):
        rosters = bt.default_rosters()
        self.assertEqual(len(rosters), 10)
        for team, roster in rosters.items():
            self.assertEqual(len(roster["lineup"]), 9, team)
            self.assertIsNotNone(roster["closer"], team)

    def test_collected_games_cover_full_regular_season(self):
        games = bt.load_games()
        self.assertEqual(len(games), 720)  # 10개 팀 × 144경기 ÷ 2

    def test_schedule_home_away_matches_official_results(self):
        official = {(g["date"], g["away"], g["home"]): g["stadium"] for g in bt.load_games()}
        path = os.path.join(bt.STATIC_DIR, "schedule.csv")
        with open(path, encoding="utf-8-sig", newline="") as f:
            schedule = [((r["date"], r["away_team"], r["home_team"]), r["stadium"]) for r in csv.DictReader(f)]

        # 우천 취소 등으로 다른 날 치른 경기를 빼면 대부분 날짜·홈·원정이 그대로 일치해야 한다
        matched = [key for key, _ in schedule if key in official]
        self.assertGreater(len(matched), 0.85 * len(schedule))

        # 홈/원정이 공식 결과와 반대인 경기는 구장 자체가 바뀐 경기여야 한다 (라벨 오류가 아님).
        # 2025년 창원NC파크 사고로 NC 홈경기 16경기가 상대 구장으로 옮겨졌다가 8월에 맞교환됐다.
        swapped = [(key, stadium) for key, stadium in schedule
                   if key not in official and (key[0], key[2], key[1]) in official]
        for (date, away, home), stadium in swapped:
            self.assertIn("NC", (away, home))
            self.assertNotEqual(official[(date, home, away)], stadium, date)


if __name__ == "__main__":
    unittest.main()
