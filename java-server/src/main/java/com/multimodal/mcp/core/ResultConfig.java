package com.multimodal.mcp.core;

import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import org.apache.arrow.vector.VectorSchemaRoot;

import com.multimodal.mcp.tabular.TabularData;

/**
 * Configuration for a benchmark dataset. Mirrors Python {@code ResultConfig} dataclass.
 */
public class ResultConfig {

    private int nRows;
    private int nCols;
    private String payloadKind = "tabular";
    private Integer rowsPerChunk;
    private String compression;
    private String encodingStrategy;
    private String ipcCompression;
    private Path materializedPath;
    private Path rawPath;
    private String rawMimeType;
    private String rawCharset;
    private Path rawGzipPath;

    private Map<String, Object> cachedHints;
    private TabularData cachedDataframe;
    private VectorSchemaRoot cachedArrowTable;
    private List<Map<String, Object>> cachedJsonRecords;
    private Integer cachedJsonBytes;
    private byte[] cachedParquetBlobBytes;
    private byte[] cachedArrowIpcBlobBytes;
    private ParquetCodec cachedParquetCodec;
    private String cachedArrowIpcCodec;

    public ResultConfig(int nRows, int nCols) {
        this.nRows = nRows;
        this.nCols = nCols;
    }

    public int getNRows() {
        return nRows;
    }

    public void setNRows(int nRows) {
        this.nRows = nRows;
    }

    public int getNCols() {
        return nCols;
    }

    public void setNCols(int nCols) {
        this.nCols = nCols;
    }

    public String getPayloadKind() {
        return payloadKind;
    }

    public void setPayloadKind(String payloadKind) {
        this.payloadKind = payloadKind;
    }

    public Integer getRowsPerChunk() {
        return rowsPerChunk;
    }

    public void setRowsPerChunk(Integer rowsPerChunk) {
        this.rowsPerChunk = rowsPerChunk;
    }

    public String getCompression() {
        return compression;
    }

    public void setCompression(String compression) {
        this.compression = compression;
    }

    public String getEncodingStrategy() {
        return encodingStrategy;
    }

    public void setEncodingStrategy(String encodingStrategy) {
        this.encodingStrategy = encodingStrategy;
    }

    public String getIpcCompression() {
        return ipcCompression;
    }

    public void setIpcCompression(String ipcCompression) {
        this.ipcCompression = ipcCompression;
    }

    public Path getMaterializedPath() {
        return materializedPath;
    }

    public void setMaterializedPath(Path materializedPath) {
        this.materializedPath = materializedPath;
    }

    public Path getRawPath() {
        return rawPath;
    }

    public void setRawPath(Path rawPath) {
        this.rawPath = rawPath;
    }

    public String getRawMimeType() {
        return rawMimeType;
    }

    public void setRawMimeType(String rawMimeType) {
        this.rawMimeType = rawMimeType;
    }

    public String getRawCharset() {
        return rawCharset;
    }

    public void setRawCharset(String rawCharset) {
        this.rawCharset = rawCharset;
    }

    public Path getRawGzipPath() {
        return rawGzipPath;
    }

    public void setRawGzipPath(Path rawGzipPath) {
        this.rawGzipPath = rawGzipPath;
    }

    public Map<String, Object> getCachedHints() {
        return cachedHints;
    }

    public void setCachedHints(Map<String, Object> cachedHints) {
        this.cachedHints = cachedHints;
    }

    public TabularData getCachedDataframe() {
        return cachedDataframe;
    }

    public void setCachedDataframe(TabularData cachedDataframe) {
        this.cachedDataframe = cachedDataframe;
    }

    public VectorSchemaRoot getCachedArrowTable() {
        return cachedArrowTable;
    }

    public void setCachedArrowTable(VectorSchemaRoot cachedArrowTable) {
        this.cachedArrowTable = cachedArrowTable;
    }

    public List<Map<String, Object>> getCachedJsonRecords() {
        return cachedJsonRecords;
    }

    public void setCachedJsonRecords(List<Map<String, Object>> cachedJsonRecords) {
        this.cachedJsonRecords = cachedJsonRecords;
    }

    public Integer getCachedJsonBytes() {
        return cachedJsonBytes;
    }

    public void setCachedJsonBytes(Integer cachedJsonBytes) {
        this.cachedJsonBytes = cachedJsonBytes;
    }

    public byte[] getCachedParquetBlobBytes() {
        return cachedParquetBlobBytes;
    }

    public void setCachedParquetBlobBytes(byte[] cachedParquetBlobBytes) {
        this.cachedParquetBlobBytes = cachedParquetBlobBytes;
    }

    public byte[] getCachedArrowIpcBlobBytes() {
        return cachedArrowIpcBlobBytes;
    }

    public void setCachedArrowIpcBlobBytes(byte[] cachedArrowIpcBlobBytes) {
        this.cachedArrowIpcBlobBytes = cachedArrowIpcBlobBytes;
    }

    public ParquetCodec getCachedParquetCodec() {
        return cachedParquetCodec;
    }

    public void setCachedParquetCodec(ParquetCodec cachedParquetCodec) {
        this.cachedParquetCodec = cachedParquetCodec;
    }

    public String getCachedArrowIpcCodec() {
        return cachedArrowIpcCodec;
    }

    public void setCachedArrowIpcCodec(String cachedArrowIpcCodec) {
        this.cachedArrowIpcCodec = cachedArrowIpcCodec;
    }

    public record ParquetCodec(String compression, String encodingStrategy) {
    }
}
