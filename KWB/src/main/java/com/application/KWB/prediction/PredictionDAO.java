package com.application.KWB.prediction;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

@Mapper
public interface PredictionDAO {

	/** 예측을 기록한다. 수정·삭제 메서드는 두지 않는다. */
	void insert(Map<String, Object> prediction);

	/** 모든 예측 + 경기 시작 시각(일정) + 결과 */
	List<PredictionRow> findAllWithResults();

	/** 직접 입력한 결과. 이미 가져온 공식 결과(import)는 덮어쓰지 않는다. */
	int upsertManualResult(@Param("gameDate") LocalDate gameDate, @Param("homeTeam") String homeTeam,
		@Param("awayTeam") String awayTeam, @Param("homeScore") int homeScore, @Param("awayScore") int awayScore,
		@Param("updatedAt") LocalDateTime updatedAt);
}
