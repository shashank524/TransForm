# NL2SQL Materialized Benchmark — Reproduction Guide

This document explains how to download each dataset, configure the environment,
and run the end-to-end materialized benchmark that measures JSON vs Parquet-blob
vs Parquet-stream delivery of real SQL query results.

## Quick Start

```bash
# 1. Start the MCP + HTTP server
uvicorn server_app:app --reload

# 2. Download a dataset (e.g. Spider 1.0)
bash scripts/prepare_spider.sh

# 3. Run the benchmark
python bench_nl2sql_materialized.py \
    --dataset spider \
    --data-dir data/datasets/spider \
    --max-queries 100 \
    -v

# Results are appended to results/nl2sql_materialized.jsonl
```

## BIRD transport (`bench_bird_e2e.py`) — core vs optional NL2SQL

[`bench_bird_e2e.py`](../bench_bird_e2e.py) measures **MCP transport** on real BIRD result shapes. **Core evaluation** uses **fixed SQL** so bytes/latency are not confounded with model quality. For **methodology** (isolation, metrics, diagrams, limitations) see **[`bird_transport_experiment.md`](bird_transport_experiment.md)**.

| `--sql-source` | Behavior |
|----------------|----------|
| **`gold`** (default) | Execute BIRD **gold** SQL from the questions JSON (`SQL` field). No NL2SQL. |
| **`jsonl`** | Execute SQL from a **frozen** file (JSONL or JSON array): each row has `question_id`, `db_id`, and `sql` or `SQL` — e.g. predictions saved from an earlier offline run. |
| **`ollama`** | **Secondary / appendix:** Ollama NL2SQL from question + schema excerpt, then same execute → register → baseline vs enhanced. |

Then: SQLite execute → `POST /materialized` → **baseline** (`large_json` only) vs **enhanced** (`describe_result_formats` + heuristic format choice + one fetch). Client-side format selection does **not** use an LLM.

Optional **`--with-summary`**: one extra LLM call on a fixed row sample (requires Ollama/DeepSeek when enabled).

```bash
uvicorn server_app:app --host 127.0.0.1 --port 8000

# Core: gold SQL (default) — no Ollama required
python bench_bird_e2e.py \
  --sql-source gold \
  --data-dir data/datasets/bird/dev \
  --bird-questions mini_dev_sqlite.json \
  --max-queries 500 \
  --overwrite

# Core: frozen SQL artifact
python bench_bird_e2e.py --sql-source jsonl --frozen-sql path/to/preds.jsonl ...

# Secondary: model-generated SQL (small subset recommended)
python bench_bird_e2e.py --sql-source ollama --max-queries 30

python summarize_bird_e2e.py
```

**Recorded benchmark outputs** (mini-dev, gold / jsonl / optional Ollama): [results/BIRD_TRANSPORT_BENCHMARKS.md](../results/BIRD_TRANSPORT_BENCHMARKS.md).

**Payload (wire bytes)** — synthetic large grids + BIRD aggregate byte sums: [results/PAYLOAD_BENCHMARKS.md](../results/PAYLOAD_BENCHMARKS.md). Run `python bench.py --jsonl-out results/bench_synthetic_payload.jsonl` then `python summarize_bench_synthetic.py`.

Other flags: `--allow-gold-fallback` (only useful with `--sql-source ollama`: if generated SQL fails, run gold SQL for transport), `--arms baseline|enhanced|both`.

**Caching / fairness:** For materialized `result_id`, server-side LRU helpers used for *synthetic* hints are **not** used; see `results/bird_e2e_summary.md` after summarizing.

| Variable | Description |
|----------|-------------|
| `LLM_BACKEND` | `ollama` (default) or `deepseek` — used for `--sql-source ollama` and/or `--with-summary` |
| `OLLAMA_MODEL` | Model tag for `/api/chat` (default `llama3.2`) |
| `OLLAMA_BASE_URL` | Default `http://localhost:11434` |

## Datasets

