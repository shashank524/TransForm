package com.multimodal.mcp.bird;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.apache.arrow.vector.VectorSchemaRoot;
import org.springframework.stereotype.Service;

import com.multimodal.mcp.core.ResultConfig;
import com.multimodal.mcp.core.RuntimeState;
import com.multimodal.mcp.tabular.TabularData;
import com.multimodal.mcp.tabular.TabularService;
import com.multimodal.mcp.util.Env;

/**
 * BIRD SQLite query execution and materialization. Port of BIRD section in {@code server_app.py}.
 */
@Service
public class BirdQueryService {

    private final RuntimeState runtimeState;
    private final TabularService tabularService;

    public BirdQueryService(RuntimeState runtimeState, TabularService tabularService) {
        this.runtimeState = runtimeState;
        this.tabularService = tabularService;
    }

    public String birdSqlForSqlite(String sql) {
        return (sql == null ? "" : sql).replace('`', '"');
    }

    public Path resolveBirdSqlitePath(String dbId) {
        String normalized = dbId == null ? "" : dbId.strip();
        if (normalized.isEmpty()) {
            return null;
        }
        String fileName = normalized + ".sqlite";
        List<Path> candidates = new ArrayList<>();

        String envRoot = Env.get("BIRD_SQLITE_ROOT");
        if (!envRoot.isEmpty()) {
            candidates.add(Path.of(envRoot, "dev_databases", normalized, fileName));
        }

        Path base = runtimeState.getRoot().resolve("data/datasets/bird/dev");
        candidates.add(base.resolve("dev_databases").resolve(normalized).resolve(fileName));
        candidates.add(base.resolve("databases").resolve(normalized).resolve(fileName));

        for (Path candidate : candidates) {
            if (Files.isRegularFile(candidate)) {
                return candidate;
            }
        }
        return null;
    }

    public TabularData executeSqliteQuery(Path dbPath, String sql, int maxRows) throws SQLException {
        String fixedSql = birdSqlForSqlite(sql);
        double timeoutSeconds = Env.getDouble("SQLITE_QUERY_TIMEOUT_S", 30.0);

        try (Connection connection = DriverManager.getConnection("jdbc:sqlite:" + dbPath.toAbsolutePath())) {
            try (Statement statement = connection.createStatement()) {
                if (timeoutSeconds > 0) {
                    statement.setQueryTimeout((int) Math.ceil(timeoutSeconds));
                }
                try (ResultSet resultSet = statement.executeQuery(fixedSql)) {
                    return resultSetToTabular(resultSet, maxRows);
                }
            }
        }
    }

    public List<Map<String, Object>> queryJson(String dbId, String sql, int maxRows) throws SQLException {
        Path dbPath = resolveBirdSqlitePath(dbId);
        if (dbPath == null) {
            throw new IllegalArgumentException(
                    "Could not resolve BIRD sqlite for db_id='" + dbId + "'. Set BIRD_SQLITE_ROOT.");
        }
        TabularData dataframe = executeSqliteQuery(dbPath, sql, maxRows);
        int cells = dataframe.numRows() * dataframe.numCols();
        Integer cap = runtimeState.jsonCellsCap();
        if (cap != null && cells > cap) {
            throw new IllegalArgumentException("Result too large for JSON (" + cells + " cells > " + cap + ")");
        }
        return dataframe.toRecords();
    }

    public Map<String, Object> materialize(String dbId, String sql, int maxRows) throws IOException, SQLException {
        Path dbPath = resolveBirdSqlitePath(dbId);
        if (dbPath == null) {
            throw new IllegalArgumentException(
                    "Could not resolve BIRD sqlite for db_id='" + dbId + "'. Set BIRD_SQLITE_ROOT.");
        }

        TabularData dataframe = executeSqliteQuery(dbPath, sql, maxRows);
        if (dataframe.numRows() == 0) {
            throw new IllegalArgumentException("Empty result");
        }

        int nRows = dataframe.numRows();
        int nCols = dataframe.numCols();
        String comp = tabularService.getDefaultCompression();
        String encStrat = tabularService.getDefaultEncodingStrategy();

        ResultConfig scratch = new ResultConfig(nRows, nCols);
        scratch.setCachedDataframe(dataframe);
        VectorSchemaRoot table = tabularService.resolveArrowTable(scratch);
        byte[] parquetBytes = tabularService.encodeParquet(table, comp, encStrat);

        String resultId = UUID.randomUUID().toString();
        Path path = runtimeState.getRoot().resolve("results/materialized/bird_exec_" + resultId + ".parquet");
        Files.createDirectories(path.getParent());
        Files.write(path, parquetBytes);

        ResultConfig config = new ResultConfig(nRows, nCols);
        config.setCompression(comp);
        config.setEncodingStrategy(encStrat);
        config.setMaterializedPath(path);

        try {
            tabularService.populateMaterializedCaches(
                    config, resultId, dataframe, table, parquetBytes, 8192);
        } catch (Exception e) {
            config.setCachedHints(null);
        }

        runtimeState.getResultRegistry().put(resultId, config);
        return Map.of("result_id", resultId, "n_rows", nRows, "n_cols", nCols);
    }

    private static TabularData resultSetToTabular(ResultSet resultSet, int maxRows) throws SQLException {
        ResultSetMetaData meta = resultSet.getMetaData();
        int columnCount = meta.getColumnCount();
        List<String> columns = new ArrayList<>(columnCount);
        for (int i = 1; i <= columnCount; i++) {
            columns.add(meta.getColumnLabel(i));
        }

        List<Map<String, Object>> rows = new ArrayList<>();
        int count = 0;
        while (resultSet.next()) {
            if (maxRows > 0 && count >= maxRows) {
                break;
            }
            Map<String, Object> row = new LinkedHashMap<>();
            for (int i = 1; i <= columnCount; i++) {
                row.put(columns.get(i - 1), resultSet.getObject(i));
            }
            rows.add(row);
            count++;
        }
        return new TabularData(columns, rows);
    }
}
