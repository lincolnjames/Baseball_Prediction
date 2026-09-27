package com.application.KWB.simulation;

import org.springframework.stereotype.Service;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

@Service
public class SimulationService {
    public Map<String, Object> runSimulation(Map<String, Object> simInput) throws IOException {
        ObjectMapper mapper = new ObjectMapper();
        String inputJson = mapper.writeValueAsString(simInput);

        String currentDir = System.getProperty("user.dir");
        File workingDir = new File(currentDir, "src/main/resources/static");

        File jsonFile = new File(workingDir, "input.json");
        try (Writer fw = new OutputStreamWriter(new FileOutputStream(jsonFile), StandardCharsets.UTF_8)) {
            fw.write(inputJson);
        }

        // 3. 파이썬 실행 명령어: workingDir을 작업 디렉토리로 지정
        List<String> command = Arrays.asList(
            "py", "simulation.py", "input.json"
        );
        ProcessBuilder pb = new ProcessBuilder(command);
        pb.directory(workingDir);
        pb.redirectErrorStream(true);

        // 3. 명령어와 input.json 내용 로그
        System.out.println("실행 명령어: " + String.join(" ", command));
        System.out.println("input.json 내용: " + inputJson);

        // 4. 파이썬 프로세스 실행 및 표준출력 읽기
        Process process = pb.start();

        BufferedReader reader = new BufferedReader(
            new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8)
        );
        StringBuilder output = new StringBuilder();
        String line;
        while ((line = reader.readLine()) != null) {
            System.out.println("[PYTHON] " + line); // 실시간 로그
            output.append(line).append("\n");
        }

        try {
            int exitCode = process.waitFor();
            System.out.println("파이썬 종료 코드: " + exitCode);
            if (exitCode != 0) {
                throw new IOException("Python process failed: " + output.toString().trim());
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IOException("Process interrupted", e);
        }

        // 5. 결과(JSON)를 Map으로 변환해 반환
        return mapper.readValue(output.toString(), Map.class);
    }
}
