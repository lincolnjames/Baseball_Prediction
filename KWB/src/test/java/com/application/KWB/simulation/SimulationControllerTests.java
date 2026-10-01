package com.application.KWB.simulation;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(SimulationController.class)
class SimulationControllerTests {

	private static final String LINEUP = "[\"a\",\"b\",\"c\",\"d\",\"e\",\"f\",\"g\",\"h\",\"i\"]";

	@Autowired
	private MockMvc mockMvc;

	@MockitoBean
	private SimulationService simulationService;

	@Test
	@SuppressWarnings("unchecked")
	void passesTeamsAndPitcherRolesToSimulation() throws Exception {
		when(simulationService.runSimulation(any())).thenReturn(Map.of("home_win_rate", 0.5));

		String body = """
			{"homeTeam":"LG","awayTeam":"KT","matchCount":500,
			 "home":{"lineup":%s,"starter":"임찬규","middle":["김진성"],"closer":"유영찬"},
			 "away":{"lineup":%s,"starter":"고영표","middle":[],"closer":null}}
			""".formatted(LINEUP, LINEUP);

		mockMvc.perform(post("/simulation/run").contentType(MediaType.APPLICATION_JSON).content(body))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.home_win_rate").value(0.5));

		ArgumentCaptor<Map<String, Object>> captor = ArgumentCaptor.forClass(Map.class);
		verify(simulationService).runSimulation(captor.capture());
		Map<String, Object> input = captor.getValue();
		Map<String, Object> home = (Map<String, Object>) input.get("home");
		Map<String, Object> away = (Map<String, Object>) input.get("away");

		assertThat(input.get("match_count")).isEqualTo(500);
		assertThat(home).containsEntry("team", "LG").containsEntry("starter", "임찬규")
			.containsEntry("middle", List.of("김진성")).containsEntry("closer", "유영찬");
		assertThat(away).containsEntry("team", "KT").containsEntry("closer", null);
	}

	@Test
	void rejectsLineupWithoutNineBatters() throws Exception {
		String body = """
			{"homeTeam":"LG","awayTeam":"KT",
			 "home":{"lineup":["a","b"],"starter":"임찬규"},
			 "away":{"lineup":%s,"starter":"고영표"}}
			""".formatted(LINEUP);

		mockMvc.perform(post("/simulation/run").contentType(MediaType.APPLICATION_JSON).content(body))
			.andExpect(status().isBadRequest());
		verify(simulationService, never()).runSimulation(any());
	}

	private static final String SCENARIO_LINEUP = """
		[{"name":"a","pos":"포수"},{"name":"b","pos":"1루수"},{"name":"c","pos":"2루수"},
		 {"name":"d","pos":"3루수"},{"name":"e","pos":"유격수"},{"name":"f","pos":"좌익수"},
		 {"name":"g","pos":"중견수"},{"name":"h","pos":"우익수"},{"name":"i","pos":"지명타자"}]""";

	@Test
	@SuppressWarnings("unchecked")
	void scenarioPassesModeTeamsAndLineupWithPositions() throws Exception {
		when(simulationService.runScenario(any())).thenReturn(Map.of("expected_home", 0.55));

		String body = """
			{"mode":"predict","homeTeam":"두산","awayTeam":"NC",
			 "home":{"starter":"곽빈","lineup":%s},
			 "away":{"starter":"구창모","lineup":%s}}
			""".formatted(SCENARIO_LINEUP, SCENARIO_LINEUP);

		mockMvc.perform(post("/simulation/scenario").contentType(MediaType.APPLICATION_JSON).content(body))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.expected_home").value(0.55));

		ArgumentCaptor<Map<String, Object>> captor = ArgumentCaptor.forClass(Map.class);
		verify(simulationService).runScenario(captor.capture());
		Map<String, Object> input = captor.getValue();
		Map<String, Object> home = (Map<String, Object>) input.get("home");
		List<Map<String, String>> lineup = (List<Map<String, String>>) home.get("lineup");

		assertThat(input).containsEntry("mode", "predict");
		assertThat(home).containsEntry("team", "두산").containsEntry("starter", "곽빈");
		assertThat(lineup).hasSize(9).first().isEqualTo(Map.of("name", "a", "pos", "포수"));
	}

