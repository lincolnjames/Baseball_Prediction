"""
KBO 기록실에서 사람이 직접 복사한 표(탭 구분 텍스트)를 검산하고 시뮬레이션용 CSV 로 바꾼다.

사용법: py kbo_import.py <입력 폴더> [--year 2026] [--out <출력 폴더>]

입력 폴더의 *.txt 를 모두 읽는다. 파일 이름·순서·헤더 유무는 상관없고,
열 개수로 표 종류를 판별한다.

  타자 기본기록 1 (16열): 순위 선수명 팀명 AVG G PA AB R H 2B 3B HR TB RBI SAC SF
  타자 기본기록 2 (15열): 순위 선수명 팀명 AVG BB IBB HBP SO GDP SLG OBP OPS MH RISP PH-BA
  투수 기본기록 1 (19열): 순위 선수명 팀명 ERA G W L SV HLD WPCT IP H HR BB HBP SO R ER WHIP
  투수 기본기록 2 (18열): 순위 선수명 팀명 ERA CG SHO QS BSV TBF NP AVG 2B 3B SAC SF IBB WP BK

검산: 타율·출루율·장타율, 피안타율·평균자책·WHIP 를 원시 기록으로 다시 계산해 표 값과 비교한다.
1·2번 표는 (팀, 순위, 이름)으로 짝짓고, 한쪽에만 있는 선수는 페이지 누락으로 보고한다.
"""
import argparse
import csv
import os
import sys
from collections import defaultdict

TABLES = {
    16: ("hitter1", ["rank", "name", "team", "AVG", "G", "PA", "AB", "R", "H", "2B", "3B", "HR", "TB", "RBI",
                     "SAC", "SF"]),
    15: ("hitter2", ["rank", "name", "team", "AVG", "BB", "IBB", "HBP", "SO", "GDP", "SLG", "OBP", "OPS", "MH",
                     "RISP", "PH-BA"]),
    19: ("pitcher1", ["rank", "name", "team", "ERA", "G", "W", "L", "SV", "HLD", "WPCT", "IP", "H", "HR", "BB",
                      "HBP", "SO", "R", "ER", "WHIP"]),
    18: ("pitcher2", ["rank", "name", "team", "ERA", "CG", "SHO", "QS", "BSV", "TBF", "NP", "AVG", "2B", "3B",
                      "SAC", "SF", "IBB", "WP", "BK"]),
}
TEAMS = {"KIA", "KT", "LG", "NC", "SSG", "두산", "롯데", "삼성", "키움", "한화"}
RATE_TOLERANCE = 0.0006    # 소수 셋째 자리 반올림 오차
ERA_TOLERANCE = 0.006      # 소수 둘째 자리 반올림 오차

HITTER_COLUMNS = ["Year", "Team", "Player", "G", "PA", "AB", "H", "2B", "3B", "HR", "BB", "HBP", "SO", "SF",
                  "AVG", "OBP", "SLG", "K%", "BB%"]
PITCHER_COLUMNS = ["Year", "Team", "Player", "G", "W", "L", "SV", "HLD", "IP", "TBF", "H", "HR", "BB", "HBP", "SO",
                   "ER", "ERA", "WHIP", "K%", "BB%", "HR/9"]


def innings_outs(text):
    """'56 2/3' → 170 아웃, '2/3' → 2, '44' → 132"""
    outs = 0
    for part in text.split():
        if "/" in part:
            numerator, denominator = part.split("/")
            outs += int(numerator) * 3 // int(denominator)
        else:
            outs += int(part) * 3
    return outs


def num(value):
    return None if value in ("-", "") else float(value)


def read_tables(folder):
    """{종류: {(팀, 순위, 이름): row}}, 오류 목록"""
    tables = defaultdict(dict)
    errors = []
    for file_name in sorted(os.listdir(folder)):
        if not file_name.endswith(".txt"):
            continue
        with open(os.path.join(folder, file_name), encoding="utf-8-sig") as f:
            for line_no, line in enumerate(f, 1):
                fields = [v.strip() for v in line.rstrip("\r\n").split("\t")]
                if len(fields) < 3 or fields[1] == "선수명":
                    continue
                where = f"{file_name}:{line_no}"
                if len(fields) not in TABLES:
                    errors.append(f"{where} 열 개수 {len(fields)}개 - 줄이 붙었거나 잘렸을 수 있음: {line.strip()[:60]}")
                    continue
                kind, columns = TABLES[len(fields)]
                row = dict(zip(columns, fields))
                if row["team"] not in TEAMS:
                    errors.append(f"{where} 알 수 없는 팀명 '{row['team']}'")
                    continue
                key = (row["team"], row["rank"], row["name"])
                if key in tables[kind] and tables[kind][key] != row:
                    errors.append(f"{where} 같은 선수({key})가 다른 값으로 두 번 들어있음")
                tables[kind][key] = row
    return tables, errors


def pair(first, second, label):
    missing = [f"{label} 1번 표에만 있음: {k}" for k in first if k not in second]
    missing += [f"{label} 2번 표에만 있음: {k}" for k in second if k not in first]
    return [(k, first[k], second[k]) for k in first if k in second], missing


def check(label, key, name, expected, actual, tolerance):
    if expected is None or actual is None:
        return None
    if abs(expected - actual) > tolerance:
        return f"{label} {key} {name}: 표 {expected:.3f} / 계산 {actual:.3f}"
    return None


