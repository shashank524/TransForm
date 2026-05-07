# BIRD server-exec E2E benchmark summary

## Run configuration

- **Records:** 1534
- **Target:** min_time_to_first_rows
- **rows_per_chunk:** 8192
- **max_rows:** 500000
- **PARQUET_ENCODING_STRATEGY:** data_driven
- **PARQUET_COMPRESSION:** snappy
- **ARROW_IPC_COMPRESSION:** none
- **prefer_streaming:** True
- **network:** {'net_profile': 'LAN', 'tc_dev': 'eth0', 'tc_delay': '1ms', 'tc_rate': '1000mbit', 'tc_loss': '0%'}

## Latency (seconds, end-to-end)

| arm | median | p95 |
|---|---:|---:|
| baseline (inline json) | 0.009543 | 0.406871 |
| client (materialize+describe+fetch) | 0.026821 | 0.374406 |
| server_auto (call+fetch) | 0.005055 | 0.008093 |

## Payload sizes (bytes, median)

- baseline: 57
- client: 57
- server_auto: 57

## Normalized payload metrics (bytes, median)

- `logical_json_records_bytes`: records-only JSON size (same logical payload baseline for all arms).
- `*_wire_bytes`: normalized wire payload where JSON uses records-only bytes; stream includes framing overhead.

- logical_json_records_bytes: 57
- baseline_wire_bytes: 57
- client_wire_bytes: 57
- server_auto_wire_bytes: 57

## Ratios (median)

- baseline/client latency: 0.370674
- baseline/server_auto latency: 1.793383
- baseline/client bytes: 1
- baseline/server_auto bytes: 1
- baseline/client wire_bytes: 1
- baseline/server_auto wire_bytes: 1

## Chosen format counts

- client: {'json': 1364, 'parquet_blob': 160, 'arrow_ipc_blob': 1, 'parquet_stream': 5}
- server_auto: {'json': 1364, 'parquet_blob': 160, 'arrow_ipc_blob': 1, 'parquet_stream': 5}

## Baseline feasibility

- **Baseline failed:** 0
- **Baseline failed rate:** 0

## Baseline failure rate by result size (cells bucket = n_rows*n_cols from materialize arm)

| bucket | total | baseline_failed |
|---|---:|---:|
| 1-1e4 | 1509 | 0 |
| 1e4-1e5 | 19 | 0 |
| 1e5-1e6 | 2 | 0 |
| 0 | 4 | 0 |

## Time to first rows (TTFR, seconds) — streaming only

| arm | median | p95 |
|---|---:|---:|
| client | 0.01753 | 0.025586 |
| server_auto | 0.008323 | 0.016437 |
