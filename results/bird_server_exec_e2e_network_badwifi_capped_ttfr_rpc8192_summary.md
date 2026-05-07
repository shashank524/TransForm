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
- **network:** {'net_profile': 'BadWifi', 'tc_dev': 'eth0', 'tc_delay': '30ms', 'tc_rate': '5mbit', 'tc_loss': '1%'}

## Latency (seconds, end-to-end)

| arm | median | p95 |
|---|---:|---:|
| baseline (inline json) | 0.048444 | 0.728048 |
| client (materialize+describe+fetch) | 0.146434 | 0.668828 |
| server_auto (call+fetch) | 0.062256 | 0.651231 |

## Payload sizes (bytes, median)

- baseline: 57
- client: 50
- server_auto: 38

## Ratios (median)

- baseline/client latency: 0.338904
- baseline/server_auto latency: 0.864205
- baseline/client bytes: 1
- baseline/server_auto bytes: 1.315789

## Chosen format counts

- client: {'json': 1364}
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
| client | — | — |
| server_auto | — | — |
