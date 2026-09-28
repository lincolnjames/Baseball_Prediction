package com.application.KWB.match;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

import com.application.KWB.team.HitterDTO;
import com.application.KWB.team.PitcherDTO;

@Mapper
public interface MatchDAO {

	List<GameDto> getGamesByMonth(int month);

	List<HitterDTO> getHitterByTeam(String teamName);

	List<PitcherDTO> getPitcherByTeam(String teamName);

	String getNextGameDate(@Param("homeTeam") String homeTeam, @Param("awayTeam") String awayTeam,
		@Param("from") LocalDate from);

	List<Map<String, Object>> getLineupCandidates(String teamName);

	List<Map<String, Object>> getPitchingStaff(String teamName);

	List<Map<String, Object>> getPositions(String teamName);

}