| Dataset   | Engine  | Prep script                     | Disk size (approx) | Notes |
|-----------|---------|---------------------------------|--------------------|-------|
| BIRD      | SQLite  | `scripts/prepare_bird.sh`, `scripts/fetch_bird_minidev.sh` | full dev ~2–33 GB; **Mini-Dev ~760 MB** | Full dev: [bird-bench.github.io](https://bird-bench.github.io/). **Mini-Dev (500):** clone [bird-bench/mini_dev](https://github.com/bird-bench/mini_dev), then `bash scripts/fetch_bird_minidev.sh` — see [data/datasets/bird/README_BIRD_MINIDEV.md](data/datasets/bird/README_BIRD_MINIDEV.md). |
| Spider    | SQLite  | `scripts/prepare_spider.sh`     | ~1 GB              | Auto-downloads from the official Google Drive link. Set `SPIDER_URL` to override. |
| WikiSQL   | SQLite  | `scripts/prepare_wikisql.sh`    | ~0.5 GB            | Auto-downloads from GitHub. Per-table SQLite DBs built on-the-fly by the benchmark runner under `wikisql_tmp/`. |
| SQLStorm  | DuckDB* | `scripts/prepare_sqlstorm.sh`   | varies             | Clones the [SQL-Storm/SQLStorm](https://github.com/SQL-Storm/SQLStorm) repo. Full integration requires loading schema data. Set `SKIP_SQLSTORM=1` to skip. |

### BIRD — Database Engine Choice

BIRD was designed for MySQL. This benchmark uses a **community SQLite port** for
simplicity: each database is stored as `dev_databases/<db_id>/<db_id>.sqlite`.
The runner also checks `data/datasets/bird/minidev/MINIDEV/dev_databases/` when
`--data-dir` is `bird/dev`, and honors `BIRD_SQLITE_ROOT` (folder containing
`dev_databases/`).

**Mini-Dev (500):** use `--bird-questions mini_dev_sqlite.json` (symlinked next
to `dev.json` when you follow `README_BIRD_MINIDEV.md`). Gold SQL uses backticks;
the runner normalizes them for SQLite.

If you need MySQL parity, run the official Docker MySQL setup from the BIRD
README and adjust `--engine mysql` in the benchmark runner (not yet exposed as CLI;
add `engine="mysql"` support to `execute_sql_*` if needed).

### WikiSQL — Per-Table DB Build

WikiSQL stores tables as JSON lines. The benchmark runner creates one SQLite file
per `table_id` under `data/datasets/wikisql/wikisql_tmp/`. This directory can
grow to several hundred MB for the full dataset. Use `--max-queries` to limit.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PARQUET_COMPRESSION` | `snappy` | Parquet compression codec (snappy, gzip, zstd, brotli, lz4, none). |
| `PARQUET_ENCODING_STRATEGY` | `default` | `default` or `data_driven` (column-level encoding selection). |
| `FORMAT_SELECT_TARGET` | `min_latency` | Optimization target: `min_bytes`, `min_latency`, `min_time_to_first_rows`. |
| `FORMAT_SELECT_MAB` | *(unset)* | Set to `1` to enable multi-armed-bandit format selection. |
| `FORMAT_SELECT_EPSILON` | `0.1` | Epsilon for epsilon-greedy MAB exploration. |
| `MCP_API_KEY` | *(unset)* | When set, all HTTP requests require `Authorization: Bearer <key>`. |
| `BIRD_DEV_URL` | *(unset)* | URL for automated BIRD dev download (used by `prepare_bird.sh`). |
| `BIRD_SQLITE_ROOT` | *(unset)* | Path to a folder that contains `dev_databases/<db_id>/<db_id>.sqlite` (e.g. Mini-Dev `MINIDEV`). |
| `BIRD_MINIDEV_URL` | Alibaba zip URL | Override URL for `fetch_bird_minidev.sh`. |
| `SPIDER_URL` | Google Drive link | Override Spider 1.0 download URL. |
| `WIKISQL_URL` | GitHub raw link | Override WikiSQL archive URL. |
| `SKIP_SQLSTORM` | `0` | Set to `1` to skip SQLStorm dataset. |

## File Layout

```
data/
  datasets/
    bird/dev/
      dev.json
      mini_dev_sqlite.json   ← symlink to minidev/MINIDEV/ (optional)
      dev_databases/<db_id>/<db_id>.sqlite   ← or use minidev layout below
    bird/minidev/MINIDEV/    ← from fetch_bird_minidev.sh / official zip
      dev_databases/<db_id>/<db_id>.sqlite
      mini_dev_sqlite.json
    spider/
      dev.json
      database/<db_id>/<db_id>.sqlite
    wikisql/
      dev.jsonl
      dev.tables.jsonl
      wikisql_tmp/<table_id>.sqlite   ← built on-the-fly
    sqlstorm/
      repo/                           ← cloned from GitHub
      queries/
  materialized/
    <uuid>.parquet                    ← registered via POST /materialized
results/
  nl2sql_materialized.jsonl           ← gold-SQL transport benchmark
  bird_e2e*.jsonl                    ← gold / jsonl / ollama runs (see BIRD_TRANSPORT_BENCHMARKS.md)
  BIRD_TRANSPORT_BENCHMARKS.md      ← recorded runs + interpretation
  PAYLOAD_BENCHMARKS.md             ← synthetic + BIRD byte aggregates
scripts/
  prepare_bird.sh
  fetch_bird_minidev.sh
  prepare_spider.sh
  prepare_wikisql.sh
  prepare_sqlstorm.sh
```

## Output Schema (JSONL)

Each line in `results/nl2sql_materialized.jsonl` is a JSON object with:

| Field | Type | Description |
|-------|------|-------------|
| `dataset` | string | `bird`, `spider`, or `wikisql` |
| `question_id` | string | Identifier from the dataset |
| `db_id` | string | Database identifier |
| `sql` | string | The executed SQL query |
| `n_rows` | int | Rows in the result DataFrame |
| `n_cols` | int | Columns in the result DataFrame |
| `result_id` | string | UUID from POST /materialized |
| `recommended_format` | string | Format chosen by the selector |
| `json_end_to_end_s` | float? | End-to-end time for JSON delivery |
| `json_response_bytes` | int? | JSON payload size in bytes |
| `parquet_blob_end_to_end_s` | float? | End-to-end time for Parquet blob |
| `parquet_blob_bytes` | int? | Parquet blob size in bytes |
| `parquet_stream_end_to_end_s` | float? | End-to-end time for Parquet stream |
| `parquet_stream_time_to_first_rows_s` | float? | Time to first decoded chunk |
| `parquet_stream_bytes` | int? | Total stream bytes read |
| `parquet_stream_rows_per_chunk` | int? | Chunk size used for streaming |
| `sql_exec_s` | float? | Local SQL execution time |
| `register_s` | float? | Encode to Parquet + `POST /materialized` |
| `describe_result_formats_s` | float? | MCP hint tool latency |
| `recommended_end_to_end_s` | float? | Fetch time for `recommended_format` only |
| `recommended_bytes` | int? | Payload bytes for `recommended_format` |
| `error` | string? | Error message if a step failed |

Aggregate with:

```bash
python summarize_nl2sql_materialized.py
```

Writes `results/nl2sql_materialized_summary.md` and `.json`. Use `python bench_nl2sql_materialized.py ... --overwrite` for a clean JSONL run.

## Server Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/materialized` | Register a Parquet blob; returns `{result_id, n_rows, n_cols}` |
| GET | `/blobs/{id}.parquet` | Download Parquet blob for result |
| GET | `/streams/{id}` | Length-prefixed Parquet chunk stream |
| POST | `/mcp/mcp` | MCP control plane (tools: `large_json`, `large_parquet_blob`, `large_parquet_stream`, `describe_result_formats`) |

All MCP tools accept an optional `result_id` parameter. When provided, the tool
operates on the registered materialized data instead of generating synthetic data.
