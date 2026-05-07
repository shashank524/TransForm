# BIRD server-exec E2E benchmark summary

## Run configuration

- **Records:** 1534
- **Target:** min_time_to_first_rows
- **rows_per_chunk:** 32768
- **max_rows:** 500000
- **PARQUET_ENCODING_STRATEGY:** data_driven
- **PARQUET_COMPRESSION:** snappy
- **ARROW_IPC_COMPRESSION:** none
- **prefer_streaming:** True
- **network:** {'net_profile': None, 'tc_dev': None, 'tc_delay': None, 'tc_rate': None, 'tc_loss': None}

## Latency (seconds, end-to-end)

| arm | median | p95 |
|---|---:|---:|
| baseline (inline json) | 0.014689 | 0.224008 |
| client (materialize+describe+fetch) | 0.044274 | 0.237337 |
| server_auto (call+fetch) | 0.021146 | 0.164615 |

## Payload sizes (bytes, median)

- baseline: 57
- client: 57
- server_auto: 45

## Ratios (median)

- baseline/client latency: 0.376063
- baseline/server_auto latency: 0.777706
- baseline/client bytes: 1
- baseline/server_auto bytes: 1.342857

## Chosen format counts

- client: {'json': 1367, 'parquet_blob': 157, 'arrow_ipc_blob': 1, 'parquet_stream': 5}
- server_auto: {'json': 1367, 'parquet_blob': 157, 'arrow_ipc_blob': 1, 'parquet_stream': 5}

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
| client | 0.014142 | 0.025057 |
| server_auto | 0.007374 | 0.011643 |
