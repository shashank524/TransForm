# Payload benchmarks (wire size) — recorded runs

This document complements latency-focused BIRD runs by documenting **on-the-wire bytes**: synthetic large grids, aggregate BIRD totals, and how to reproduce.

**Recorded:** 2026-03-31 (synthetic + full BIRD dev gold; same stack as [`BIRD_TRANSPORT_BENCHMARKS.md`](BIRD_TRANSPORT_BENCHMARKS.md)).

---

## 1. Synthetic tables (`bench.py`)

Controlled **(n_rows, n_cols)** with no SQLite. Measures JSON vs Parquet **blob** (and stream in JSONL) for **large** shapes where Parquet clearly wins on bytes.

```bash
uvicorn server_app:app --host 127.0.0.1 --port 8000
python bench.py --jsonl-out results/bench_synthetic_payload.jsonl
python summarize_bench_synthetic.py --input results/bench_synthetic_payload.jsonl
```

**Outcome (default `FORMAT_SELECT_TARGET=min_latency`):** JSON payload is **~2.7–2.9× larger** than Parquet blob for the same grid.

| n_rows | n_cols | JSON bytes | Parquet blob bytes | JSON / Parquet |
|--------|-------:|------------:|-------------------:|---------------:|
| 10,000 | 6 | 1,111,687 | 407,792 | 2.73× |
| 10,000 | 20 | 3,472,085 | 1,226,861 | 2.83× |
| 100,000 | 6 | 11,816,688 | 4,230,402 | 2.79× |
| 100,000 | 20 | 36,820,422 | 12,738,833 | 2.89× |

**Artifacts:** [`bench_synthetic_payload.jsonl`](bench_synthetic_payload.jsonl), [`bench_synthetic_payload_summary.md`](bench_synthetic_payload_summary.md).

---

## 2. BIRD mini-dev (500) — per-query payload + aggregates

[`bench_bird_e2e.py`](../bench_bird_e2e.py) records **`baseline_bytes`** (always JSON MCP response) and **`enhanced_bytes`** (one fetch: JSON, Parquet blob, or stream per selector). [`summarize_bird_e2e.py`](../summarize_bird_e2e.py) aggregates:

- Median / **p95** bytes (tiny medians; p95 shows larger answers).
- **Counts** where enhanced payload is smaller than baseline (Parquet chosen and smaller).
- **Sum of bytes** over all 500 successful transports (total “wire volume” for the run).

### Gold SQL, `FORMAT_SELECT_TARGET=min_latency` (default)

| Metric | Value |
|--------|------:|
| Median baseline / enhanced bytes | 78 / 78 |
| p95 baseline / enhanced bytes | 6,572 / 3,208 |
| Queries with equal bytes | 458 (enhanced also chose JSON) |
| Queries where enhanced payload is smaller than baseline | 42 |
| **Sum baseline bytes (500 queries)** | **3,936,866** |
| **Sum enhanced bytes (500 queries)** | **976,683** |

So: **median** hides tiny rows; **aggregate sum** shows ~**4.0×** less bytes on the enhanced arm for this full mini-dev pass (mostly small JSON, 42 larger Parquet wins).

**Artifacts:** [`bird_e2e_gold.jsonl`](bird_e2e_gold.jsonl), [`bird_e2e_gold_summary.md`](bird_e2e_gold_summary.md), [`bird_e2e_gold_summary.json`](bird_e2e_gold_summary.json).

### Gold SQL, `FORMAT_SELECT_TARGET=min_bytes`

Same SQL and questions; selector optimizes for **bytes** (`min_bytes`).

```bash
FORMAT_SELECT_TARGET=min_bytes python bench_bird_e2e.py --sql-source gold \
  --data-dir data/datasets/bird/dev --bird-questions mini_dev_sqlite.json \
  --max-queries 500 --overwrite --results results/bird_e2e_gold_min_bytes.jsonl
```

For this mini-dev split, **recommended_format counts matched** the `min_latency` run (458 JSON / 42 Parquet) — hints already favor smaller payload for these shapes. **Aggregate sums** match the min_latency run.

**Artifacts:** [`bird_e2e_gold_min_bytes.jsonl`](bird_e2e_gold_min_bytes.jsonl), [`bird_e2e_gold_min_bytes_summary.md`](bird_e2e_gold_min_bytes_summary.md).

---

## 3. BIRD dev full (`dev.json`, 1534) — per-query payload + aggregates

Gold SQL, `FORMAT_SELECT_TARGET=min_latency` (default), full dev split (unpack BIRD `dev.zip` into `data/datasets/bird/dev/` so `dev.json` and `dev_databases/` are present).

```bash
.venv/bin/python bench_bird_e2e.py --sql-source gold --data-dir data/datasets/bird/dev \
  --bird-questions dev.json --max-queries 1534 --overwrite \
  --results results/bird_e2e_dev_full_gold.jsonl
.venv/bin/python summarize_bird_e2e.py --input results/bird_e2e_dev_full_gold.jsonl \
  --md results/bird_e2e_dev_full_gold_summary.md --json-out results/bird_e2e_dev_full_gold_summary.json
```

| Metric | Value |
|--------|------:|
| Median baseline / enhanced bytes | 57 / 57 |
| p95 baseline / enhanced bytes | 11,966 / 3,650 |
| Queries with equal bytes | 1370 |
| Queries where enhanced payload is smaller than baseline | 164 |
| **Sum baseline bytes (1534 queries)** | **43,439,928** |
| **Sum enhanced bytes (1534 queries)** | **6,386,514** |

**Artifacts:** [`bird_e2e_dev_full_gold.jsonl`](bird_e2e_dev_full_gold.jsonl), [`bird_e2e_dev_full_gold_summary.md`](bird_e2e_dev_full_gold_summary.md), [`bird_e2e_dev_full_gold_summary.json`](bird_e2e_dev_full_gold_summary.json).

---

## 4. How to read “latency-only” vs “payload”

- **Latency tables** in `bird_e2e_*_summary.md` focus on **fetch seconds**; enhanced includes an extra **describe** call vs baseline.
- **Payload tables** compare **bytes** actually transferred for baseline JSON vs enhanced **chosen** format; use **sums** and **p95** for BIRD when medians are tiny.

---

## 5. Related

- [`docs/bird_transport_experiment.md`](../docs/bird_transport_experiment.md) — methodology (metrics definitions, limitations).
- [`BIRD_TRANSPORT_BENCHMARKS.md`](BIRD_TRANSPORT_BENCHMARKS.md) — full BIRD e2e run log (gold / jsonl / ollama).
- [`docs/nl2sql_benchmark.md`](../docs/nl2sql_benchmark.md) — reproduction commands.
