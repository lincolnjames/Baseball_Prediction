# KWB - KBO 경기 승부 예측

> **English summary**: A full-stack web app (Spring Boot + MyBatis + MySQL backend, Thymeleaf/vanilla-JS frontend) that predicts KBO (Korean Baseball Organization) game outcomes via Monte Carlo simulation in Python. Player stats feed a pitch-by-pitch simulation (odds-ratio batter/pitcher matchups, platoon splits, sample-size regression, park factors, errors, steals, wild pitches) to estimate win probability and expected runs for a given lineup. It also recommends lineup changes — both bench swaps and batting-order reshuffling — and verifies each recommendation with its own simulation run. The repo ships a 2025-season baseline dataset, used for the backtest below (468 real games, **57.9% accuracy** — in line with the ~55–58% ceiling cited for MLB-style pregame models such as FiveThirtyEight, with results reported honestly including confidence intervals). Live predictions are kept current with 2026-season data, hand-copied from KBO's official site (no scraping, per their terms) and verified by cross-checking derived stats (batting average, ERA, etc.) against the raw box-score numbers before use. See below for details (Korean).

KBO 경기 일정을 보고, 양 팀 라인업(타순 9명 + 선발·중간계투·마무리)을 골라 몬테카를로 시뮬레이션으로 승률과 평균 득점을 예측하는 웹 애플리케이션입니다.

- **백엔드**: Spring Boot 3.4 / MyBatis / MySQL
- **화면**: Thymeleaf + 순수 JS (외부 프론트엔드 라이브러리 없음), 공통 디자인 시스템(`static/css/kwb.css`)
- **시뮬레이션**: Python (표준 라이브러리만 사용)
- **데이터**: 저장소에는 2025 시즌 타자·투수 기록·경기 일정(CSV)만 기본으로 들어 있고(백테스트도 이 데이터 기준), 실제 운영 중인 예측은 2026 시즌 데이터를 [`kbo_import.py`](KWB/tools/kbo_import.py)로 갱신해 사용합니다(사람이 직접 복사한 원시 기록, 안타·볼넷 등 그대로 — 아래 "최신 시즌 기록 넣기" 참고)

## 실행 환경

| 도구 | 버전 | 비고 |
|---|---|---|
| JDK | 17 | Gradle 8.13 은 JDK 24 이상에서 실행되지 않음. `JAVA_HOME` 이 JDK 17을 가리켜야 함 |
| MySQL | 8.x | DB(`KWB`)는 자동 생성됨 |
| Python | 3.10+ | Windows `py` 런처 필요 (현재 시뮬레이션 호출이 `py` 명령 사용) |

## 실행 방법

```bash
# 앱 실행 (http://localhost). Python 추가 패키지는 필요 없음
cd KWB
./gradlew bootRun          # Windows: gradlew.bat bootRun
```

DB 접속 정보는 환경변수로 바꿀 수 있습니다. 설정하지 않으면 괄호 안의 기본값을 씁니다.

| 환경변수 | 기본값 |
|---|---|
| `DB_HOST` | `localhost` |
| `DB_PORT` | `3306` |
| `DB_NAME` | `KWB` |
| `DB_USERNAME` | `root` |
| `DB_PASSWORD` | `1234` |

## 데이터 적재 방식

앱이 시작될 때마다 다음 순서로 DB를 초기화합니다.

1. [`db/schema.sql`](KWB/src/main/resources/db/schema.sql)이 `hitters`, `pitchers`, `schedule`, `positions` 테이블을 **삭제 후 다시 생성**
2. [`CsvDataLoader`](KWB/src/main/java/com/application/KWB/data/CsvDataLoader.java)가 `static/*.csv`를 읽어 적재. CSV 헤더를 그대로 DB 컬럼명으로 바꿔 INSERT를 만들기 때문에, **CSV에 새 열을 추가하면 `schema.sql`에도 같은 이름의 컬럼을 추가해야** 앱이 죽지 않습니다.

**CSV가 원본 데이터입니다.** 데이터를 바꾸려면 CSV를 수정하고 앱을 재시작하세요(템플릿과 마찬가지로, 코드/리소스를 바꾼 뒤에는 재시작해야 반영됩니다). DB에 직접 수정한 내용은 재시작하면 사라집니다.

