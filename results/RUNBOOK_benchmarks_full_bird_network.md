# Benchmark runbook: full BIRD + (planned) network shaping

This file documents the benchmark commands and output artifacts produced in this repo for:
- TPC-DS format hint reference table (preliminary)
- TPC-DS codec/compression ablation (`bench_codec.py`)
- Full BIRD dev split end-to-end benchmarks (server executes SQL) for:
  - baseline JSON (inline)
  - client-side selection (`describe_result_formats` + `large_*`)
  - server-side one-shot auto selection (`bird_query_auto` → `large_result_auto`)

## Environment

### Local (conda)
- Env: `multimodal-mcp` created from `environment.yml`

### Docker network shaping (tc netem)
Files added to support reproducible shaping:
- `Dockerfile`
- `docker-compose.yml`
- `scripts/tc_apply.sh`

**Important:** Docker network-shaping runs require the Docker daemon to be running. If Docker Desktop isn’t running, `docker compose build/run` will fail.

## TPC-DS: format hint reference table

Input:
- `data/tpcds_catalog_sales_sf1.parquet`

Command:

```bash
conda run -n multimodal-mcp python bench_tpcds_format_hints.py --tpcds data/tpcds_catalog_sales_sf1.parquet
conda run -n multimodal-mcp python summarize_tpcds_format_hints.py
conda run -n multimodal-mcp python plot_tpcds_format_hints.py
```

Outputs:
- `results/tpcds_format_hints.json`
- `results/tpcds_format_hints.md`
- `results/tpcds_format_hints_summary.json`
- `results/tpcds_format_hints_summary.md`
- `results/format_latency_calibration_tpcds.json`
- `results/figures/fig_A1_tpcds_size_scaling.(png|pdf)`
- `results/figures/fig_A2_tpcds_first_chunk_bytes.(png|pdf)`
- `results/figures/fig_A3_tpcds_decode_ns_per_byte.(png|pdf)`

## TPC-DS: codec/compression ablation (`bench_codec.py`)

Command:

```bash
conda run -n multimodal-mcp python bench_codec.py --tpcds data/tpcds_catalog_sales_sf1.parquet
conda run -n multimodal-mcp python summarize_bench_codec_tpcds.py
conda run -n multimodal-mcp python plot_bench_codec_tpcds.py
```

Outputs:
- `results/bench_codec_tpcds.json`
- `results/bench_codec_tpcds.md`
- `results/bench_codec_tpcds_pareto.json`
- `results/bench_codec_tpcds_pareto.md`
- `results/figures/fig_C1_codec_bytes_bars.(png|pdf)`
- `results/figures/fig_C2_codec_tradeoff_scatter.(png|pdf)`

## Full BIRD dev: end-to-end format-selection benchmarks

Dataset:
- Questions: `data/datasets/bird/dev/dev.json` (1534 queries)
- SQLite DB resolution uses `BIRD_SQLITE_ROOT` (points at `.../data/datasets/bird/dev`).

### Server settings used for stability
- `SQLITE_QUERY_TIMEOUT_S=30` (server-side interrupt for pathological SQL)

### Regime A: capped baseline (production-feasible)
Baseline inline JSON may fail for very large results due to JSON cell cap.

Server start:

```bash
export BIRD_SQLITE_ROOT="$PWD/data/datasets/bird/dev"
export SQLITE_QUERY_TIMEOUT_S=30
conda run -n multimodal-mcp uvicorn server_app:app --host 127.0.0.1 --port 8000
```

Client runs (each produces one JSONL file with 1534 records + 1 header line):

```bash
export PARQUET_ENCODING_STRATEGY=data_driven
export PARQUET_COMPRESSION=snappy
export ARROW_IPC_COMPRESSION=none

# min_bytes (rpc=8192)
conda run -n multimodal-mcp python bench_bird_server_exec_e2e.py \
  --bird-questions dev.json --max-queries 0 \
  --targets min_bytes --rows-per-chunk-list 8192 --overwrite

# min_latency (rpc=8192)
conda run -n multimodal-mcp python bench_bird_server_exec_e2e.py \
  --bird-questions dev.json --max-queries 0 \
  --targets min_latency --rows-per-chunk-list 8192 --overwrite

# min_time_to_first_rows (prefer_streaming) for multiple chunk sizes
conda run -n multimodal-mcp python bench_bird_server_exec_e2e.py \
  --bird-questions dev.json --max-queries 0 \
  --targets min_time_to_first_rows --rows-per-chunk-list 2048,8192,32768 \
  --prefer-streaming --overwrite
```

Outputs (created by the benchmark runner):
- `results/bird_server_exec_e2e_min_bytes_rpc8192.jsonl`
- `results/bird_server_exec_e2e_min_latency_rpc8192.jsonl`
- `results/bird_server_exec_e2e_min_time_to_first_rows_rpc2048.jsonl`
- `results/bird_server_exec_e2e_min_time_to_first_rows_rpc8192.jsonl`
- `results/bird_server_exec_e2e_min_time_to_first_rows_rpc32768.jsonl`

