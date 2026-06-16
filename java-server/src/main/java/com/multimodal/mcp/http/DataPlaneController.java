package com.multimodal.mcp.http;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.zip.GZIPOutputStream;

import org.apache.arrow.vector.VectorSchemaRoot;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.multimodal.mcp.core.ResultConfig;
import com.multimodal.mcp.core.RuntimeState;
import com.multimodal.mcp.tabular.PayloadCache;
import com.multimodal.mcp.tabular.TabularData;
import com.multimodal.mcp.tabular.TabularService;

/**
 * REST data-plane endpoints. Port of {@code server/http_endpoints.py}.
 */
@RestController
public class DataPlaneController {

    private static final Set<String> VALID_ARROW_IPC_COMPRESSIONS = Set.of("none", "lz4", "zstd");

    private final RuntimeState runtimeState;
    private final TabularService tabularService;
    private final PayloadCache payloadCache;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public DataPlaneController(RuntimeState runtimeState, TabularService tabularService, PayloadCache payloadCache) {
        this.runtimeState = runtimeState;
        this.tabularService = tabularService;
        this.payloadCache = payloadCache;
    }

    @GetMapping("/blobs/{resultId}.parquet")
    public ResponseEntity<byte[]> parquetBlob(@PathVariable("resultId") String resultId) throws IOException {
        ResultConfig config = getConfigOr404(resultId);
        if (config == null) {
            return notFoundEntity();
        }

        String comp = config.getCompression() != null ? config.getCompression() : tabularService.getDefaultCompression();
        String encStrat = config.getEncodingStrategy() != null
                ? config.getEncodingStrategy()
                : tabularService.getDefaultEncodingStrategy();

        byte[] data;
        ResultConfig.ParquetCodec cachedCodec = config.getCachedParquetCodec();
        if (config.getCachedParquetBlobBytes() != null
                && cachedCodec != null
                && comp.equals(cachedCodec.compression())
                && encStrat.equals(cachedCodec.encodingStrategy())) {
            data = config.getCachedParquetBlobBytes();
            payloadCache.touch(resultId);
        } else if (config.getMaterializedPath() != null) {
            VectorSchemaRoot table = tabularService.resolveArrowTable(config);
            data = tabularService.encodeParquet(table, comp, encStrat);
        } else {
            TabularData df = tabularService.resolveDataframe(config, 0, null);
            VectorSchemaRoot table = tabularService.resolveArrowTable(withCachedDataframe(config, df));
            data = tabularService.encodeParquet(table, comp, encStrat);
        }

        HttpHeaders headers = benchmarkHeaders(config);
        headers.set("X-Benchmark-Bytes", String.valueOf(data.length));
        headers.set("X-Benchmark-Compression", comp);
        headers.set("X-Benchmark-Encoding-Strategy", encStrat);
        return ResponseEntity.ok().headers(headers).contentType(MediaType.APPLICATION_OCTET_STREAM).body(data);
    }

    @GetMapping("/streams/{resultId}")
    public ResponseEntity<StreamingResponseBody> parquetStream(@PathVariable("resultId") String resultId)
            throws IOException {
        ResultConfig config = getConfigOr404(resultId);
        if (config == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(out -> objectMapper.writeValue(out, Map.of("error", "unknown result_id")));
        }

        Integer rowsPerChunk = config.getRowsPerChunk();
        if (rowsPerChunk == null || rowsPerChunk <= 0) {
            return ResponseEntity.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(out -> objectMapper.writeValue(out, Map.of("error", "rows_per_chunk not configured")));
        }

        HttpHeaders headers = benchmarkHeaders(config);
        headers.set("X-Benchmark-Rows-Per-Chunk", String.valueOf(rowsPerChunk));
        StreamingResponseBody body = outputStream -> streamParquetChunks(config, outputStream);
        return ResponseEntity.ok().headers(headers).contentType(MediaType.APPLICATION_OCTET_STREAM).body(body);
    }

