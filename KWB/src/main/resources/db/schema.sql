-- KWB 스키마
-- 앱 시작 시마다 실행되어 테이블을 다시 만들고, CsvDataLoader 가 static/*.csv 를 적재한다.
-- CSV 가 원본 데이터(source of truth)이므로 DB 에 직접 수정한 내용은 재시작 시 사라진다.
-- 컬럼명 규칙: CSV 헤더를 소문자로 바꾸고 % → _pct, + → _plus, / → _per_, 공백 → _ 로 치환

DROP TABLE IF EXISTS hitters;
DROP TABLE IF EXISTS pitchers;
DROP TABLE IF EXISTS schedule;

CREATE TABLE hitters (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    year      INT          NOT NULL,
    team      VARCHAR(20)  NOT NULL,
    player    VARCHAR(50)  NOT NULL,
    pa        INT,
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
    ip        DECIMAL(5,1),  -- 야구식 표기: 58.2 = 58⅔ 이닝
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
    INDEX idx_pitchers_team (team, year)
) DEFAULT CHARSET = utf8mb4;

CREATE TABLE schedule (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    date       DATE         NOT NULL,
    stadium    VARCHAR(20)  NOT NULL,
    home_team  VARCHAR(20)  NOT NULL,
    away_team  VARCHAR(20)  NOT NULL,
    INDEX idx_schedule_date (date)
) DEFAULT CHARSET = utf8mb4;
