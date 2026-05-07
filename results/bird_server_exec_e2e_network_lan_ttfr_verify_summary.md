# BIRD server-exec E2E benchmark summary

## Run configuration

- **Records:** 200
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
| baseline (inline json) | 0.015496 | 0.725892 |
| client (materialize+describe+fetch) | 0.041388 | 0.559728 |
| server_auto (call+fetch) | 0.024597 | 0.567477 |

## Payload sizes (bytes, median)

- baseline: 55
- client: 55
- server_auto: 43

## Ratios (median)

- baseline/client latency: 0.377
- baseline/server_auto latency: 0.664803
- baseline/client bytes: 1
- baseline/server_auto bytes: 1.369318

## Chosen format counts

- client: {'json': 173, 'parquet_blob': 26, 'arrow_ipc_blob': 1}
- server_auto: {'json': 173, 'parquet_blob': 26, 'arrow_ipc_blob': 1}

## Baseline feasibility

- **Baseline failed:** 0
- **Baseline failed rate:** 0

## Baseline failure rate by result size (cells bucket = n_rows*n_cols from materialize arm)

| bucket | total | baseline_failed |
|---|---:|---:|
| 1-1e4 | 197 | 0 |
| 1e4-1e5 | 3 | 0 |

## Time to first rows (TTFR, seconds) — streaming only

| arm | median | p95 |
|---|---:|---:|
| client | — | — |
| server_auto | — | — |
