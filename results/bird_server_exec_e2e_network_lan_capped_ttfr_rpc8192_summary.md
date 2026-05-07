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
| baseline (inline json) | 0.016373 | 0.850735 |
| client (materialize+describe+fetch) | 0.049075 | 0.645153 |
| server_auto (call+fetch) | 0.029942 | 0.798234 |

## Payload sizes (bytes, median)

- baseline: 57
- client: 50
- server_auto: 38

## Normalized payload metrics (bytes, median)

- `logical_json_records_bytes`: records-only JSON size (same logical payload baseline for all arms).
- `*_wire_bytes`: normalized wire payload where JSON uses records-only bytes; stream includes framing overhead.

- logical_json_records_bytes: —
- baseline_wire_bytes: —
- client_wire_bytes: —
- server_auto_wire_bytes: —

## Ratios (median)

- baseline/client latency: 0.36573
- baseline/server_auto latency: 0.659132
- baseline/client bytes: 1
- baseline/server_auto bytes: 1.315789
- baseline/client wire_bytes: —
- baseline/server_auto wire_bytes: —

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
