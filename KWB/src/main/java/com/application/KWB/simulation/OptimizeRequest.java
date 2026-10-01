package com.application.KWB.simulation;

/**
 * POST /simulation/optimize 요청 본문.
 * target: 추천을 받을 쪽 ("home" 또는 "away"). 상대 쪽 라인업도 득점 가치 계산에 필요해 함께 받는다.
 */
public record OptimizeRequest(String homeTeam, String awayTeam,
		ScenarioRequest.TeamSide home, ScenarioRequest.TeamSide away, String target) {
}
