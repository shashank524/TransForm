package com.multimodal.mcp.format;

/**
 * Supported payload format arms for tabular and unstructured data.
 */
public enum FormatName {
    JSON("json"),
    PARQUET_BLOB("parquet_blob"),
    PARQUET_STREAM("parquet_stream"),
    ARROW_IPC_BLOB("arrow_ipc_blob"),
    ARROW_IPC_STREAM("arrow_ipc_stream"),
    TEXT_INLINE("text_inline"),
    RAW_BLOB("raw_blob"),
    GZIP_BLOB("gzip_blob");

    private final String value;

    FormatName(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }

    public static FormatName fromString(String raw) {
        for (FormatName format : values()) {
            if (format.value.equals(raw)) {
                return format;
            }
        }
        throw new IllegalArgumentException("Unknown format: " + raw);
    }
}
