package com.application.KWB.prediction;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.Map;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Controller
@RequestMapping("/predictions")
public class PredictionController {

	private final PredictionService predictionService;

	public PredictionController(PredictionService predictionService) {
		this.predictionService = predictionService;
	}

	/** 예측 기록 (예측 화면에서 호출) */
	@PostMapping
	@ResponseBody
	public Map<String, Object> record(@RequestBody PredictionRequest request) {
		LocalDateTime createdAt = predictionService.record(request);
		return Map.of("createdAt", createdAt.toString());
	}

	/** 예측 성적: 단계별 요약과 전체 기록 */
	@GetMapping
	public String page(Model model) {
		model.addAttribute("report", predictionService.report());
		return "predictions";
	}

	/** 경기 결과 직접 입력 */
	@PostMapping("/results")
	public String saveResult(
			@RequestParam("gameDate") @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate gameDate,
			@RequestParam("homeTeam") String homeTeam,
			@RequestParam("awayTeam") String awayTeam,
			@RequestParam("homeScore") int homeScore,
			@RequestParam("awayScore") int awayScore,
			RedirectAttributes redirect) {
		try {
			predictionService.saveManualResult(gameDate, homeTeam, awayTeam, homeScore, awayScore);
		} catch (IllegalArgumentException e) {
			redirect.addFlashAttribute("error", e.getMessage());
		}
		return "redirect:/predictions";
	}

	@ExceptionHandler(IllegalArgumentException.class)
	public ResponseEntity<Map<String, String>> handleInvalidInput(IllegalArgumentException e) {
		return ResponseEntity.badRequest().body(Map.of("message", e.getMessage()));
	}
}
