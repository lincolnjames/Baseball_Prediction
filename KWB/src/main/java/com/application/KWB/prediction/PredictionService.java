package com.application.KWB.prediction;

import java.time.Clock;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

@Service
public class PredictionService {

	private static final Set<String> STAGES = Set.of("analyze", "predict");
	private static final ZoneId KST = ZoneId.of("Asia/Seoul");

	private final PredictionDAO predictionDAO;
	private final ObjectMapper mapper = new ObjectMapper();
	private final Clock clock;

	@Autowired
	public PredictionService(PredictionDAO predictionDAO) {
		this(predictionDAO, Clock.system(KST));
	}

	PredictionService(PredictionDAO predictionDAO, Clock clock) {
		this.predictionDAO = predictionDAO;
		this.clock = clock;
	}

	/** 예측을 기록하고 서버 기록 시각을 돌려준다. 기록 시각은 요청 값이 아니라 서버 시계로 정한다. */
	public LocalDateTime record(PredictionRequest request) {
		if (!STAGES.contains(request.stage())) {
			throw new IllegalArgumentException("stage 는 analyze 또는 predict 여야 합니다.");
		}
		if (request.gameDate() == null || isBlank(request.homeTeam()) || isBlank(request.awayTeam())) {
			throw new IllegalArgumentException("경기 날짜와 두 팀을 지정해야 합니다.");
		}
		if (request.homeTeam().equals(request.awayTeam())) {
			throw new IllegalArgumentException("홈팀과 원정팀이 같습니다.");
		}
		if (request.homeWinProb() == null || request.homeWinProb() < 0 || request.homeWinProb() > 1) {
			throw new IllegalArgumentException("홈 승률은 0~1 사이여야 합니다.");
		}

		LocalDateTime now = LocalDateTime.now(clock).withNano(0);
		Map<String, Object> row = new LinkedHashMap<>();
		row.put("createdAt", now);
		row.put("gameDate", request.gameDate());
		row.put("homeTeam", request.homeTeam());
		row.put("awayTeam", request.awayTeam());
		row.put("stage", request.stage());
		row.put("homeWinProb", request.homeWinProb());
		row.put("baseHomeProb", request.baseHomeProb());
		row.put("rangeLow", request.rangeLow());
		row.put("rangeHigh", request.rangeHigh());
		row.put("drawProb", request.drawProb());
		row.put("games", request.games());
		row.put("homeStarter", request.homeStarter());
		row.put("awayStarter", request.awayStarter());
		row.put("homeLineup", toJson(request.homeLineup()));
		row.put("awayLineup", toJson(request.awayLineup()));
		predictionDAO.insert(row);
		return now;
	}

	public PredictionScorer.Report report() {
		return PredictionScorer.score(predictionDAO.findAllWithResults());
	}

	/** 경기 결과를 직접 입력한다. 가져온 공식 결과가 있으면 그대로 둔다. */
	public void saveManualResult(LocalDate gameDate, String homeTeam, String awayTeam, int homeScore, int awayScore) {
		if (homeScore < 0 || awayScore < 0) {
			throw new IllegalArgumentException("점수는 0 이상이어야 합니다.");
		}
		predictionDAO.upsertManualResult(gameDate, homeTeam, awayTeam, homeScore, awayScore,
			LocalDateTime.now(clock).withNano(0));
	}

	private String toJson(List<Map<String, String>> lineup) {
		if (lineup == null) {
			return null;
		}
		try {
			return mapper.writeValueAsString(lineup);
		} catch (JsonProcessingException e) {
			throw new IllegalArgumentException("라인업을 저장할 수 없습니다.", e);
		}
	}

	private static boolean isBlank(String s) {
		return s == null || s.isBlank();
	}
}
