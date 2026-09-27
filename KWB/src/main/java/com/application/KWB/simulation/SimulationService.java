package com.application.KWB.simulation;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Python 스크립트(static/simulation.py, static/scenario.py)를 실행하고 결과 JSON 을 돌려준다.
 * 입력은 요청마다 임시 파일로 넘겨 동시 요청끼리 섞이지 않게 한다.
 */
@Service
public class SimulationService {

	private static final Logger log = LoggerFactory.getLogger(SimulationService.class);

	/** 스크립트가 입력 오류(ValueError)로 끝났을 때의 종료 코드 */
	private static final int EXIT_INVALID_INPUT = 2;

	private final ObjectMapper mapper = new ObjectMapper();
	private final String dataDir;

	public SimulationService(@Value("${kwb.data-dir:}") String dataDir) {
		this.dataDir = dataDir;
	}

	public Map<String, Object> runSimulation(Map<String, Object> input) throws IOException {
		return run("simulation.py", input);
	}

	public Map<String, Object> runScenario(Map<String, Object> input) throws IOException {
		return run("scenario.py", input);
	}

	private Map<String, Object> run(String script, Map<String, Object> input) throws IOException {
		// DB 에 적재한 것과 같은 선수 기록을 쓰도록 데이터 폴더를 넘긴다 (비어 있으면 스크립트 기본 데이터)
		if (dataDir != null && !dataDir.isBlank()) {
			input.put("data_dir", Path.of(dataDir).toAbsolutePath().toString());
		}
		File workingDir = new File(System.getProperty("user.dir"), "src/main/resources/static");
		Path inputFile = Files.createTempFile("kwb-" + script.replace(".py", "") + "-", ".json");
		try {
			Files.writeString(inputFile, mapper.writeValueAsString(input), StandardCharsets.UTF_8);
			ProcessBuilder pb = new ProcessBuilder(List.of("py", script, inputFile.toString()));
			pb.directory(workingDir);
			pb.redirectErrorStream(true);

			long started = System.currentTimeMillis();
			Process process = pb.start();
			String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8).trim();
			int exitCode = waitFor(process);
			log.info("{} 종료 코드 {} ({}ms)", script, exitCode, System.currentTimeMillis() - started);

			if (exitCode == EXIT_INVALID_INPUT) {
				throw new IllegalArgumentException(errorMessage(output));
			}
			if (exitCode != 0) {
				throw new IOException(script + " 실행 실패: " + output);
			}
			return mapper.readValue(output, new TypeReference<>() {
			});
		} finally {
			Files.deleteIfExists(inputFile);
		}
	}

	private static int waitFor(Process process) throws IOException {
		try {
			return process.waitFor();
		} catch (InterruptedException e) {
			Thread.currentThread().interrupt();
			throw new IOException("Python 프로세스 대기 중 중단됨", e);
		}
	}

	private String errorMessage(String output) {
		try {
			Object error = mapper.readValue(output, new TypeReference<Map<String, Object>>() {
			}).get("error");
			return error != null ? error.toString() : output;
		} catch (IOException e) {
			return output;
		}
	}
}
