package com.application.KWB.data;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import com.application.KWB.team.HitterDTO;
import com.application.KWB.team.PitcherDTO;
import com.application.KWB.team.TeamDAO;

/**
 * kwb.data-dir 로 지정한 폴더의 2026 형식 CSV(원시 기록 포함, 가상 선수)를 적재하는지 확인한다.
 * 기본 데이터를 쓰는 다른 테스트와 DB 가 섞이지 않도록 별도 DB 를 쓴다.
 */
@SpringBootTest(properties = {
	"kwb.data-dir=src/test/resources/data-2026-sample",
	"DB_NAME=kwb_test_external",
})
class ExternalDataDirTests {

	@Autowired
	private JdbcTemplate jdbcTemplate;

	@Autowired
	private TeamDAO teamDAO;

	@Test
	void loadsRawCountColumnsFromExternalFolder() {
		Map<String, Object> hitter = jdbcTemplate.queryForMap(
			"SELECT pa, h, `2b`, `3b`, hr, bb, hbp, so FROM hitters WHERE player = '가타자'");

		assertThat(hitter).containsEntry("pa", 400).containsEntry("h", 105).containsEntry("2b", 20)
			.containsEntry("bb", 40).containsEntry("hbp", 5).containsEntry("so", 70);
		assertThat(jdbcTemplate.queryForObject("SELECT tbf FROM pitchers WHERE player = '마투수'", Integer.class))
			.isEqualTo(175);
	}

	@Test
	void screensShowExternalPlayers() {
		List<HitterDTO> hitters = teamDAO.findHitterListByTeam("KT");
		List<PitcherDTO> pitchers = teamDAO.findPitcherListByTeam("KT");

		assertThat(hitters).extracting(HitterDTO::getPlayer).containsExactly("가타자", "나타자");
		assertThat(pitchers).extracting(PitcherDTO::getIP).containsExactly("120.0", "40.1");
	}

	@Test
	void missingFilesFallBackToBundledData() {
		// 샘플 폴더에 schedule.csv 가 없으므로 저장소의 기본 일정이 들어가야 한다
		assertThat(jdbcTemplate.queryForObject("SELECT COUNT(*) FROM schedule", Integer.class)).isEqualTo(675);
	}
}
