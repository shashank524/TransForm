package com.multimodal.mcp.tabular;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.channels.Channels;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.FileTime;
import java.util.concurrent.TimeUnit;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.apache.arrow.dataset.file.DatasetFileWriter;
import org.apache.arrow.dataset.file.FileFormat;
import org.apache.arrow.dataset.file.FileSystemDatasetFactory;
import org.apache.arrow.dataset.jni.NativeMemoryPool;
import org.apache.arrow.dataset.scanner.ScanOptions;
import org.apache.arrow.dataset.scanner.Scanner;
import org.apache.arrow.dataset.source.Dataset;
import org.apache.arrow.dataset.source.DatasetFactory;
import org.apache.arrow.memory.BufferAllocator;
import org.apache.arrow.memory.RootAllocator;
import org.apache.arrow.vector.BigIntVector;
import org.apache.arrow.vector.BitVector;
import org.apache.arrow.vector.FieldVector;
import org.apache.arrow.vector.Float8Vector;
import org.apache.arrow.vector.IntVector;
import org.apache.arrow.vector.VarCharVector;
import org.apache.arrow.vector.VectorSchemaRoot;
import org.apache.arrow.vector.dictionary.DictionaryProvider;
import org.apache.arrow.vector.ipc.ArrowFileWriter;
import org.apache.arrow.vector.ipc.ArrowReader;
import org.apache.arrow.vector.types.pojo.ArrowType;
import org.apache.arrow.vector.types.pojo.Field;
import org.apache.arrow.vector.types.pojo.FieldType;
import org.apache.arrow.vector.types.pojo.Schema;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.multimodal.mcp.codec.CodecSelector;
import com.multimodal.mcp.core.ResultConfig;
import com.multimodal.mcp.core.RuntimeState;
import com.multimodal.mcp.format.FormatSelector;
import com.multimodal.mcp.hints.HintStore;
import com.multimodal.mcp.util.Env;

/**
 * Tabular data generation, resolution, encoding, hints, and caching.
 * Port of Python {@code server/core/tabular.py}.
 */
@Service
public class TabularService {

    public static final int SMALL_PAYLOAD_CELLS = 4096;
    public static final int JSON_OBVIOUS_WINNER_BYTES_DEFAULT = 4096;

    private static final int JSON_INT_VALUE_WIDTH = 12;
    private static final int JSON_FLOAT_VALUE_WIDTH = 22;
    private static final int JSON_BOOL_VALUE_WIDTH = 5;
    private static final int JSON_DATETIME_VALUE_WIDTH = 30;
    private static final int JSON_DEFAULT_VALUE_WIDTH = 32;

    private static final Set<String> VALID_COMPRESSIONS =
            Set.of("snappy", "gzip", "zstd", "brotli", "lz4", "none");
    private static final Set<String> VALID_ENCODING_STRATEGIES = Set.of("default", "data_driven");
    private static final Set<String> VALID_ARROW_IPC_COMPRESSIONS = Set.of("none", "lz4", "zstd");

    private final RuntimeState runtimeState;
    private final PayloadCache payloadCache;
    private final CodecSelector codecSelector;
    private final FormatSelector formatSelector;
    private final HintStore hintStore;
    private final ObjectMapper objectMapper = new ObjectMapper();
    private final BufferAllocator allocator = new RootAllocator(Long.MAX_VALUE);

    private TabularData tpcdsBaseTable;
    private final String tpcdsParquetPath = Env.get("TPCDS_PARQUET_PATH");

    private final LruCache<ParquetCacheKey, byte[]> parquetBlobCache = new LruCache<>(128);
    private final LruCache<ParquetChunkKey, byte[]> parquetChunkCache = new LruCache<>(1024);
    private final LruCache<IpcCacheKey, byte[]> arrowIpcBlobCache = new LruCache<>(128);
    private final LruCache<IpcChunkKey, byte[]> arrowIpcChunkCache = new LruCache<>(1024);
    private final LruCache<ShapeKey, Integer> jsonByteSizeCache = new LruCache<>(128);

    public TabularService(
            RuntimeState runtimeState,
            PayloadCache payloadCache,
            CodecSelector codecSelector,
            FormatSelector formatSelector,
            HintStore hintStore) {
        this.runtimeState = runtimeState;
        this.payloadCache = payloadCache;
        this.codecSelector = codecSelector;
        this.formatSelector = formatSelector;
        this.hintStore = hintStore;
    }

