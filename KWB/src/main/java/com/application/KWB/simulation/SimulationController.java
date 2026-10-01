package com.application.KWB.simulation;

import java.io.IOException;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.application.KWB.simulation.SimulationRequest.TeamLineup;

@RestController
@RequestMapping("/simulation")
public class SimulationController {

	private static final int DEFAULT_MATCH_COUNT = 1000;
	private static final int MAX_MATCH_COUNT = 10000;

	private final SimulationService simulationService;

	public SimulationController(SimulationService simulationService) {
		this.simulationService = simulationService;
	}

	@PostMapping("/run")
	public Map<String, Object> runSimulation(@RequestBody SimulationRequest request) throws IOException {
		int matchCount = request.matchCount() == null ? DEFAULT_MATCH_COUNT : request.matchCount();
		if (matchCount < 1 || matchCount > MAX_MATCH_COUNT) {
			throw badRequest("시뮬레이션 횟수는 1~" + MAX_MATCH_COUNT + " 사이여야 합니다.");
		}

		// simulation.py 입력 형식 (simulation.py 상단 설명 참고)
		Map<String, Object> simInput = new LinkedHashMap<>();
		simInput.put("home", toSimTeam("홈팀", request.homeTeam(), request.home()));
		simInput.put("away", toSimTeam("원정팀", request.awayTeam(), request.away()));
		simInput.put("match_count", matchCount);

		return simulationService.runSimulation(simInput);
	}

	@PostMapping("/scenario")
	public Map<String, Object> runScenario(@RequestBody ScenarioRequest request) throws IOException {
		String mode = request.mode() == null ? "analyze" : request.mode();
		if (!mode.equals("analyze") && !mode.equals("predict")) {
			throw badRequest("mode 는 analyze 또는 predict 여야 합니다.");
		}
		Map<String, Object> input = new LinkedHashMap<>();
		input.put("mode", mode);
		input.put("home", toScenarioTeam("홈팀", request.homeTeam(), request.home()));
		input.put("away", toScenarioTeam("원정팀", request.awayTeam(), request.away()));
		return simulationService.runScenario(input);
	}

	@PostMapping("/optimize")
	public Map<String, Object> optimizeLineup(@RequestBody OptimizeRequest request) throws IOException {
		String target = request.target();
		if (!"home".equals(target) && !"away".equals(target)) {
			throw badRequest("target 은 home 또는 away 여야 합니다.");
		}
		Map<String, Object> input = new LinkedHashMap<>();
		input.put("mode", "optimize");
		input.put("target", target);
		input.put("home", toScenarioTeam("홈팀", request.homeTeam(), request.home()));
		input.put("away", toScenarioTeam("원정팀", request.awayTeam(), request.away()));
		return simulationService.runScenario(input);
	}

	/** 입력 오류(스크립트의 검증 실패 포함)는 400 과 메시지로 응답한다 */
	@ExceptionHandler(IllegalArgumentException.class)
	public ResponseEntity<Map<String, String>> handleInvalidInput(IllegalArgumentException e) {
		return ResponseEntity.badRequest().body(Map.of("message", e.getMessage()));
	}

	private static Map<String, Object> toScenarioTeam(String label, String team, ScenarioRequest.TeamSide side) {
		if (team == null || team.isBlank() || side == null) {
			throw badRequest(label + " 정보가 없습니다.");
		}
		if (side.lineup() == null || side.lineup().size() != 9) {
			throw badRequest(label + " 타순은 9명이어야 합니다.");
		}
		if (side.starter() == null || side.starter().isBlank()) {
			throw badRequest(label + " 선발투수를 지정해야 합니다.");
		}
		Map<String, Object> simTeam = new LinkedHashMap<>();
		simTeam.put("team", team);
		simTeam.put("starter", side.starter());
		simTeam.put("lineup", side.lineup().stream()
			.map(slot -> Map.of("name", slot.name() == null ? "" : slot.name(), "pos", slot.pos() == null ? "" : slot.pos()))
			.toList());
		return simTeam;
	}

	private static Map<String, Object> toSimTeam(String label, String team, TeamLineup lineup) {
		if (lineup == null || lineup.lineup() == null || lineup.lineup().size() != 9
			|| new HashSet<>(lineup.lineup()).size() != 9) {
			throw badRequest(label + " 타순은 서로 다른 9명이어야 합니다.");
		}
		if (lineup.starter() == null || lineup.starter().isBlank()) {
			throw badRequest(label + " 선발투수를 지정해야 합니다.");
		}

		Map<String, Object> simTeam = new LinkedHashMap<>();
		simTeam.put("team", team);
		simTeam.put("lineup", lineup.lineup());
		simTeam.put("starter", lineup.starter());
		simTeam.put("middle", lineup.middle() == null ? List.of() : lineup.middle());
		simTeam.put("closer", lineup.closer());
		return simTeam;
	}

	private static IllegalArgumentException badRequest(String message) {
		return new IllegalArgumentException(message);
	}
}
