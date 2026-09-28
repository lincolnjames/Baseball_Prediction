-- KWB 스키마
-- 앱 시작 시마다 실행되어 테이블을 다시 만들고, CsvDataLoader 가 static/*.csv 를 적재한다.
-- CSV 가 원본 데이터(source of truth)이므로 DB 에 직접 수정한 내용은 재시작 시 사라진다.
-- 컬럼명 규칙: CSV 헤더를 소문자로 바꾸고 % → _pct, + → _plus, / → _per_, 공백 → _ 로 치환
-- 데이터 종류(2025 비율 기록 / 2026 원시 기록)에 따라 채워지는 컬럼이 다르며, 없는 컬럼은 NULL

DROP TABLE IF EXISTS hitters;
DROP TABLE IF EXISTS pitchers;
DROP TABLE IF EXISTS schedule;
DROP TABLE IF EXISTS positions;

CREATE TABLE hitters (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    year      INT          NOT NULL,
    team      VARCHAR(20)  NOT NULL,
    player    VARCHAR(50)  NOT NULL,
    g         INT,
    pa        INT,
    ab        INT,
    h         INT,
    `2b`      INT,
    `3b`      INT,
    hr        INT,
    bb        INT,
    hbp       INT,
    so        INT,
    sf        INT,
    avg       DECIMAL(5,3),
    obp       DECIMAL(5,3),
    slg       DECIMAL(5,3),
    wrc_plus  DECIMAL(6,1),
    k_pct     DECIMAL(5,1),
    bb_pct    DECIMAL(5,1),
    babip     DECIMAL(5,3),
    sb_raa    DECIMAL(5,2),
    sb        INT,
    sb_pct    DECIMAL(5,1),
    ravg      DECIMAL(5,3),
    robp      DECIMAL(5,3),
    rslg      DECIMAL(5,3),
    lavg      DECIMAL(5,3),
    lobp      DECIMAL(5,3),
    lslg      DECIMAL(5,3),
    uavg      DECIMAL(5,3),
    uobp      DECIMAL(5,3),
    uslg      DECIMAL(5,3),
    INDEX idx_hitters_team (team, year)
) DEFAULT CHARSET = utf8mb4;

CREATE TABLE pitchers (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    year      INT          NOT NULL,
    team      VARCHAR(20)  NOT NULL,
    player    VARCHAR(50)  NOT NULL,
    g         INT,
    w         INT,
    l         INT,
    sv        INT,
    hld       INT,
    ip        DECIMAL(5,1),  -- 야구식 표기: 58.2 = 58⅔ 이닝
    tbf       INT,           -- 상대 타자 수
    h         INT,
    hr        INT,
    bb        INT,
    hbp       INT,
    so        INT,
    er        INT,
    era       DECIMAL(5,2),
    fip       DECIMAL(5,2),
    whip      DECIMAL(5,2),
    k_pct     DECIMAL(5,1),
    bb_pct    DECIMAL(5,1),
    hr_per_9  DECIMAL(5,2),
    babip     DECIMAL(5,3),
    v_r_era   DECIMAL(5,2),
    v_r_whip  DECIMAL(5,2),
    v_r_avg   DECIMAL(5,3),
    v_r_obp   DECIMAL(5,3),
    v_l_era   DECIMAL(5,2),
    v_l_whip  DECIMAL(5,2),
    v_l_avg   DECIMAL(5,3),
    v_l_obp   DECIMAL(5,3),
    wp        INT,           -- 폭투 (직접 복사한 2026 원시 기록에만 있음)
    INDEX idx_pitchers_team (team, year)
) DEFAULT CHARSET = utf8mb4;

CREATE TABLE schedule (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    date       DATE         NOT NULL,
    start_time VARCHAR(5),               -- 'HH:MM' (가져온 일정에만 있음)
    stadium    VARCHAR(20)  NOT NULL,
    home_team  VARCHAR(20)  NOT NULL,
    away_team  VARCHAR(20)  NOT NULL,
    INDEX idx_schedule_date (date)
) DEFAULT CHARSET = utf8mb4;

-- 수비 포지션별 출장 (선택: 데이터 폴더에 positions.csv 가 있을 때만 채워진다)
CREATE TABLE positions (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    year       INT          NOT NULL,
    team       VARCHAR(20)  NOT NULL,
    player     VARCHAR(50)  NOT NULL,
    pos        VARCHAR(10)  NOT NULL,
    g          INT,
    gs         INT,           -- 해당 포지션 선발 출장
    inn        DECIMAL(6,1),  -- 수비 이닝 (야구식 표기)
    INDEX idx_positions_team (team)
) DEFAULT CHARSET = utf8mb4;

-- ============================================================
-- 아래 두 테이블은 앱을 재시작해도 지우지 않는다 (DROP 없음).
-- 예측 기록은 수정·삭제하지 않는다: 결과를 보고 예측을 고치지 못하게 하기 위함.
-- ============================================================

-- 기록한 예측. 채점은 경기마다 '경기 시작 전 가장 늦은 기록'을 단계(stage)별로 쓴다.
CREATE TABLE IF NOT EXISTS predictions (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    created_at      DATETIME     NOT NULL,           -- 서버 기록 시각 (Asia/Seoul)
    game_date       DATE         NOT NULL,
    home_team       VARCHAR(20)  NOT NULL,
    away_team       VARCHAR(20)  NOT NULL,
    stage           VARCHAR(10)  NOT NULL,           -- analyze: 라인업 발표 전 / predict: 발표 후
    home_win_prob   DECIMAL(6,4) NOT NULL,           -- 채점 대상: 무승부 제외 홈 승률 (analyze 는 기댓값)
    base_home_prob  DECIMAL(6,4),                    -- analyze: 입력 라인업 기준 승률
    range_low       DECIMAL(6,4),
    range_high      DECIMAL(6,4),
    draw_prob       DECIMAL(6,4),
    games           INT,
    home_starter    VARCHAR(50),
    away_starter    VARCHAR(50),
    home_lineup     TEXT,                            -- JSON [{name, pos}]
    away_lineup     TEXT,
    INDEX idx_predictions_game (game_date, home_team, away_team)
) DEFAULT CHARSET = utf8mb4;

-- 경기 결과. 가져온 일정(games.csv)의 종료 경기로 채우고, 화면에서 직접 입력할 수도 있다.
CREATE TABLE IF NOT EXISTS game_results (
    game_date   DATE         NOT NULL,
    home_team   VARCHAR(20)  NOT NULL,
    away_team   VARCHAR(20)  NOT NULL,
    home_score  INT          NOT NULL,
    away_score  INT          NOT NULL,
    source      VARCHAR(10)  NOT NULL,               -- import / manual
    updated_at  DATETIME     NOT NULL,
    PRIMARY KEY (game_date, home_team, away_team)
) DEFAULT CHARSET = utf8mb4;
