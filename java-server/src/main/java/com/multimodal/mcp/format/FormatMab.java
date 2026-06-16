package com.multimodal.mcp.format;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.concurrent.ThreadLocalRandom;

import org.springframework.stereotype.Component;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.multimodal.mcp.util.Env;

/**
 * Multi-armed bandit (MAB) for format selection: reward estimates, epsilon-greedy selection,
 * outcome recording, and persistence.
 */
@Component
public class FormatMab {

    public static final Path DEFAULT_HISTORY_PATH = Path.of("results/format_selection_history.jsonl");
    public static final Path DEFAULT_MAB_STATE_PATH = Path.of("results/format_mab_state.json");

    public static final List<FormatName> FORMATS = List.of(
            FormatName.JSON,
            FormatName.PARQUET_BLOB,
            FormatName.PARQUET_STREAM,
            FormatName.ARROW_IPC_BLOB,
            FormatName.ARROW_IPC_STREAM,
            FormatName.TEXT_INLINE,
            FormatName.RAW_BLOB,
            FormatName.GZIP_BLOB
    );

    private final FormatSelector formatSelector;
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final Random random = ThreadLocalRandom.current();

    public FormatMab(FormatSelector formatSelector) {
        this.formatSelector = formatSelector;
    }

    public double rewardFromOutcome(Map<String, Object> outcome, OptimizationTarget target) {
        if (target == OptimizationTarget.MIN_BYTES) {
            Object bytes = outcome.get("bytes");
            if (bytes == null) {
                return 0.0;
            }
            return -toDouble(bytes);
        }
        if (target == OptimizationTarget.MIN_LATENCY) {
            Object latency = outcome.get("latency_s");
            if (latency == null) {
                return 0.0;
            }
            return -toDouble(latency);
        }
        if (target == OptimizationTarget.MIN_TIME_TO_FIRST_ROWS) {
            Object ttfr = outcome.get("time_to_first_rows_s");
            if (ttfr != null) {
                return -toDouble(ttfr);
            }
            Object latency = outcome.get("latency_s");
            if (latency != null) {
                return -toDouble(latency);
            }
            return 0.0;
        }
        return 0.0;
    }

    public Map<String, Map<String, Map<String, Double>>> loadMabState(Path path) {
        Path resolved = path != null ? path : defaultMabStatePath();
        if (!Files.isRegularFile(resolved)) {
            return new HashMap<>();
        }
        try {
            Map<String, Object> data = objectMapper.readValue(resolved.toFile(), new TypeReference<>() {
            });
            if (data == null) {
                return new HashMap<>();
            }
            Map<String, Map<String, Map<String, Double>>> out = new HashMap<>();
            for (Map.Entry<String, Object> targetEntry : data.entrySet()) {
                if (!(targetEntry.getValue() instanceof Map<?, ?> formatsDict)) {
                    continue;
                }
                Map<String, Map<String, Double>> formats = new HashMap<>();
                for (Map.Entry<?, ?> fmtEntry : formatsDict.entrySet()) {
                    if (fmtEntry.getValue() instanceof Map<?, ?> statsMap) {
                        Object sumReward = statsMap.get("sum_reward");
                        Object count = statsMap.get("count");
                        if (sumReward != null && count != null) {
                            Map<String, Double> stats = new HashMap<>();
                            stats.put("sum_reward", toDouble(sumReward));
                            stats.put("count", toDouble(count));
                            formats.put(String.valueOf(fmtEntry.getKey()), stats);
                        }
                    }
                }
                out.put(targetEntry.getKey(), formats);
            }
            return out;
        } catch (IOException e) {
            return new HashMap<>();
        }
    }

    public void saveMabState(Map<String, Map<String, Map<String, Double>>> state, Path path) throws IOException {
        Path resolved = path != null ? path : defaultMabStatePath();
        Files.createDirectories(resolved.getParent());
        objectMapper.writerWithDefaultPrettyPrinter().writeValue(resolved.toFile(), state);
    }

