"""
KBO 경기 몬테카를로 시뮬레이션.

사용법: py simulation.py input.json
입력:  {"home": Team, "away": Team, "match_count": 1000, "seed": null, "data_dir": null}
       Team = {"team": "LG", "lineup": [타자 9명], "starter": "선발",
               "middle": ["중간계투", ...], "closer": "마무리" 또는 null}
       data_dir = hitters.csv, pitchers.csv 가 있는 폴더 (없으면 이 파일이 있는 폴더의 기본 데이터)
출력:  결과 JSON 한 줄 (표준출력)

모델 요약
1. 선수 기록을 타석당 사건 확률(삼진 / 볼넷+사구 / 안타 / 인플레이 아웃)로 바꾼다.
2. 표본이 적은 기록은 리그 평균 쪽으로 회귀시킨다 (시즌 초 100타석 기록을 그대로 믿지 않기 위해).
3. 좌/우/언더 상대 기록은 "선수 전체 기록과의 차이"를 리그 평균 플래툰 차이(예: 좌타자의 우투수 상대 이점)
   쪽으로 회귀시켜 반영한다.
4. 타자·투수 확률을 odds ratio(Log5 일반화)로 결합한다: P(e) ∝ 타자(e) × 투수(e) / 리그(e)
5. 안타 종류는 타자의 안타당 추가 루타((SLG-AVG)/AVG)와 투수의 피홈런 비율로 나눈다.
"""
import csv
import json
import os
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

EVENTS = ("k", "bb", "h", "out")

# 회귀 강도: 리그 평균을 몇 타석(투수는 상대 타자 수)만큼 섞을지
BATTER_REG = {"k": 60, "bb": 120, "h": 400}
PITCHER_REG = {"k": 70, "bb": 170, "h": 500}
XB_REG_HITS = 80    # 안타당 추가 루타 (안타 수 기준)
HR_REG_BF = 400     # 투수 피홈런 비율
SPLIT_REG = 600     # 좌/우/언더 상대 기록: 플래툰 차이는 표본이 매우 커야 안정되므로 강하게 회귀
PLATOON_LEAGUE_REG = 1000  # 리그 평균 플래툰 차이 자체의 회귀 (그룹 전체 타석 기준)

# 좌/우/언더 상대 타석 수는 CSV 에 없으므로 전체 대비 비율로 추정 (선수 유형 CSV 분포 기준)
BATTER_SPLIT_SHARE = {"R": 0.63, "L": 0.27, "U": 0.10}  # 상대 투수: 우투 / 좌투 / 우언
PITCHER_SPLIT_SHARE = {"R": 0.58, "L": 0.42}            # 상대 타자: 우타 / 좌타

NON_AB_SHARE = 0.02  # 볼넷 외에 타수로 잡히지 않는 타석 비율 (사구, 희생타)
HBP_RATE = 0.01      # 투수 사구 비율 (CSV 에 없음)

# 장타 구성 근사치: 장타 중 2루타 / 3루타 / 홈런 비율
XBH_MIX = {"double": 0.60, "triple": 0.04, "homerun": 0.36}
XB_PER_XBH = XBH_MIX["double"] * 1 + XBH_MIX["triple"] * 2 + XBH_MIX["homerun"] * 3

# 주루 근사치 (값, 2아웃일 때 값) - 2아웃이면 타구와 동시에 뛰므로 더 많이 진루한다
P_SINGLE_2B_SCORES = (0.60, 0.85)  # 단타 때 2루 주자 득점
P_SINGLE_1B_TO_3B = (0.25, 0.35)   # 단타 때 1루 주자 3루까지
P_DOUBLE_1B_SCORES = (0.40, 0.65)  # 2루타 때 1루 주자 득점
P_DOUBLE_PLAY = 0.15       # 1루 주자 있고 2아웃 미만일 때 인플레이 아웃이 병살이 될 확률
P_SAC_FLY = 0.35           # 3루 주자 있고 2아웃 미만일 때 인플레이 아웃으로 득점
P_OUT_2B_TO_3B = 0.25      # 인플레이 아웃 때 2루 주자 3루 진루
P_REACH_ON_ERROR = 0.03    # 인플레이 아웃이 실책 출루가 될 확률 (주자는 한 베이스씩 진루)

