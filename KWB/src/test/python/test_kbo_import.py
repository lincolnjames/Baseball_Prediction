"""tools/kbo_import.py 테스트 (가상의 선수 데이터 사용). 실행: py -m unittest discover -s KWB/src/test/python"""
import csv
import os
import sys
import tempfile
import unittest

KWB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(KWB_DIR, "tools"))
sys.path.insert(0, os.path.join(KWB_DIR, "src", "main", "resources", "static"))

import kbo_import as ki  # noqa: E402
import simulation as sim  # noqa: E402

# 가상 선수. 열 구성은 KBO 기록실 기본기록 표와 같다.
HITTER1 = [
    "순위\t선수명\t팀명\tAVG\tG\tPA\tAB\tR\tH\t2B\t3B\tHR\tTB\tRBI\tSAC\tSF",
    "1\t가타자\tKT\t0.300\t100\t400\t350\t50\t105\t20\t2\t10\t159\t50\t2\t3",
    "2\t나타자\tKT\t0.250\t80\t220\t200\t20\t50\t8\t0\t3\t67\t20\t0\t0",
    "3\t다투수\tKT\t-\t1\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0\t0",
]
HITTER2 = [
    "1\t가타자\tKT\t0.300\t40\t1\t5\t70\t8\t0.454\t0.377\t0.831\t30\t0.300\t0.000",
    "2\t나타자\tKT\t0.250\t15\t0\t5\t40\t3\t0.335\t0.318\t0.653\t10\t0.250\t0.000",
    "3\t다투수\tKT\t-\t0\t0\t0\t0\t0\t-\t-\t-\t0\t0.000\t0.000",
]
PITCHER1 = [
    "1\t라투수\tKT\t3.00\t20\t8\t5\t0\t0\t0.615\t120\t110\t10\t30\t5\t100\t45\t40\t1.17",
    "2\t마투수\tKT\t4.46\t40\t2\t2\t10\t5\t0.500\t40 1/3\t40\t4\t15\t2\t35\t22\t20\t1.36",
]
PITCHER2 = [
    "1\t라투수\tKT\t3.00\t0\t0\t10\t0\t500\t1900\t0.239\t20\t2\t3\t2\t0\t3\t0",
    "2\t마투수\tKT\t4.46\t0\t0\t0\t2\t175\t700\t0.256\t8\t1\t1\t1\t1\t1\t0",
]


def write_folder(files):
    folder = tempfile.mkdtemp()
    for name, lines in files.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return folder


def complete_folder(**overrides):
    files = {"h1.txt": HITTER1, "h2.txt": HITTER2, "p1.txt": PITCHER1, "p2.txt": PITCHER2}
    files.update(overrides)
    return write_folder(files)


class ParsingTest(unittest.TestCase):

    def test_innings_notation(self):
        self.assertEqual(ki.innings_outs("56 2/3"), 170)
        self.assertEqual(ki.innings_outs("2/3"), 2)
        self.assertEqual(ki.innings_outs("44"), 132)
        self.assertEqual(ki.innings_outs("0"), 0)

    def test_tables_are_detected_by_column_count_regardless_of_file_name(self):
        tables, errors = ki.read_tables(complete_folder())
        self.assertEqual(errors, [])
        self.assertEqual({k: len(v) for k, v in tables.items()},
                         {"hitter1": 3, "hitter2": 3, "pitcher1": 2, "pitcher2": 2})

    def test_merged_lines_from_paste_are_reported(self):
        merged = HITTER2[:1] + [HITTER2[1] + HITTER2[2]]  # 줄바꿈이 빠져 두 줄이 붙은 경우
        _, errors = ki.read_tables(complete_folder(**{"h2.txt": merged}))
        self.assertEqual(len(errors), 1)
        self.assertIn("열 개수", errors[0])


