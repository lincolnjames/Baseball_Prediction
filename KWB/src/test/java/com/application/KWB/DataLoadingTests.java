package com.application.KWB;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import com.application.KWB.match.GameDateDto;
import com.application.KWB.match.MatchDAO;
import com.application.KWB.match.MatchService;
import com.application.KWB.team.HitterDTO;
import com.application.KWB.team.PitcherDTO;
import com.application.KWB.team.TeamDAO;

/** 로컬 MySQL 이 필요하다 (application.properties 의 DB 설정 사용). */
@SpringBootTest
class DataLoadingTests {

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@Autowired
	private MatchDAO matchDAO;

	@Autowired
	private TeamDAO teamDAO;

	@Autowired
	private MatchService matchService;

	@Test
	void csvRowsAreLoaded() {
		assertThat(count("hitters")).isEqualTo(256);
		assertThat(count("pitchers")).isEqualTo(205);
		assertThat(count("schedule")).isEqualTo(675);
	}

	@Test
	void matchMapperReturnsCorrectDtoTypes() {
		List<HitterDTO> hitters = matchDAO.getHitterByTeam("LG");
		List<PitcherDTO> pitchers = matchDAO.getPitcherByTeam("LG");

		// 제네릭 타입 소거 때문에 resultType 이 뒤바뀌어도 컴파일은 되므로 실제 원소 타입을 확인한다
		assertThat(hitters).isNotEmpty().allSatisfy(h -> {
			assertThat(h).isInstanceOf(HitterDTO.class);
			assertThat(h.getPlayer()).isNotBlank();
		});
		assertThat(pitchers).isNotEmpty().allSatisfy(p -> {
			assertThat(p).isInstanceOf(PitcherDTO.class);
			assertThat(p.getPlayer()).isNotBlank();
		});
	}

	@Test
	void teamMapperReturnsStats() {
		HitterDTO first = teamDAO.findHitterListByTeam("LG").get(0);
		assertThat(first.getPlayer()).isEqualTo("박동원");
		assertThat(first.getAVG()).isEqualTo("0.316");
		assertThat(teamDAO.findPitcherListByTeam("LG").get(0).getWHIP()).isEqualTo("1.07");
	}

	@Test
	void gamesAreGroupedByDate() {
		List<GameDateDto> march = matchService.getMatchesByMonth(3);

		assertThat(march).isNotEmpty();
		GameDateDto opening = march.get(0);
		assertThat(opening.getDate()).isEqualTo("2025-03-22");
		assertThat(opening.getGames()).allSatisfy(g -> {
			assertThat(g.getHometeam()).isNotBlank();
			assertThat(g.getAwayteam()).isNotBlank();
		});
	}

	private int count(String table) {
		return jdbcTemplate.queryForObject("SELECT COUNT(*) FROM " + table, Integer.class);
	}
}
