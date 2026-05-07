# TPC-DS format hints summary

- **Slices:** 9

## Size ratios

- **median(json/parquet)**: 24.149371206618625
- **p95(json/parquet)**: 30.4242855085175
- **median(json/arrow_ipc)**: 3.195118711003162
- **median(parquet/arrow_ipc)**: 0.13230649707879247

## Decode proxy (ns/byte)

- json: 4.798903748210889
- parquet_blob: 2.1649480231502274
- arrow_ipc_blob: 0.004414778779602035

This `decode_ns_per_byte` dict is directly usable as `FORMAT_LATENCY_CALIBRATION_JSON`.