	@Test
	void scenarioRejectsUnknownMode() throws Exception {
		String body = """
			{"mode":"guess","homeTeam":"두산","awayTeam":"NC",
			 "home":{"starter":"곽빈","lineup":%s},"away":{"starter":"구창모","lineup":%s}}
			""".formatted(SCENARIO_LINEUP, SCENARIO_LINEUP);

		mockMvc.perform(post("/simulation/scenario").contentType(MediaType.APPLICATION_JSON).content(body))
			.andExpect(status().isBadRequest())
			.andExpect(jsonPath("$.message").value("mode 는 analyze 또는 predict 여야 합니다."));
		verify(simulationService, never()).runScenario(any());
	}

	@Test
	void scriptInputErrorsBecomeBadRequestWithMessage() throws Exception {
		when(simulationService.runScenario(any()))
			.thenThrow(new IllegalArgumentException("home 수비 포지션이 비었습니다: 포수"));

		String body = """
			{"homeTeam":"두산","awayTeam":"NC",
			 "home":{"starter":"곽빈","lineup":%s},"away":{"starter":"구창모","lineup":%s}}
			""".formatted(SCENARIO_LINEUP, SCENARIO_LINEUP);

		mockMvc.perform(post("/simulation/scenario").contentType(MediaType.APPLICATION_JSON).content(body))
			.andExpect(status().isBadRequest())
			.andExpect(jsonPath("$.message").value("home 수비 포지션이 비었습니다: 포수"));
	}

	@Test
	@SuppressWarnings("unchecked")
	void optimizePassesTargetTeamsAndLineupWithPositions() throws Exception {
		when(simulationService.runScenario(any())).thenReturn(Map.of("recommended", Map.of("win", 0.6)));

		String body = """
			{"homeTeam":"두산","awayTeam":"NC","target":"home",
			 "home":{"starter":"곽빈","lineup":%s},
			 "away":{"starter":"구창모","lineup":%s}}
			""".formatted(SCENARIO_LINEUP, SCENARIO_LINEUP);

		mockMvc.perform(post("/simulation/optimize").contentType(MediaType.APPLICATION_JSON).content(body))
			.andExpect(status().isOk())
			.andExpect(jsonPath("$.recommended.win").value(0.6));

		ArgumentCaptor<Map<String, Object>> captor = ArgumentCaptor.forClass(Map.class);
		verify(simulationService).runScenario(captor.capture());
		Map<String, Object> input = captor.getValue();
		Map<String, Object> home = (Map<String, Object>) input.get("home");

		assertThat(input).containsEntry("mode", "optimize").containsEntry("target", "home");
		assertThat(home).containsEntry("team", "두산").containsEntry("starter", "곽빈");
	}

	@Test
	void optimizeRejectsUnknownTarget() throws Exception {
		String body = """
			{"homeTeam":"두산","awayTeam":"NC","target":"guess",
			 "home":{"starter":"곽빈","lineup":%s},"away":{"starter":"구창모","lineup":%s}}
			""".formatted(SCENARIO_LINEUP, SCENARIO_LINEUP);

		mockMvc.perform(post("/simulation/optimize").contentType(MediaType.APPLICATION_JSON).content(body))
			.andExpect(status().isBadRequest())
			.andExpect(jsonPath("$.message").value("target 은 home 또는 away 여야 합니다."));
		verify(simulationService, never()).runScenario(any());
	}

	@Test
	void rejectsMissingStarter() throws Exception {
		String body = """
			{"homeTeam":"LG","awayTeam":"KT",
			 "home":{"lineup":%s,"starter":"임찬규"},
			 "away":{"lineup":%s,"starter":" "}}
			""".formatted(LINEUP, LINEUP);

		mockMvc.perform(post("/simulation/run").contentType(MediaType.APPLICATION_JSON).content(body))
			.andExpect(status().isBadRequest());
		verify(simulationService, never()).runSimulation(any());
	}
}
