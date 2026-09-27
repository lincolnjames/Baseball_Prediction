"""
시뮬레이션 모델 백테스트: 선수 기록 스냅샷 이후 실제 경기 결과를 얼마나 맞히는지 측정한다.

사용법: py backtest.py [--sims 500] [--report REPORT.md]

- 선수 기록 CSV(static/*.csv)는 2025-05-20 경기까지 반영된 스냅샷이다
  (선발 39명의 등판 수가 이 날짜까지의 선발 등판 수와 모두 일치).
  미래 정보가 섞이지 않도록 그 다음 날부터의 경기만 평가한다.
- 선발투수는 실제 경기 선발을 쓰고, 타순·불펜은 팀별 기본값(타석 수 상위 9명, 등판 많은 불펜)을 쓴다.
  실제 경기 타순은 데이터에 없다.
- 무승부 경기는 평가에서 제외하고, 예측값은 "무승부가 아닐 때 홈팀이 이길 확률"로 본다.

경기 결과 데이터(data/kbo_2025_games.csv)는 저장소에 포함하지 않는다.
KBO 사이트는 사전 승인 없는 자동 수집·복제를 금지하므로, 승인받은 경로로 확보한 파일을
data/ 에 두고 실행한다. 형식은 GAMES_COLUMNS 참고 (status 가 final 인 경기만 사용).
"""
import argparse
import csv
import math
import os
import random
import sys
import time
from collections import defaultdict

BACKTEST_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BACKTEST_DIR, "..", "src", "main", "resources", "static")
sys.path.insert(0, os.path.abspath(STATIC_DIR))

import simulation as sim  # noqa: E402

GAMES_CSV = os.path.join(BACKTEST_DIR, "data", "kbo_2025_games.csv")
GAMES_COLUMNS = ["date", "game_id", "stadium", "away", "home", "away_score", "home_score",
                 "away_starter", "home_starter", "status"]
SNAPSHOT_DATE = "2025-05-20"
PYTHAGOREAN_EXPONENT = 1.83
RELIEVER_MAX_IP_PER_G = 2.0
CALIBRATION_BINS = [0.0, 0.35, 0.45, 0.55, 0.65, 1.0]


# ---------- 데이터 ----------

def load_games(path=GAMES_CSV):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"경기 결과 파일이 없습니다: {path}\n"
            f"저장소에는 포함되지 않습니다. 컬럼: {', '.join(GAMES_COLUMNS)}")
    with open(path, encoding="utf-8", newline="") as f:
        games = [g for g in csv.DictReader(f) if g["status"] == "final"]
    for g in games:
        g["home_score"], g["away_score"] = int(g["home_score"]), int(g["away_score"])
    return games


def split_games(games, snapshot_date=SNAPSHOT_DATE):
    """(스냅샷까지 경기, 스냅샷 이후 경기)"""
    return ([g for g in games if g["date"] <= snapshot_date],
            [g for g in games if g["date"] > snapshot_date])


