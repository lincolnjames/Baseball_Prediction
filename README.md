# KWB - KBO 경기 승부 예측

KBO 경기 일정을 보고, 양 팀 라인업(타순 9명 + 투수 1~5명)을 골라 몬테카를로 시뮬레이션으로 승률과 평균 득점을 예측하는 웹 애플리케이션입니다.

- **백엔드**: Spring Boot 3.4 / MyBatis / MySQL
- **화면**: Thymeleaf + jQuery
- **시뮬레이션**: Python (pandas, multiprocessing)
- **데이터**: 2025 시즌 타자·투수 기록, 경기 일정 (CSV)

## 실행 환경

| 도구 | 버전 | 비고 |
|---|---|---|
| JDK | 17 | Gradle 8.13 은 JDK 24 이상에서 실행되지 않음. `JAVA_HOME` 이 JDK 17을 가리켜야 함 |
| MySQL | 8.x | DB(`KWB`)는 자동 생성됨 |
| Python | 3.10+ | Windows `py` 런처 필요 (현재 시뮬레이션 호출이 `py` 명령 사용) |

## 실행 방법

```bash
# 1. Python 의존성 설치
py -m pip install -r KWB/requirements.txt

# 2. 앱 실행 (http://localhost)
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
| `schedule.csv` | 2025 정규시즌 일정 | O |
| `hitters_type.csv` | 타자 좌/우타 | X (시뮬레이션만 사용) |
| `pitchers_type.csv` | 투수 유형 (우투/좌투/우언) | X (시뮬레이션만 사용) |

## 테스트

```bash
cd KWB
./gradlew test
```

로컬 MySQL이 필요합니다. 테스트도 앱과 똑같이 테이블을 다시 만들고 CSV를 적재합니다.

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
- `hitters.csv`에 타격 기록 없는 투수 41명이 포함되어 라인업 선택 목록에 나타남
- 같은 이름의 선수(예: 김민혁)를 구분하지 못함 (시뮬레이션이 이름으로만 선수를 찾음)
