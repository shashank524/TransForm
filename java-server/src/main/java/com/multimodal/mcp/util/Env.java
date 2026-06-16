package com.multimodal.mcp.util;

import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Locale;
import java.util.Set;

/**
 * Environment variable helpers matching Python {@code os.environ} usage patterns.
 */
public final class Env {

    private static final Set<String> TRUTHY = Set.of("1", "true", "yes", "y");

    private Env() {
    }

    public static String get(String name, String defaultValue) {
        String raw = System.getenv(name);
        if (raw == null) {
            return defaultValue;
        }
        String trimmed = raw.strip();
        return trimmed.isEmpty() ? defaultValue : trimmed;
    }

    public static String get(String name) {
        return get(name, "");
    }

    public static boolean isTruthy(String name) {
        return TRUTHY.contains(get(name).toLowerCase(Locale.ROOT));
    }

    public static boolean isTruthy(String name, Set<String> truthyValues) {
        return truthyValues.contains(get(name).toLowerCase(Locale.ROOT));
    }

    public static int getInt(String name, int defaultValue) {
        String raw = get(name);
        if (raw.isEmpty()) {
            return defaultValue;
        }
        try {
            return Integer.parseInt(raw);
        } catch (NumberFormatException e) {
            return defaultValue;
        }
    }

    public static Integer getOptionalPositiveInt(String name) {
        String raw = get(name);
        if (raw.isEmpty()) {
            return null;
        }
        try {
            int value = Integer.parseInt(raw);
            return value > 0 ? value : null;
        } catch (NumberFormatException e) {
            return null;
        }
    }

    public static long getLong(String name, long defaultValue) {
        String raw = get(name);
        if (raw.isEmpty()) {
            return defaultValue;
        }
        try {
            return Long.parseLong(raw);
        } catch (NumberFormatException e) {
            return defaultValue;
        }
    }

    public static double getDouble(String name, double defaultValue) {
        String raw = get(name);
        if (raw.isEmpty()) {
            return defaultValue;
        }
        try {
            return Double.parseDouble(raw);
        } catch (NumberFormatException e) {
            return defaultValue;
        }
    }

    public static Path getPath(String name, String defaultValue) {
        return Paths.get(get(name, defaultValue));
    }
}