def default_rosters(static_dir=STATIC_DIR):
    """팀별 기본 타순(타석 상위 9명, 타석 순)과 불펜(등판 많은 순: 1명 마무리 + 3명 중간계투)"""
    def read(name):
        with open(os.path.join(static_dir, name), encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    def num(row, key):
        try:
            return float(row[key])
        except (TypeError, ValueError):
            return 0.0

    rosters = {}
    hitters, pitchers = read("hitters.csv"), read("pitchers.csv")
    for team in sorted({r["Team"] for r in hitters}):
        lineup = sorted((r for r in hitters if r["Team"] == team), key=lambda r: -num(r, "PA"))[:9]
        relievers = sorted(
            (r for r in pitchers if r["Team"] == team and num(r, "G") > 0
             and sim.innings(num(r, "IP")) / num(r, "G") < RELIEVER_MAX_IP_PER_G),
            key=lambda r: -num(r, "G"))
        rosters[team] = {
            "lineup": [r["Player"] for r in lineup],
            "closer": relievers[0]["Player"] if relievers else None,
            "middle": [r["Player"] for r in relievers[1:4]],
        }
    return rosters


# ---------- 예측 ----------

def simulation_predictions(games, sims, seed=2025):
    """경기마다 sims 번 시뮬레이션 → 무승부 제외 홈 승리 확률, 예상 총득점"""
    model = sim.Model()
    rosters = default_rosters()
    predictions = []
    for index, game in enumerate(games):
        plans = {}
        for side in ("home", "away"):
            team = game[side]
            spec = dict(rosters[team], team=team, starter=game[f"{side}_starter"])
            plans[side] = model.team_plan(spec)

        rng = random.Random(seed + index)
        home_wins = away_wins = total_runs = 0
        for _ in range(sims):
            h, a = sim.simulate_game(model, plans["home"], plans["away"], rng)
            total_runs += h + a
            home_wins += h > a
            away_wins += a > h
        decided = home_wins + away_wins
        predictions.append({
            "p_home": home_wins / decided if decided else 0.5,
            "expected_runs": total_runs / sims,
        })
    return predictions, model.warnings


def pythagorean_baseline(train_games, test_games, home_edge):
    """스냅샷까지 득실점 → 피타고리안 승률 → Log5 + 홈 이점"""
    scored, allowed = defaultdict(int), defaultdict(int)
    for g in train_games:
        scored[g["home"]] += g["home_score"]
        allowed[g["home"]] += g["away_score"]
        scored[g["away"]] += g["away_score"]
        allowed[g["away"]] += g["home_score"]

    def strength(team):
        rs, ra = scored[team] ** PYTHAGOREAN_EXPONENT, allowed[team] ** PYTHAGOREAN_EXPONENT
        return rs / (rs + ra) if rs + ra else 0.5

    return [with_home_edge(log5(strength(g["home"]), strength(g["away"])), home_edge) for g in test_games]


def log5(a, b):
    return (a - a * b) / (a + b - 2 * a * b) if a + b - 2 * a * b else 0.5


def with_home_edge(p, home_edge):
    """중립 승률 p 에 홈 이점(리그 홈 승률 - 0.5)을 로짓 공간에서 더한다"""
    shift = logit(0.5 + home_edge)
    return 1 / (1 + math.exp(-(logit(p) + shift)))


def logit(p):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def home_win_rate(games):
    decided = [g for g in games if g["home_score"] != g["away_score"]]
    return sum(g["home_score"] > g["away_score"] for g in decided) / len(decided)


# ---------- 평가 ----------

def evaluate(probabilities, outcomes):
    """outcomes: 홈 승 1, 원정 승 0 (무승부는 미리 제외)"""
    n = len(outcomes)
    brier = sum((p - o) ** 2 for p, o in zip(probabilities, outcomes)) / n
    log_loss = -sum(math.log(min(max(p if o else 1 - p, 1e-6), 1)) for p, o in zip(probabilities, outcomes)) / n
    accuracy = sum((p > 0.5) == bool(o) for p, o in zip(probabilities, outcomes) if p != 0.5) / max(
        sum(1 for p in probabilities if p != 0.5), 1)
    return {"n": n, "accuracy": accuracy, "brier": brier, "log_loss": log_loss,
            "brier_skill": 1 - brier / 0.25}


def brier_skill_ci(probabilities, outcomes, resamples=2000, seed=0):
    """경기를 복원 추출해 Brier skill(동전 던지기 대비)의 95% 신뢰구간을 구한다"""
    rng = random.Random(seed)
    n = len(outcomes)
    skills = []
    for _ in range(resamples):
        sample = [rng.randrange(n) for _ in range(n)]
        brier = sum((probabilities[i] - outcomes[i]) ** 2 for i in sample) / n
        skills.append(1 - brier / 0.25)
    skills.sort()
    return skills[int(resamples * 0.025)], skills[int(resamples * 0.975)]


def calibration(probabilities, outcomes, bins=CALIBRATION_BINS):
    rows = []
    for low, high in zip(bins, bins[1:]):
        members = [(p, o) for p, o in zip(probabilities, outcomes) if low <= p < high or (high == 1.0 and p == 1.0)]
        if members:
            rows.append({"range": f"{low:.2f}~{high:.2f}", "n": len(members),
                         "predicted": sum(p for p, _ in members) / len(members),
                         "actual": sum(o for _, o in members) / len(members)})
    return rows


# ---------- 실행 ----------

def run_backtest(sims):
    games = load_games()
    train, test = split_games(games)
    test = [g for g in test if g["home_score"] != g["away_score"]]
    outcomes = [int(g["home_score"] > g["away_score"]) for g in test]
    home_edge = home_win_rate(train) - 0.5

    start = time.time()
    sim_preds, warnings = simulation_predictions(test, sims)
    elapsed = time.time() - start

    sim_p = [p["p_home"] for p in sim_preds]
    models = {
        "시뮬레이션 모델": sim_p,
        "시뮬레이션 + 홈 이점": [with_home_edge(p, home_edge) for p in sim_p],
        "기준: 동전 던지기 (0.5)": [0.5] * len(test),
        "기준: 홈팀 승률 상수": [0.5 + home_edge] * len(test),
        "기준: 피타고리안 + 홈 이점": pythagorean_baseline(train, test, home_edge),
    }
    return {
        "train_games": len(train),
        "test_games": len(test),
        "test_period": f"{test[0]['date']} ~ {test[-1]['date']}",
        "home_edge": home_edge,
        "sims": sims,
        "elapsed": elapsed,
        "metrics": {name: evaluate(p, outcomes) for name, p in models.items()},
        "skill_ci": brier_skill_ci(sim_p, outcomes),
        "calibration": calibration(sim_p, outcomes),
        "runs": {
            "predicted": sum(p["expected_runs"] for p in sim_preds) / len(test),
            "actual": sum(g["home_score"] + g["away_score"] for g in test) / len(test),
        },
        "warnings": warnings,
    }


def format_report(result):
    lines = [
        "# 백테스트 결과",
        "",
        f"- 학습 구간: 2025-03-22 ~ {SNAPSHOT_DATE} ({result['train_games']}경기, 선수 기록 스냅샷 기준)",
        f"- 평가 구간: {result['test_period']} ({result['test_games']}경기, 무승부 제외)",
        f"- 경기당 시뮬레이션: {result['sims']}회 (소요 {result['elapsed']:.0f}초)",
        f"- 학습 구간 홈 승률: {0.5 + result['home_edge']:.3f}",
        "",
        "## 예측 성능",
        "",
        "| 모델 | 적중률 | Brier ↓ | Log loss ↓ | Brier skill ↑ |",
        "|---|---|---|---|---|",
    ]
    for name, m in result["metrics"].items():
        lines.append(f"| {name} | {m['accuracy']:.3f} | {m['brier']:.4f} | {m['log_loss']:.4f} | {m['brier_skill']:+.3f} |")
    lines += [
        "",
        "Brier skill = 1 - Brier / 0.25 (동전 던지기 대비 개선 비율, 0 이하면 동전보다 못함)",
        "",
        "시뮬레이션 모델 Brier skill 95% 신뢰구간 (경기 부트스트랩 2000회): "
        f"{result['skill_ci'][0]:+.3f} ~ {result['skill_ci'][1]:+.3f}",
        "",
        "## 보정 (시뮬레이션 모델)",
        "",
        "| 예측 홈 승률 구간 | 경기 수 | 평균 예측 | 실제 홈 승률 |",
        "|---|---|---|---|",
    ]
    for row in result["calibration"]:
        lines.append(f"| {row['range']} | {row['n']} | {row['predicted']:.3f} | {row['actual']:.3f} |")
    lines += [
        "",
        "## 득점",
        "",
        f"- 경기당 총득점: 예측 {result['runs']['predicted']:.2f} / 실제 {result['runs']['actual']:.2f}",
        "",
        f"## 기록 없는 선수 ({len(result['warnings'])}건, 리그 평균으로 계산)",
        "",
    ]
    lines += [f"- {w}" for w in result["warnings"]] or ["- 없음"]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sims", type=int, default=500, help="경기당 시뮬레이션 횟수")
    parser.add_argument("--report", help="마크다운 보고서 저장 경로")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")
    report = format_report(run_backtest(args.sims))
    print(report)
    if args.report:
        with open(args.report, "w", encoding="utf-8", newline="\n") as f:
            f.write(report)


if __name__ == "__main__":
    main()
