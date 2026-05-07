# Compare: Regular (rule-based) vs New (hint-driven) — FORMAT_SELECT_TARGET=min_bytes

| n_rows | n_cols | regular_format | regular_bytes | regular_latency_s | new_format | new_bytes | new_latency_s |
|--------|--------|----------------|---------------|-------------------|------------|-----------|----------------|
| 10000 | 6 | parquet_blob | 407792 | 0.1942 | parquet_blob | 407792 | 0.0048 |
| 10000 | 20 | parquet_blob | 1226861 | 0.0058 | parquet_blob | 1226861 | 0.0055 |
| 100000 | 6 | parquet_blob | 4230402 | 0.0094 | parquet_blob | 4230402 | 0.0098 |
| 100000 | 20 | parquet_blob | 12738833 | 0.0211 | parquet_blob | 12738833 | 0.0191 |
