"""
라인업 시나리오 분석: 라인업 발표 전에 "가능한 라인업들"의 승률을 미리 계산한다.

사용법: py scenario.py input.json
입력:
  {"mode": "analyze" | "predict",
   "home": Team, "away": Team, "data_dir": null, "seed": 0}
  Team = {"team": "두산", "starter": "곽빈",
          "lineup": [{"name": "박찬호", "pos": "유격수"}, ... 9명],
          "closer": null, "middle": null}      # 불펜을 비우면 세이브·홀드 기록으로 자동 구성
출력: 결과 JSON 한 줄 (표준출력)

analyze (라인업 발표 전)
  1. 기준 라인업(보통 최근 라인업) 승률
  2. 교체 효과: 각 자리를 그 포지션을 실제로 맡아온 벤치 선수로 바꿨을 때 승률 변화.
     선수 한 명의 효과(1~3%p)는 시뮬레이션 노이즈와 크기가 비슷해 시뮬레이션 차이로는 구분이 안 된다.
     그래서 계산으로 구한다: 상대 선발·불펜 상대 타석당 득점 가치(선형 가중치) 차이 × 타순별 타석 수
     → 경기당 득점 차이 → 기준 시뮬레이션 득점 수준에서의 득점 1점당 승률 변화(피타고리안 기울기).
  3. 승률 범위: 주전마다 결장 확률(시즌 선발 비율로 추정)과 대체 선수 분포(포지션 선발 수)로
     가능한 라인업을 뽑고, 교체 효과를 더해 승률 분포를 만든다 (교체 효과가 더해진다고 가정한 근사).
predict (라인업 발표 후)
  실제 라인업 한 쌍의 승률만 더 많은 경기 수로 계산한다.
"""
import csv
import json
import os
import random
import sys
import time
from collections import defaultdict
from dataclasses import replace

import simulation as sim

DH = "지명타자"
FIELD_POSITIONS = ["포수", "1루수", "2루수", "3루수", "유격수", "좌익수", "중견수", "우익수"]
LINEUP_POSITIONS = FIELD_POSITIONS + [DH]

GAMES_BASE = 4000          # 기준 라인업
GAMES_PREDICT = 10000      # 확정 예측
CANDIDATES_PER_SLOT = 3
LINEUP_DRAWS = 5000
PA_PER_START = 4.2         # 선발 출장 한 경기당 평균 타석 (선발 비율 추정용)
REST_PROB_RANGE = (0.05, 0.35)  # 주전 결장 확률 하한·상한 (최근 라인업에 들었다면 현재 뛰고 있는 선수)
MIDDLE_RELIEVERS = 3

# 타석 결과별 득점 가치 (아웃 대비, 일반적인 선형 가중치 근사). 삼진·인플레이 아웃은 0
RUN_VALUES = {"bb": 0.69, "single": 0.88, "double": 1.25, "triple": 1.59, "homerun": 2.05}
# 타순별 경기당 평균 타석 (1번 → 9번)
PA_BY_ORDER = [4.65, 4.55, 4.45, 4.35, 4.25, 4.15, 4.05, 3.95, 3.85]
PYTHAGOREAN_EXPONENT = 1.83
# 계산한 교체 효과를 시뮬레이션에 맞추는 보정 계수. 2026 NC@두산 라인업에서 교체 6건을 각 10만 경기씩
# 시뮬레이션해 최소제곱으로 구함 (0.815). 피타고리안 기울기는 연장 11회 무승부·끝내기 때문에
# 이 시뮬레이션의 실제 민감도보다 크고, 선형 가중치 득점 계산도 10~25% 크게 나온다.
SWAP_EFFECT_CALIBRATION = 0.815


# ---------- 데이터 ----------

