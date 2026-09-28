package com.application.KWB.prediction;

import java.time.LocalDateTime;
import java.time.LocalTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 기록된 예측을 채점한다 (DB 와 무관한 순수 계산).
 *
 * 규칙
 * - 경기(날짜·홈·원정)와 단계(analyze / predict)마다 "경기 시작 전에 기록한 것 중 가장 늦은 예측" 하나만 채점한다.
 * - 경기 시작 뒤에 기록한 예측은 채점하지 않는다 (시작 시각을 모르면 DEFAULT_START 로 본다).
 * - 무승부 경기와 결과가 아직 없는 경기는 채점하지 않는다.
 * - 예측값은 "무승부가 아닐 때 홈팀이 이길 확률"이다.
 */
public final class PredictionScorer {

	/** KBO 평일 경기 시작 시각. 일정에 시작 시각이 없을 때 쓴다. */
	public static final LocalTime DEFAULT_START = LocalTime.of(18, 30);

	public enum Status {
		SCORED("채점"), AFTER_START("경기 시작 후 기록 - 제외"), SUPERSEDED("이후 기록으로 대체"),
		NO_RESULT("결과 대기"), DRAW("무승부 - 제외");

		private final String label;

		Status(String label) {
			this.label = label;
		}

		public String getLabel() {
			return label;
		}
	}

	public record Entry(PredictionRow row, Status status, Boolean correct, Double brier) {
	}

	public record Summary(int games, int correct, double accuracy, double brier, double logLoss, double brierSkill) {
	}

	public record Report(Map<String, Summary> summaries, List<Entry> entries) {
	}

	private PredictionScorer() {
	}

	public static Report score(List<PredictionRow> rows) {
		// 경기·단계별로 시작 전 가장 늦은 기록을 고른다
		Map<String, PredictionRow> latestBeforeStart = new HashMap<>();
		for (PredictionRow row : rows) {
			if (!row.getCreatedAt().isBefore(startOf(row))) {
				continue;
			}
			latestBeforeStart.merge(key(row), row,
				(a, b) -> a.getCreatedAt().isAfter(b.getCreatedAt()) || (a.getCreatedAt().equals(b.getCreatedAt())
					&& a.getId() > b.getId()) ? a : b);
		}

		List<Entry> entries = new ArrayList<>();
		Map<String, List<Entry>> scoredByStage = new LinkedHashMap<>();
		for (PredictionRow row : rows.stream()
				.sorted(Comparator.comparing(PredictionRow::getGameDate).thenComparing(PredictionRow::getCreatedAt).reversed())
				.toList()) {
			Entry entry = entryFor(row, latestBeforeStart.get(key(row)));
			entries.add(entry);
			if (entry.status() == Status.SCORED) {
				scoredByStage.computeIfAbsent(row.getStage(), s -> new ArrayList<>()).add(entry);
			}
		}

		Map<String, Summary> summaries = new LinkedHashMap<>();
		for (String stage : List.of("analyze", "predict")) {
			List<Entry> scored = scoredByStage.getOrDefault(stage, List.of());
			if (!scored.isEmpty()) {
				summaries.put(stage, summarize(scored));
			}
		}
		return new Report(summaries, entries);
	}

	private static Entry entryFor(PredictionRow row, PredictionRow chosen) {
		if (!row.getCreatedAt().isBefore(startOf(row))) {
			return new Entry(row, Status.AFTER_START, null, null);
		}
		if (chosen == null || chosen.getId() != row.getId()) {
			return new Entry(row, Status.SUPERSEDED, null, null);
		}
		if (row.getHomeScore() == null || row.getAwayScore() == null) {
			return new Entry(row, Status.NO_RESULT, null, null);
		}
		if (row.getHomeScore().equals(row.getAwayScore())) {
			return new Entry(row, Status.DRAW, null, null);
		}
		int homeWon = row.getHomeScore() > row.getAwayScore() ? 1 : 0;
		double p = row.getHomeWinProb();
		boolean correct = p != 0.5 && (p > 0.5) == (homeWon == 1);
		return new Entry(row, Status.SCORED, correct, (p - homeWon) * (p - homeWon));
	}

	private static Summary summarize(List<Entry> scored) {
		int n = scored.size();
		int correct = (int) scored.stream().filter(e -> Boolean.TRUE.equals(e.correct())).count();
		double brier = scored.stream().mapToDouble(Entry::brier).sum() / n;
		double logLoss = scored.stream().mapToDouble(e -> {
			double p = Math.min(Math.max(e.row().getHomeWinProb(), 1e-6), 1 - 1e-6);
			boolean homeWon = e.row().getHomeScore() > e.row().getAwayScore();
			return -Math.log(homeWon ? p : 1 - p);
		}).sum() / n;
		return new Summary(n, correct, (double) correct / n, brier, logLoss, 1 - brier / 0.25);
	}

	static LocalDateTime startOf(PredictionRow row) {
		LocalTime start = DEFAULT_START;
		if (row.getStartTime() != null && row.getStartTime().matches("\\d{1,2}:\\d{2}")) {
			start = LocalTime.parse(row.getStartTime().length() == 4 ? "0" + row.getStartTime() : row.getStartTime());
		}
		return row.getGameDate().atTime(start);
	}

	private static String key(PredictionRow row) {
		return row.getGameDate() + "|" + row.getHomeTeam() + "|" + row.getAwayTeam() + "|" + row.getStage();
	}
}