    public TabularData generateDataframe(int nRows, int nCols, int offset) {
        if (tpcdsParquetPath != null && !tpcdsParquetPath.isBlank()) {
            TabularData base = loadTpcdsBaseTable();
            int start = Math.max(offset, 0);
            int stop = Math.min(start + nRows, base.numRows());
            TabularData sliced = start >= base.numRows() ? TabularData.empty() : base.slice(start, stop - start);
            if (nCols > 0 && sliced.numCols() > nCols) {
                List<String> cols = sliced.getColumnNames().subList(0, nCols);
                List<Map<String, Object>> rows = new ArrayList<>();
                for (Map<String, Object> row : sliced.getRows()) {
                    Map<String, Object> trimmed = new LinkedHashMap<>();
                    for (String col : cols) {
                        trimmed.put(col, row.get(col));
                    }
                    rows.add(trimmed);
                }
                return new TabularData(cols, rows);
            }
            return sliced;
        }

        List<String> columns = new ArrayList<>();
        columns.add("row_id");
        for (int j = 0; j < nCols; j++) {
            columns.add("col_" + j);
        }
        List<Map<String, Object>> rows = new ArrayList<>(nRows);
        for (int i = 0; i < nRows; i++) {
            long index = (long) offset + i;
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("row_id", index);
            for (int j = 0; j < nCols; j++) {
                row.put("col_" + j, index * (j + 1L) + j);
            }
            rows.add(row);
        }
        return new TabularData(columns, rows);
    }

    public TabularData loadMaterializedDataframe(Path path, int offset, Integer limit) throws IOException {
        TabularData full = ArrowParquetSupport.readParquet(path, allocator);
        return full.slice(offset, limit);
    }

    public TabularData resolveDataframe(ResultConfig config, int offset, Integer limit) throws IOException {
        if (config.getCachedDataframe() != null) {
            return config.getCachedDataframe().slice(offset, limit);
        }
        if (config.getMaterializedPath() != null) {
            return loadMaterializedDataframe(config.getMaterializedPath(), offset, limit);
        }
        int n = limit != null ? limit : config.getNRows();
        return generateDataframe(n, config.getNCols(), offset);
    }

    public VectorSchemaRoot resolveArrowTable(ResultConfig config) throws IOException {
        if (config.getCachedArrowTable() != null) {
            return config.getCachedArrowTable();
        }
        TabularData df = resolveDataframe(config, 0, null);
        return ArrowParquetSupport.toArrowTable(df, allocator);
    }

    public byte[] encodeParquet(VectorSchemaRoot table, String compression, String encodingStrategy)
            throws IOException {
        if ("data_driven".equals(encodingStrategy)) {
            // CodecDB-inspired params inform hint metadata; Parquet bytes use Arrow Dataset writer.
            codecSelector.selectEncodingParams(table);
        }
        return ArrowParquetSupport.writeParquet(table, allocator);
    }

    public byte[] encodeArrowIpcFile(VectorSchemaRoot table, String ipcCompression) throws IOException {
        return ArrowParquetSupport.writeArrowIpc(table, ipcCompression);
    }

