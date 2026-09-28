package com.application.KWB.prediction;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

/**
 * 예측 기록·결과 테이블 연동 (테스트 DB). predictions / game_results 는 재시작해도 지우지 않는 테이블이라
 * 가상의 팀 이름으로 넣고 테스트마다 정리한다.
 */
@SpringBootTest
class PredictionPersistenceTests {

	private static final String HOME = "가상홈";
	private static final String AWAY = "가상원정";
	private static final LocalDate DAY = LocalDate.of(2026, 9, 29);

	@Autowired
	private PredictionDAO dao;

	@Autowired
	private JdbcTemplate jdbc;

	@BeforeEach
	void cleanUp() {
		jdbc.update("DELETE FROM predictions WHERE home_team = ?", HOME);
		jdbc.update("DELETE FROM game_results WHERE home_team = ?", HOME);
		jdbc.update("DELETE FROM schedule WHERE home_team = ?", HOME);
	}

	private void insertPrediction(String stage, LocalDateTime createdAt, double prob) {
		dao.insert(Map.of("createdAt", createdAt, "gameDate", DAY, "homeTeam", HOME, "awayTeam", AWAY,
			"stage", stage, "homeWinProb", prob, "homeLineup", "[]", "awayLineup", "[]"));
	}

	private List<PredictionRow> ours() {
		return dao.findAllWithResults().stream().filter(r -> HOME.equals(r.getHomeTeam())).toList();
	}

	@Test
	void predictionsJoinScheduleStartTimeAndResults() {
		jdbc.update("INSERT INTO schedule (date, start_time, stadium, away_team, home_team) VALUES (?, '14:00', '잠실', ?, ?)",
			DAY, AWAY, HOME);
		insertPrediction("predict", DAY.atTime(13, 0), 0.6);
		dao.upsertManualResult(DAY, HOME, AWAY, 5, 2, LocalDateTime.now());

		PredictionRow row = ours().get(0);
		assertThat(row.getStartTime()).isEqualTo("14:00");
		assertThat(row.getHomeWinProb()).isEqualTo(0.6);
		assertThat(row.getHomeScore()).isEqualTo(5);
		assertThat(row.getAwayScore()).isEqualTo(2);
		assertThat(row.getResultSource()).isEqualTo("manual");
	}

	@Test
	void manualResultDoesNotOverwriteImportedResult() {
		jdbc.update("INSERT INTO game_results VALUES (?, ?, ?, 7, 1, 'import', NOW())", DAY, HOME, AWAY);
		insertPrediction("analyze", DAY.atTime(12, 0), 0.5);

		dao.upsertManualResult(DAY, HOME, AWAY, 0, 9, LocalDateTime.now());

		PredictionRow row = ours().get(0);
		assertThat(row.getHomeScore()).isEqualTo(7);
		assertThat(row.getResultSource()).isEqualTo("import");
	}

	@Test
	void manualResultCanBeCorrectedUntilImported() {
		insertPrediction("predict", DAY.atTime(12, 0), 0.5);
		dao.upsertManualResult(DAY, HOME, AWAY, 1, 2, LocalDateTime.now());
		dao.upsertManualResult(DAY, HOME, AWAY, 4, 2, LocalDateTime.now());

		assertThat(ours().get(0).getHomeScore()).isEqualTo(4);
	}

	@Test
	void predictionsTableSurvivesSchemaScript() throws java.io.IOException {
		// schema.sql 은 기록 테이블을 DROP 하지 않는다
		String schema = new String(getClass().getResourceAsStream("/db/schema.sql").readAllBytes(),
			java.nio.charset.StandardCharsets.UTF_8);
		assertThat(schema).doesNotContain("DROP TABLE IF EXISTS predictions")
			.doesNotContain("DROP TABLE IF EXISTS game_results")
			.contains("CREATE TABLE IF NOT EXISTS predictions")
			.contains("CREATE TABLE IF NOT EXISTS game_results");
	}
}