CSV 헤더는 다음 규칙에 따라 DB 컬럼명으로 바뀝니다: 소문자화, `%`→`_pct`, `+`→`_plus`, `/`→`_per_`, 공백→`_` (예: `wRC+` → `wrc_plus`, `HR/9` → `hr_per_9`).

| 파일 | 내용 | DB 적재 | 시뮬레이션 사용 |
|---|---|---|---|
| `hitters.csv` | 타자 시즌 기록 (좌/우/언더 투수 상대 기록 포함) | O | O |
| `pitchers.csv` | 투수 시즌 기록 (좌/우 타자 상대 기록, 폭투 `WP` 포함) | O | O |
| `schedule.csv` | 앞으로 치를(또는 이미 치른) 경기 일정 | O | X |
| `positions.csv` | 타자별 수비 포지션 출장(선택, 예측 화면의 포지션별 교체 후보) | O | O |
| `games.csv` | 경기 결과(선택). 종료 경기는 `game_results`에 자동 반영 | 부분(결과만) | O(구장 요인) |
| `fielding.csv` | 팀별 실책·허용 도루·포일(선택, 2026 원시 기록에서만) | X | O |
| `running.csv` | 타자별 도루 시도·성공(선택, 2026 원시 기록에서만) | X | O |
| `hitters_type.csv` | 타자 좌/우타 | X | O |
| `pitchers_type.csv` | 투수 유형 (우투/좌투/우언) | X | O |

## 최신 시즌 기록 넣기

저장소에는 2025년 5월 시점의 기본 데이터만 있습니다. 최신 기록은 **KBO 기록실에서 사람이 직접 표를 복사해** 넣습니다. KBO와 스탯티즈는 사전 승인 없는 자동 수집을 금지하므로 크롤러는 쓰지 않고, 복사한 원본과 변환 결과도 저장소에 올리지 않습니다 (`KWB/import/`는 `.gitignore` 대상).

1. KBO 기록실 → 선수 기록에서 시즌과 팀을 고르고, 아래 표를 복사해 `KWB/import/<연도>/` 아래 `.txt` 파일로 저장합니다. 파일 이름, 순서, 헤더 유무는 상관없습니다 (열 개수로 표 종류를 판별).

   | 표 | 열 개수 | CSV |
   |---|---|---|
   | 타자 → 기본기록 (1번 표) | 16 | `hitters.csv` |
   | 타자 → 기본기록 (다음 ▶ 2번 표) | 15 | `hitters.csv` |
   | 투수 → 기본기록 (1번 표) | 19 | `pitchers.csv` |
   | 투수 → 기본기록 (다음 ▶ 2번 표, 폭투 `WP` 포함) | 18 | `pitchers.csv` |
   | 수비 → 기본기록 (선택. 포지션별 교체 후보, 팀 실책·허용 도루·포일) | 17 | `positions.csv`, `fielding.csv` |
   | 주루 → 기본기록 (선택. 타자별 도루 시도·성공) | 10 | `running.csv` |

   일정도 넣으려면 KBO 일정·결과 페이지를 월별로 복사해 `schedule`로 시작하는 파일(예: `schedule.txt`)에 이어 붙입니다. 겹쳐 붙여도 중복은 합쳐집니다.

2. 검산 및 변환:

   ```bash
   cd KWB
   py tools/kbo_import.py import/2026    # → import/2026/out/hitters.csv, pitchers.csv, ...
   ```

   [`kbo_import.py`](KWB/tools/kbo_import.py)가 타율, 출루율, 장타율, 피안타율, 평균자책, WHIP, 수비율을 원시 기록으로 다시 계산해 표 값과 비교합니다. 붙여넣다 줄이 붙거나 페이지가 빠지면 알려주고 CSV를 만들지 않습니다. 같은 팀의 동명이인은 `이름(N경기)`로 구분합니다.

   일정 파일이 있으면 `schedule.csv`(치른 경기와 남은 경기, 앱 일정용)와 `games.csv`(취소 포함 전체와 점수)도 만듭니다. **경기 결과로 센 팀 승패**와 **투수 기록의 승패 합계**를 비교해, 두 페이지가 서로 어긋나면(복사 누락, 복사 시점 차이) 알려줍니다.