class Roster:
    """팀별 타자·투수 목록과 포지션별 선발 출장 수"""

    def __init__(self, data_dir):
        self.hitters = defaultdict(dict)   # 팀 → 이름 → row
        self.pitchers = defaultdict(dict)
        self.gs = defaultdict(lambda: defaultdict(int))  # (팀, 이름) → 포지션 → 선발 출장
        with open(os.path.join(data_dir, "hitters.csv"), encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if (sim._num(r, "PA") or 0) > 0:
                    self.hitters[r["Team"]][r["Player"]] = r
        with open(os.path.join(data_dir, "pitchers.csv"), encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if (sim._num(r, "IP") or 0) > 0:
                    self.pitchers[r["Team"]][r["Player"]] = r
        positions_path = os.path.join(data_dir, "positions.csv")
        self.has_positions = os.path.exists(positions_path)
        if self.has_positions:
            with open(positions_path, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    self.gs[(r["Team"], r["Player"])][r["POS"]] += int(r["GS"])

    def team_games(self, team):
        """포지션별 선발 출장 합계 중 최댓값 ≈ 팀 경기 수 (포지션 정보가 없으면 최다 경기 출장)"""
        totals = defaultdict(int)
        for (t, _), by_pos in self.gs.items():
            if t == team:
                for pos, n in by_pos.items():
                    totals[pos] += n
        if totals:
            return max(totals.values())
        return max((sim._num(r, "G") or 0) for r in self.hitters[team].values())

    def pa(self, team, name):
        row = self.hitters[team].get(name)
        return (sim._num(row, "PA") or 0) if row else 0

    def candidates(self, team, pos, exclude):
        """포지션을 맡을 수 있는 벤치 선수와 가중치(해당 포지션 선발 수, 지명타자는 타석)"""
        pool = []
        for name in self.hitters[team]:
            if name in exclude:
                continue
            if pos == DH or not self.has_positions:
                weight = self.pa(team, name)
            else:
                weight = self.gs[(team, name)].get(pos, 0)
            if weight > 0:
                pool.append((name, weight))
        pool.sort(key=lambda x: -x[1])
        return pool[:CANDIDATES_PER_SLOT]

    def rest_probability(self, team, name):
        starts = self.pa(team, name) / PA_PER_START
        rate = min(starts / max(self.team_games(team), 1), 1.0)
        low, high = REST_PROB_RANGE
        return min(max(1 - rate, low), high)

    def default_bullpen(self, team, starter):
        """마무리 = 세이브 1위, 중간계투 = 홀드 상위 (세이브·홀드가 없는 데이터면 구원 등판 수)"""
        relievers = []
        for name, r in self.pitchers[team].items():
            g = sim._num(r, "G") or 0
            if name == starter or g == 0 or sim.innings(sim._num(r, "IP")) / g >= 2:
                continue
            relievers.append((name, sim._num(r, "SV") or 0, sim._num(r, "HLD") or 0, g))
        if not relievers:
            return None, []
        closer = max(relievers, key=lambda x: (x[1], x[3]))[0]
        middle = [x[0] for x in sorted(relievers, key=lambda x: (-x[2], -x[3])) if x[0] != closer]
        return closer, middle[:MIDDLE_RELIEVERS]


# ---------- 계산 ----------

def validate_lineup(side, spec):
    lineup = spec.get("lineup") or []
    if len(lineup) != 9:
        raise ValueError(f"{side} 타순은 9명이어야 합니다 (현재 {len(lineup)}명)")
    names = [s["name"] for s in lineup]
    if len(set(names)) != 9:
        raise ValueError(f"{side} 타순에 같은 선수가 두 번 있습니다")
    positions = [s["pos"] for s in lineup]
    unknown = [p for p in positions if p not in LINEUP_POSITIONS]
    if unknown:
        raise ValueError(f"{side} 알 수 없는 포지션: {', '.join(unknown)}")
    missing = [p for p in FIELD_POSITIONS if p not in positions]
    if missing:
        raise ValueError(f"{side} 수비 포지션이 비었습니다: {', '.join(missing)}")
    if not spec.get("starter"):
        raise ValueError(f"{side} 선발투수를 지정해야 합니다")


def build_plan(model, roster, spec):
    team = spec["team"]
    closer, middle = spec.get("closer"), spec.get("middle")
    if closer is None and middle is None:
        closer, middle = roster.default_bullpen(team, spec["starter"])
    return model.team_plan({"team": team, "lineup": [s["name"] for s in spec["lineup"]],
                            "starter": spec["starter"], "middle": middle or [], "closer": closer})


def win_probability(model, home, away, games, seed):
    rng = random.Random(seed)
    home_wins = away_wins = home_runs = away_runs = 0
    for _ in range(games):
        h, a = sim.simulate_game(model, home, away, rng)
        home_wins += h > a
        away_wins += a > h
        home_runs += h
        away_runs += a
    decided = home_wins + away_wins
    return {"home": home_wins / decided if decided else 0.5, "draw": 1 - decided / games,
            "home_runs": home_runs / games, "away_runs": away_runs / games}


def run_value(model, batter, staff):
    """상대 투수진(선발 + 불펜)을 만났을 때 타석당 득점 가치. 선발은 예상 이닝 비율만큼 가중한다."""
    def against(pitcher):
        table, value, previous = model.outcome_table(batter, pitcher), 0.0, 0.0
        for cumulative, outcome in table:
            value += (cumulative - previous) * RUN_VALUES.get(outcome, 0.0)
            previous = cumulative
        return value

    starter_share = min(staff.starter.starter_innings, 9) / 9
    relievers = list({p.key: p for p in staff.middle + ([staff.closer] if staff.closer else [])}.values())
    bullpen = sum(against(p) for p in relievers) / len(relievers) if relievers else against(staff.starter)
    return starter_share * against(staff.starter) + (1 - starter_share) * bullpen


def swap_lineup(plan, slot, batter):
    lineup = list(plan.lineup)
    lineup[slot] = batter
    return replace(plan, lineup=lineup)


def analyze(args):
    started = time.time()
    data_dir = args.get("data_dir") or sim.DATA_DIR
    seed = args.get("seed", 0)
    model = sim.Model(data_dir)
    roster = Roster(data_dir)
    specs = {"home": args["home"], "away": args["away"]}
    for side, spec in specs.items():
        validate_lineup(side, spec)
    plans = {side: build_plan(model, roster, spec) for side, spec in specs.items()}

    base = win_probability(model, plans["home"], plans["away"], GAMES_BASE, seed)
    # 득점 1점당 승률 변화: 피타고리안 승률의 기울기 x / (4R) (양 팀 평균 득점 R) × 시뮬레이션 보정
    runs = (base["home_runs"] + base["away_runs"]) / 2
    win_per_run = PYTHAGOREAN_EXPONENT / (4 * runs) * SWAP_EFFECT_CALIBRATION

    slots = []  # 자리별 결장 확률과 대체 선수 효과
    for side, spec in specs.items():
        team = spec["team"]
        opponent = plans["away" if side == "home" else "home"]
        sign = 1 if side == "home" else -1
        names = {s["name"] for s in spec["lineup"]}
        for i, s in enumerate(spec["lineup"]):
            current = run_value(model, plans[side].lineup[i], opponent)
            options = []
            for name, weight in roster.candidates(team, s["pos"], names):
                runs_delta = (run_value(model, model.batter(team, name), opponent) - current) * PA_BY_ORDER[i]
                options.append({"name": name, "weight": weight, "runs": runs_delta,
                                "delta_home": sign * runs_delta * win_per_run})
            total = sum(o["weight"] for o in options)
            for o in options:
                o["share"] = o["weight"] / total if total else 0
            slots.append({
                "side": side, "team": team, "order": i + 1, "pos": s["pos"], "name": s["name"],
                "rest_probability": roster.rest_probability(team, s["name"]),
                "absence_delta_home": sum(o["share"] * o["delta_home"] for o in options),
                "replacements": [{k: o[k] for k in ("name", "share", "runs", "delta_home")} for o in options],
            })

    distribution = lineup_distribution(slots, base["home"], random.Random(seed + 1))
    return {
        "mode": "analyze",
        "base": base,
        "expected_home": distribution["mean"],
        "range_home": [distribution["p10"], distribution["p90"]],
        "slots": slots,
        "bullpen": {side: {"closer": plans[side].closer.key[1] if plans[side].closer else None,
                           "middle": [p.key[1] for p in plans[side].middle]} for side in plans},
        "positions_available": roster.has_positions,
        "win_per_run": win_per_run,
        "games": {"base": GAMES_BASE, "lineup_draws": LINEUP_DRAWS},
        "warnings": model.warnings,
        "elapsed_time": time.time() - started,
    }


def lineup_distribution(slots, base_home, rng):
    """주전마다 결장 여부와 대체 선수를 뽑아 교체 효과를 더한 홈 승률 분포"""
    samples = []
    for _ in range(LINEUP_DRAWS):
        p = base_home
        for slot in slots:
            if slot["replacements"] and rng.random() < slot["rest_probability"]:
                r = rng.random()
                cumulative = 0.0
                for option in slot["replacements"]:
                    cumulative += option["share"]
                    if r < cumulative:
                        p += option["delta_home"]
                        break
        samples.append(min(max(p, 0.0), 1.0))
    samples.sort()
    return {"mean": sum(samples) / len(samples),
            "p10": samples[int(len(samples) * 0.1)], "p90": samples[int(len(samples) * 0.9)]}


def predict(args):
    started = time.time()
    data_dir = args.get("data_dir") or sim.DATA_DIR
    model = sim.Model(data_dir)
    roster = Roster(data_dir)
    for side in ("home", "away"):
        validate_lineup(side, args[side])
    home, away = (build_plan(model, roster, args[side]) for side in ("home", "away"))
    result = win_probability(model, home, away, GAMES_PREDICT, args.get("seed", 0))
    return {"mode": "predict", "home": result["home"], "draw": result["draw"], "games": GAMES_PREDICT,
            "bullpen": {"home": {"closer": home.closer.key[1] if home.closer else None,
                                 "middle": [p.key[1] for p in home.middle]},
                        "away": {"closer": away.closer.key[1] if away.closer else None,
                                 "middle": [p.key[1] for p in away.middle]}},
            "warnings": model.warnings, "elapsed_time": time.time() - started}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        if len(argv) < 2:
            raise ValueError("입력 파일 경로가 필요합니다: py scenario.py input.json")
        with open(argv[1], encoding="utf-8") as f:
            args = json.load(f)
        result = predict(args) if args.get("mode") == "predict" else analyze(args)
    except ValueError as e:  # 입력 오류 → 종료 코드 2 (Java 에서 400 으로 응답)
        print(json.dumps({"error": str(e)}, ensure_ascii=False), flush=True)
        return 2
    except Exception as e:  # Java 쪽에서 메시지를 보여줄 수 있도록 JSON 으로 출력
        print(json.dumps({"error": str(e)}, ensure_ascii=False), flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
