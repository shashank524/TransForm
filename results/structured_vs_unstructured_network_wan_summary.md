# Structured vs unstructured transport summary

## Run configuration

- **targets:** ['min_bytes', 'min_latency', 'min_time_to_first_rows']
- **nominal sizes (bytes):** [262144, 1048576, 5242880]
- **rows_per_chunk:** 8192
- **prefer_streaming:** True
- **network:** `{'net_profile': 'WAN', 'tc_dev': 'eth0', 'tc_delay': '40ms', 'tc_rate': '50mbit', 'tc_loss': '0%'}`

## Client path (describe + fetch) — median / p95 seconds

| payload_class | nominal_bytes | target | median_s | p95_s | median_client_bytes |
|---|---:|---|---:|---:|---:|
| structured | 1048576 | min_bytes | 0.770671 | 0.770671 | 517716 |
| unstructured | 1048576 | min_bytes | 0.576898 | 0.576898 | 1048576 |
| structured | 1048576 | min_latency | 0.642898 | 0.642898 | 517716 |
| unstructured | 1048576 | min_latency | 0.350029 | 0.350029 | 1048576 |
| structured | 1048576 | min_time_to_first_rows | 0.658434 | 0.658434 | 522295 |
| unstructured | 1048576 | min_time_to_first_rows | 0.311612 | 0.311612 | 1048576 |
| structured | 262144 | min_bytes | 0.482019 | 0.482019 | 131586 |
| unstructured | 262144 | min_bytes | 0.144341 | 0.144341 | 262144 |
| structured | 262144 | min_latency | 0.390309 | 0.390309 | 131586 |
| unstructured | 262144 | min_latency | 0.190105 | 0.190105 | 262144 |
| structured | 262144 | min_time_to_first_rows | 0.406951 | 0.406951 | 131586 |
| unstructured | 262144 | min_time_to_first_rows | 0.183225 | 0.183225 | 262144 |
| structured | 5242880 | min_bytes | 1.973638 | 1.973638 | 2828065 |
| unstructured | 5242880 | min_bytes | 0.799457 | 0.799457 | 5242880 |
| structured | 5242880 | min_latency | 1.767605 | 1.767605 | 2828065 |
| unstructured | 5242880 | min_latency | 0.472095 | 0.472095 | 5242880 |
| structured | 5242880 | min_time_to_first_rows | 2.354037 | 2.354037 | 2887375 |
| unstructured | 5242880 | min_time_to_first_rows | 0.926395 | 0.926395 | 5242880 |

## Per-row detail

See JSONL input for `client_chosen_format`, `server_auto_chosen_format`, and errors.
