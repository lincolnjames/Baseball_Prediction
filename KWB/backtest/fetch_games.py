"""
KBO 공식 사이트에서 정규시즌 경기 결과와 선발투수를 받아 CSV 로 저장한다.

사용법: py fetch_games.py [시작일 YYYYMMDD] [종료일 YYYYMMDD]
출력:   data/kbo_2025_games.csv

날짜마다 요청 1건을 보내며, 서버 부담을 줄이려고 요청 사이에 쉰다.
결과 CSV 는 저장소에 커밋해 두므로 백테스트를 돌릴 때마다 다시 받을 필요는 없다.
"""
import csv
import datetime
import json
import os
import sys
import time
import urllib.parse
import urllib.request

URL = "https://www.koreabaseball.com/ws/Main.asmx/GetKboGameList"
HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "User-Agent": "Mozilla/5.0 (KWB backtest)",
    "Referer": "https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx",
}
REGULAR_SEASON = 0  # SR_ID: 0 = 정규시즌
REQUEST_INTERVAL_SEC = 0.5

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "kbo_2025_games.csv")
FIELDS = ["date", "game_id", "stadium", "away", "home", "away_score", "home_score",
          "away_starter", "home_starter", "status"]


def fetch_day(day):
    body = urllib.parse.urlencode({"leId": 1, "srId": "0,1,3,4,5,6,7,8,9", "date": day.strftime("%Y%m%d")})
    request = urllib.request.Request(URL, data=body.encode(), headers=HEADERS, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response).get("game") or []


def to_row(game):
    finished = game["CANCEL_SC_ID"] == "0" and str(game.get("GAME_RESULT_CK")) == "1"
    return {
        "date": f"{game['G_DT'][:4]}-{game['G_DT'][4:6]}-{game['G_DT'][6:]}",
        "game_id": game["G_ID"],
        "stadium": game["S_NM"],
        "away": game["AWAY_NM"],
        "home": game["HOME_NM"],
        "away_score": game["T_SCORE_CN"] if finished else "",
        "home_score": game["B_SCORE_CN"] if finished else "",
        "away_starter": (game.get("T_PIT_P_NM") or "").strip(),
        "home_starter": (game.get("B_PIT_P_NM") or "").strip(),
        "status": "final" if finished else (game.get("CANCEL_SC_NM") or "unknown"),
    }


def main(argv):
    start = datetime.datetime.strptime(argv[1] if len(argv) > 1 else "20250322", "%Y%m%d").date()
    end = datetime.datetime.strptime(argv[2] if len(argv) > 2 else "20251005", "%Y%m%d").date()

    rows = []
    day = start
    while day <= end:
        games = [g for g in fetch_day(day) if g.get("SR_ID") == REGULAR_SEASON]
        rows += [to_row(g) for g in games]
        print(f"{day} {len(games)}경기", file=sys.stderr)
        day += datetime.timedelta(days=1)
        time.sleep(REQUEST_INTERVAL_SEC)

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    final = sum(1 for r in rows if r["status"] == "final")
    print(f"{len(rows)}경기 저장 (종료 {final}경기) → {OUTPUT}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv)
