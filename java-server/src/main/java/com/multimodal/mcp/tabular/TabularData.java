package com.multimodal.mcp.tabular;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
/**
 * In-memory tabular data wrapper ({@code List<Map<String,Object>>} + column names).
 */
public class TabularData {

    private final List<String> columnNames;
    private final List<Map<String, Object>> rows;

    public TabularData(List<String> columnNames, List<Map<String, Object>> rows) {
        this.columnNames = List.copyOf(columnNames);
        this.rows = List.copyOf(rows);
    }

    public static TabularData empty() {
        return new TabularData(List.of(), List.of());
    }

    public List<String> getColumnNames() {
        return columnNames;
    }

    public List<Map<String, Object>> getRows() {
        return rows;
    }

    public int numRows() {
        return rows.size();
    }

    public int numCols() {
        return columnNames.size();
    }

    public TabularData slice(int offset, Integer limit) {
        int start = Math.max(offset, 0);
        if (start >= rows.size()) {
            return new TabularData(columnNames, List.of());
        }
        int end = limit != null ? Math.min(start + limit, rows.size()) : rows.size();
        return new TabularData(columnNames, rows.subList(start, end));
    }

    public List<Map<String, Object>> toRecords() {
        List<Map<String, Object>> records = new ArrayList<>(rows.size());
        for (Map<String, Object> row : rows) {
            Map<String, Object> record = new LinkedHashMap<>();
            for (String col : columnNames) {
                record.put(col, row.get(col));
            }
            records.add(record);
        }
        return records;
    }

    public long estimateMemoryBytes() {
        long total = 64L;
        for (Map<String, Object> row : rows) {
            for (String col : columnNames) {
                Object value = row.get(col);
                total += estimateObjectBytes(value);
                total += col.length() * 2L;
            }
            total += 48L;
        }
        return total;
    }

    public ColumnKind columnKind(String column) {
        for (Map<String, Object> row : rows) {
            Object value = row.get(column);
            if (value == null) {
                continue;
            }
            if (value instanceof Boolean) {
                return ColumnKind.BOOLEAN;
            }
            if (value instanceof Integer || value instanceof Long) {
                return ColumnKind.INTEGER;
            }
            if (value instanceof Float || value instanceof Double) {
                return ColumnKind.FLOAT;
            }
            if (value instanceof java.time.temporal.TemporalAccessor) {
                return ColumnKind.DATETIME;
            }
            return ColumnKind.STRING;
        }
        return ColumnKind.STRING;
    }

    public int averageStringLength(String column) {
        int total = 0;
        int count = 0;
        for (Map<String, Object> row : rows) {
            Object value = row.get(column);
            if (value != null) {
                total += String.valueOf(value).length();
                count++;
            }
        }
        return count > 0 ? total / count : 0;
    }

    private static long estimateObjectBytes(Object value) {
        if (value == null) {
            return 8L;
        }
        if (value instanceof Number) {
            return 16L;
        }
        if (value instanceof Boolean) {
            return 8L;
        }
        return String.valueOf(value).length() * 2L + 40L;
    }

    public enum ColumnKind {
        BOOLEAN,
        INTEGER,
        FLOAT,
        DATETIME,
        STRING
    }
}
