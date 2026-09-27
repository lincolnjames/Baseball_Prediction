package com.application.KWB.data;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

/**
 * 앱 시작 시 static/*.csv 를 DB 테이블에 적재한다.
 * 테이블은 db/schema.sql 이 매 시작마다 새로 만든다.
 */
@Component
public class CsvDataLoader implements ApplicationRunner {

	private static final Logger log = LoggerFactory.getLogger(CsvDataLoader.class);

	private static final String[][] TABLES = {
		{ "hitters", "static/hitters.csv" },
		{ "pitchers", "static/pitchers.csv" },
		{ "schedule", "static/schedule.csv" },
	};

	private final JdbcTemplate jdbcTemplate;

	public CsvDataLoader(JdbcTemplate jdbcTemplate) {
		this.jdbcTemplate = jdbcTemplate;
	}

	@Override
	public void run(ApplicationArguments args) throws IOException {
		for (String[] table : TABLES) {
			int count = load(table[0], table[1]);
			log.info("{} 테이블에 {}건 적재 ({})", table[0], count, table[1]);
		}
	}

	private int load(String table, String csvPath) throws IOException {
		try (BufferedReader reader = new BufferedReader(
				new InputStreamReader(new ClassPathResource(csvPath).getInputStream(), StandardCharsets.UTF_8))) {

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
					throw new IllegalStateException(csvPath + " 컬럼 수 불일치: " + line);
				}
				rows.add(Arrays.stream(values)
					.map(v -> v.isBlank() ? null : v.trim())
					.toArray());
			}

			String sql = "INSERT INTO " + table + " (" + String.join(", ", columns) + ") VALUES ("
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
