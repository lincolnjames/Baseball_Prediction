# KWB - KBO 경기 승부 예측

KBO 경기 일정을 보고, 양 팀 라인업(타순 9명 + 선발·중간계투·마무리)을 골라 몬테카를로 시뮬레이션으로 승률과 평균 득점을 예측하는 웹 애플리케이션입니다.

- **백엔드**: Spring Boot 3.4 / MyBatis / MySQL
- **화면**: Thymeleaf + jQuery
- **시뮬레이션**: Python (표준 라이브러리만 사용)
- **데이터**: 2025 시즌 타자·투수 기록, 경기 일정 (CSV)

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

1. [`db/schema.sql`](KWB/src/main/resources/db/schema.sql)이 `hitters`, `pitchers`, `schedule` 테이블을 **삭제 후 다시 생성**
2. [`CsvDataLoader`](KWB/src/main/java/com/application/KWB/data/CsvDataLoader.java)가 `static/*.csv`를 읽어 적재

**CSV가 원본 데이터입니다.** 데이터를 바꾸려면 CSV를 수정하고 앱을 재시작하세요. DB에 직접 수정한 내용은 재시작하면 사라집니다.

CSV 헤더는 다음 규칙에 따라 DB 컬럼명으로 바뀝니다: 소문자화, `%`→`_pct`, `+`→`_plus`, `/`→`_per_`, 공백→`_` (예: `wRC+` → `wrc_plus`, `HR/9` → `hr_per_9`).

| 파일 | 내용 | DB 적재 |
|---|---|---|
| `hitters.csv` | 타자 시즌 기록 (좌/우/언더 투수 상대 기록 포함) | O |
| `pitchers.csv` | 투수 시즌 기록 (좌/우 타자 상대 기록 포함) | O |
| `schedule.csv` | 2025 정규시즌 일정 (개막 전 원래 일정. 우천 취소, NC 구장 변경 16경기 미반영) | O |
| `hitters_type.csv` | 타자 좌/우타 | X (시뮬레이션만 사용) |
| `pitchers_type.csv` | 투수 유형 (우투/좌투/우언) | X (시뮬레이션만 사용) |

## 최신 시즌 기록 넣기

저장소에는 2025년 5월 시점의 기본 데이터만 있습니다. 최신 기록은 **KBO 기록실에서 사람이 직접 표를 복사해** 넣습니다. KBO와 스탯티즈는 사전 승인 없는 자동 수집을 금지하므로 크롤러는 쓰지 않고, 복사한 원본과 변환 결과도 저장소에 올리지 않습니다 (`KWB/import/`는 `.gitignore` 대상).

1. KBO 기록실 → 선수 기록에서 시즌과 팀을 고르고, 아래 4개 표를 복사해 `KWB/import/<연도>/` 아래 `.txt` 파일로 저장합니다. 파일 이름, 순서, 헤더 유무는 상관없습니다 (열 개수로 표 종류를 판별).

   | 표 | 열 개수 |
   |---|---|
   | 타자 → 기본기록 (1번 표) | 16 |
   | 타자 → 기본기록 (다음 ▶ 2번 표) | 15 |
   | 투수 → 기본기록 (1번 표) | 19 |
   | 투수 → 기본기록 (다음 ▶ 2번 표) | 18 |

2. 검산 및 변환:

   ```bash
   cd KWB
   py tools/kbo_import.py import/2026    # → import/2026/out/hitters.csv, pitchers.csv
   ```

   [`kbo_import.py`](KWB/tools/kbo_import.py)가 타율, 출루율, 장타율, 피안타율, 평균자책, WHIP를 원시 기록으로 다시 계산해 표 값과 비교합니다. 붙여넣다 줄이 붙거나 페이지가 빠지면 알려주고 CSV를 만들지 않습니다. 같은 팀의 동명이인은 `이름(N경기)`로 구분합니다.

3. 앱 실행 시 데이터 폴더 지정:

   ```bash
   KWB_DATA_DIR=import/2026/out ./gradlew bootRun
   ```

   지정한 폴더에 있는 파일만 바꿔 쓰고, 없는 파일(예: `schedule.csv`)은 기본 데이터를 씁니다. 시뮬레이션도 같은 폴더를 씁니다. 원시 기록(안타, 볼넷, 상대 타자 수 등)이 있으면 비율을 역산하지 않고 그대로 계산합니다. 좌우 정보는 기본 데이터의 `*_type.csv`를 쓰며, 여기에 없는 신인·새 외국인 선수는 좌우 상성 없이 계산합니다.

