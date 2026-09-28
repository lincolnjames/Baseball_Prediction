package com.application.KWB.prediction;

import java.time.LocalDate;
import java.time.LocalDateTime;

import lombok.Data;

/** 기록된 예측 한 건과 그 경기의 시작 시각·결과 (결과가 없으면 점수는 null) */
@Data
public class PredictionRow {
	private long id;
	private LocalDateTime createdAt;
	private LocalDate gameDate;
	private String homeTeam;
	private String awayTeam;
	private String stage;
	private double homeWinProb;
	private Double baseHomeProb;
	private Double rangeLow;
	private Double rangeHigh;
	private String homeStarter;
	private String awayStarter;
	private String startTime;
	private Integer homeScore;
	private Integer awayScore;
	private String resultSource;
}