3. 앱 실행 시 데이터 폴더 지정:

   ```bash
   KWB_DATA_DIR=import/2026/out ./gradlew bootRun
   ```

   지정한 폴더에 있는 파일만 바꿔 쓰고, 없는 파일(예: 일정을 넣지 않았을 때의 `schedule.csv`)은 기본 데이터를 씁니다. 시뮬레이션도 같은 폴더를 씁니다. 원시 기록(안타, 볼넷, 상대 타자 수 등)이 있으면 비율을 역산하지 않고 그대로 계산합니다. 좌우 정보는 기본 데이터의 `*_type.csv`를 쓰며, 여기에 없는 신인·새 외국인 선수는 좌우 상성 없이 계산합니다.

## 테스트

```bash
# Java (로컬 MySQL 필요. 테이블을 다시 만들고 CSV를 적재하므로, 실행 중인 앱의 DB(KWB)와 섞이지 않게
#       기본으로 별도 DB kwb_test 를 씀)
cd KWB
./gradlew test

# Python 시뮬레이션 (저장소 루트에서)
py -m unittest discover -s KWB/src/test/python
```

## 시뮬레이션 모델

[`simulation.py`](KWB/src/main/resources/static/simulation.py)가 한 타석씩 경기를 진행하며 기본 1000경기를 반복합니다.

1. **타석 결과 확률**: 선수 기록을 타석당 삼진 / 볼넷+사구 / 안타 / 인플레이 아웃 비율로 바꿉니다. 타자와 투수 확률은 odds ratio(Log5 일반화)로 결합합니다.
2. **표본 회귀**: 시즌 초 100타석 안팎의 기록을 그대로 믿지 않도록, 표본이 작을수록 리그 평균 쪽으로 당깁니다.
3. **플래툰**: 좌/우/언더 상대 기록은 리그 평균 플래툰 차이(예: 좌타자의 언더 투수 상대 이점) 쪽으로 강하게 회귀시켜 반영합니다.
4. **장타**: 타자의 안타당 추가 루타((SLG-AVG)/AVG)와 투수의 피홈런 비율로 안타 종류를 나눕니다.
5. **경기 규칙**: 원정 초·홈 말 공격, 9회말 생략, 끝내기, 연장 11회 후 무승부. 선발 → 중간계투(지정 순서대로 1이닝씩) → 9회 이후 3점 차 이내 리드나 동점이면 마무리.
6. **주루**: 2아웃 여부에 따른 추가 진루, 병살, 희생플라이를 근사치 확률로 반영합니다.
7. **실책**: 인플레이 아웃이 실책 출루가 될 확률을, 수비 팀의 이닝당 실책을 리그 평균 쪽으로 회귀시켜 반영합니다(`fielding.csv`가 없으면 리그 평균 고정값).
8. **도루**: `running.csv`가 있으면 1루 주자가 2루가 비어 있을 때 선수별 시도율로 도루를 시도하고, 성공률은 주자 성공률과 수비 팀(포수)의 도루 허용률을 odds ratio로 결합합니다.
9. **폭투·포일**: 주자가 있는 타석마다, 투수의 폭투 비율(`pitchers.csv`의 `WP`)과 수비 팀의 포일 비율(`fielding.csv`의 `PB`)을 리그 평균 쪽으로 회귀시킨 확률로 주자 전원이 한 베이스씩 진루합니다.
10. **구장 요인**: `games.csv`가 있으면 팀의 홈/원정 득점 비율(표본이 적으면 리그 평균 쪽으로 강하게 회귀)만큼 안타 확률을 조정합니다. 경기는 항상 홈팀 구장에서 열린다고 봅니다.

**보정 기준**: 리그 평균 타자·투수끼리 붙이면 팀당 경기 득점이 데이터상 리그 수준(IP 가중 ERA × 1.08 ≈ 4.56점)과 ±0.3점 이내로 맞아야 합니다. 테스트 `test_league_average_teams_score_like_the_league`가 이를 검증합니다.

선수는 **팀 + 이름**으로 찾으므로 동명이인도 구분합니다. 기록이 없는 선수는 리그 평균으로 계산하고 결과의 `warnings`에 표시합니다.