    @GetMapping("/ipc-blobs/{resultId}.arrow")
    public ResponseEntity<byte[]> ipcBlob(@PathVariable("resultId") String resultId) throws IOException {
        ResultConfig config = getConfigOr404(resultId);
        if (config == null) {
            return notFoundEntity();
        }

        String ipcComp = normalizeIpcCompression(
                config.getIpcCompression() != null
                        ? config.getIpcCompression()
                        : tabularService.getDefaultArrowIpcCompression());

        byte[] data;
        if (config.getCachedArrowIpcBlobBytes() != null
                && ipcComp.equals(config.getCachedArrowIpcCodec())) {
            data = config.getCachedArrowIpcBlobBytes();
            payloadCache.touch(resultId);
        } else if (config.getMaterializedPath() != null) {
            VectorSchemaRoot table = tabularService.resolveArrowTable(config);
            data = tabularService.encodeArrowIpcFile(table, ipcComp);
        } else {
            TabularData df = tabularService.resolveDataframe(config, 0, null);
            VectorSchemaRoot table = tabularService.resolveArrowTable(withCachedDataframe(config, df));
            data = tabularService.encodeArrowIpcFile(table, ipcComp);
        }

        HttpHeaders headers = benchmarkHeaders(config);
        headers.set("X-Benchmark-Bytes", String.valueOf(data.length));
        headers.set("X-Benchmark-IPC-Compression", ipcComp);
        return ResponseEntity.ok()
                .headers(headers)
                .contentType(MediaType.parseMediaType("application/vnd.apache.arrow.file"))
                .body(data);
    }

    @GetMapping("/ipc-streams/{resultId}")
    public ResponseEntity<StreamingResponseBody> ipcStream(@PathVariable("resultId") String resultId)
            throws IOException {
        ResultConfig config = getConfigOr404(resultId);
        if (config == null) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(out -> objectMapper.writeValue(out, Map.of("error", "unknown result_id")));
        }

        Integer rowsPerChunk = config.getRowsPerChunk();
        if (rowsPerChunk == null || rowsPerChunk <= 0) {
            return ResponseEntity.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(out -> objectMapper.writeValue(out, Map.of("error", "rows_per_chunk not configured")));
        }

        String ipcComp = normalizeIpcCompression(
                config.getIpcCompression() != null
                        ? config.getIpcCompression()
                        : tabularService.getDefaultArrowIpcCompression());

