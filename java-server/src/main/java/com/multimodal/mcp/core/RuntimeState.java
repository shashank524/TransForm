package com.multimodal.mcp.core;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.function.BiFunction;

import org.springframework.stereotype.Component;

import com.multimodal.mcp.hints.HintStore;
import com.multimodal.mcp.util.Env;

/**
 * Singleton runtime state mirroring Python {@code server/core/runtime.py}.
 */
@Component
public class RuntimeState {

    public static final Set<String> ALLOWED_MIME_TYPES = Set.of(
            "image/jpeg",
            "image/png",
            "image/gif",
            "image/webp",
            "audio/wav",
            "audio/mp3",
            "video/mp4",
            "application/pdf"
    );

    public static final int MAX_MATERIALIZED_ROWS = 1_000_000;
    public static final int MAX_JSON_CELLS = 5_000_000;
    public static final int MAX_INLINE_TEXT_BYTES = 256 * 1024;
    public static final int MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024;
    public static final int HINTS_CACHE_MAX = 512;

    private final Path root;
    private final Path materializedDir;
    private final Path materializedRawDir;
    private final Path serverMabStatePath;
    private final HintStore hintStore;

    private final Map<String, ResultConfig> resultRegistry = new HashMap<>();
    private final Map<String, Map<String, Object>> validatedFiles = new HashMap<>();
    private final Map<String, String> activeSessions = new HashMap<>();
    private final LinkedHashMap<String, Map<String, Object>> hintsCacheByKeyJson = new LinkedHashMap<>();

    public RuntimeState(HintStore hintStore) {
        this.hintStore = hintStore;
        this.root = resolveRoot();
        this.materializedDir = root.resolve("data/materialized");
        this.materializedRawDir = root.resolve("data/materialized_raw");
        this.serverMabStatePath = Env.getPath("FORMAT_MAB_STATE_PATH", "results/format_mab_state.json");
    }

    public Path getRoot() {
        return root;
    }

    public Path getMaterializedDir() {
        return materializedDir;
    }

    public Path getMaterializedRawDir() {
        return materializedRawDir;
    }

    public Path getServerMabStatePath() {
        return serverMabStatePath;
    }

    public HintStore getHintStore() {
        return hintStore;
    }

    public Map<String, ResultConfig> getResultRegistry() {
        return resultRegistry;
    }

    public Map<String, Map<String, Object>> getValidatedFiles() {
        return validatedFiles;
    }

    public Map<String, String> getActiveSessions() {
        return activeSessions;
    }

    public Map<String, Object> hintsCacheGet(String keyJson) {
        return hintsCacheByKeyJson.get(keyJson);
    }

    public void hintsCachePut(String keyJson, Map<String, Object> hints) {
        if (hintsCacheByKeyJson.containsKey(keyJson)) {
            hintsCacheByKeyJson.put(keyJson, hints);
            return;
        }
        if (hintsCacheByKeyJson.size() >= HINTS_CACHE_MAX) {
            String firstKey = hintsCacheByKeyJson.keySet().iterator().next();
            hintsCacheByKeyJson.remove(firstKey);
        }
        hintsCacheByKeyJson.put(keyJson, hints);
    }

    public boolean hintsDbDisabled() {
        return Env.isTruthy("FORMAT_HINTS_DB_DISABLE");
    }

    public Integer jsonCellsCap() {
        if (Env.isTruthy("DISABLE_JSON_CAP")) {
            return null;
        }
        Integer override = Env.getOptionalPositiveInt("MAX_JSON_CELLS_OVERRIDE");
        if (override != null) {
            return override;
        }
        return MAX_JSON_CELLS;
    }

    public Map<String, Object> validateFileLocally(
            String filePath,
            String expectedType,
            BiFunction<Path, byte[], String> detectMimeType) {
        Path path = Path.of(filePath);
        if (!Files.isRegularFile(path)) {
            return Map.of("valid", false, "error", "File not found: " + filePath);
        }

        long size;
        try {
            size = Files.size(path);
        } catch (IOException e) {
            return Map.of("valid", false, "error", "Unable to read file size: " + filePath);
        }

        if (size > MAX_FILE_SIZE_BYTES) {
            return Map.of(
                    "valid", false,
                    "error", "File size " + size + " exceeds limit " + MAX_FILE_SIZE_BYTES);
        }

        byte[] header;
        try {
            header = readFileHeader(path, 2048);
        } catch (IOException e) {
            return Map.of("valid", false, "error", "Unable to read file header: " + filePath);
        }

        String detectedMime = detectMimeType.apply(path, header);
        if (!ALLOWED_MIME_TYPES.contains(detectedMime)) {
            return Map.of("valid", false, "error", "MIME type " + detectedMime + " not allowed");
        }

        if (expectedType != null && !expectedType.isBlank() && !expectedType.equals(detectedMime)) {
            return Map.of(
                    "valid", false,
                    "error", "MIME type mismatch: expected " + expectedType + ", got " + detectedMime);
        }

        String fileHash = calculateFileHash(path);
        Map<String, Object> result = new HashMap<>();
        result.put("valid", true);
        result.put("details", "Type: " + detectedMime + ", Size: " + size + ", Hash: " + fileHash.substring(0, 16));
        result.put("mime", detectedMime);
        result.put("size", size);
        result.put("hash", fileHash);
        result.put("file_path", path.toString());
        return result;
    }

    public static String detectMimeTypeFallback(Path path, byte[] header) {
        try {
            String guessed = Files.probeContentType(path);
            if (guessed != null && !guessed.isBlank()) {
                return guessed;
            }
        } catch (IOException ignored) {
            // fall through
        }
        return "application/octet-stream";
    }

    private static Path resolveRoot() {
        Path cwd = Path.of(System.getProperty("user.dir")).toAbsolutePath().normalize();
        if (cwd.getFileName() != null && "java-server".equals(cwd.getFileName().toString())) {
            Path parent = cwd.getParent();
            if (parent != null) {
                return parent;
            }
        }
        return cwd;
    }

    private static byte[] readFileHeader(Path path, int numBytes) throws IOException {
        try (InputStream in = Files.newInputStream(path)) {
            return in.readNBytes(numBytes);
        }
    }

    private static String calculateFileHash(Path path) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            try (InputStream in = Files.newInputStream(path)) {
                byte[] buffer = new byte[8192];
                int read;
                while ((read = in.read(buffer)) != -1) {
                    digest.update(buffer, 0, read);
                }
            }
            byte[] hash = digest.digest();
            StringBuilder sb = new StringBuilder(hash.length * 2);
            for (byte b : hash) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (NoSuchAlgorithmException | IOException e) {
            throw new IllegalStateException("Failed to hash file: " + path, e);
        }
    }
}