    public FormatName selectFormatWithMab(
            SelectionContext context,
            Map<String, Object> hints,
            Map<String, Map<String, Map<String, Double>>> mabState,
            Double epsilon) {
        if (mabState == null) {
            return hints != null
                    ? formatSelector.selectFormatWithHints(context, hints)
                    : formatSelector.selectFormat(context);
        }

        String targetVal = context.getTarget().value();
        Map<String, Map<String, Double>> stateForTarget = mabState.get(targetVal);
        if (stateForTarget == null || stateForTarget.isEmpty()) {
            return hints != null
                    ? formatSelector.selectFormatWithHints(context, hints)
                    : formatSelector.selectFormat(context);
        }

        boolean hasAny = FORMATS.stream()
                .anyMatch(fmt -> {
                    Map<String, Double> stats = stateForTarget.get(fmt.value());
                    return stats != null && stats.getOrDefault("count", 0.0) > 0;
                });
        if (!hasAny) {
            return hints != null
                    ? formatSelector.selectFormatWithHints(context, hints)
                    : formatSelector.selectFormat(context);
        }

        double eps = epsilon != null ? epsilon : Env.getDouble("FORMAT_SELECT_EPSILON", 0.1);
        if (random.nextDouble() < eps) {
            return FORMATS.get(random.nextInt(FORMATS.size()));
        }

        FormatName bestFormat = null;
        double bestQ = Double.NEGATIVE_INFINITY;
        for (FormatName fmt : FORMATS) {
            Map<String, Double> stats = stateForTarget.get(fmt.value());
            if (stats == null) {
                continue;
            }
            double count = stats.getOrDefault("count", 0.0);
            if (count <= 0) {
                continue;
            }
            double q = stats.getOrDefault("sum_reward", 0.0) / count;
            if (q > bestQ) {
                bestQ = q;
                bestFormat = fmt;
            }
        }

        if (bestFormat != null) {
            return bestFormat;
        }
        return hints != null
                ? formatSelector.selectFormatWithHints(context, hints)
                : formatSelector.selectFormat(context);
    }

    public void recordOutcome(
            SelectionContext context,
            FormatName formatUsed,
            Map<String, Object> outcome,
            Map<String, Map<String, Map<String, Double>>> mabState,
            Path historyPath) throws IOException {
        Map<String, Object> record = new HashMap<>();
        record.put("n_rows", context.getNRows());
        record.put("n_cols", context.getNCols());
        record.put("target", context.getTarget().value());
        record.put("format", formatUsed.value());
        record.put("bytes", outcome.get("bytes"));
        record.put("latency_s", outcome.get("latency_s"));
        record.put("time_to_first_rows_s", outcome.get("time_to_first_rows_s"));

        Path resolvedHistory = historyPath != null ? historyPath : DEFAULT_HISTORY_PATH;
        Files.createDirectories(resolvedHistory.getParent());
        Files.writeString(resolvedHistory, objectMapper.writeValueAsString(record) + System.lineSeparator(),
                java.nio.file.StandardOpenOption.CREATE, java.nio.file.StandardOpenOption.APPEND);

        if (mabState != null) {
            double reward = rewardFromOutcome(outcome, context.getTarget());
            String targetVal = context.getTarget().value();
            mabState.computeIfAbsent(targetVal, k -> new HashMap<>());
            Map<String, Map<String, Double>> targetState = mabState.get(targetVal);
            targetState.computeIfAbsent(formatUsed.value(), k -> {
                Map<String, Double> stats = new HashMap<>();
                stats.put("sum_reward", 0.0);
                stats.put("count", 0.0);
                return stats;
            });
            Map<String, Double> stats = targetState.get(formatUsed.value());
            stats.put("sum_reward", stats.get("sum_reward") + reward);
            stats.put("count", stats.get("count") + 1.0);
        }
    }

    public boolean mabEnabled() {
        return Env.isTruthy("FORMAT_SELECT_MAB");
    }

    public Path defaultMabStatePath() {
        return Env.getPath("FORMAT_MAB_STATE_PATH", DEFAULT_MAB_STATE_PATH.toString());
    }

    private static double toDouble(Object value) {
        if (value instanceof Number number) {
            return number.doubleValue();
        }
        return Double.parseDouble(String.valueOf(value));
    }
}