class VerificationTest(unittest.TestCase):

    def test_clean_data_passes_and_converts(self):
        hitters, pitchers, problems, renamed = ki.build(complete_folder(), 2026)

        self.assertEqual(problems, [])
        self.assertEqual(renamed, [])
        self.assertEqual([h["Player"] for h in hitters], ["가타자", "나타자"])  # 타석 0 인 선수 제외
        first = hitters[0]
        self.assertEqual((first["K%"], first["BB%"]), ("17.5", "10.0"))
        mid = next(p for p in pitchers if p["Player"] == "마투수")
        self.assertEqual((mid["IP"], mid["TBF"], mid["HR/9"], mid["WP"]), ("40.1", 175, "0.89", "1"))

    def test_typo_in_a_stat_is_caught(self):
        wrong = list(HITTER2)
        wrong[0] = wrong[0].replace("0.377", "0.387")  # 출루율 오타
        _, _, problems, _ = ki.build(complete_folder(**{"h2.txt": wrong}), 2026)
        self.assertEqual(len(problems), 1)
        self.assertIn("출루율", problems[0])

    def test_missing_page_is_caught(self):
        _, _, problems, _ = ki.build(complete_folder(**{"p2.txt": PITCHER2[:1]}), 2026)
        self.assertEqual(len(problems), 1)
        self.assertIn("1번 표에만 있음", problems[0])

    def test_same_name_in_same_team_is_disambiguated(self):
        twin1 = PITCHER1 + ["3\t라투수\tKT\t4.46\t40\t2\t2\t10\t5\t0.500\t40 1/3\t40\t4\t15\t2\t35\t22\t20\t1.36"]
        twin2 = PITCHER2 + ["3\t라투수\tKT\t4.46\t0\t0\t0\t2\t175\t700\t0.256\t8\t1\t1\t1\t1\t1\t0"]
        _, pitchers, problems, renamed = ki.build(complete_folder(**{"p1.txt": twin1, "p2.txt": twin2}), 2026)

        self.assertEqual(problems, [])
        self.assertEqual(sorted(p["Player"] for p in pitchers), ["라투수(20경기)", "라투수(40경기)", "마투수"])
        self.assertEqual(len(renamed), 2)


SCHEDULE_PAGE = """전체
LGLG
날짜\t시간\t경기\t게임센터\t하이라이트\tTV\t라디오\t구장\t비고
03.28(토)\t14:00\tKT11vs7LG\t리뷰\t하이라이트\tS-T\t\t잠실\t-
14:00\t두산0vs6NC\t리뷰\t하이라이트\tSPO-T
KN-T
SS-T\t\t창원\t-
04.09(목)\t18:30\t키움vs두산\t\t\tSPO-2T\t\t잠실\t우천취소
10.06(화)\t18:30\tNCvsLG\t\t\t\t\t잠실\t-
18:30\t두산vs롯데\t\t\t\t\t사직\t-
"""