def verify_hitter(key, h1, h2):
    ab, h, sf, tb = (int(h1[c]) for c in ("AB", "H", "SF", "TB"))
    bb, hbp = int(h2["BB"]), int(h2["HBP"])
    problems = []
    if ab > 0:
        problems.append(check("타자", key, "타율", num(h1["AVG"]), h / ab, RATE_TOLERANCE))
        problems.append(check("타자", key, "장타율", num(h2["SLG"]), tb / ab, RATE_TOLERANCE))
    if ab + bb + hbp + sf > 0:
        problems.append(check("타자", key, "출루율", num(h2["OBP"]), (h + bb + hbp) / (ab + bb + hbp + sf),
                              RATE_TOLERANCE))
    return [p for p in problems if p]


def verify_pitcher(key, p1, p2):
    outs = innings_outs(p1["IP"])
    h, bb, hbp, er = (int(p1[c]) for c in ("H", "BB", "HBP", "ER"))
    tbf, sac, sf = (int(p2[c]) for c in ("TBF", "SAC", "SF"))
    problems = []
    at_bats = tbf - bb - hbp - sac - sf
    if at_bats > 0:
        problems.append(check("투수", key, "피안타율", num(p2["AVG"]), h / at_bats, RATE_TOLERANCE))
    if outs > 0:
        problems.append(check("투수", key, "평균자책", num(p1["ERA"]), er * 27 / outs, ERA_TOLERANCE))
        problems.append(check("투수", key, "WHIP", num(p1["WHIP"]), (h + bb) * 3 / outs, ERA_TOLERANCE))
    return [p for p in problems if p]


def disambiguate(rows, games_column="G"):
    """같은 팀에 이름이 같은 선수가 있으면 '이름(N경기)'로 바꾼다"""
    counts = defaultdict(int)
    for row in rows:
        counts[(row["Team"], row["Player"])] += 1
    renamed = []
    for row in rows:
        if counts[(row["Team"], row["Player"])] > 1:
            old = row["Player"]
            row["Player"] = f"{old}({row[games_column]}경기)"
            renamed.append(f"{row['Team']} {old} → {row['Player']}")
    return renamed


def build(folder, year):
    tables, errors = read_tables(folder)
    hitter_pairs, missing_h = pair(tables["hitter1"], tables["hitter2"], "타자")
    pitcher_pairs, missing_p = pair(tables["pitcher1"], tables["pitcher2"], "투수")
    problems = errors + missing_h + missing_p

    hitters = []
    for key, h1, h2 in hitter_pairs:
        problems += verify_hitter(key, h1, h2)
        pa = int(h1["PA"])
        if pa == 0:
            continue  # 타석 없는 선수(주로 투수)는 제외
        hitters.append({
            "Year": year, "Team": h1["team"], "Player": h1["name"],
            "G": h1["G"], "PA": pa, "AB": h1["AB"], "H": h1["H"], "2B": h1["2B"], "3B": h1["3B"],
            "HR": h1["HR"], "BB": h2["BB"], "HBP": h2["HBP"], "SO": h2["SO"], "SF": h1["SF"],
            "AVG": h1["AVG"], "OBP": h2["OBP"], "SLG": h2["SLG"],
            "K%": f"{int(h2['SO']) / pa * 100:.1f}", "BB%": f"{int(h2['BB']) / pa * 100:.1f}",
        })

    pitchers = []
    for key, p1, p2 in pitcher_pairs:
        problems += verify_pitcher(key, p1, p2)
        outs, tbf = innings_outs(p1["IP"]), int(p2["TBF"])
        if outs == 0 or tbf == 0:
            continue  # 아웃을 하나도 못 잡은 투수는 비율 계산 불가
        pitchers.append({
            "Year": year, "Team": p1["team"], "Player": p1["name"],
            "G": p1["G"], "W": p1["W"], "L": p1["L"], "SV": p1["SV"], "HLD": p1["HLD"],
            "IP": f"{outs // 3}.{outs % 3}", "TBF": tbf, "H": p1["H"], "HR": p1["HR"], "BB": p1["BB"],
            "HBP": p1["HBP"], "SO": p1["SO"], "ER": p1["ER"], "ERA": p1["ERA"], "WHIP": p1["WHIP"],
            "K%": f"{int(p1['SO']) / tbf * 100:.1f}", "BB%": f"{int(p1['BB']) / tbf * 100:.1f}",
            "HR/9": f"{int(p1['HR']) * 27 / outs:.2f}",
        })

    renamed = disambiguate(hitters) + disambiguate(pitchers)
    return hitters, pitchers, problems, renamed


def write_csv(path, columns, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["Team"], r["Player"])))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--out", help="CSV 출력 폴더 (기본: <입력 폴더>/out)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    hitters, pitchers, problems, renamed = build(args.folder, args.year)

    teams = sorted({r["Team"] for r in hitters} | {r["Team"] for r in pitchers})
    print(f"팀 {len(teams)}개: {', '.join(teams)}  (없는 팀: {', '.join(sorted(TEAMS - set(teams))) or '없음'})")
    for team in teams:
        print(f"  {team}: 타자 {sum(r['Team'] == team for r in hitters)}명, "
              f"투수 {sum(r['Team'] == team for r in pitchers)}명")
    for message in renamed:
        print(f"  동명이인 구분: {message}")

    if problems:
        print(f"\n문제 {len(problems)}건 - CSV 를 만들지 않았습니다:")
        for p in problems:
            print(f"  - {p}")
        return 1

    out = args.out or os.path.join(args.folder, "out")
    os.makedirs(out, exist_ok=True)
    write_csv(os.path.join(out, "hitters.csv"), HITTER_COLUMNS, hitters)
    write_csv(os.path.join(out, "pitchers.csv"), PITCHER_COLUMNS, pitchers)
    print(f"\n검산 통과. CSV 저장: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
