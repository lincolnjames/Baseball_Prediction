package com.application.KWB.prediction;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

/**
 * POST /predictions 요청 본문: 예측 화면에서 계산한 결과를 기록한다.
 * stage: analyze (라인업 발표 전, homeWinProb 는 기댓값) 또는 predict (발표 후 확정 예측)
 */
public record PredictionRequest(
	String stage,
	LocalDate gameDate,
	String homeTeam,
	String awayTeam,
	Double homeWinProb,
	Double baseHomeProb,
	Double rangeLow,
	Double rangeHigh,
	Double drawProb,
	Integer games,
	String homeStarter,
	String awayStarter,
	List<Map<String, String>> homeLineup,
	List<Map<String, String>> awayLineup) {
}