class ScheduleTest(unittest.TestCase):

    def test_parses_results_cancellations_and_upcoming_games(self):
        games, problems = ki.parse_schedule_text(SCHEDULE_PAGE, 2026)

        self.assertEqual(problems, [])
        self.assertEqual([(g["date"], g["away"], g["home"], g["status"]) for g in games], [
            ("2026-03-28", "KT", "LG", "final"),
            ("2026-03-28", "두산", "NC", "final"),     # TV 칸 줄바꿈으로 세 줄에 걸친 경기
            ("2026-04-09", "키움", "두산", "우천취소"),
            ("2026-10-06", "NC", "LG", "scheduled"),
            ("2026-10-06", "두산", "롯데", "scheduled"),
        ])
        self.assertEqual((games[0]["away_score"], games[0]["home_score"]), ("11", "7"))
        self.assertEqual(games[1]["stadium"], "창원")

    def test_overlapping_pastes_are_merged(self):
        folder = write_folder({"schedule_1.txt": SCHEDULE_PAGE.splitlines(),
                               "schedule_2.txt": SCHEDULE_PAGE.splitlines()[:4]})  # 첫 경기까지만 겹침
        games, problems, notes = ki.build_schedule(folder, 2026)
        self.assertEqual(problems, [])
        self.assertEqual(len(games), 5)
        self.assertEqual(notes, [])

    def test_unreadable_game_cell_is_reported(self):
        _, problems = ki.parse_schedule_text("03.28(토)\t14:00\tKT11vs7엘지\t리뷰\t잠실\t-", 2026)
        self.assertEqual(len(problems), 2)  # 경기 칸 오류 + 경기 0개
        self.assertIn("경기 칸", problems[0])

    def test_wins_cross_check_between_schedule_and_pitchers(self):
        games, _ = ki.parse_schedule_text(SCHEDULE_PAGE, 2026)
        pitchers = [{"Team": "KT", "W": "1", "L": "0"}, {"Team": "LG", "W": "0", "L": "1"},
                    {"Team": "NC", "W": "1", "L": "0"}, {"Team": "두산", "W": "0", "L": "1"}]
        self.assertEqual(ki.cross_check_wins(games, pitchers), [])

        pitchers[0]["W"] = "2"
        problems = ki.cross_check_wins(games, pitchers)
        self.assertEqual(len(problems), 1)
        self.assertIn("KT", problems[0])


DEFENSE = [
    "1\t가타자\tKT\t2루수\t90\t85\t700\t5\t0\t150\t250\t50\t0.988\t0\t0\t0\t-",
    "2\t나타자\tKT\t포수\t60\t50\t400 1/3\t2\t0\t300\t20\t2\t0.994\t3\t30\t10\t25.0",
    "2\t나타자\tKT\t1루수\t5\t2\t20\t0\t0\t15\t1\t1\t1.000\t0\t0\t0\t-",   # 같은 순위, 다른 포지션
    "3\t라투수\tKT\t투수\t20\t20\t120\t1\t0\t5\t10\t0\t0.938\t0\t0\t0\t-",   # 투수는 제외
    "4\t다투수\tKT\t좌익수\t1\t0\t1\t0\t0\t0\t0\t0\t-\t0\t0\t0\t-",          # 타석 없는 선수는 제외
]


class PositionsTest(unittest.TestCase):

    def test_defense_rows_become_positions_for_hitters(self):
        folder = complete_folder(**{"defense.txt": DEFENSE})
        hitters, _, problems, _ = ki.build(folder, 2026)
        positions, position_problems, notes = ki.build_positions(folder, 2026, hitters)

        self.assertEqual(problems + position_problems, [])
        self.assertEqual(sorted((p["Player"], p["POS"], p["GS"], p["INN"]) for p in positions), [
            ("가타자", "2루수", "85", "700.0"), ("나타자", "1루수", "2", "20.0"), ("나타자", "포수", "50", "400.1")])
        self.assertEqual(notes, [])

    def test_fielding_percentage_typo_is_caught(self):
        wrong = [DEFENSE[0].replace("0.988", "0.978")]
        folder = complete_folder(**{"defense.txt": wrong})
        hitters, _, _, _ = ki.build(folder, 2026)
        _, problems, _ = ki.build_positions(folder, 2026, hitters)
        self.assertEqual(len(problems), 1)
        self.assertIn("수비율", problems[0])

    def test_team_fielding_counts_every_position_including_pitchers(self):
        fielding = ki.build_fielding(complete_folder(**{"defense.txt": DEFENSE}), 2026)
        # 실책 5+2+0+1+0, 수비 아웃 (700 + 400 1/3 + 20 + 120 + 1) × 3 = 3724 → 9개 포지션으로 나눠 414 아웃
        # 허용 도루·도루저지·포일은 포수 줄(나타자)에서만 나온다
        self.assertEqual(fielding, [{"Year": 2026, "Team": "KT", "E": 8, "INN": "138.0", "SB": 30, "CS": 10, "PB": 3}])


