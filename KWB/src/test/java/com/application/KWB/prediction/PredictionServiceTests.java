package com.application.KWB.prediction;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class PredictionServiceTests {

	private final PredictionDAO dao = mock(PredictionDAO.class);
	// 2026-09-29 17:30:00 KST 로 고정
	private final Clock clock = Clock.fixed(Instant.parse("2026-09-29T08:30:00Z"), ZoneId.of("Asia/Seoul"));
	private final PredictionService service = new PredictionService(dao, clock);

	private static PredictionRequest request(String stage, String home, String away, Double prob) {
		return new PredictionRequest(stage, LocalDate.of(2026, 9, 29), home, away, prob, null, null, null, 0.03,
			10000, "곽빈", "구창모", List.of(Map.of("name", "박찬호", "pos", "유격수")), null);
	}

	@Test
	@SuppressWarnings("unchecked")
	void recordsWithServerClockNotClientTime() {
		LocalDateTime createdAt = service.record(request("predict", "두산", "NC", 0.56));

		assertThat(createdAt).isEqualTo(LocalDateTime.of(2026, 9, 29, 17, 30));
		ArgumentCaptor<Map<String, Object>> captor = ArgumentCaptor.forClass(Map.class);
		verify(dao).insert(captor.capture());
		assertThat(captor.getValue())
			.containsEntry("createdAt", createdAt)
			.containsEntry("stage", "predict")
			.containsEntry("homeWinProb", 0.56)
			.containsEntry("homeLineup", "[{\"name\":\"박찬호\",\"pos\":\"유격수\"}]")
			.containsEntry("awayLineup", null);
	}

	@Test
	void rejectsInvalidRequests() {
		assertThatThrownBy(() -> service.record(request("guess", "두산", "NC", 0.5))).hasMessageContaining("stage");
		assertThatThrownBy(() -> service.record(request("predict", "두산", "두산", 0.5))).hasMessageContaining("같습니다");
		assertThatThrownBy(() -> service.record(request("predict", "두산", "NC", 1.2))).hasMessageContaining("0~1");
		assertThatThrownBy(() -> service.record(request("predict", "두산", "NC", null))).hasMessageContaining("0~1");
		verify(dao, never()).insert(any());
	}

	@Test
	void manualResultRejectsNegativeScores() {
		assertThatThrownBy(() -> service.saveManualResult(LocalDate.of(2026, 9, 29), "두산", "NC", -1, 3))
			.isInstanceOf(IllegalArgumentException.class);
	}
}
