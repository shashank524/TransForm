package com.multimodal.mcp.tabular;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.stereotype.Component;

import com.multimodal.mcp.core.ResultConfig;
import com.multimodal.mcp.core.RuntimeState;
import com.multimodal.mcp.util.Env;

/**
 * Bounded LRU payload cache for materialized result_ids (Round-2 F7 from tabular.py).
 */
@Component
public class PayloadCache {

    private final RuntimeState runtimeState;
    private final LinkedHashMap<String, Integer> lru = new LinkedHashMap<>(16, 0.75f, true);
    private long totalBytes = 0;

    public PayloadCache(RuntimeState runtimeState) {
        this.runtimeState = runtimeState;
    }

    public void record(String resultId, long approxBytes) {
        Integer prev = lru.remove(resultId);
        if (prev != null) {
            totalBytes -= prev;
        }
        int size = (int) Math.min(Integer.MAX_VALUE, approxBytes);
        lru.put(resultId, size);
        totalBytes += size;
        enforceCap(resultId);
    }

    public void touch(String resultId) {
        if (lru.containsKey(resultId)) {
            lru.get(resultId);
        }
    }

    public void clearEntry(String resultId) {
        Integer prev = lru.remove(resultId);
        if (prev != null) {
            totalBytes -= prev;
        }
        if (totalBytes < 0) {
            totalBytes = 0;
        }
        ResultConfig cfg = runtimeState.getResultRegistry().get(resultId);
        if (cfg != null) {
            if (cfg.getCachedArrowTable() != null) {
                cfg.getCachedArrowTable().close();
            }
            cfg.setCachedDataframe(null);
            cfg.setCachedArrowTable(null);
            cfg.setCachedJsonRecords(null);
            cfg.setCachedParquetBlobBytes(null);
            cfg.setCachedArrowIpcBlobBytes(null);
            cfg.setCachedParquetCodec(null);
            cfg.setCachedArrowIpcCodec(null);
        }
    }

    public long approxPayloadBytes(
            TabularData df,
            byte[] parquetBytes,
            byte[] ipcBytes,
            java.util.List<Map<String, Object>> jsonRecords) {
        long n = 0;
        if (df != null) {
            n += df.estimateMemoryBytes();
        }
        if (parquetBytes != null) {
            n += parquetBytes.length;
        }
        if (ipcBytes != null) {
            n += ipcBytes.length;
        }
        if (jsonRecords != null && !jsonRecords.isEmpty()) {
            int cols = jsonRecords.get(0).size();
            n += (long) jsonRecords.size() * cols * 64L;
        }
        return n;
    }

    private void enforceCap(String currentResultId) {
        long cap = resultCacheMaxBytes();
        if (cap <= 0) {
            return;
        }
        while (totalBytes > cap && !lru.isEmpty()) {
            Map.Entry<String, Integer> oldest = lru.entrySet().iterator().next();
            if (oldest.getKey().equals(currentResultId)) {
                break;
            }
            clearEntry(oldest.getKey());
        }
    }

    public static long resultCacheMaxBytes() {
        String raw = Env.get("RESULT_CACHE_MAX_BYTES");
        if (!raw.isEmpty()) {
            try {
                return Math.max(0, Long.parseLong(raw));
            } catch (NumberFormatException ignored) {
                // fall through
            }
        }
        return 64L * 1024 * 1024;
    }
}