7~10번은 모두 **선택 데이터**(`fielding.csv`/`running.csv`/`games.csv`)가 있을 때만 켜집니다. 2025 기본 데이터에는 이 파일들이 없어 꺼진 채로 계산되고, 2026 원시 기록을 넣으면 자동으로 켜집니다.

모델에 없는 것: 홈 어드밴티지(구장 득점 환경과는 별개로, 순수 홈팀 이점은 백테스트에서만 보정), 투수 체력(투구 수)

## 승부 예측 화면

메인 화면 경기 목록의 **예측** 버튼(또는 `/match/predict?hometeam=두산&awayteam=NC`)으로 엽니다. KBO는 예고 선발을 전날 발표하고, 라인업은 경기 30분~1시간 전에 발표합니다. 이 흐름에 맞춰 두 단계로 예측합니다.

1. **시나리오 분석 (라인업 발표 전)**: 예고 선발과 예상 라인업(보통 최근 라인업)을 넣습니다. "주전 자동 채우기"로 포지션별 선발 출장 1위를 채울 수도 있습니다.
   - **기준 승률**: 입력한 라인업으로 4000경기를 시뮬레이션합니다.
   - **주요 변수**: 선수마다 결장했을 때 소속팀 승률이 얼마나 바뀌는지 보여줍니다. 대체 후보는 그 포지션을 실제로 맡아온 선수(수비 기록의 포지션별 선발 출장)입니다.
   - **라인업 변동을 반영한 예상**: 주전마다 결장 확률(시즌 선발 비율로 추정, 5~35%)을 두고 가능한 라인업 5000개를 뽑아, 승률 기댓값과 80% 범위를 계산합니다.
2. **확정 예측 (라인업 발표 후)**: 발표된 실제 라인업으로 1만 경기를 시뮬레이션합니다.

불펜은 세이브 1위를 마무리로, 홀드 상위 3명을 중간계투로 자동 구성합니다. 입력한 라인업은 브라우저에 팀별로 저장돼 "최근 입력 불러오기"로 다시 쓸 수 있습니다.

### 최적 라인업 추천

각 팀 라인업 카드의 **"최적 라인업 추천"** 버튼은 입력한 라인업에서 승률을 올릴 수 있는 변경을 두 단계로 찾아 보여줍니다.

1. **인선(포지션별 교체)**: 벤치에서 그 포지션을 실제로 맡아본 선수(수비 기록의 선발 출장 GS>0)로 바꿨을 때의 효과를, 위 "교체 효과를 계산으로 구하는 방법"과 같은 방식으로 계산해 전역 그리디로 승률을 최대화하는 조합을 고릅니다.
2. **타순(배팅 오더) 재배열**: 정해진 9명을 상대 선발·불펜 기준 타석당 득점 가치(OBP·SLG 가중)가 높은 순으로 재배열합니다. 타순별 평균 타석 수가 1번이 가장 많도록 고정된 수열이라, 이 정렬이 재배열 부등식에 의해 바로 전역 최적입니다(9! 전체 탐색이나 국소 탐색이 필요 없습니다).

추천 결과는 현재 라인업과 같은 seed로 비교 시뮬레이션해 검증한 뒤 보여주며, **"추천 라인업 적용"**으로 반영한 다음에는 "시나리오 분석"이나 "확정 예측"으로 다시 확인해야 합니다(추천 화면 자체는 결과를 기록하지 않습니다).

**표 붙여넣기로 채우기**: 각 팀 라인업 카드 아래 접이식 상자에, 다른 사이트에서 복사한 타순표나 경기 기록(박스스코어)을 붙여넣으면 로스터 이름과 일치하는 선수를 찾아 타순·선발투수를 자동으로 채웁니다. 열 순서는 상관없고, 포지션은 정식 명칭("좌익수")이든 한 글자·한자 숫자 약자("좌", "一"=1루)든 인식합니다. 경기 기록처럼 같은 타순에 교체 선수가 같이 나오면 먼저 나온 선발 줄만 쓰고, "타三"(대타 후 3루)처럼 포지션이 두 글자로 붙어 있으면 첫 글자(경기를 시작한 포지션)를 씁니다. 이미 끝난 경기를 실제 라인업으로 검증할 때 유용합니다 — 다만 **경기일 입력칸은 자동으로 안 바뀌므로, 예측을 기록할 거면 그 경기의 실제 날짜로 직접 바꿔야** 합니다(안 바꾸면 다음 예정 경기 날짜로 기록돼 실제 예측 성적에 섞입니다).

