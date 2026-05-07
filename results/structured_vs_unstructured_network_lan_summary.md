# Structured vs unstructured transport summary

## Run configuration

- **targets:** ['min_bytes', 'min_latency', 'min_time_to_first_rows']
- **nominal sizes (bytes):** [262144, 1048576, 5242880]
- **rows_per_chunk:** 8192
- **prefer_streaming:** True
- **network:** `{'net_profile': 'LAN', 'tc_dev': 'eth0', 'tc_delay': '1ms', 'tc_rate': '1000mbit', 'tc_loss': '0%'}`

## Client path (describe + fetch) — median / p95 seconds

| payload_class | nominal_bytes | target | median_s | p95_s | median_client_bytes |
|---|---:|---|---:|---:|---:|
| structured | 1048576 | min_bytes | 0.531628 | 0.531628 | 517716 |
| unstructured | 1048576 | min_bytes | 0.034094 | 0.034094 | 1048576 |
| structured | 1048576 | min_latency | 0.320483 | 0.320483 | 517716 |
| unstructured | 1048576 | min_latency | 0.028506 | 0.028506 | 1048576 |
| structured | 1048576 | min_time_to_first_rows | 0.301541 | 0.301541 | 522295 |
| unstructured | 1048576 | min_time_to_first_rows | 0.020485 | 0.020485 | 1048576 |
| structured | 262144 | min_bytes | 0.267970 | 0.267970 | 131586 |
| unstructured | 262144 | min_bytes | 0.015639 | 0.015639 | 262144 |
| structured | 262144 | min_latency | 0.128955 | 0.128955 | 131586 |
| unstructured | 262144 | min_latency | 0.025325 | 0.025325 | 262144 |
| structured | 262144 | min_time_to_first_rows | 0.087886 | 0.087886 | 131586 |
| unstructured | 262144 | min_time_to_first_rows | 0.017480 | 0.017480 | 262144 |
| structured | 5242880 | min_bytes | 1.782239 | 1.782239 | 2828065 |
| unstructured | 5242880 | min_bytes | 0.056410 | 0.056410 | 5242880 |
| structured | 5242880 | min_latency | 1.372022 | 1.372022 | 2828065 |
| unstructured | 5242880 | min_latency | 0.056722 | 0.056722 | 5242880 |
| structured | 5242880 | min_time_to_first_rows | 1.341482 | 1.341482 | 2887375 |
| unstructured | 5242880 | min_time_to_first_rows | 0.034429 | 0.034429 | 5242880 |

## Per-row detail

See JSONL input for `client_chosen_format`, `server_auto_chosen_format`, and errors.
