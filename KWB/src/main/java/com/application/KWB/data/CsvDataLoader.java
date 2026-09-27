package com.application.KWB.data;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * 앱 시작 시 선수 기록·일정 CSV 를 DB 테이블에 적재한다.
 * 테이블은 db/schema.sql 이 매 시작마다 새로 만든다.
 *
 * kwb.data-dir 폴더에 파일이 있으면 그것을, 없으면 저장소의 static/ 기본 데이터를 쓴다.
 */
@Component
public class CsvDataLoader implements ApplicationRunner {

	private static final Logger log = LoggerFactory.getLogger(CsvDataLoader.class);

	private static final String[][] TABLES = {
		{ "hitters", "hitters.csv" },
		{ "pitchers", "pitchers.csv" },
		{ "schedule", "schedule.csv" },
		{ "positions", "positions.csv" },  // 선택: 없으면 건너뜀
	};

	private final JdbcTemplate jdbcTemplate;
	private final String dataDir;

	public CsvDataLoader(JdbcTemplate jdbcTemplate, @Value("${kwb.data-dir:}") String dataDir) {
		this.jdbcTemplate = jdbcTemplate;
		this.dataDir = dataDir;
	}

	@Override
	public void run(ApplicationArguments args) throws IOException {
		for (String[] table : TABLES) {
			Resource csv = resolve(table[1]);
			if (!csv.exists()) {
				log.info("{} 파일이 없어 {} 테이블을 비워 둡니다", table[1], table[0]);
				continue;
			}
			int count = load(table[0], csv);
			log.info("{} 테이블에 {}건 적재 ({})", table[0], count, csv.getDescription());
		}
	}

	private Resource resolve(String fileName) {
		if (dataDir != null && !dataDir.isBlank()) {
			Resource external = new FileSystemResource(Path.of(dataDir, fileName));
			if (external.exists()) {
				return external;
			}
		}
		return new ClassPathResource("static/" + fileName);
	}

	private int load(String table, Resource csv) throws IOException {
		try (BufferedReader reader = new BufferedReader(
				new InputStreamReader(csv.getInputStream(), StandardCharsets.UTF_8))) {

			String header = reader.readLine();
			if (header == null) {
				return 0;
			}
			List<String> columns = Arrays.stream(stripBom(header).split(",", -1))
				.map(CsvDataLoader::toColumnName)
				.toList();

			List<Object[]> rows = new ArrayList<>();
			String line;
			while ((line = reader.readLine()) != null) {
				if (line.isBlank()) {
					continue;
				}
				String[] values = line.split(",", -1);
				if (values.length != columns.size()) {
					throw new IllegalStateException(csv.getDescription() + " 컬럼 수 불일치: " + line);
				}
				rows.add(Arrays.stream(values)
					.map(v -> v.isBlank() ? null : v.trim())
					.toArray());
			}

			// `2b` 처럼 숫자로 시작하는 컬럼이 있어 식별자를 백틱으로 감싼다
			String sql = "INSERT INTO " + table + " ("
				+ String.join(", ", columns.stream().map(c -> "`" + c + "`").toList()) + ") VALUES ("
				+ String.join(", ", columns.stream().map(c -> "?").toList()) + ")";
			jdbcTemplate.batchUpdate(sql, rows);
			return rows.size();
		}
	}

	private static String stripBom(String s) {
		return s.startsWith("﻿") ? s.substring(1) : s;
	}

	/** CSV 헤더 → DB 컬럼명 (예: "wRC+" → "wrc_plus", "HR/9" → "hr_per_9") */
	static String toColumnName(String header) {
		return header.trim().toLowerCase()
			.replace("%", "_pct")
			.replace("+", "_plus")
			.replace("/", "_per_")
			.replace(" ", "_");
	}
}
