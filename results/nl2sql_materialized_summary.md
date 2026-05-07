# NL2SQL materialized MCP benchmark summary

- **Total records:** 500
- **Successful (with result_id, no error):** 499
- **Failed / skipped:** 1

## Recommended format (hint-driven selector)

- `json`: 457
- `parquet_blob`: 42

## By row-count bucket

| bucket | n | median json B | median pq blob B | median json fetch s | median rec fetch s | median baseline E2E s | median enhanced E2E s | median jsonB/pqB | median jsonLat/recLat |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 499 | 78 | 1344 | 0.0051 | 0.0051 | 0.0089 | 0.0137 | 0.05 | 1.00 |
| 1-10 | 428 | 57 | 1316 | 0.0050 | 0.0050 | 0.0086 | 0.0135 | 0.04 | 1.00 |
| 11-100 | 40 | 1235 | 1628 | 0.0056 | 0.0054 | 0.0090 | 0.0133 | 0.65 | 1.00 |
| 101-1000 | 18 | 6120 | 3275 | 0.0074 | 0.0055 | 0.0205 | 0.0181 | 2.24 | 1.44 |
| 1001+ | 13 | 130445 | 37746 | 0.0577 | 0.0065 | 0.1108 | 0.0397 | 3.58 | 9.30 |

**Baseline E2E (proxy):** `sql_exec_s + register_s + json_end_to_end_s`.

**Enhanced E2E (proxy):** `sql_exec_s + register_s + describe_result_formats_s + recommended_end_to_end_s` (recommended path = json, parquet_blob, or parquet_stream per selector).

