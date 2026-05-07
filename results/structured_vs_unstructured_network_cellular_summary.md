# Structured vs unstructured transport summary

## Run configuration

- **targets:** ['min_bytes', 'min_latency', 'min_time_to_first_rows']
- **nominal sizes (bytes):** [262144, 1048576, 5242880]
- **rows_per_chunk:** 8192
- **prefer_streaming:** True
- **network:** `{'net_profile': 'Cellular', 'tc_dev': 'eth0', 'tc_delay': '80ms', 'tc_rate': '10mbit', 'tc_loss': '0.1%'}`

## Client path (describe + fetch) — median / p95 seconds

| payload_class | nominal_bytes | target | median_s | p95_s | median_client_bytes |
|---|---:|---|---:|---:|---:|
| structured | 1048576 | min_bytes | 1.025570 | 1.025570 | 517716 |
| unstructured | 1048576 | min_bytes | 0.545732 | 0.545732 | 1048576 |
| structured | 1048576 | min_latency | 0.998667 | 0.998667 | 517716 |
| unstructured | 1048576 | min_latency | 0.525389 | 0.525389 | 1048576 |
| structured | 1048576 | min_time_to_first_rows | 0.997201 | 0.997201 | 522295 |
| unstructured | 1048576 | min_time_to_first_rows | 0.522778 | 0.522778 | 1048576 |
| structured | 262144 | min_bytes | 0.797478 | 0.797478 | 131586 |
| unstructured | 262144 | min_bytes | 0.267368 | 0.267368 | 262144 |
| structured | 262144 | min_latency | 0.651525 | 0.651525 | 131586 |
| unstructured | 262144 | min_latency | 0.268831 | 0.268831 | 262144 |
| structured | 262144 | min_time_to_first_rows | 0.660187 | 0.660187 | 131586 |
| unstructured | 262144 | min_time_to_first_rows | 0.267930 | 0.267930 | 262144 |
| structured | 5242880 | min_bytes | 2.163884 | 2.163884 | 2828065 |
| unstructured | 5242880 | min_bytes | 0.964733 | 0.964733 | 5242880 |
| structured | 5242880 | min_latency | 2.150344 | 2.150344 | 2828065 |
| unstructured | 5242880 | min_latency | 0.963184 | 0.963184 | 5242880 |
| structured | 5242880 | min_time_to_first_rows | 1.874025 | 1.874025 | 2887375 |

## Per-row detail

See JSONL input for `client_chosen_format`, `server_auto_chosen_format`, and errors.
