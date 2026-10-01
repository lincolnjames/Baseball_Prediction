package com.application.KWB.prediction;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.within;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;

import com.application.KWB.prediction.PredictionScorer.Entry;
import com.application.KWB.prediction.PredictionScorer.Status;

class PredictionScorerTests {

	private static final LocalDate DAY = LocalDate.of(2026, 9, 29);
	private static long nextId = 1;

	private static PredictionRow row(String stage, String createdAt, double homeProb, Integer home, Integer away,
		String startTime) {
		PredictionRow r = new PredictionRow();
		r.setId(nextId++);
		r.setStage(stage);
		r.setCreatedAt(LocalDateTime.parse(createdAt));
		r.setGameDate(DAY);
		r.setHomeTeam("두산");
		r.setAwayTeam("NC");
		r.setHomeWinProb(homeProb);
		r.setHomeScore(home);
		r.setAwayScore(away);
		r.setStartTime(startTime);
		return r;
	}

	private static Map<Long, Status> statuses(List<Entry> entries) {
		return entries.stream().collect(Collectors.toMap(e -> e.row().getId(), Entry::status));
	}

	@Test
	void onlyLatestPredictionBeforeStartIsScoredPerStage() {
		PredictionRow early = row("predict", "2026-09-29T17:50:00", 0.40, 5, 3, "18:30");
		PredictionRow latest = row("predict", "2026-09-29T18:10:00", 0.60, 5, 3, "18:30");
		PredictionRow afterStart = row("predict", "2026-09-29T18:31:00", 0.99, 5, 3, "18:30");
		PredictionRow analyze = row("analyze", "2026-09-28T21:00:00", 0.55, 5, 3, "18:30");

		PredictionScorer.Report report = PredictionScorer.score(List.of(early, latest, afterStart, analyze));
		Map<Long, Status> status = statuses(report.entries());

		assertThat(status.get(latest.getId())).isEqualTo(Status.SCORED);
		assertThat(status.get(early.getId())).isEqualTo(Status.SUPERSEDED);
		assertThat(status.get(afterStart.getId())).isEqualTo(Status.AFTER_START);
		assertThat(status.get(analyze.getId())).isEqualTo(Status.SCORED);   // 단계가 다르면 따로 채점
		assertThat(report.summaries()).containsOnlyKeys("analyze", "predict");
		assertThat(report.summaries().get("predict").games()).isEqualTo(1);
	}

	@Test
	void afterStartPredictionIsScoredInInclusiveSummaryOnly() {
		PredictionRow early = row("predict", "2026-09-29T17:50:00", 0.40, 5, 3, "18:30");
		PredictionRow afterStart = row("predict", "2026-09-29T20:00:00", 0.99, 5, 3, "18:30");

		PredictionScorer.Report report = PredictionScorer.score(List.of(early, afterStart));

		assertThat(report.summaries().get("predict").games()).isEqualTo(1);
		Map<Long, Entry> byId = report.entries().stream().collect(Collectors.toMap(e -> e.row().getId(), Function.identity()));
		assertThat(byId.get(early.getId()).status()).isEqualTo(Status.SCORED);

		// 사후 기록 포함 지표는 "가장 최근 기록"(afterStart)을 기준으로 채점한다
		assertThat(report.inclusiveSummaries().get("predict").games()).isEqualTo(1);
		assertThat(report.inclusiveSummaries().get("predict").correct()).isEqualTo(1);
	}

	@Test
	void predictionAtExactStartTimeIsExcluded() {
		PredictionRow atStart = row("predict", "2026-09-29T14:00:00", 0.6, 1, 0, "14:00");
		assertThat(PredictionScorer.score(List.of(atStart)).entries().get(0).status()).isEqualTo(Status.AFTER_START);
	}

	@Test
	void unknownStartTimeFallsBackToDefault() {
		PredictionRow before = row("predict", "2026-09-29T18:29:59", 0.6, 1, 0, null);
		PredictionRow after = row("analyze", "2026-09-29T18:30:00", 0.6, 1, 0, null);
		Map<Long, Status> status = statuses(PredictionScorer.score(List.of(before, after)).entries());
		assertThat(status.get(before.getId())).isEqualTo(Status.SCORED);
		assertThat(status.get(after.getId())).isEqualTo(Status.AFTER_START);
	}

	@Test
	void drawsAndMissingResultsAreNotScored() {
		PredictionRow draw = row("predict", "2026-09-29T12:00:00", 0.6, 3, 3, "18:30");
		PredictionRow pending = row("analyze", "2026-09-29T12:00:00", 0.6, null, null, "18:30");
		Map<Long, Status> status = statuses(PredictionScorer.score(List.of(draw, pending)).entries());
		assertThat(status.get(draw.getId())).isEqualTo(Status.DRAW);
		assertThat(status.get(pending.getId())).isEqualTo(Status.NO_RESULT);
	}

	@Test
	void metricsMatchHandCalculation() {
		// 서로 다른 경기 세 개: 홈 승 0.7 적중, 홈 패 0.6 빗나감, 홈 패 0.2 적중
		PredictionRow a = row("predict", "2026-09-29T12:00:00", 0.7, 5, 1, "18:30");
		PredictionRow b = row("predict", "2026-09-29T12:00:00", 0.6, 1, 5, "18:30");
		PredictionRow c = row("predict", "2026-09-29T12:00:00", 0.2, 2, 4, "18:30");
		b.setHomeTeam("LG");
		c.setHomeTeam("KT");

		PredictionScorer.Summary s = PredictionScorer.score(List.of(a, b, c)).summaries().get("predict");
		Map<Long, Entry> byId = PredictionScorer.score(List.of(a, b, c)).entries().stream()
			.collect(Collectors.toMap(e -> e.row().getId(), Function.identity()));

		assertThat(s.games()).isEqualTo(3);
		assertThat(s.correct()).isEqualTo(2);
		assertThat(s.brier()).isCloseTo((0.09 + 0.36 + 0.04) / 3, within(1e-9));
		assertThat(s.logLoss()).isCloseTo(-(Math.log(0.7) + Math.log(0.4) + Math.log(0.8)) / 3, within(1e-9));
		assertThat(s.brierSkill()).isCloseTo(1 - s.brier() / 0.25, within(1e-9));
		assertThat(byId.get(b.getId()).correct()).isFalse();
	}

	@Test
	void coinFlipPredictionIsNeverCountedAsCorrect() {
		PredictionRow coin = row("predict", "2026-09-29T12:00:00", 0.5, 5, 1, "18:30");
		PredictionScorer.Summary s = PredictionScorer.score(List.of(coin)).summaries().get("predict");
		assertThat(s.correct()).isZero();
		assertThat(s.brier()).isEqualTo(0.25);
	}
}