### 예측 기록과 채점

결과 아래 **"이 예측 기록하기"**를 누르면 예측이 DB에 저장되고, **예측 성적**(`/predictions`)에서 채점됩니다.

- 기록 시각은 서버 시계(한국 시간)로 정합니다. 기록은 **고치거나 지울 수 없습니다.** 결과를 보고 예측을 고치지 못하게 하기 위해서입니다. 검증·테스트 목적이면 기록하지 말고 화면 결과만 보세요.
- 경기마다 단계(발표 전 / 발표 후)별로 **경기 시작 전에 기록한 것 중 가장 늦은 예측** 하나만 채점합니다. 시작 뒤 기록은 제외하고, 시작 시각을 모르면 18:30으로 봅니다.
- 경기 결과는 일정을 다시 가져오면(`games.csv`) 자동으로 들어갑니다. 예측 성적 화면에서 직접 입력할 수도 있고, 직접 입력한 결과는 나중에 가져온 공식 결과가 덮어씁니다.
- 지표: 적중률, Brier, log loss, 동전 던지기 대비 개선. 무승부는 제외합니다.
- `predictions`, `game_results` 테이블은 다른 테이블과 달리 **앱을 재시작해도 지우지 않습니다.**

**교체 효과를 시뮬레이션이 아니라 계산으로 구하는 이유**: 선수 한 명 교체의 효과(1~3%p)는 수천 경기 시뮬레이션의 노이즈(±1%p)와 크기가 비슷해서, 시뮬레이션 두 번의 차이로는 구분이 안 됩니다. 그래서 [`scenario.py`](KWB/src/main/resources/static/scenario.py)는 다음처럼 계산합니다.

1. 상대 선발·불펜을 만났을 때의 타석당 득점 가치(선형 가중치) 차이를 구합니다.
2. 여기에 타순별 타석 수를 곱해 경기당 득점 차이로 바꿉니다.
3. 득점 1점당 승률 변화를 곱합니다.

마지막 계수는 교체 6건을 각 10만 경기씩 시뮬레이션해 보정했습니다 (보정 계수 0.815, 보정 후 오차 약 ±0.5%p). 테스트가 2025 데이터에서도 계산값과 4만 경기 시뮬레이션이 맞는지 확인합니다.

## 백테스트

모델이 실제 경기를 얼마나 맞히는지 [`KWB/backtest/`](KWB/backtest/)에서 측정합니다.

```bash
cd KWB/backtest
py backtest.py --sims 1000 --report REPORT.md   # 약 1분
```

`--data-dir`, `--games`, `--snapshot-date` 옵션으로 다른 시즌·다른 시점도 평가할 수 있습니다(기본값은 아래 2025 데이터). 예: `py backtest.py --data-dir import/2026/out --games data/kbo_2026_games.csv --snapshot-date 2026-06-30`.

- **데이터**: 2025 정규시즌 720경기 결과와 실제 선발투수. **저장소에는 포함하지 않습니다.** KBO 공식 사이트가 사전 승인 없는 자동 수집·복제를 금지하기 때문입니다. 승인받은 경로로 확보한 파일을 `KWB/backtest/data/kbo_2025_games.csv`에 두고 실행하세요 (컬럼은 `backtest.py`의 `GAMES_COLUMNS` 참고). 파일이 없으면 관련 테스트는 건너뜁니다.
- **미래 정보 차단**: 선수 기록 CSV는 2025-05-20 경기까지 반영된 스냅샷이므로(선발 39명의 등판 수가 모두 일치), 5월 21일 이후 경기만 평가합니다.
- **입력**: 선발투수는 실제 선발, 타순과 불펜은 팀별 기본값(타석 상위 9명, 등판 많은 불펜)
- 2025 기본 데이터에는 `fielding.csv`·`running.csv`·`games.csv`가 없어서, 아래 결과는 실책·도루·폭투/포일·구장 요인이 **모두 꺼진** 기본 모델 기준입니다.