    public void populateMaterializedCaches(
            ResultConfig cfg,
            String resultId,
            TabularData df,
            VectorSchemaRoot table,
            byte[] parquetBytes,
            int rowsPerChunk) throws IOException {
        String defaultComp = getDefaultCompression();
        String defaultEncStrat = getDefaultEncodingStrategy();
        String defaultIpcComp = getDefaultArrowIpcCompression();

        VectorSchemaRoot resolvedTable = table;
        if (resolvedTable == null) {
            try {
                resolvedTable = ArrowParquetSupport.toArrowTable(df, allocator);
            } catch (Exception ignored) {
                resolvedTable = null;
            }
        }

        cfg.setCachedDataframe(df);
        cfg.setCachedArrowTable(resolvedTable);

        try {
            Map<String, Object> hints = computeTabularSizeHintsFromDf(
                    df, rowsPerChunk, defaultComp, defaultEncStrat, defaultIpcComp, resolvedTable);
            Map<String, Object> cachedHints = new HashMap<>();
            cachedHints.put("rows_per_chunk", rowsPerChunk);
            cachedHints.put("parquet_compression", defaultComp);
            cachedHints.put("parquet_encoding_strategy", defaultEncStrat);
            cachedHints.put("arrow_ipc_compression", defaultIpcComp);
            cachedHints.put("hints", hints);
            cfg.setCachedHints(cachedHints);
        } catch (Exception e) {
            cfg.setCachedHints(null);
        }

        try {
            int cells = df.numRows() * df.numCols();
            if (cells <= SMALL_PAYLOAD_CELLS) {
                List<Map<String, Object>> records = df.toRecords();
                cfg.setCachedJsonRecords(records);
                try {
                    cfg.setCachedJsonBytes(objectMapper.writeValueAsBytes(records).length);
                } catch (Exception e) {
                    cfg.setCachedJsonBytes(null);
                }
            }
        } catch (Exception e) {
            cfg.setCachedJsonRecords(null);
        }

        try {
            if (parquetBytes != null) {
                cfg.setCachedParquetBlobBytes(parquetBytes);
                cfg.setCachedParquetCodec(new ResultConfig.ParquetCodec(defaultComp, defaultEncStrat));
            } else if (resolvedTable != null) {
                byte[] enc = encodeParquet(resolvedTable, defaultComp, defaultEncStrat);
                cfg.setCachedParquetBlobBytes(enc);
                cfg.setCachedParquetCodec(new ResultConfig.ParquetCodec(defaultComp, defaultEncStrat));
            }
        } catch (Exception e) {
            cfg.setCachedParquetBlobBytes(null);
            cfg.setCachedParquetCodec(null);
        }

        try {
            if (resolvedTable != null) {
                byte[] ipc = encodeArrowIpcFile(resolvedTable, defaultIpcComp);
                cfg.setCachedArrowIpcBlobBytes(ipc);
                cfg.setCachedArrowIpcCodec(defaultIpcComp);
            }
        } catch (Exception e) {
            cfg.setCachedArrowIpcBlobBytes(null);
            cfg.setCachedArrowIpcCodec(null);
        }

        long approx = payloadCache.approxPayloadBytes(
                cfg.getCachedDataframe(),
                cfg.getCachedParquetBlobBytes(),
                cfg.getCachedArrowIpcBlobBytes(),
                cfg.getCachedJsonRecords());
        payloadCache.record(resultId, approx);
    }

    public Map<String, Object> getTabularSizeHintsCached(
            int nRows,
            int nCols,
            int rowsPerChunk,
            String resultId,
            String comp,
            String encStrat,
            String ipcComp) throws IOException {
        if (resultId != null) {
            ResultConfig cfg = runtimeState.getResultRegistry().get(resultId);
            int resolvedNRows = cfg != null ? cfg.getNRows() : nRows;
            if (cfg != null && cachedHintsMatch(cfg.getCachedHints(), rowsPerChunk, comp, encStrat, ipcComp, resolvedNRows)) {
                @SuppressWarnings("unchecked")
                Map<String, Object> hints = (Map<String, Object>) cfg.getCachedHints().get("hints");
                return hints;
            }
            Map<String, Object> computed = computeTabularSizeHints(
                    nRows, nCols, rowsPerChunk, resultId, comp, encStrat, ipcComp);
            if (cfg != null && cfg.getCachedHints() == null) {
                Map<String, Object> cachedHints = new HashMap<>();
                cachedHints.put("rows_per_chunk", rowsPerChunk);
                cachedHints.put("parquet_compression", comp);
                cachedHints.put("parquet_encoding_strategy", encStrat);
                cachedHints.put("arrow_ipc_compression", ipcComp);
                cachedHints.put("hints", computed);
                cfg.setCachedHints(cachedHints);
            }
            return computed;
        }

        Map<String, Object> key = tabularHintsKey(
                "tabular", nRows, nCols, rowsPerChunk, comp, encStrat, ipcComp, null, null);
        String keyJson = hintStore.stableKeyJson(key);
        Map<String, Object> cached = runtimeState.hintsCacheGet(keyJson);
        if (cached != null) {
            return cached;
        }

        if (!runtimeState.hintsDbDisabled()) {
            Map<String, Object> stored = hintStore.get(key);
            if (stored != null) {
                runtimeState.hintsCachePut(keyJson, stored);
                return stored;
            }
        }

        Map<String, Object> computed = computeTabularSizeHints(
                nRows, nCols, rowsPerChunk, null, comp, encStrat, ipcComp);
        runtimeState.hintsCachePut(keyJson, computed);
        if (!runtimeState.hintsDbDisabled()) {
            hintStore.upsert(key, computed);
        }
        return computed;
    }

