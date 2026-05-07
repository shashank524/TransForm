# Structured vs unstructured transport summary

## Run configuration

- **targets:** ['min_bytes', 'min_latency', 'min_time_to_first_rows']
- **nominal sizes (bytes):** [262144, 1048576, 5242880]
- **rows_per_chunk:** 8192
- **prefer_streaming:** True
- **network:** `{'net_profile': 'BadWifi', 'tc_dev': 'eth0', 'tc_delay': '30ms', 'tc_rate': '5mbit', 'tc_loss': '1%'}`

## Client path (describe + fetch) — median / p95 seconds

| payload_class | nominal_bytes | target | median_s | p95_s | median_client_bytes |
|---|---:|---|---:|---:|---:|
| structured | 1048576 | min_bytes | 0.778470 | 0.778470 | 517716 |
| unstructured | 1048576 | min_bytes | 0.492313 | 0.492313 | 1048576 |
| structured | 1048576 | min_latency | 0.671308 | 0.671308 | 517716 |
| unstructured | 1048576 | min_latency | 0.398374 | 0.398374 | 1048576 |
| structured | 1048576 | min_time_to_first_rows | 0.570529 | 0.570529 | 522295 |
| unstructured | 1048576 | min_time_to_first_rows | 0.385082 | 0.385082 | 1048576 |
| structured | 262144 | min_bytes | 0.660885 | 0.660885 | 131586 |
| unstructured | 262144 | min_bytes | 0.152733 | 0.152733 | 262144 |
| structured | 262144 | min_latency | 0.333599 | 0.333599 | 131586 |
| unstructured | 262144 | min_latency | 0.167258 | 0.167258 | 262144 |
| structured | 262144 | min_time_to_first_rows | 0.721902 | 0.721902 | 131586 |
| unstructured | 262144 | min_time_to_first_rows | 0.227845 | 0.227845 | 262144 |

## Per-row detail

See JSONL input for `client_chosen_format`, `server_auto_chosen_format`, and errors.
