package com.multimodal.mcp.hints;

import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.Map;

import org.springframework.stereotype.Component;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.multimodal.mcp.util.Env;

/**
 * Persisted reference table for format hint estimates and observed outcomes.
 */
@Component
public class HintStore {

    private final Path dbPath;
    private final ObjectMapper objectMapper;

    public HintStore() {
        this(defaultDbPath());
    }

    public HintStore(Path dbPath) {
        this.dbPath = dbPath;
        this.objectMapper = new ObjectMapper();
        this.objectMapper.configure(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS, true);
    }

    public static HintStore createDefault() {
        return new HintStore(defaultDbPath());
    }

    public static Path defaultDbPath() {
        String raw = Env.get("FORMAT_HINTS_DB_PATH");
        if (!raw.isEmpty()) {
            return Path.of(raw);
        }
        return Path.of("results/format_hints.sqlite");
    }

    public Path getDbPath() {
        return dbPath;
    }

    public Map<String, Object> get(Map<String, Object> key) {
        String keyJson = stableKeyJson(key);
        try (Connection conn = connect()) {
            ensureSchema(conn);
            try (PreparedStatement ps = conn.prepareStatement(
                    "SELECT hints_json FROM format_hints WHERE key_json = ?")) {
                ps.setString(1, keyJson);
                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        return null;
                    }
                    return parseHintsJson(rs.getString(1));
                }
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Failed to read hints from SQLite", e);
        }
    }

    public void upsert(Map<String, Object> key, Map<String, Object> hints) {
        String keyJson = stableKeyJson(key);
        String hintsJson = writeJson(hints);
        try (Connection conn = connect()) {
            ensureSchema(conn);
            try (PreparedStatement ps = conn.prepareStatement("""
                    INSERT INTO format_hints(key_json, hints_json, updated_at)
                    VALUES(?, ?, ?)
                    ON CONFLICT(key_json) DO UPDATE SET
                      hints_json = excluded.hints_json,
                      updated_at = excluded.updated_at
                    """)) {
                ps.setString(1, keyJson);
                ps.setString(2, hintsJson);
                ps.setDouble(3, System.currentTimeMillis() / 1000.0);
                ps.executeUpdate();
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Failed to upsert hints into SQLite", e);
        }
    }

    public void recordOutcome(Map<String, Object> key, Map<String, Object> outcome) {
        String keyJson = stableKeyJson(key);
        String outcomeJson = writeJson(outcome);
        try (Connection conn = connect()) {
            ensureSchema(conn);
            try (PreparedStatement ps = conn.prepareStatement(
                    "INSERT INTO format_outcomes(key_json, outcome_json, created_at) VALUES(?, ?, ?)")) {
                ps.setString(1, keyJson);
                ps.setString(2, outcomeJson);
                ps.setDouble(3, System.currentTimeMillis() / 1000.0);
                ps.executeUpdate();
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Failed to record outcome in SQLite", e);
        }
    }

    public String stableKeyJson(Map<String, Object> key) {
        try {
            return objectMapper.writeValueAsString(key);
        } catch (Exception e) {
            throw new IllegalArgumentException("Unable to serialize hint key", e);
        }
    }

    private Connection connect() throws SQLException {
        if (dbPath.getParent() != null) {
            try {
                java.nio.file.Files.createDirectories(dbPath.getParent());
            } catch (java.io.IOException e) {
                throw new SQLException("Unable to create database directory", e);
            }
        }
        Connection conn = DriverManager.getConnection("jdbc:sqlite:" + dbPath.toAbsolutePath());
        try (Statement stmt = conn.createStatement()) {
            stmt.execute("PRAGMA journal_mode=WAL;");
            stmt.execute("PRAGMA synchronous=NORMAL;");
        }
        return conn;
    }

    private void ensureSchema(Connection conn) throws SQLException {
        try (Statement stmt = conn.createStatement()) {
            stmt.execute("""
                    CREATE TABLE IF NOT EXISTS format_hints (
                      key_json TEXT PRIMARY KEY,
                      hints_json TEXT NOT NULL,
                      updated_at REAL NOT NULL
                    )
                    """);
            stmt.execute("""
                    CREATE TABLE IF NOT EXISTS format_outcomes (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      key_json TEXT NOT NULL,
                      outcome_json TEXT NOT NULL,
                      created_at REAL NOT NULL
                    )
                    """);
        }
    }

    private Map<String, Object> parseHintsJson(String json) {
        try {
            Map<String, Object> data = objectMapper.readValue(json, new TypeReference<>() {
            });
            return data;
        } catch (Exception e) {
            return null;
        }
    }

    private String writeJson(Map<String, Object> value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (Exception e) {
            throw new IllegalArgumentException("Unable to serialize JSON", e);
        }
    }
}