    public Map<String, Object> computeTabularSizeHints(
            int nRows,
            int nCols,
            int rowsPerChunk,
            String resultId,
            String comp,
            String encStrat,
            String ipcComp) throws IOException {
        if (resultId != null) {
            ResultConfig config = runtimeState.getResultRegistry().get(resultId);
            if (config == null) {
                throw new IllegalArgumentException("Unknown result_id: " + resultId);
            }
            TabularData df = resolveDataframe(config, 0, null);
            return computeTabularSizeHintsFromDf(df, rowsPerChunk, comp, encStrat, ipcComp, null);
        }

        int jsonBytes = getJsonByteSize(nRows, nCols);
        if (formatHintsSkipLargeForSmall() && jsonBytes <= jsonObviousWinnerBytes()) {
            long sentinel = Math.max(jsonBytes * 64L, 1L << 30);
            return smallPayloadHints(nRows, nCols, jsonBytes, sentinel);
        }

        byte[] parquetBytes = getParquetBlobBytes(nRows, nCols, comp, encStrat);
        byte[] arrowIpcBytes = getArrowIpcBlobBytes(nRows, nCols, ipcComp);
        int firstChunkRows = Math.min(rowsPerChunk, nRows);
        byte[] parquetChunk = getParquetChunkBytes(nRows, nCols, 0, firstChunkRows, comp, encStrat);
        byte[] arrowChunk = getArrowIpcChunkBytes(nRows, nCols, 0, firstChunkRows, ipcComp);
        return fullPayloadHints(nRows, nCols, jsonBytes, parquetBytes, arrowIpcBytes, parquetChunk, arrowChunk);
    }

    public Map<String, Object> computeTabularSizeHintsFromDf(
            TabularData df,
            int rowsPerChunk,
            String comp,
            String encStrat,
            String ipcComp,
            VectorSchemaRoot table) throws IOException {
        int nRows = df.numRows();
        int nCols = df.numCols();
        int jsonBytes = measureJsonBytesFromDf(df);

        if (formatHintsSkipLargeForSmall() && jsonBytes <= jsonObviousWinnerBytes()) {
            long sentinel = Math.max(jsonBytes * 64L, 1L << 30);
            return smallPayloadHints(nRows, nCols, jsonBytes, sentinel);
        }

        VectorSchemaRoot resolvedTable = table;
        if (resolvedTable == null) {
            resolvedTable = ArrowParquetSupport.toArrowTable(df, allocator);
        }
        byte[] parquetBytes = encodeParquet(resolvedTable, comp, encStrat);
        byte[] arrowIpcBytes = encodeArrowIpcFile(resolvedTable, ipcComp);
        int firstChunkRows = Math.min(rowsPerChunk, nRows);
        byte[] parquetChunk;
        byte[] arrowChunk;
        if (firstChunkRows > 0) {
            VectorSchemaRoot chunk = ArrowParquetSupport.slice(resolvedTable, 0, firstChunkRows, allocator);
            try {
                parquetChunk = encodeParquet(chunk, comp, encStrat);
                arrowChunk = encodeArrowIpcFile(chunk, ipcComp);
            } finally {
                chunk.close();
            }
        } else {
            parquetChunk = new byte[0];
            arrowChunk = new byte[0];
        }
        return fullPayloadHints(
                nRows, nCols, jsonBytes, parquetBytes, arrowIpcBytes, parquetChunk, arrowChunk);
    }

    public String getDefaultCompression() {
        String raw = Env.get("PARQUET_COMPRESSION", "snappy").toLowerCase();
        return VALID_COMPRESSIONS.contains(raw) ? raw : "snappy";
    }

    public String getDefaultEncodingStrategy() {
        String raw = Env.get("PARQUET_ENCODING_STRATEGY", "default").toLowerCase();
        return VALID_ENCODING_STRATEGIES.contains(raw) ? raw : "default";
    }

    public String getDefaultArrowIpcCompression() {
        String raw = Env.get("ARROW_IPC_COMPRESSION", "none").toLowerCase();
        return VALID_ARROW_IPC_COMPRESSIONS.contains(raw) ? raw : "none";
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
        return formatSelector.jsonObviousWinnerBytes();
    }

    public boolean formatHintsSkipLargeForSmall() {
        String raw = Env.get("FORMAT_HINTS_SKIP_LARGE_FORMATS_FOR_SMALL", "1").toLowerCase();
        return !Set.of("0", "false", "no").contains(raw);
    }