Per-run summaries:

```bash
conda run -n multimodal-mcp python summarize_bird_server_exec_e2e.py --input results/bird_server_exec_e2e_min_bytes_rpc8192.jsonl
conda run -n multimodal-mcp python summarize_bird_server_exec_e2e.py --input results/bird_server_exec_e2e_min_latency_rpc8192.jsonl
conda run -n multimodal-mcp python summarize_bird_server_exec_e2e.py --input results/bird_server_exec_e2e_min_time_to_first_rows_rpc2048.jsonl
conda run -n multimodal-mcp python summarize_bird_server_exec_e2e.py --input results/bird_server_exec_e2e_min_time_to_first_rows_rpc8192.jsonl
conda run -n multimodal-mcp python summarize_bird_server_exec_e2e.py --input results/bird_server_exec_e2e_min_time_to_first_rows_rpc32768.jsonl
```

Figures (suffix by input stem to avoid overwrites):

```bash
conda run -n multimodal-mcp python plot_bird_server_exec_e2e.py --inputs \
  "results/bird_server_exec_e2e_min_bytes_rpc8192.jsonl,\
results/bird_server_exec_e2e_min_latency_rpc8192.jsonl,\
results/bird_server_exec_e2e_min_time_to_first_rows_rpc2048.jsonl,\
results/bird_server_exec_e2e_min_time_to_first_rows_rpc8192.jsonl,\
results/bird_server_exec_e2e_min_time_to_first_rows_rpc32768.jsonl"
```

Key figure families:
- `fig_B1_bird_latency_paired_<run>.{png,pdf}`
- `fig_B3_bird_overhead_breakdown_<run>.{png,pdf}`
- `fig_S1_baseline_failure_rate_<run>.{png,pdf}`
- `fig_S2_ttfr_cdf_<run>.{png,pdf}`

### Regime B: uncapped baseline (benchmark-only)
Disable JSON cap on the server:

```bash
export DISABLE_JSON_CAP=1
export BIRD_SQLITE_ROOT="$PWD/data/datasets/bird/dev"
export SQLITE_QUERY_TIMEOUT_S=30
conda run -n multimodal-mcp uvicorn server_app:app --host 127.0.0.1 --port 8000
```

Client runs (explicit output paths):

```bash
conda run -n multimodal-mcp python bench_bird_server_exec_e2e.py \
  --bird-questions dev.json --max-queries 0 \
  --targets min_bytes --rows-per-chunk-list 8192 \
  --results results/bird_server_exec_e2e_uncapped_min_bytes_rpc8192.jsonl --overwrite

conda run -n multimodal-mcp python bench_bird_server_exec_e2e.py \
  --bird-questions dev.json --max-queries 0 \
  --targets min_latency --rows-per-chunk-list 8192 \
  --results results/bird_server_exec_e2e_uncapped_min_latency_rpc8192.jsonl --overwrite

conda run -n multimodal-mcp python bench_bird_server_exec_e2e.py \
  --bird-questions dev.json --max-queries 0 \
  --targets min_time_to_first_rows --rows-per-chunk-list 2048,8192,32768 \
  --prefer-streaming \
  --results results/bird_server_exec_e2e_uncapped_ttfr.jsonl --overwrite
```

Summaries and plots:

```bash
conda run -n multimodal-mcp python summarize_bird_server_exec_e2e.py --input results/bird_server_exec_e2e_uncapped_min_bytes_rpc8192.jsonl
conda run -n multimodal-mcp python summarize_bird_server_exec_e2e.py --input results/bird_server_exec_e2e_uncapped_min_latency_rpc8192.jsonl
conda run -n multimodal-mcp python summarize_bird_server_exec_e2e.py --input results/bird_server_exec_e2e_uncapped_ttfr.jsonl

conda run -n multimodal-mcp python plot_bird_server_exec_e2e.py --inputs \
  "results/bird_server_exec_e2e_uncapped_min_bytes_rpc8192.jsonl,\
results/bird_server_exec_e2e_uncapped_min_latency_rpc8192.jsonl,\
results/bird_server_exec_e2e_uncapped_ttfr.jsonl"
```

## Network shaping (Docker) — how to run

If Docker Desktop/daemon is running:

```bash
# Example: WAN profile, streaming target
NET_PROFILE=WAN FORMAT_SELECT_TARGET=min_time_to_first_rows docker compose run --rm client

# Uncapped baseline regime
DISABLE_JSON_CAP=1 NET_PROFILE=Cellular docker compose run --rm client
```

The `scripts/tc_apply.sh` output prints the effective delay/rate/loss and the benchmark runner records `network` fields in the JSONL header when `NET_PROFILE`/`TC_*` are present.