MAX_INNINGS = 11           # KBO 2025 정규시즌: 연장 11회까지, 동점이면 무승부
MAX_CLOSER_LEAD = 3        # 9회 이후 이 점수 차 이내 리드(또는 동점)면 마무리 등판
DEFAULT_STARTER_INNINGS = 5.0

PITCH_TYPES = {"우투": "R", "좌투": "L", "우언": "U"}
BAT_HANDS = {"우타": "R", "좌타": "L", "양타": "S"}
SPLIT_COLUMNS = {"R": ("RAVG", "ROBP"), "L": ("LAVG", "LOBP"), "U": ("UAVG", "UOBP")}
PITCHER_SPLIT_COLUMNS = {"R": ("V_R_AVG", "V_R_OBP"), "L": ("V_L_AVG", "V_L_OBP")}


def _read_csv(data_dir, name):
    with open(os.path.join(data_dir, name), encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _num(row, key):
    try:
        return float((row.get(key) or "").strip())
    except ValueError:
        return None


def innings(ip):
    """야구식 이닝 표기 → 실제 이닝 (58.2 → 58.667)"""
    whole = int(ip)
    return whole + round((ip - whole) * 10) / 3


def _regress(observed, n, prior, k):
    return (observed * n + prior * k) / (n + k)


def _hit_walk_rates(avg, obp, bb):
    """타율·출루율 → 타석당 (안타, 볼넷+사구) 비율. OBP 에 볼넷이 포함되므로 안타를 빼서 구한다."""
    h = avg * (1 - bb - NON_AB_SHARE)
    return h, max(obp - h, bb)


@dataclass
class Batter:
    key: tuple
    rates: dict              # 전체: k, bb, h
    split_rates: dict        # 상대 투수 유형(R/L/U) → {bb, h}
    xb_per_hit: float
    hand: str = None         # R / L / S(양타)


@dataclass
class Pitcher:
    key: tuple
    rates: dict              # 전체: k, bb, h
    split_rates: dict        # 상대 타자(R/L) → {bb, h}
    hr_per_hit: float
    starter_innings: float
    ptype: str = None        # R / L / U(언더)


@dataclass
class TeamPlan:
    team: str
    lineup: list
    starter: Pitcher
    middle: list
    closer: Pitcher = None


class Model:
    def __init__(self, data_dir=DATA_DIR):
        hitters = [r for r in _read_csv(data_dir, "hitters.csv") if (_num(r, "PA") or 0) > 0]
        pitchers = [r for r in _read_csv(data_dir, "pitchers.csv") if (_num(r, "IP") or 0) > 0]

        self._hitters = _index_rows(hitters)
        self._pitchers = _index_rows(pitchers)
        # 좌우 정보는 시즌이 바뀌어도 거의 같으므로, 데이터 폴더에 없으면 기본 폴더 것을 쓴다
        type_dir = data_dir if os.path.exists(os.path.join(data_dir, "hitters_type.csv")) else DATA_DIR
        self._hands = _index_types(_read_csv(type_dir, "hitters_type.csv"), "Handedness", BAT_HANDS)
        self._ptypes = _index_types(_read_csv(type_dir, "pitchers_type.csv"), "Pitching_Type", PITCH_TYPES)

        self.league_batter = _league_batter(hitters)
        self.league_pitcher = _league_pitcher(pitchers)
        # 리그 평균 플래툰 차이: (타자 손, 투수 유형) / (투수 유형, 타자 손) → (안타 차이, 볼넷 차이)
        self.batter_platoon = _league_platoon(
            (_lookup_type(self._hands, r["Team"], r["Player"]), split, diff)
            for r in hitters for split, diff in _batter_split_diffs(r).items())
        self.pitcher_platoon = _league_platoon(
            (_lookup_type(self._ptypes, r["Team"], r["Player"]), split, diff)
            for r in pitchers for split, diff in _pitcher_split_diffs(r).items())
        self.warnings = []
        self._outcome_cache = {}

    # ---------- 선수 조회 ----------

    def batter(self, team, name):
        row = self._find(self._hitters, team, name, "타자")
        hand = _lookup_type(self._hands, team, name)
        lb = self.league_batter
        if row is None:
            rates = {e: lb[e] for e in ("k", "bb", "h")}
            splits = _apply_splits(rates, SPLIT_COLUMNS, self.batter_platoon, _platoon_group(hand), {})
            return Batter((team, name), rates, splits, lb["xb"], hand)

        obs = _batter_observed(row)
        pa = obs["pa"]
        rates = {e: _regress(obs[e], pa, lb[e], BATTER_REG[e]) for e in ("k", "bb", "h")}
        splits = _apply_splits(rates, SPLIT_COLUMNS, self.batter_platoon, _platoon_group(hand), _batter_split_diffs(row))

        xb_obs = obs["xb"] if obs["xb"] is not None else lb["xb"]
        xb = _regress(xb_obs, obs["hits"], lb["xb"], XB_REG_HITS)
        return Batter((team, name), rates, splits, xb, hand)

    def pitcher(self, team, name):
        row = self._find(self._pitchers, team, name, "투수")
        ptype = _lookup_type(self._ptypes, team, name)
        lp = self.league_pitcher
        if row is None:
            rates = {e: lp[e] for e in ("k", "bb", "h")}
            splits = _apply_splits(rates, PITCHER_SPLIT_COLUMNS, self.pitcher_platoon, ptype, {}, include_league=False)
            return Pitcher((team, name), rates, splits, lp["hr_per_hit"], DEFAULT_STARTER_INNINGS, ptype)

        obs = _pitcher_observed(row, lp["whip"])
        bf = obs["bf"]
        rates = {e: _regress(obs[e], bf, lp[e], PITCHER_REG[e]) for e in ("k", "bb", "h")}
        splits = _apply_splits(rates, PITCHER_SPLIT_COLUMNS, self.pitcher_platoon, ptype, _pitcher_split_diffs(row),
                               include_league=False)

        hr_per_hit = _regress(obs["hr"] / max(obs["h"], 0.02), bf, lp["hr_per_hit"], HR_REG_BF)
        g = _num(row, "G") or 0
        starter_innings = obs["ip"] / g if g > 0 else DEFAULT_STARTER_INNINGS
        return Pitcher((team, name), rates, splits, hr_per_hit, starter_innings, ptype)

    def _find(self, index, team, name, role):
        by_key, by_name = index
        if (team, name) in by_key:
            return by_key[(team, name)]
        candidates = by_name.get(name, [])
        if len(candidates) == 1:
            return candidates[0]
        reason = "동명이인 구분 불가" if candidates else "기록 없음"
        self._warn(f"{role} {name}({team or '팀 미지정'}): {reason} → 리그 평균으로 계산")
        return None

    def _warn(self, message):
        if message not in self.warnings:
            self.warnings.append(message)

    # ---------- 타석 결과 확률 ----------

    def outcome_table(self, batter, pitcher):
        """(누적확률, 결과) 목록. 결과: k, bb, single, double, triple, homerun, out"""
        cache_key = (batter.key, pitcher.key)
        if cache_key not in self._outcome_cache:
            self._outcome_cache[cache_key] = self._build_outcome_table(batter, pitcher)
        return self._outcome_cache[cache_key]

    def _build_outcome_table(self, batter, pitcher):
        lp = self.league_pitcher
        b = dict(batter.rates)
        if pitcher.ptype:
            b.update(batter.split_rates[pitcher.ptype])

        bat_side = batter.hand
        if bat_side == "S":  # 양타는 투수 반대 손으로 친다
            bat_side = {"R": "L", "U": "L", "L": "R"}.get(pitcher.ptype)
        p = dict(pitcher.rates)
        if bat_side in pitcher.split_rates:
            p.update(pitcher.split_rates[bat_side])

        b["out"] = max(1 - b["k"] - b["bb"] - b["h"], 0.05)
        p["out"] = max(1 - p["k"] - p["bb"] - p["h"], 0.05)
        weights = {e: b[e] * p[e] / lp[e] for e in EVENTS}
        total = sum(weights.values())
        probs = {e: w / total for e, w in weights.items()}

        xbh = min(batter.xb_per_hit / XB_PER_XBH, 0.7)
        hr_factor = pitcher.hr_per_hit / lp["hr_per_hit"]
        hit_mix = {
            "double": xbh * XBH_MIX["double"],
            "triple": xbh * XBH_MIX["triple"],
            "homerun": xbh * XBH_MIX["homerun"] * hr_factor,
        }
        xbh_total = sum(hit_mix.values())
        if xbh_total > 0.85:
            hit_mix = {t: v * 0.85 / xbh_total for t, v in hit_mix.items()}
        hit_mix["single"] = 1 - sum(hit_mix.values())

        outcomes = [("k", probs["k"]), ("bb", probs["bb"])]
        outcomes += [(t, probs["h"] * hit_mix[t]) for t in ("single", "double", "triple", "homerun")]
        outcomes.append(("out", probs["out"]))

        table, cumulative = [], 0.0
        for outcome, prob in outcomes:
            cumulative += prob
            table.append((cumulative, outcome))
        return table

    def team_plan(self, spec):
        team = spec.get("team")
        lineup = spec.get("lineup") or []
        if len(lineup) != 9:
            raise ValueError(f"{team or '팀'} 타순은 9명이어야 합니다 (현재 {len(lineup)}명)")
        if not spec.get("starter"):
            raise ValueError(f"{team or '팀'} 선발투수가 없습니다")
        return TeamPlan(
            team=team,
            lineup=[self.batter(team, n) for n in lineup],
            starter=self.pitcher(team, spec["starter"]),
            middle=[self.pitcher(team, n) for n in spec.get("middle") or []],
            closer=self.pitcher(team, spec["closer"]) if spec.get("closer") else None,
        )


def _batter_split_diffs(row):
    """투수 유형별 (안타 비율 - 전체, 볼넷 비율 - 전체, 추정 타석 수)"""
    pa = _num(row, "PA") or 0
    bb = (_num(row, "BB%") or 0) / 100
    h, walk = _hit_walk_rates(_num(row, "AVG") or 0, _num(row, "OBP") or 0, bb)
    diffs = {}
    for split, (avg_col, obp_col) in SPLIT_COLUMNS.items():
        s_avg, s_obp = _num(row, avg_col), _num(row, obp_col)
        if s_avg is not None and s_obp is not None:
            s_h, s_walk = _hit_walk_rates(s_avg, s_obp, bb)
            diffs[split] = (s_h - h, s_walk - walk, pa * BATTER_SPLIT_SHARE[split])
    return diffs


def _pitcher_split_diffs(row):
    """상대 타자 손별 (피안타 비율 - 평균, 볼넷 비율 - 평균, 추정 상대 타자 수)"""
    whip = _num(row, "WHIP")
    if whip is None:
        return {}
    bf = innings(_num(row, "IP")) * (3 + whip)
    bb = (_num(row, "BB%") or 0) / 100
    raw = {}
    for split, (avg_col, obp_col) in PITCHER_SPLIT_COLUMNS.items():
        s_avg, s_obp = _num(row, avg_col), _num(row, obp_col)
        if s_avg is None or s_obp is None:
            return {}
        raw[split] = _hit_walk_rates(s_avg, s_obp, bb)
    mean_h = sum(PITCHER_SPLIT_SHARE[s] * raw[s][0] for s in raw)
    mean_walk = sum(PITCHER_SPLIT_SHARE[s] * raw[s][1] for s in raw)
    return {s: (s_h - mean_h, s_walk - mean_walk, bf * PITCHER_SPLIT_SHARE[s]) for s, (s_h, s_walk) in raw.items()}


def _league_platoon(entries):
    """(그룹, 스플릿, (안타 차이, 볼넷 차이, 표본)) 목록 → 표본 가중 평균. 그룹 None 은 전체 평균."""
    sums = {}
    for group, split, (dh, dw, n) in entries:
        for key in {(group, split), (None, split)}:
            total = sums.setdefault(key, [0.0, 0.0, 0.0])
            total[0] += dh * n
            total[1] += dw * n
            total[2] += n
    # 그룹 평균도 표본이 작으면(예: 좌타자 vs 언더 약 800타석) 0 쪽으로 줄인다
    return {key: (t[0] / (t[2] + PLATOON_LEAGUE_REG), t[1] / (t[2] + PLATOON_LEAGUE_REG))
            for key, t in sums.items() if t[2] > 0}


def _platoon_group(hand):
    """양타자는 표본이 적어(9명) 그룹 평균이 불안정하므로 전체 평균을 쓴다."""
    return None if hand == "S" else hand


def _apply_splits(rates, splits, league_platoon, group, diffs, include_league=True):
    """개인 플래툰 차이를 리그 평균 플래툰 차이 쪽으로 회귀시켜 전체 비율에 더한다.

    리그 평균 플래툰 효과는 타자·투수 중 한쪽(타자)에만 넣는다. 양쪽에 넣으면 odds ratio 결합 때
    같은 효과가 두 번 반영된다. 투수 쪽은 include_league=False 로 개인 편차만 반영한다.
    """
    result = {}
    for split in splits:
        base_h, base_w = league_platoon.get((group, split)) or league_platoon.get((None, split)) or (0.0, 0.0)
        dh, dw, n = diffs.get(split, (base_h, base_w, 0))
        weight = n / (n + SPLIT_REG)
        shift_h = (base_h if include_league else 0.0) + (dh - base_h) * weight
        shift_w = (base_w if include_league else 0.0) + (dw - base_w) * weight
        result[split] = {
            "h": max(rates["h"] + shift_h, 0.02),
            "bb": max(rates["bb"] + shift_w, 0.005),
        }
    return result


def _index_rows(rows):
    by_key, by_name = {}, {}
    for row in rows:
        by_key[(row["Team"], row["Player"])] = row
        by_name.setdefault(row["Player"], []).append(row)
    return by_key, by_name


def _index_types(rows, column, mapping):
    by_key, by_name = {}, {}
    for row in rows:
        value = mapping.get((row.get(column) or "").strip())
        if value:
            by_key[(row["Team"], row["Name"])] = value
            by_name.setdefault(row["Name"], set()).add(value)
    return by_key, by_name


def _lookup_type(index, team, name):
    by_key, by_name = index
    if (team, name) in by_key:
        return by_key[(team, name)]
    values = by_name.get(name, set())
    return next(iter(values)) if len(values) == 1 else None


def _batter_observed(row):
    """타자 한 명의 타석당 관측 비율 {pa, k, bb, h, xb, hits}.

    원시 기록(H, BB, HBP, SO, 2B, 3B, HR)이 있으면 그대로 나누고,
    없으면(비율만 있는 데이터) 타율·출루율·K%·BB% 로 추정한다.
    bb 는 볼넷+사구, xb 는 안타당 추가 루타(안타가 없으면 None).
    """
    pa = _num(row, "PA") or 0
    if _num(row, "H") is not None and _num(row, "BB") is not None:
        hits = _num(row, "H")
        extra = (_num(row, "2B") or 0) + 2 * (_num(row, "3B") or 0) + 3 * (_num(row, "HR") or 0)
        return {"pa": pa, "k": (_num(row, "SO") or 0) / pa, "bb": (_num(row, "BB") + (_num(row, "HBP") or 0)) / pa,
                "h": hits / pa, "xb": extra / hits if hits else None, "hits": hits}

    bb_pct = (_num(row, "BB%") or 0) / 100
    avg, obp, slg = _num(row, "AVG") or 0, _num(row, "OBP") or 0, _num(row, "SLG") or 0
    h, walk = _hit_walk_rates(avg, obp, bb_pct)
    return {"pa": pa, "k": (_num(row, "K%") or 0) / 100, "bb": walk, "h": h,
            "xb": (slg - avg) / avg if avg > 0 else None, "hits": h * pa}


def _pitcher_observed(row, default_whip):
    """투수 한 명의 상대 타자당 관측 비율 {bf, k, bb, h, hr, ip}.

    상대 타자 수(TBF)와 원시 기록이 있으면 그대로 나누고,
    없으면 WHIP·K%·BB%·HR/9 로 상대 타자 수와 비율을 추정한다.
    """
    ip = innings(_num(row, "IP"))
    tbf = _num(row, "TBF")
    if tbf:
        return {"bf": tbf, "k": (_num(row, "SO") or 0) / tbf,
                "bb": ((_num(row, "BB") or 0) + (_num(row, "HBP") or 0)) / tbf,
                "h": (_num(row, "H") or 0) / tbf, "hr": (_num(row, "HR") or 0) / tbf, "ip": ip}

    whip = _num(row, "WHIP") or default_whip
    bb_pct = (_num(row, "BB%") or 0) / 100
    return {"bf": ip * (3 + whip), "k": (_num(row, "K%") or 0) / 100, "bb": bb_pct + HBP_RATE,
            "h": max(whip / (3 + whip) - bb_pct, 0.02), "hr": (_num(row, "HR/9") or 0) / (9 * (3 + whip)),
            "ip": ip}


def _league_batter(rows):
    total = defaultdict(float)
    for r in rows:
        obs = _batter_observed(r)
        pa = obs["pa"]
        for e in ("k", "bb", "h"):
            total[e] += obs[e] * pa
        total["pa"] += pa
        if obs["xb"] is not None:
            total["xb"] += obs["xb"] * obs["hits"]
            total["hits"] += obs["hits"]
    league = {e: total[e] / total["pa"] for e in ("k", "bb", "h")}
    league["out"] = 1 - league["k"] - league["bb"] - league["h"]
    league["xb"] = total["xb"] / total["hits"]
    return league


def _league_pitcher(rows):
    whips = [(_num(r, "WHIP"), innings(_num(r, "IP"))) for r in rows if _num(r, "WHIP") is not None]
    league_whip = sum(w * ip for w, ip in whips) / sum(ip for _, ip in whips)
    total = defaultdict(float)
    for r in rows:
        obs = _pitcher_observed(r, league_whip)
        for e in ("k", "bb", "h", "hr"):
            total[e] += obs[e] * obs["bf"]
        total["bf"] += obs["bf"]
    league = {e: total[e] / total["bf"] for e in ("k", "bb", "h")}
    league["out"] = 1 - league["k"] - league["bb"] - league["h"]
    league["hr_per_hit"] = total["hr"] / total["h"]
    league["whip"] = league_whip
    return league


# ---------- 경기 진행 ----------

class Offense:
    """팀별 타순 상태. 두 팀이 타순을 공유하지 않도록 팀마다 따로 둔다."""

    def __init__(self, lineup):
        self.lineup = lineup
        self.next_index = 0

    def next_batter(self):
        batter = self.lineup[self.next_index % len(self.lineup)]
        self.next_index += 1
        return batter


class Staff:
    """선발 → 중간계투(입력 순서대로 1이닝씩) → 9회 이후 세이브/동점 상황에 마무리"""

    def __init__(self, plan, rng):
        expected = plan.starter.starter_innings
        whole = int(expected)
        self.starter_innings = min(max(whole + (rng.random() < expected - whole), 1), 9)
        self.plan = plan
        self.relief_index = 0
        self.closer_used = False

    def pitcher_for(self, inning, lead):
        if inning <= self.starter_innings:
            return self.plan.starter
        closer = self.plan.closer
        if closer and not self.closer_used and inning >= 9 and 0 <= lead <= MAX_CLOSER_LEAD:
            self.closer_used = True
            return closer
        pool = self.plan.middle or [closer or self.plan.starter]
        pitcher = pool[min(self.relief_index, len(pool) - 1)]
        self.relief_index += 1
        return pitcher


def play_half_inning(model, offense, pitcher, rng, runs_to_win=None):
    """반 이닝 득점. runs_to_win 이 있으면 끝내기 점수에 도달하는 즉시 종료한다."""
    runs, outs = 0, 0
    bases = [False, False, False]
    while outs < 3:
        table = model.outcome_table(offense.next_batter(), pitcher)
        r = rng.random()
        outcome = next((o for cum, o in table if r < cum), table[-1][1])
        scored, bases, outs = advance_runners(outcome, bases, outs, rng)
        runs += scored
        if runs_to_win is not None and runs >= runs_to_win:
            break
    return runs


def advance_runners(outcome, bases, outs, rng):
    """(득점, 새 주자 상태, 아웃 수)"""
    first, second, third = bases
    if outcome == "k":
        return 0, bases, outs + 1

    if outcome == "bb":  # 밀려나는 주자만 진루
        runs = 1 if first and second and third else 0
        return runs, [True, first or second, third or (first and second)], outs

    two_out = outs == 2

    if outcome == "out":
        if rng.random() < P_REACH_ON_ERROR:
            return int(third), [True, first, second], outs
        if first and outs < 2 and rng.random() < P_DOUBLE_PLAY:
            outs += 2
            runs = 1 if third and outs < 3 else 0
            return runs, [False, second, third and not runs], outs
        outs += 1
        runs = 0
        if outs < 3:
            if third and rng.random() < P_SAC_FLY:
                runs, third = 1, False
            if second and not third and rng.random() < P_OUT_2B_TO_3B:
                second, third = False, True
        return runs, [first, second, third], outs

    if outcome == "single":
        runs = int(third)
        new = [True, False, False]
        if second:
            if rng.random() < P_SINGLE_2B_SCORES[two_out]:
                runs += 1
            else:
                new[2] = True
        if first:
            if not new[2] and rng.random() < P_SINGLE_1B_TO_3B[two_out]:
                new[2] = True
            else:
                new[1] = True
        return runs, new, outs

    if outcome == "double":
        runs = int(third) + int(second)
        new = [False, True, False]
        if first:
            if rng.random() < P_DOUBLE_1B_SCORES[two_out]:
                runs += 1
            else:
                new[2] = True
        return runs, new, outs

    if outcome == "triple":
        return first + second + third, [False, False, True], outs

    if outcome == "homerun":
        return 1 + first + second + third, [False, False, False], outs

    raise ValueError(f"알 수 없는 결과: {outcome}")


def simulate_game(model, home, away, rng):
    """(홈 득점, 원정 득점). 원정팀이 초, 홈팀이 말 공격."""
    home_bats, away_bats = Offense(home.lineup), Offense(away.lineup)
    home_staff, away_staff = Staff(home, rng), Staff(away, rng)
    home_score = away_score = 0

    for inning in range(1, MAX_INNINGS + 1):
        pitcher = home_staff.pitcher_for(inning, home_score - away_score)
        away_score += play_half_inning(model, away_bats, pitcher, rng)

        if inning >= 9 and home_score > away_score:
            break  # 9회말 이후 홈팀이 이기고 있으면 말 공격 없음

        pitcher = away_staff.pitcher_for(inning, away_score - home_score)
        runs_to_win = away_score - home_score + 1 if inning >= 9 else None
        home_score += play_half_inning(model, home_bats, pitcher, rng, runs_to_win)

        if inning >= 9 and home_score != away_score:
            break
    return home_score, away_score


def run(args, data_dir=DATA_DIR):
    start = time.time()
    model = Model(args.get("data_dir") or data_dir)
    home = model.team_plan(args["home"])
    away = model.team_plan(args["away"])
    match_count = int(args.get("match_count", 1000))
    rng = random.Random(args.get("seed"))

    home_wins = away_wins = draws = home_runs = away_runs = 0
    for _ in range(match_count):
        h, a = simulate_game(model, home, away, rng)
        home_runs += h
        away_runs += a
        if h > a:
            home_wins += 1
        elif a > h:
            away_wins += 1
        else:
            draws += 1

    return {
        "match_count": match_count,
        "home_win_count": home_wins,
        "away_win_count": away_wins,
        "draw_count": draws,
        "home_win_rate": home_wins / match_count,
        "away_win_rate": away_wins / match_count,
        "draw_rate": draws / match_count,
        "home_avg_score": home_runs / match_count,
        "away_avg_score": away_runs / match_count,
        "warnings": model.warnings,
        "elapsed_time": time.time() - start,
    }


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        if len(argv) < 2:
            raise ValueError("입력 파일 경로가 필요합니다: py simulation.py input.json")
        with open(argv[1], encoding="utf-8") as f:
            result = run(json.load(f))
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
