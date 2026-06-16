package com.multimodal.mcp.format;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.multimodal.mcp.util.Env;

/**
 * AdaEdge-inspired format selection: choose JSON vs Parquet vs Arrow IPC (blob/stream)
 * using optimization target and data features.
 */
@Component
public class FormatSelector {

    public static final int CELLS_SMALL = 50_000;
    public static final int CELLS_MEDIUM = 300_000;
    public static final int CELLS_LARGE = 2_000_000;
    public static final int ROWS_STREAM_FAVOR = 50_000;
    public static final int JSON_OBVIOUS_WINNER_BYTES_DEFAULT = 4096;

    private static final Map<String, Double> DEFAULT_DECODE_NS = Map.of(
            "json", 1.0,
            "parquet_blob", 4.0,
            "arrow_ipc_blob", 0.5
    );

    private final ObjectMapper objectMapper = new ObjectMapper();

    public FormatName recommendFormatLegacy(int nRows, int nCols) {
        int totalCells = nRows * nCols;
        if (totalCells <= CELLS_SMALL) {
            return FormatName.JSON;
        } else if (totalCells <= CELLS_MEDIUM) {
            return FormatName.PARQUET_BLOB;
        } else if (totalCells <= CELLS_LARGE) {
            return FormatName.PARQUET_BLOB;
        } else {
            return FormatName.PARQUET_STREAM;
        }
    }

    public FormatName selectFormat(SelectionContext context) {
        int nRows = context.getNRows();
        int nCols = context.getNCols();
        OptimizationTarget target = context.getTarget();
        int cells = nRows * nCols;

        if (target == OptimizationTarget.MIN_TIME_TO_FIRST_ROWS) {
            if (context.isPreferStreaming() || nRows >= ROWS_STREAM_FAVOR) {
                if (cells > CELLS_SMALL) {
                    return FormatName.PARQUET_STREAM;
                }
            }
            if (cells <= CELLS_SMALL) {
                return FormatName.JSON;
            }
            return FormatName.PARQUET_BLOB;
        }

        if (target == OptimizationTarget.MIN_BYTES) {
            if (cells <= CELLS_SMALL) {
                return FormatName.JSON;
            }
            if (cells > CELLS_LARGE) {
                return FormatName.PARQUET_STREAM;
            }
            return FormatName.PARQUET_BLOB;
        }

        if (cells <= CELLS_SMALL) {
            return FormatName.JSON;
        }
        if (cells <= CELLS_MEDIUM) {
            return FormatName.PARQUET_BLOB;
        }
        if (cells <= CELLS_LARGE) {
            return FormatName.PARQUET_BLOB;
        }
        return FormatName.PARQUET_STREAM;
    }

    public FormatName selectFormatWithHints(SelectionContext context, Map<String, Object> hints) {
        if (hints.containsKey("raw_bytes") || hints.containsKey("text_inline_bytes")) {
            return selectUnstructuredFormat(context, hints);
        }

        Object jsonObj = hints.get("json_bytes");
        Object parquetObj = hints.get("parquet_bytes");
        if (jsonObj == null || parquetObj == null) {
            return selectFormat(context);
        }

        int jsonBytes = toInt(jsonObj);
        int parquetBytes = toInt(parquetObj);
        Integer arrowIpcBytes = hints.containsKey("arrow_ipc_bytes")
                ? toInt(hints.get("arrow_ipc_bytes"))
                : null;

        Integer firstChunkBytes = hints.containsKey("parquet_stream_first_chunk_bytes")
                ? toInt(hints.get("parquet_stream_first_chunk_bytes"))
                : null;
        Integer arrowIpcFirstChunk = hints.containsKey("arrow_ipc_stream_first_chunk_bytes")
                ? toInt(hints.get("arrow_ipc_stream_first_chunk_bytes"))
                : null;

        int nRows = context.getNRows();
        OptimizationTarget target = context.getTarget();
        int cells = nRows * context.getNCols();

        if ((target == OptimizationTarget.MIN_LATENCY || target == OptimizationTarget.MIN_BYTES)
                && jsonBytes <= jsonObviousWinnerBytes()) {
            return FormatName.JSON;
        }

        if (target == OptimizationTarget.MIN_BYTES) {
            return minBlobFormat(jsonBytes, parquetBytes, arrowIpcBytes);
        }

        if (target == OptimizationTarget.MIN_TIME_TO_FIRST_ROWS) {
            boolean wantStream = context.isPreferStreaming() || nRows >= ROWS_STREAM_FAVOR;
            if (wantStream && cells > CELLS_SMALL) {
                if (firstChunkBytes != null && arrowIpcFirstChunk != null) {
                    if (getNetworkMbps() <= 0.0) {
                        return firstChunkBytes <= arrowIpcFirstChunk
                                ? FormatName.PARQUET_STREAM
                                : FormatName.ARROW_IPC_STREAM;
                    }
                    double pqS = estimatedE2eLatencySeconds(firstChunkBytes, "parquet_blob");
                    double ipcS = estimatedE2eLatencySeconds(arrowIpcFirstChunk, "arrow_ipc_blob");
                    return pqS <= ipcS ? FormatName.PARQUET_STREAM : FormatName.ARROW_IPC_STREAM;
                }
                if (firstChunkBytes != null) {
                    return FormatName.PARQUET_STREAM;
                }
                if (arrowIpcFirstChunk != null) {
                    return FormatName.ARROW_IPC_STREAM;
                }
            }
            return minBlobFormatLatency(jsonBytes, parquetBytes, arrowIpcBytes);
        }

        return minBlobFormatLatency(jsonBytes, parquetBytes, arrowIpcBytes);
    }