        HttpHeaders headers = benchmarkHeaders(config);
        headers.set("X-Benchmark-Rows-Per-Chunk", String.valueOf(rowsPerChunk));
        headers.set("X-Benchmark-IPC-Compression", ipcComp);
        StreamingResponseBody body = outputStream -> streamIpcChunks(config, ipcComp, outputStream);
        return ResponseEntity.ok().headers(headers).contentType(MediaType.APPLICATION_OCTET_STREAM).body(body);
    }

    @GetMapping("/raw/{resultId}")
    public ResponseEntity<byte[]> rawBlob(@PathVariable("resultId") String resultId) throws IOException {
        ResultConfig config = getConfigOr404(resultId);
        if (config == null) {
            return notFoundEntity();
        }
        if (!"unstructured".equals(config.getPayloadKind()) || config.getRawPath() == null) {
            return ResponseEntity.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(objectMapper.writeValueAsBytes(Map.of("error", "result_id is not unstructured")));
        }

        byte[] data = Files.readAllBytes(config.getRawPath());
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Benchmark-Bytes", String.valueOf(data.length));
        MediaType mediaType = MediaType.parseMediaType(
                config.getRawMimeType() != null ? config.getRawMimeType() : "application/octet-stream");
        return ResponseEntity.ok().headers(headers).contentType(mediaType).body(data);
    }

    @GetMapping("/raw-gzip/{resultId}")
    public ResponseEntity<byte[]> rawGzipBlob(@PathVariable("resultId") String resultId) throws IOException {
        ResultConfig config = getConfigOr404(resultId);
        if (config == null) {
            return notFoundEntity();
        }
        if (!"unstructured".equals(config.getPayloadKind()) || config.getRawPath() == null) {
            return ResponseEntity.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(objectMapper.writeValueAsBytes(Map.of("error", "result_id is not unstructured")));
        }

        Path gzPath = config.getRawGzipPath();
        if (gzPath == null || !Files.isRegularFile(gzPath)) {
            gzPath = runtimeState.getMaterializedRawDir().resolve(resultId + ".bin.gz");
            byte[] raw = Files.readAllBytes(config.getRawPath());
            Files.createDirectories(gzPath.getParent());
            try (ByteArrayOutputStream baos = new ByteArrayOutputStream();
                    GZIPOutputStream gzip = new GZIPOutputStream(baos)) {
                gzip.write(raw);
                gzip.finish();
                Files.write(gzPath, baos.toByteArray());
            }
            config.setRawGzipPath(gzPath);
        }

        byte[] gz = Files.readAllBytes(gzPath);
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Benchmark-Bytes", String.valueOf(gz.length));
        headers.set("Content-Encoding", "gzip");
        MediaType mediaType = MediaType.parseMediaType(
                config.getRawMimeType() != null ? config.getRawMimeType() : "application/octet-stream");
        return ResponseEntity.ok().headers(headers).contentType(mediaType).body(gz);
    }

    @PostMapping("/materialized")
    public ResponseEntity<byte[]> registerMaterialized(
            @RequestHeader(value = HttpHeaders.CONTENT_TYPE, required = false) String contentType,
            @RequestBody byte[] body) throws IOException {
        if (contentType == null
                || (!contentType.contains("application/octet-stream") && !contentType.contains("multipart"))) {
            return ResponseEntity.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(objectMapper.writeValueAsBytes(
                            Map.of("error", "Content-Type must be application/octet-stream")));
        }
        if (body == null || body.length == 0) {
            return ResponseEntity.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(objectMapper.writeValueAsBytes(Map.of("error", "empty body")));
        }

        TabularData dataframe;
        try {
            Path temp = Files.createTempFile("mmcp-upload-", ".parquet");
            try {
                Files.write(temp, body);
                dataframe = tabularService.loadMaterializedDataframe(temp, 0, null);
            } finally {
                Files.deleteIfExists(temp);
            }
        } catch (Exception e) {
            return ResponseEntity.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(objectMapper.writeValueAsBytes(Map.of("error", "invalid Parquet file: " + e.getMessage())));
        }

        int nRows = dataframe.numRows();
        int nCols = dataframe.numCols();
        if (nRows > RuntimeState.MAX_MATERIALIZED_ROWS) {
            return ResponseEntity.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(objectMapper.writeValueAsBytes(Map.of(
                            "error",
                            "too many rows (" + nRows + "); limit is " + RuntimeState.MAX_MATERIALIZED_ROWS)));
        }

        Files.createDirectories(runtimeState.getMaterializedDir());
        String resultId = UUID.randomUUID().toString();
        Path path = runtimeState.getMaterializedDir().resolve(resultId + ".parquet");
        Files.write(path, body);

        ResultConfig config = new ResultConfig(nRows, nCols);
        config.setPayloadKind("tabular");
        config.setMaterializedPath(path);

        try {
            tabularService.populateMaterializedCaches(config, resultId, dataframe, null, body, 8192);
        } catch (Exception e) {
            config.setCachedHints(null);
        }

        runtimeState.getResultRegistry().put(resultId, config);
        return ResponseEntity.status(HttpStatus.CREATED)
                .contentType(MediaType.APPLICATION_JSON)
                .body(objectMapper.writeValueAsBytes(Map.of(
                        "result_id", resultId,
                        "n_rows", nRows,
                        "n_cols", nCols)));
    }

    @PostMapping("/materialized-raw")
    public ResponseEntity<byte[]> registerMaterializedRaw(
            @RequestHeader(value = HttpHeaders.CONTENT_TYPE, required = false) String contentType,
            @RequestBody byte[] body) throws IOException {
        if (body == null || body.length == 0) {
            return ResponseEntity.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(objectMapper.writeValueAsBytes(Map.of("error", "empty body")));
        }

        Files.createDirectories(runtimeState.getMaterializedRawDir());
        String resultId = UUID.randomUUID().toString();
        Path path = runtimeState.getMaterializedRawDir().resolve(resultId + ".bin");
        Files.write(path, body);

        String mime = "application/octet-stream";
        String charset = null;
        if (contentType != null && !contentType.isBlank()) {
            mime = contentType.split(";", 2)[0].strip();
            int charsetIdx = contentType.toLowerCase().indexOf("charset=");
            if (charsetIdx >= 0) {
                charset = contentType.substring(charsetIdx + "charset=".length()).strip();
            }
        }

        ResultConfig config = new ResultConfig(0, 0);
        config.setPayloadKind("unstructured");
        config.setRawPath(path);
        config.setRawMimeType(mime);
        config.setRawCharset(charset);
        runtimeState.getResultRegistry().put(resultId, config);

        return ResponseEntity.status(HttpStatus.CREATED)
                .contentType(MediaType.APPLICATION_JSON)
                .body(objectMapper.writeValueAsBytes(Map.of(
                        "result_id", resultId,
                        "payload_kind", "unstructured",
                        "mime_type", mime,
                        "bytes", body.length)));
    }

    private void streamParquetChunks(ResultConfig config, java.io.OutputStream outputStream) throws IOException {
        int rowsPerChunk = config.getRowsPerChunk();
        String comp = config.getCompression() != null ? config.getCompression() : tabularService.getDefaultCompression();
        String encStrat = config.getEncodingStrategy() != null
                ? config.getEncodingStrategy()
                : tabularService.getDefaultEncodingStrategy();

        if (config.getMaterializedPath() != null || config.getCachedDataframe() != null) {
            TabularData fullDf = tabularService.resolveDataframe(config, 0, null);
            int offset = 0;
            int totalRows = fullDf.numRows();
            while (offset < totalRows) {
                int thisRows = Math.min(rowsPerChunk, totalRows - offset);
                TabularData chunkDf = fullDf.slice(offset, thisRows);
                VectorSchemaRoot table = tabularService.resolveArrowTable(withCachedDataframe(config, chunkDf));
                writeLengthPrefixedChunk(outputStream, tabularService.encodeParquet(table, comp, encStrat));
                offset += thisRows;
            }
        } else {
            int offset = 0;
            int totalRows = config.getNRows();
            while (offset < totalRows) {
                int thisRows = Math.min(rowsPerChunk, totalRows - offset);
                TabularData chunkDf = tabularService.resolveDataframe(config, offset, thisRows);
                VectorSchemaRoot table = tabularService.resolveArrowTable(withCachedDataframe(config, chunkDf));
                writeLengthPrefixedChunk(outputStream, tabularService.encodeParquet(table, comp, encStrat));
                offset += thisRows;
            }
        }
    }

    private void streamIpcChunks(ResultConfig config, String ipcComp, java.io.OutputStream outputStream)
            throws IOException {
        int rowsPerChunk = config.getRowsPerChunk();
        if (config.getMaterializedPath() != null || config.getCachedDataframe() != null) {
            TabularData fullDf = tabularService.resolveDataframe(config, 0, null);
            int offset = 0;
            int totalRows = fullDf.numRows();
            while (offset < totalRows) {
                int thisRows = Math.min(rowsPerChunk, totalRows - offset);
                TabularData chunkDf = fullDf.slice(offset, thisRows);
                VectorSchemaRoot table = tabularService.resolveArrowTable(withCachedDataframe(config, chunkDf));
                writeLengthPrefixedChunk(outputStream, tabularService.encodeArrowIpcFile(table, ipcComp));
                offset += thisRows;
            }
        } else {
            int offset = 0;
            int totalRows = config.getNRows();
            while (offset < totalRows) {
                int thisRows = Math.min(rowsPerChunk, totalRows - offset);
                TabularData chunkDf = tabularService.resolveDataframe(config, offset, thisRows);
                VectorSchemaRoot table = tabularService.resolveArrowTable(withCachedDataframe(config, chunkDf));
                writeLengthPrefixedChunk(outputStream, tabularService.encodeArrowIpcFile(table, ipcComp));
                offset += thisRows;
            }
        }
    }

    private static void writeLengthPrefixedChunk(java.io.OutputStream outputStream, byte[] chunk) throws IOException {
        byte[] lengthPrefix = new byte[8];
        long len = chunk.length;
        for (int i = 7; i >= 0; i--) {
            lengthPrefix[i] = (byte) (len & 0xFF);
            len >>>= 8;
        }
        outputStream.write(lengthPrefix);
        outputStream.write(chunk);
    }

    private ResultConfig getConfigOr404(String resultId) {
        return runtimeState.getResultRegistry().get(resultId);
    }

    private ResponseEntity<byte[]> notFoundEntity() throws IOException {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .contentType(MediaType.APPLICATION_JSON)
                .body(objectMapper.writeValueAsBytes(Map.of("error", "unknown result_id")));
    }

    private static HttpHeaders benchmarkHeaders(ResultConfig config) {
        HttpHeaders headers = new HttpHeaders();
        headers.set("X-Benchmark-Rows", String.valueOf(config.getNRows()));
        headers.set("X-Benchmark-Cols", String.valueOf(config.getNCols()));
        return headers;
    }

    private static String normalizeIpcCompression(String ipcComp) {
        if (!VALID_ARROW_IPC_COMPRESSIONS.contains(ipcComp)) {
            return "none";
        }
        return ipcComp;
    }

    private static ResultConfig withCachedDataframe(ResultConfig source, TabularData dataframe) {
        ResultConfig scratch = new ResultConfig(source.getNRows(), source.getNCols());
        scratch.setCachedDataframe(dataframe);
        scratch.setMaterializedPath(source.getMaterializedPath());
        scratch.setCompression(source.getCompression());
        scratch.setEncodingStrategy(source.getEncodingStrategy());
        scratch.setIpcCompression(source.getIpcCompression());
        return scratch;
    }
}
