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
        self.assertEqual((mid["IP"], mid["TBF"], mid["HR/9"]), ("40.1", 175, "0.89"))

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


if __name__ == "__main__":
    unittest.main()
