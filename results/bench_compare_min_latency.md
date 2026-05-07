# Compare: Regular (rule-based) vs New (hint-driven) — FORMAT_SELECT_TARGET=min_latency


| n_rows | n_cols | regular_format | regular_bytes | regular_latency_s | new_format   | new_bytes | new_latency_s |
| ------ | ------ | -------------- | ------------- | ----------------- | ------------ | --------- | ------------- |
| 10000  | 6      | parquet_blob   | 407792        | 0.006             | parquet_blob | 407792    | 0.0042        |
| 10000  | 20     | parquet_blob   | 1226861       | 0.0058            | parquet_blob | 1226861   | 0.0057        |
| 100000 | 6      | parquet_blob   | 4230402       | 0.0089            | parquet_blob | 4230402   | 0.0146        |
| 100000 | 20     | parquet_blob   | 12738833      | 0.0235            | parquet_blob | 12738833  | 0.0191        |