    public OptimizationTarget getDefaultTarget() {
        return OptimizationTarget.fromString(Env.get("FORMAT_SELECT_TARGET", "min_latency"));
    }

    public int jsonObviousWinnerBytes() {
        String raw = Env.get("FORMAT_HINTS_JSON_OBVIOUS_WINNER_BYTES");
        if (!raw.isEmpty()) {
            try {
                return Math.max(0, Integer.parseInt(raw));
            } catch (NumberFormatException ignored) {
                // fall through
            }
        }
        return JSON_OBVIOUS_WINNER_BYTES_DEFAULT;
    }

    private FormatName selectUnstructuredFormat(SelectionContext context, Map<String, Object> hints) {
        Object rawObj = hints.get("raw_bytes");
        if (rawObj == null) {
            return selectFormat(context);
        }
        int rawBytes = toInt(rawObj);
        Integer gzipBytes = hints.containsKey("gzip_bytes") ? toInt(hints.get("gzip_bytes")) : null;
        Integer inlineBytes = hints.containsKey("text_inline_bytes")
                ? toInt(hints.get("text_inline_bytes"))
                : null;

        if (context.getTarget() == OptimizationTarget.MIN_BYTES) {
            return minUnstructuredBytes(rawBytes, gzipBytes, inlineBytes);
        }

        if (getNetworkMbps() <= 0.0) {
            return minUnstructuredBytes(rawBytes, gzipBytes, inlineBytes);
        }

        List<CandidateScore> candidates = new ArrayList<>();
        candidates.add(new CandidateScore(transferSeconds(rawBytes), 2, FormatName.RAW_BLOB));
        if (gzipBytes != null) {
            candidates.add(new CandidateScore(transferSeconds(gzipBytes), 1, FormatName.GZIP_BLOB));
        }
        if (inlineBytes != null) {
            candidates.add(new CandidateScore(transferSeconds(inlineBytes), 0, FormatName.TEXT_INLINE));
        }
        return candidates.stream()
                .min(Comparator.comparingDouble(CandidateScore::score).thenComparingInt(CandidateScore::tie))
                .map(CandidateScore::format)
                .orElse(FormatName.RAW_BLOB);
    }

    private FormatName minUnstructuredBytes(int rawBytes, Integer gzipBytes, Integer inlineBytes) {
        List<CandidateScore> candidates = new ArrayList<>();
        candidates.add(new CandidateScore(rawBytes, 2, FormatName.RAW_BLOB));
        if (gzipBytes != null) {
            candidates.add(new CandidateScore(gzipBytes, 1, FormatName.GZIP_BLOB));
        }
        if (inlineBytes != null) {
            candidates.add(new CandidateScore(inlineBytes, 0, FormatName.TEXT_INLINE));
        }
        return candidates.stream()
                .min(Comparator.comparingDouble(CandidateScore::score).thenComparingInt(CandidateScore::tie))
                .map(CandidateScore::format)
                .orElse(FormatName.RAW_BLOB);
    }