**결과** (평가 468경기, 무승부 제외, 자세한 내용은 [`REPORT.md`](KWB/backtest/REPORT.md))

| 모델 | 적중률 | Brier ↓ |
|---|---|---|
| 시뮬레이션 모델 | **0.579** | **0.2441** |
| 기준: 동전 던지기 | - | 0.2500 |
| 기준: 홈팀 승률 상수 | 0.511 | 0.2499 |
| 기준: 5월까지 득실점 피타고리안 + 홈 이점 | 0.547 | 0.2525 |

- 적중률 57~58%는 실제 MLB 예측 모델(FiveThirtyEight 등)의 성적과 비슷한 수준입니다 — 논문·업계에서 말하는 "경기 전 정보만으로 낼 수 있는 현실적인 상한선"(약 55~58%)에 이미 들어와 있어서, 모델을 더 다듬어도 크게 오르진 않을 것으로 봅니다.
- Brier skill(동전 대비)은 +2.3%이지만 **95% 신뢰구간이 -0.1% ~ +4.8%로 0을 포함합니다.** 표본(468경기)이 늘면 신뢰구간은 좁아지지만(√n 법칙), 0에서 확실히 벗어나려면 수천 경기 단위가 필요합니다.
- 5월 20일 이후 합류한 선발 24명(부상 복귀, 대체 외국인 선수 등)은 기록이 없어 리그 평균으로 계산됩니다.
- (별도 확인) 실책·도루·폭투/포일·구장 요인을 다 켠 2026시즌 데이터로는, 팀 기본 라인업 시뮬레이션의 경기당 예측 득점이 실제 득점(10.16점)과 거의 일치(10.04점)합니다 — 정식 백테스트는 아니고(2026시즌 결과 데이터가 아직 없음), 득점 예측이 붙는지만 본 결과입니다.

## 구조

```
KWB/src/main/
├── java/com/application/KWB/
│   ├── main/        메인 페이지
│   ├── match/       경기 일정, 경기 상세(라인업 선택)
│   ├── team/        팀별 선수 기록
│   ├── simulation/  Python 시뮬레이션 호출
│   └── data/        CSV → DB 적재
└── resources/
    ├── db/schema.sql
    ├── mapper/              MyBatis 매퍼
    ├── templates/           Thymeleaf 화면
    │   └── fragments/       공통 상단바 등 조각 템플릿
    └── static/              CSV 데이터, simulation.py
        └── css/kwb.css      공통 디자인 시스템 (팀 색상, 배지, 카드, 버튼 등)
```

## 주요 경로

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/` | 메인 (월별 경기 일정, 팀 목록) |
| GET | `/match/month?month=5` | 해당 월 경기 목록 (JSON) |
| GET | `/match/detail?hometeam=LG&awayteam=KT` | 라인업 선택 화면 |
| GET | `/team/detail?team=LG` | 팀 선수 기록 |
| POST | `/simulation/run` | 시뮬레이션 실행 (JSON) |
| GET | `/match/predict?hometeam=두산&awayteam=NC` | 승부 예측 화면 |
| POST | `/simulation/scenario` | 시나리오 분석(`mode: analyze`) / 확정 예측(`mode: predict`) (JSON) |
| POST | `/predictions` | 예측 기록 (JSON) |
| GET | `/predictions` | 예측 성적 (채점 요약과 전체 기록) |
| POST | `/predictions/results` | 경기 결과 직접 입력 (폼) |

## 알려진 제약

- `simulation.py`와 CSV가 `static/`에 있어 웹에서 그대로 접근할 수 있음
- 시뮬레이션 스크립트를 `src/main/resources/static` 경로에서 실행함 → JAR로 배포하면 동작하지 않음 (입력은 요청마다 임시 파일이라 동시 요청은 안전)
- 앱이 시작될 때 DB 테이블을 다시 만드므로, 같은 DB를 쓰는 앱을 두 개 띄우면 먼저 떠 있던 앱의 데이터가 지워짐 (두 번째 앱이 포트 충돌로 실패해도 초기화는 이미 실행됨)
- 시뮬레이션 실행이 Windows `py` 런처에 의존함