    private TabularData loadTpcdsBaseTable() {
        if (tpcdsBaseTable != null) {
            return tpcdsBaseTable;
        }
        if (tpcdsParquetPath == null || tpcdsParquetPath.isBlank()) {
            throw new IllegalStateException("TPCDS_PARQUET_PATH is not set but loadTpcdsBaseTable was called");
        }
        Path path = Path.of(tpcdsParquetPath);
        if (!Files.isRegularFile(path)) {
            throw new IllegalStateException("TPCDS_PARQUET_PATH points to missing file: " + path);
        }
        try {
            tpcdsBaseTable = ArrowParquetSupport.readParquet(path, allocator);
            return tpcdsBaseTable;
        } catch (IOException e) {
            throw new IllegalStateException("Failed to load TPCDS parquet: " + path, e);
        }
    }

    private int getJsonByteSize(int nRows, int nCols) {
        ShapeKey key = new ShapeKey(nRows, nCols);
        Integer cached = jsonByteSizeCache.get(key);
        if (cached != null) {
            return cached;
        }
        TabularData df = generateDataframe(nRows, nCols, 0);
        int size = measureJsonBytesFromDf(df);
        jsonByteSizeCache.put(key, size);
        return size;
    }

    private byte[] getParquetBlobBytes(int nRows, int nCols, String compression, String encodingStrategy)
            throws IOException {
        ParquetCacheKey key = new ParquetCacheKey(nRows, nCols, compression, encodingStrategy);
        byte[] cached = parquetBlobCache.get(key);
        if (cached != null) {
            return cached;
        }
        TabularData df = generateDataframe(nRows, nCols, 0);
        VectorSchemaRoot table = ArrowParquetSupport.toArrowTable(df, allocator);
        try {
            byte[] bytes = encodeParquet(table, compression, encodingStrategy);
            parquetBlobCache.put(key, bytes);
            return bytes;
        } finally {
            table.close();
        }
    }

    private byte[] getParquetChunkBytes(
            int nRows, int nCols, int offset, int thisRows, String compression, String encodingStrategy)
            throws IOException {
        ParquetChunkKey key = new ParquetChunkKey(nRows, nCols, offset, thisRows, compression, encodingStrategy);
        byte[] cached = parquetChunkCache.get(key);
        if (cached != null) {
            return cached;
        }
        TabularData df = generateDataframe(thisRows, nCols, offset);
        VectorSchemaRoot table = ArrowParquetSupport.toArrowTable(df, allocator);
        try {
            byte[] bytes = encodeParquet(table, compression, encodingStrategy);
            parquetChunkCache.put(key, bytes);
            return bytes;
        } finally {
            table.close();
        }
    }

    private byte[] getArrowIpcBlobBytes(int nRows, int nCols, String ipcCompression) throws IOException {
        IpcCacheKey key = new IpcCacheKey(nRows, nCols, ipcCompression);
        byte[] cached = arrowIpcBlobCache.get(key);
        if (cached != null) {
            return cached;
        }
        TabularData df = generateDataframe(nRows, nCols, 0);
        VectorSchemaRoot table = ArrowParquetSupport.toArrowTable(df, allocator);
        try {
            byte[] bytes = encodeArrowIpcFile(table, ipcCompression);
            arrowIpcBlobCache.put(key, bytes);
            return bytes;
        } finally {
            table.close();
        }
    }

    private byte[] getArrowIpcChunkBytes(int nRows, int nCols, int offset, int thisRows, String ipcCompression)
            throws IOException {
        IpcChunkKey key = new IpcChunkKey(nRows, nCols, offset, thisRows, ipcCompression);
        byte[] cached = arrowIpcChunkCache.get(key);
        if (cached != null) {
            return cached;
        }
        TabularData df = generateDataframe(thisRows, nCols, offset);
        VectorSchemaRoot table = ArrowParquetSupport.toArrowTable(df, allocator);
        try {
            byte[] bytes = encodeArrowIpcFile(table, ipcCompression);
            arrowIpcChunkCache.put(key, bytes);
            return bytes;
        } finally {
            table.close();
        }
    }

    private int measureJsonBytesFromDf(TabularData df) {
        int cells = df.numRows() * df.numCols();
        if (cells <= SMALL_PAYLOAD_CELLS) {
            try {
                return objectMapper.writeValueAsBytes(df.toRecords()).length;
            } catch (Exception e) {
                return estimateJsonBytesFromDf(df);
            }
        }
        return estimateJsonBytesFromDf(df);
    }