    private FormatName minBlobFormat(int jsonBytes, int parquetBytes, Integer arrowIpcBytes) {
        List<CandidateScore> candidates = new ArrayList<>();
        candidates.add(new CandidateScore(jsonBytes, 0, FormatName.JSON));
        candidates.add(new CandidateScore(parquetBytes, 1, FormatName.PARQUET_BLOB));
        if (arrowIpcBytes != null) {
            candidates.add(new CandidateScore(arrowIpcBytes, 2, FormatName.ARROW_IPC_BLOB));
        }
        return candidates.stream()
                .min(Comparator.comparingDouble(CandidateScore::score).thenComparingInt(CandidateScore::tie))
                .map(CandidateScore::format)
                .orElse(FormatName.JSON);
    }

    private FormatName minBlobFormatLatency(int jsonBytes, int parquetBytes, Integer arrowIpcBytes) {
        if (getNetworkMbps() <= 0.0) {
            return minBlobFormat(jsonBytes, parquetBytes, arrowIpcBytes);
        }
        List<CandidateScore> candidates = new ArrayList<>();
        candidates.add(new CandidateScore(estimatedE2eLatencySeconds(jsonBytes, "json"), 0, FormatName.JSON));
        candidates.add(new CandidateScore(
                estimatedE2eLatencySeconds(parquetBytes, "parquet_blob"), 1, FormatName.PARQUET_BLOB));
        if (arrowIpcBytes != null) {
            candidates.add(new CandidateScore(
                    estimatedE2eLatencySeconds(arrowIpcBytes, "arrow_ipc_blob"), 2, FormatName.ARROW_IPC_BLOB));
        }
        return candidates.stream()
                .min(Comparator.comparingDouble(CandidateScore::score).thenComparingInt(CandidateScore::tie))
                .map(CandidateScore::format)
                .orElse(FormatName.JSON);
    }

    private double getNetworkMbps() {
        return Math.max(0.0, Env.getDouble("FORMAT_LATENCY_NETWORK_MBPS", 0.0));
    }

    private Map<String, Double> loadCalibrationDecodeNs() {
        String pathStr = Env.get("FORMAT_LATENCY_CALIBRATION_JSON");
        if (pathStr.isEmpty()) {
            return Map.of();
        }
        Path path = Path.of(pathStr);
        if (!Files.isRegularFile(path)) {
            return Map.of();
        }
        try {
            Map<String, Object> data = objectMapper.readValue(path.toFile(), new TypeReference<>() {
            });
            Object raw = data.get("decode_ns_per_byte");
            if (!(raw instanceof Map<?, ?> rawMap)) {
                return Map.of();
            }
            Map<String, Double> out = new HashMap<>();
            for (Map.Entry<?, ?> entry : rawMap.entrySet()) {
                try {
                    out.put(String.valueOf(entry.getKey()), Double.parseDouble(String.valueOf(entry.getValue())));
                } catch (NumberFormatException ignored) {
                    // skip invalid entries
                }
            }
            return out;
        } catch (IOException e) {
            return Map.of();
        }
    }

    private double decodeNsPerByte(String fmt) {
        Map<String, Double> cal = loadCalibrationDecodeNs();
        if (cal.containsKey(fmt)) {
            return cal.get(fmt);
        }
        String envKey = "FORMAT_LATENCY_DECODE_NS_PER_BYTE_" + fmt.toUpperCase();
        String raw = Env.get(envKey);
        if (!raw.isEmpty()) {
            try {
                return Math.max(0.0, Double.parseDouble(raw));
            } catch (NumberFormatException ignored) {
                // fall through
            }
        }
        return DEFAULT_DECODE_NS.getOrDefault(fmt, 1.0);
    }

    private double estimatedE2eLatencySeconds(int blobBytes, String fmt) {
        double decodeS = blobBytes * decodeNsPerByte(fmt) / 1e9;
        double mbps = getNetworkMbps();
        if (mbps <= 0.0) {
            return decodeS;
        }
        double transferS = (blobBytes * 8.0) / (mbps * 1_000_000.0);
        return transferS + decodeS;
    }

    private double transferSeconds(int numBytes) {
        double mbps = getNetworkMbps();
        if (mbps <= 0.0) {
            return numBytes;
        }
        return (numBytes * 8.0) / (mbps * 1_000_000.0);
    }

    private static int toInt(Object value) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        return Integer.parseInt(String.valueOf(value));
    }

    private record CandidateScore(double score, int tie, FormatName format) {
    }
}