## 테스트

```bash
# Java (로컬 MySQL 필요. 앱과 똑같이 테이블을 다시 만들고 CSV를 적재함)
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
6. **주루**: 2아웃 여부에 따른 추가 진루, 병살, 희생플라이, 실책 출루를 근사치 확률로 반영합니다.

**보정 기준**: 리그 평균 타자·투수끼리 붙이면 팀당 경기 득점이 데이터상 리그 수준(IP 가중 ERA × 1.08 ≈ 4.56점)과 ±0.3점 이내로 맞아야 합니다. 테스트 `test_league_average_teams_score_like_the_league`가 이를 검증합니다.

선수는 **팀 + 이름**으로 찾으므로 동명이인도 구분합니다. 기록이 없는 선수는 리그 평균으로 계산하고 결과의 `warnings`에 표시합니다.

모델에 없는 것: 홈 어드밴티지, 투수 체력(투구 수), 도루, 수비력, 구장 효과

## 백테스트

모델이 실제 경기를 얼마나 맞히는지 [`KWB/backtest/`](KWB/backtest/)에서 측정합니다.

```bash
cd KWB/backtest
py backtest.py --sims 1000 --report REPORT.md   # 약 1분
```

- **데이터**: 2025 정규시즌 720경기 결과와 실제 선발투수. **저장소에는 포함하지 않습니다.** KBO 공식 사이트가 사전 승인 없는 자동 수집·복제를 금지하기 때문입니다. 승인받은 경로로 확보한 파일을 `KWB/backtest/data/kbo_2025_games.csv`에 두고 실행하세요 (컬럼은 `backtest.py`의 `GAMES_COLUMNS` 참고). 파일이 없으면 관련 테스트는 건너뜁니다.
- **미래 정보 차단**: 선수 기록 CSV는 2025-05-20 경기까지 반영된 스냅샷이므로(선발 39명의 등판 수가 모두 일치), 5월 21일 이후 경기만 평가합니다.
- **입력**: 선발투수는 실제 선발, 타순과 불펜은 팀별 기본값(타석 상위 9명, 등판 많은 불펜)

**결과** (평가 468경기, 무승부 제외, 자세한 내용은 [`REPORT.md`](KWB/backtest/REPORT.md))

| 모델 | 적중률 | Brier ↓ |
|---|---|---|
| 시뮬레이션 모델 | **0.572** | **0.2447** |
| 기준: 동전 던지기 | - | 0.2500 |
| 기준: 홈팀 승률 상수 | 0.511 | 0.2499 |
| 기준: 5월까지 득실점 피타고리안 + 홈 이점 | 0.547 | 0.2525 |

- 적중률 57.2%는 50% 대비 약 3 표준오차 위입니다. 참고로 MLB 최고 수준 모델의 적중률은 58~60% 정도입니다.
- Brier skill(동전 대비)은 +2.1%이지만 **95% 신뢰구간이 -0.3% ~ +4.5%로 0을 포함합니다.** 확률 예측의 질이 확실히 낫다고 말하려면 표본이나 모델 개선이 더 필요합니다.
- 5월 20일 이후 합류한 선발 24명(부상 복귀, 대체 외국인 선수 등)은 기록이 없어 리그 평균으로 계산됩니다. 기록 갱신이 가장 큰 개선 여지입니다.

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
    ├── mapper/      MyBatis 매퍼
    ├── templates/   Thymeleaf 화면
    └── static/      CSV 데이터, simulation.py
```

## 주요 경로

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/` | 메인 (월별 경기 일정, 팀 목록) |
| GET | `/match/month?month=5` | 해당 월 경기 목록 (JSON) |
| GET | `/match/detail?hometeam=LG&awayteam=KT` | 라인업 선택 화면 |
| GET | `/team/detail?team=LG` | 팀 선수 기록 |
| POST | `/simulation/run` | 시뮬레이션 실행 (JSON) |

## 알려진 제약

- `simulation.py`와 CSV가 `static/`에 있어 웹에서 그대로 접근할 수 있음
- 시뮬레이션이 `src/main/resources/static/input.json` 파일 하나를 공유함 → 동시 요청 시 충돌하고, JAR로 배포하면 동작하지 않음
- 시뮬레이션 실행이 Windows `py` 런처에 의존함
