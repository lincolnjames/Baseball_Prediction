package com.application.KWB.simulation;

import java.util.List;

/** POST /simulation/run 요청 본문 */
public record SimulationRequest(
	String homeTeam,
	String awayTeam,
	TeamLineup home,
	TeamLineup away,
	Integer matchCount) {

	/** 타순 9명, 선발, 중간계투(등판 순서대로), 마무리(없으면 null) */
	public record TeamLineup(List<String> lineup, String starter, List<String> middle, String closer) {
	}
}
