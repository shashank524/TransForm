package com.multimodal.mcp.codec;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.apache.arrow.vector.FieldVector;
import org.apache.arrow.vector.VectorSchemaRoot;
import org.apache.arrow.vector.types.pojo.ArrowType;
import org.springframework.stereotype.Component;

/**
 * CodecDB-inspired data-driven encoding selection for Parquet columns.
 */
@Component
public class CodecSelector {

    public static final double CARDINALITY_THRESHOLD = 0.3;

    public Map<String, Map<String, Object>> computeColumnFeatures(VectorSchemaRoot table) {
        Map<String, Map<String, Object>> features = new HashMap<>();
        int nRows = table.getRowCount();

        for (FieldVector vector : table.getFieldVectors()) {
            String name = vector.getField().getName();
            Map<String, Object> feat = new HashMap<>();
            feat.put("dtype", vector.getField().getType().toString());
            feat.put("n_rows", nRows);

            int nUnique = estimateUniqueCount(vector, nRows);
            feat.put("n_unique", nUnique);
            feat.put("cardinality_ratio", nRows > 0 ? (double) nUnique / nRows : 1.0);

            ArrowType type = vector.getField().getType();
            boolean isNumeric = isIntegerType(type) || isFloatingType(type);
            boolean isString = isStringType(type);

            if (isNumeric && nRows > 1) {
                populateNumericFeatures(vector, nRows, feat);
            } else if (isString && nRows > 1) {
                populateStringFeatures(vector, nRows, feat);
            } else {
                feat.putIfAbsent("is_sorted", nRows <= 1);
            }

            features.put(name, feat);
        }
        return features;
    }

    public Map<String, Object> selectEncodingParams(VectorSchemaRoot table) {
        Map<String, Map<String, Object>> features = computeColumnFeatures(table);
        List<String> dictColumns = new ArrayList<>();
        Map<String, String> columnEncoding = new HashMap<>();

        for (Map.Entry<String, Map<String, Object>> entry : features.entrySet()) {
            String name = entry.getKey();
            Map<String, Object> feat = entry.getValue();
            double cr = toDouble(feat.get("cardinality_ratio"), 1.0);
            boolean isSorted = Boolean.TRUE.equals(feat.get("is_sorted"));
            String dtypeStr = String.valueOf(feat.get("dtype"));
            String dtypeLower = dtypeStr.toLowerCase();
            boolean isInt = dtypeLower.contains("int") && !dtypeLower.contains("point");
            boolean isStr = dtypeLower.contains("utf8") || dtypeLower.contains("string");

            if (cr < CARDINALITY_THRESHOLD) {
                dictColumns.add(name);
            } else {
                if (isInt && isSorted) {
                    columnEncoding.put(name, "DELTA_BINARY_PACKED");
                } else if (isStr) {
                    columnEncoding.put(name, "DELTA_BYTE_ARRAY");
                } else {
                    columnEncoding.put(name, "PLAIN");
                }
            }
        }

        Map<String, Object> result = new HashMap<>();
        result.put("use_dictionary", dictColumns);
        result.put("column_encoding", columnEncoding.isEmpty() ? null : columnEncoding);
        result.put("features", features);
        return result;
    }

    private void populateNumericFeatures(FieldVector vector, int nRows, Map<String, Object> feat) {
        try {
            List<Double> values = new ArrayList<>();
            for (int i = 0; i < nRows; i++) {
                if (!vector.isNull(i)) {
                    values.add(readNumericValue(vector, i));
                }
            }
            if (values.size() > 1) {
                boolean sorted = true;
                for (int i = 1; i < values.size(); i++) {
                    if (values.get(i - 1) > values.get(i)) {
                        sorted = false;
                        break;
                    }
                }
                feat.put("is_sorted", sorted);
                double max = values.stream().mapToDouble(Double::doubleValue).max().orElse(0);
                double min = values.stream().mapToDouble(Double::doubleValue).min().orElse(0);
                feat.put("max_value", (long) max);
                feat.put("min_value", (long) min);
            } else if (values.size() == 1) {
                feat.put("is_sorted", true);
                feat.put("max_value", values.get(0).longValue());
                feat.put("min_value", values.get(0).longValue());
            } else {
                feat.put("is_sorted", true);
                feat.put("max_value", 0L);
                feat.put("min_value", 0L);
            }
        } catch (Exception e) {
            feat.put("is_sorted", false);
        }
    }

    private void populateStringFeatures(FieldVector vector, int nRows, Map<String, Object> feat) {
        try {
            List<String> nonNull = new ArrayList<>();
            for (int i = 0; i < nRows; i++) {
                if (!vector.isNull(i)) {
                    Object value = vector.getObject(i);
                    if (value != null) {
                        nonNull.add(String.valueOf(value));
                    }
                }
            }
            boolean sorted = true;
            for (int i = 1; i < nonNull.size(); i++) {
                if (nonNull.get(i - 1).compareTo(nonNull.get(i)) > 0) {
                    sorted = false;
                    break;
                }
            }
            feat.put("is_sorted", sorted);
            if (!nonNull.isEmpty()) {
                int totalLen = nonNull.stream().mapToInt(String::length).sum();
                feat.put("mean_value_length", (double) totalLen / nonNull.size());
            } else {
                feat.put("mean_value_length", 0.0);
            }
        } catch (Exception e) {
            feat.put("is_sorted", false);
        }
    }

    private int estimateUniqueCount(FieldVector vector, int nRows) {
        try {
            Set<Object> unique = new HashSet<>();
            for (int i = 0; i < nRows; i++) {
                if (!vector.isNull(i)) {
                    unique.add(vector.getObject(i));
                }
            }
            return unique.size();
        } catch (Exception e) {
            return nRows;
        }
    }

    private double readNumericValue(FieldVector vector, int index) {
        Object value = vector.getObject(index);
        if (value instanceof Number number) {
            return number.doubleValue();
        }
        return Double.parseDouble(String.valueOf(value));
    }

    private static boolean isIntegerType(ArrowType type) {
        return type instanceof ArrowType.Int;
    }

    private static boolean isFloatingType(ArrowType type) {
        return type instanceof ArrowType.FloatingPoint;
    }

    private static boolean isStringType(ArrowType type) {
        return type instanceof ArrowType.Utf8 || type instanceof ArrowType.LargeUtf8;
    }

    private static double toDouble(Object value, double defaultValue) {
        if (value instanceof Number number) {
            return number.doubleValue();
        }
        if (value == null) {
            return defaultValue;
        }
        try {
            return Double.parseDouble(String.valueOf(value));
        } catch (NumberFormatException e) {
            return defaultValue;
        }
    }
}