RUNNING = [
    "1\t가타자\tKT\t100\t20\t15\t5\t75.0\t2\t0",
    "2\t나타자\tKT\t80\t0\t0\t0\t-\t1\t0",
    "3\t대주자\tKT\t30\t5\t4\t1\t80.0\t0\t0",   # 타석이 없는 대주자는 제외
]


class RunningTest(unittest.TestCase):

    def test_running_rows_attach_to_hitters(self):
        folder = complete_folder(**{"running.txt": RUNNING})
        hitters, _, problems, _ = ki.build(folder, 2026)
        running, running_problems = ki.build_running(folder, 2026, hitters)

        self.assertEqual(problems + running_problems, [])
        self.assertEqual(sorted((r["Player"], r["SBA"], r["SB"], r["CS"]) for r in running),
                         [("가타자", 20, 15, 5), ("나타자", 0, 0, 0)])

    def test_inconsistent_attempts_are_caught(self):
        wrong = [RUNNING[0].replace("\t20\t15\t5\t", "\t21\t15\t5\t")]
        folder = complete_folder(**{"running.txt": wrong})
        hitters, _, _, _ = ki.build(folder, 2026)
        _, problems = ki.build_running(folder, 2026, hitters)
        self.assertEqual(len(problems), 1)
        self.assertIn("도루시도", problems[0])

    def test_simulation_uses_running_csv(self):
        folder = complete_folder(**{"running.txt": RUNNING, "defense.txt": DEFENSE})
        hitters, pitchers, _, _ = ki.build(folder, 2026)
        running, _ = ki.build_running(folder, 2026, hitters)
        out = tempfile.mkdtemp()
        ki.write_csv(os.path.join(out, "hitters.csv"), ki.HITTER_COLUMNS, hitters)
        ki.write_csv(os.path.join(out, "pitchers.csv"), ki.PITCHER_COLUMNS, pitchers)
        ki.write_csv(os.path.join(out, "running.csv"), ki.RUNNING_COLUMNS, running)

        model = sim.Model(out)
        runner, slow = model.batter("KT", "가타자"), model.batter("KT", "나타자")
        self.assertGreater(runner.steal_attempt, slow.steal_attempt)
        self.assertGreater(slow.steal_attempt, 0)  # 시도 0 회도 리그 평균 쪽으로 회귀


class SimulationWithRawCountsTest(unittest.TestCase):

    def test_exact_rates_are_used_when_raw_counts_exist(self):
        hitters, pitchers, _, _ = ki.build(complete_folder(), 2026)
        out = tempfile.mkdtemp()
        ki.write_csv(os.path.join(out, "hitters.csv"), ki.HITTER_COLUMNS, hitters)
        ki.write_csv(os.path.join(out, "pitchers.csv"), ki.PITCHER_COLUMNS, pitchers)
        with open(os.path.join(out, "hitters.csv"), encoding="utf-8") as f:
            row = next(csv.DictReader(f))

        obs = sim._batter_observed(row)
        self.assertAlmostEqual(obs["h"], 105 / 400)
        self.assertAlmostEqual(obs["bb"], (40 + 5) / 400)
        self.assertAlmostEqual(obs["k"], 70 / 400)
        self.assertAlmostEqual(obs["xb"], (20 + 2 * 2 + 3 * 10) / 105)

        model = sim.Model(out)
        self.assertEqual(model.warnings, [])
        pitcher = model.pitcher("KT", "라투수")
        self.assertAlmostEqual(pitcher.starter_innings, 120 / 20)
        self.assertGreater(pitcher.wp_factor, 0)  # WP 열이 pitchers.csv 로 흘러들어와 폭투 기능이 켜짐
        self.assertGreater(model.wp_pb_rate, 0)


if __name__ == "__main__":
    unittest.main()
