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