    private int estimateJsonBytesFromDf(TabularData df) {
        int nRows = df.numRows();
        if (nRows == 0) {
            return 2;
        }
        int perRecordOverhead = 2;
        int recordValueBytes = 0;
        for (String col : df.getColumnNames()) {
            perRecordOverhead += col.length() + 4;
            TabularData.ColumnKind kind = df.columnKind(col);
            switch (kind) {
                case BOOLEAN -> recordValueBytes += JSON_BOOL_VALUE_WIDTH;
                case INTEGER -> recordValueBytes += JSON_INT_VALUE_WIDTH;
                case FLOAT -> recordValueBytes += JSON_FLOAT_VALUE_WIDTH;
                case DATETIME -> recordValueBytes += JSON_DATETIME_VALUE_WIDTH;
                default -> {
                    int avgLen = df.averageStringLength(col);
                    recordValueBytes += avgLen + 2;
                    if (avgLen == 0) {
                        recordValueBytes += JSON_DEFAULT_VALUE_WIDTH;
                    }
                }
            }
        }
        int perRecord = perRecordOverhead + recordValueBytes;
        return 2 + nRows * perRecord + Math.max(0, nRows - 1);
    }

    private Map<String, Object> smallPayloadHints(int nRows, int nCols, int jsonBytes, long sentinel) {
        Map<String, Object> hints = new HashMap<>();
        hints.put("resolved_n_rows", nRows);
        hints.put("resolved_n_cols", nCols);
        hints.put("json_bytes", jsonBytes);
        hints.put("parquet_bytes", sentinel);
        hints.put("parquet_stream_first_chunk_bytes", sentinel);
        hints.put("arrow_ipc_bytes", sentinel);
        hints.put("arrow_ipc_stream_first_chunk_bytes", sentinel);
        hints.put("small_payload_skip_large_formats", true);
        return hints;
    }

    private Map<String, Object> fullPayloadHints(
            int nRows,
            int nCols,
            int jsonBytes,
            byte[] parquetBytes,
            byte[] arrowIpcBytes,
            byte[] parquetChunk,
            byte[] arrowChunk) {
        Map<String, Object> hints = new HashMap<>();
        hints.put("resolved_n_rows", nRows);
        hints.put("resolved_n_cols", nCols);
        hints.put("json_bytes", jsonBytes);
        hints.put("parquet_bytes", parquetBytes.length);
        hints.put("parquet_stream_first_chunk_bytes", parquetChunk.length);
        hints.put("arrow_ipc_bytes", arrowIpcBytes.length);
        hints.put("arrow_ipc_stream_first_chunk_bytes", arrowChunk.length);
        return hints;
    }

    private Map<String, Object> tabularHintsKey(
            String kind,
            int nRows,
            int nCols,
            int rowsPerChunk,
            String parquetCompression,
            String parquetEncodingStrategy,
            String arrowIpcCompression,
            String resultId,
            Path materializedPath) throws IOException {
        Map<String, Object> key = new HashMap<>();
        key.put("kind", kind);
        key.put("n_rows", nRows);
        key.put("n_cols", nCols);
        key.put("rows_per_chunk", rowsPerChunk);
        key.put("parquet_compression", parquetCompression);
        key.put("parquet_encoding_strategy", parquetEncodingStrategy);
        key.put("arrow_ipc_compression", arrowIpcCompression);
        if (resultId != null) {
            key.put("result_id", resultId);
        }
        if (materializedPath != null && Files.isRegularFile(materializedPath)) {
            key.put("materialized_path", materializedPath.toString());
            BasicFileAttributes attrs = Files.readAttributes(materializedPath, BasicFileAttributes.class);
            FileTime mtime = attrs.lastModifiedTime();
            key.put("materialized_mtime_ns", mtime.to(TimeUnit.NANOSECONDS));
            key.put("materialized_size", attrs.size());
        }
        return key;
    }

