package com.application.KWB.match;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;

import com.application.KWB.team.HitterDTO;
import com.application.KWB.team.PitcherDTO;


@Controller
@RequestMapping("/match")
public class MatchController{
	@Autowired
	private MatchService matchService;

	@GetMapping("/detail")
	public String detail(
		    @RequestParam("hometeam") String homeTeam,
		    @RequestParam("awayteam") String awayTeam,
		    Model model) {

		    // 서비스에서 홈팀 선수 목록 조회s
		    List<HitterDTO> homeHitters = matchService.getHitterByTeam(homeTeam);
		    List<PitcherDTO> homePitchers = matchService.getPitcherByTeam(homeTeam);

		    // 서비스에서 어웨이팀 선수 목록 조회
		    List<HitterDTO> awayHitters = matchService.getHitterByTeam(awayTeam);
		    List<PitcherDTO> awayPitchers = matchService.getPitcherByTeam(awayTeam);

		    model.addAttribute("homeTeam", homeTeam);
		    model.addAttribute("awayTeam", awayTeam);
		    model.addAttribute("homeHitters", homeHitters);
		    model.addAttribute("homePitchers", homePitchers);
		    model.addAttribute("awayHitters", awayHitters);
		    model.addAttribute("awayPitchers", awayPitchers);

		    return "match/detail";  // detail.html 뷰로 전달
		}
	
	/** 승부 예측: 선발·라인업을 입력해 시나리오 분석(발표 전)과 확정 예측(발표 후)을 한다 */
	@GetMapping("/predict")
	public String predict(
			@RequestParam("hometeam") String homeTeam,
			@RequestParam("awayteam") String awayTeam,
			Model model) {
		Map<String, Object> data = new LinkedHashMap<>();
		data.put("home", matchService.getPredictionRoster(homeTeam));
		data.put("away", matchService.getPredictionRoster(awayTeam));
		model.addAttribute("homeTeam", homeTeam);
		model.addAttribute("awayTeam", awayTeam);
		model.addAttribute("predictData", data);
		return "match/predict";
	}

	@GetMapping("/month")
	@ResponseBody
    public List<GameDateDto> getMatchesByMonth(@RequestParam("month") int month) {
        // 서비스에서 해당 월 경기 데이터 가져오기
		
        List<GameDateDto> gameDates = matchService.getMatchesByMonth(month);
        
        System.out.println(gameDates);

     

        return gameDates;
    }
	
	@PostMapping("/detail")
	@ResponseBody
	public ResponseEntity<Map<String, String>> receivePlayers(@RequestBody Map<String, List<String>> players) {
	    List<String> homeHitters = players.get("homeHitters");
	    List<String> homePitchers = players.get("homePitchers");
	    List<String> awayHitters = players.get("awayHitters");
	    List<String> awayPitchers = players.get("awayPitchers");

	    // 로직 처리 예시
	    System.out.println("홈 타자: " + homeHitters);
	    System.out.println("홈 투수: " + homePitchers);
	    System.out.println("어웨이 타자: " + awayHitters);
	    System.out.println("어웨이 투수: " + awayPitchers);
	    
	    Map<String, String> result = new HashMap<>();
	    result.put("message", "성공");
	    return ResponseEntity.ok(result);
	}
	
	
	
}
