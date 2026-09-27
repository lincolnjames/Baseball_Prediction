package com.application.KWB.simulation;

import java.util.List;

/**
 * POST /simulation/scenario 요청 본문.
 * mode: analyze (라인업 발표 전 시나리오 분석) 또는 predict (발표된 실제 라인업으로 확정 예측)
 */
public record ScenarioRequest(String mode, String homeTeam, String awayTeam, TeamSide home, TeamSide away) {

	/** 선발투수와 타순 9명(포지션 포함). 불펜은 세이브·홀드 기록으로 자동 구성한다. */
	public record TeamSide(String starter, List<Slot> lineup) {
	}

	public record Slot(String name, String pos) {
	}
}