    @SuppressWarnings("unchecked")
    private boolean cachedHintsMatch(
            Map<String, Object> cached,
            int rowsPerChunk,
            String comp,
            String encStrat,
            String ipcComp,
            int resolvedNRows) {
        if (cached == null || !(cached.get("hints") instanceof Map)) {
            return false;
        }
        if (!comp.equals(cached.get("parquet_compression"))
                || !encStrat.equals(cached.get("parquet_encoding_strategy"))
                || !ipcComp.equals(cached.get("arrow_ipc_compression"))) {
            return false;
        }
        int nRows = Math.max(1, resolvedNRows);
        int effCached = Math.min(toInt(cached.get("rows_per_chunk")), nRows);
        int effReq = Math.min(rowsPerChunk, nRows);
        return effCached == effReq;
    }

    private static int toInt(Object value) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        return Integer.parseInt(String.valueOf(value));
    }

    private static final class LruCache<K, V> extends LinkedHashMap<K, V> {
        private final int maxSize;

        private LruCache(int maxSize) {
            super(maxSize, 0.75f, true);
            this.maxSize = maxSize;
        }

        @Override
        protected boolean removeEldestEntry(Map.Entry<K, V> eldest) {
            return size() > maxSize;
        }
    }

    private record ShapeKey(int nRows, int nCols) {
    }

    private record ParquetCacheKey(int nRows, int nCols, String compression, String encodingStrategy) {
    }

    private record ParquetChunkKey(
            int nRows, int nCols, int offset, int thisRows, String compression, String encodingStrategy) {
    }

    private record IpcCacheKey(int nRows, int nCols, String ipcCompression) {
    }

    private record IpcChunkKey(int nRows, int nCols, int offset, int thisRows, String ipcCompression) {
    }

    /**
     * Apache Arrow / Parquet conversion helpers.
     */
    static final class ArrowParquetSupport {

        private ArrowParquetSupport() {
        }

        static TabularData readParquet(Path path, BufferAllocator allocator) throws IOException {
            String uri = "file:" + path.toAbsolutePath();
            ScanOptions options = new ScanOptions(32_768);
            DatasetFactory datasetFactory = null;
            Dataset dataset = null;
            Scanner scanner = null;
            org.apache.arrow.vector.ipc.ArrowReader reader = null;
            try {
                datasetFactory = new FileSystemDatasetFactory(
                        allocator, NativeMemoryPool.getDefault(), FileFormat.PARQUET, uri);
                dataset = datasetFactory.finish();
                scanner = dataset.newScan(options);
                reader = scanner.scanBatches();
                List<String> columns = new ArrayList<>();
                List<Map<String, Object>> rows = new ArrayList<>();
                while (reader.loadNextBatch()) {
                    VectorSchemaRoot root = reader.getVectorSchemaRoot();
                    if (columns.isEmpty()) {
                        for (Field field : root.getSchema().getFields()) {
                            columns.add(field.getName());
                        }
                    }
                    for (int i = 0; i < root.getRowCount(); i++) {
                        Map<String, Object> row = new LinkedHashMap<>();
                        for (FieldVector vector : root.getFieldVectors()) {
                            row.put(vector.getField().getName(), vector.isNull(i) ? null : vector.getObject(i));
                        }
                        rows.add(row);
                    }
                }
                return new TabularData(columns, rows);
            } catch (Exception e) {
                if (e instanceof IOException io) {
                    throw io;
                }
                throw new IOException("Failed to read parquet: " + path, e);
            } finally {
                closeQuietly(reader);
                closeQuietly(scanner);
                closeQuietly(dataset);
                closeQuietly(datasetFactory);
            }
        }

        private static void closeQuietly(AutoCloseable closeable) {
            if (closeable == null) {
                return;
            }
            try {
                closeable.close();
            } catch (Exception ignored) {
                // best-effort cleanup
            }
        }

        static VectorSchemaRoot toArrowTable(TabularData data, BufferAllocator allocator) {
            List<Field> fields = new ArrayList<>();
            for (String col : data.getColumnNames()) {
                fields.add(new Field(col, FieldType.nullable(inferFieldType(data, col)), null));
            }
            Schema schema = new Schema(fields);
            VectorSchemaRoot root = VectorSchemaRoot.create(schema, allocator);
            root.allocateNew();
            for (String col : data.getColumnNames()) {
                FieldVector vector = root.getVector(col);
                for (int rowIdx = 0; rowIdx < data.numRows(); rowIdx++) {
                    Object value = data.getRows().get(rowIdx).get(col);
                    setVectorValue(vector, rowIdx, value);
                }
            }
            root.setRowCount(data.numRows());
            return root;
        }

        static void setVectorValue(FieldVector vector, int index, Object value) {
            if (value == null) {
                vector.setNull(index);
                return;
            }
            switch (vector) {
                case BigIntVector bigIntVector -> bigIntVector.setSafe(index, ((Number) value).longValue());
                case IntVector intVector -> intVector.setSafe(index, ((Number) value).intValue());
                case Float8Vector float8Vector -> float8Vector.setSafe(index, ((Number) value).doubleValue());
                case BitVector bitVector -> bitVector.setSafe(index, (Boolean) value ? 1 : 0);
                case VarCharVector varCharVector -> varCharVector.setSafe(index, String.valueOf(value).getBytes(StandardCharsets.UTF_8));
                default -> {
                    if (value instanceof Number number) {
                        if (vector instanceof BigIntVector bigIntVector) {
                            bigIntVector.setSafe(index, number.longValue());
                        } else if (vector instanceof Float8Vector float8Vector) {
                            float8Vector.setSafe(index, number.doubleValue());
                        }
                    } else if (vector instanceof VarCharVector varCharVector) {
                        varCharVector.setSafe(index, String.valueOf(value).getBytes(StandardCharsets.UTF_8));
                    }
                }
            }
        }

        static VectorSchemaRoot slice(VectorSchemaRoot source, int offset, int length, BufferAllocator allocator) {
            TabularData data = vectorRootToTabular(source);
            TabularData sliced = data.slice(offset, length);
            return toArrowTable(sliced, allocator);
        }

        static TabularData vectorRootToTabular(VectorSchemaRoot root) {
            List<String> columns = new ArrayList<>();
            for (Field field : root.getSchema().getFields()) {
                columns.add(field.getName());
            }
            List<Map<String, Object>> rows = new ArrayList<>(root.getRowCount());
            for (int i = 0; i < root.getRowCount(); i++) {
                Map<String, Object> row = new LinkedHashMap<>();
                for (FieldVector vector : root.getFieldVectors()) {
                    row.put(vector.getField().getName(), vector.isNull(i) ? null : vector.getObject(i));
                }
                rows.add(row);
            }
            return new TabularData(columns, rows);
        }

        static byte[] writeParquet(VectorSchemaRoot table, BufferAllocator allocator) throws IOException {
            Path temp = Files.createTempFile("mmcp-parquet-", ".parquet");
            String uri = temp.toUri().toString();
            try (SingleBatchArrowReader reader = new SingleBatchArrowReader(table, allocator)) {
                DatasetFileWriter.write(allocator, reader, FileFormat.PARQUET, uri);
                return Files.readAllBytes(temp);
            } finally {
                Files.deleteIfExists(temp);
            }
        }

        static byte[] writeArrowIpc(VectorSchemaRoot table, String ipcCompression) throws IOException {
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            DictionaryProvider.MapDictionaryProvider provider = new DictionaryProvider.MapDictionaryProvider();
            try (ArrowFileWriter writer = new ArrowFileWriter(
                    table, provider, Channels.newChannel(baos))) {
                writer.start();
                writer.writeBatch();
                writer.end();
            }
            return baos.toByteArray();
        }

        private static ArrowType inferFieldType(TabularData data, String column) {
            TabularData.ColumnKind kind = data.columnKind(column);
            return switch (kind) {
                case BOOLEAN -> new ArrowType.Bool();
                case INTEGER -> new ArrowType.Int(64, true);
                case FLOAT -> new ArrowType.FloatingPoint(org.apache.arrow.vector.types.FloatingPointPrecision.DOUBLE);
                case DATETIME -> new ArrowType.Timestamp(
                        org.apache.arrow.vector.types.TimeUnit.MILLISECOND, null);
                default -> new ArrowType.Utf8();
            };
        }
    }

    static final class SingleBatchArrowReader extends ArrowReader {

        private final VectorSchemaRoot root;
        private boolean consumed;

        SingleBatchArrowReader(VectorSchemaRoot root, BufferAllocator allocator) {
            super(allocator);
            this.root = root;
        }

        @Override
        public boolean loadNextBatch() {
            if (!consumed) {
                consumed = true;
                return true;
            }
            return false;
        }

        @Override
        public VectorSchemaRoot getVectorSchemaRoot() {
            return root;
        }

        @Override
        public long bytesRead() {
            return 0L;
        }

        @Override
        protected Schema readSchema() {
            return root.getSchema();
        }

        @Override
        protected void closeReadSource() {
            // root lifecycle managed by caller
        }
    }
}
