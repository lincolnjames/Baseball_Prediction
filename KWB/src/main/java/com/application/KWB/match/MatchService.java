package com.application.KWB.match;

import java.util.List;
import java.util.Map;

import com.application.KWB.team.HitterDTO;
import com.application.KWB.team.PitcherDTO;

public interface MatchService {

	List<GameDateDto> getMatchesByMonth(int month);

	List<HitterDTO> getHitterByTeam(String teamName);

	List<PitcherDTO> getPitcherByTeam(String teamName);

	/** 예측 화면용 팀 데이터: 라인업 후보(hitters), 투수진(pitchers), 포지션별 선발 출장(positions) */
	Map<String, Object> getPredictionRoster(String teamName);

}
