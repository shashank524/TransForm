package com.multimodal.mcp.format;

/**
 * What we optimize for when choosing format (AdaEdge: workload/target).
 */
public enum OptimizationTarget {
    MIN_BYTES("min_bytes"),
    MIN_LATENCY("min_latency"),
    MIN_TIME_TO_FIRST_ROWS("min_time_to_first_rows");

    private final String value;

    OptimizationTarget(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }

    public static OptimizationTarget fromString(String raw) {
        if (raw == null || raw.isBlank()) {
            return MIN_LATENCY;
        }
        String normalized = raw.strip().toLowerCase();
        for (OptimizationTarget target : values()) {
            if (target.value.equals(normalized)) {
                return target;
            }
        }
        return MIN_LATENCY;
    }
}
