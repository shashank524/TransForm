# BIRD MCP transport benchmarks — recorded runs

This document records **reproducible** runs of [`bench_bird_e2e.py`](../bench_bird_e2e.py) on **BIRD dev** with a local MCP server: **mini-dev (500)** and **full dev (`dev.json`, 1534)**. It supports the paper story: **fixed SQL** isolates **transport + client-side format selection + Parquet** vs **JSON baseline**; optional **Ollama NL2SQL** is a secondary track only.

**Recorded:** 2026-03-31 (full dev gold); mini-dev rows unchanged from 2026-03-30.  
**Environment:** macOS, localhost `127.0.0.1:8000` (uvicorn `server_app:app`), `FORMAT_SELECT_TARGET=min_latency` (default).  
**Datasets:** `data/datasets/bird/dev/` — `mini_dev_sqlite.json` (500) or `dev.json` (1534), plus `dev_databases/` (from BIRD `dev.zip` or equivalent layout).

---

## Commands (reproduction)

```bash
# Terminal 1
cd /path/to/MultiModalMCP && .venv/bin/uvicorn server_app:app --host 127.0.0.1 --port 8000

# Frozen file for jsonl mode (same SQL as gold, different code path)
jq -c '.[]' data/datasets/bird/dev/mini_dev_sqlite.json > results/bird_mini_dev_frozen.jsonl

# Core — gold SQL (default)
.venv/bin/python bench_bird_e2e.py --sql-source gold --data-dir data/datasets/bird/dev \
  --bird-questions mini_dev_sqlite.json --max-queries 500 --overwrite \
  --results results/bird_e2e_gold.jsonl

# Core — frozen JSONL (must match mini-dev keys)
.venv/bin/python bench_bird_e2e.py --sql-source jsonl \
  --frozen-sql results/bird_mini_dev_frozen.jsonl \
  --data-dir data/datasets/bird/dev --bird-questions mini_dev_sqlite.json \
  --max-queries 500 --overwrite --results results/bird_e2e_jsonl.jsonl

# Secondary — Ollama NL2SQL (small N; not for primary transport claims)
.venv/bin/python bench_bird_e2e.py --sql-source ollama \
  --data-dir data/datasets/bird/dev --bird-questions mini_dev_sqlite.json \
  --max-queries 25 --overwrite --results results/bird_e2e_ollama.jsonl

# Summaries
.venv/bin/python summarize_bird_e2e.py --input results/bird_e2e_gold.jsonl \
  --md results/bird_e2e_gold_summary.md --json-out results/bird_e2e_gold_summary.json
# (repeat for jsonl / ollama paths)

# Full dev (1534) — same stack, `dev.json` + `dev_databases/`
.venv/bin/python bench_bird_e2e.py --sql-source gold --data-dir data/datasets/bird/dev \
  --bird-questions dev.json --max-queries 1534 --overwrite \
  --results results/bird_e2e_dev_full_gold.jsonl
.venv/bin/python summarize_bird_e2e.py --input results/bird_e2e_dev_full_gold.jsonl \
  --md results/bird_e2e_dev_full_gold_summary.md --json-out results/bird_e2e_dev_full_gold_summary.json
```

---

## Run A — `--sql-source gold` (primary core evaluation)

| Metric | Value |
|--------|------:|
| Query records | 500 |
| Exec OK / registration OK / transport measured | 500 / 500 / 500 |
| NL2SQL | N/A (gold SQL only) |
| Median baseline fetch (JSON) | **6.08 ms** |
| p95 baseline fetch | 29.9 ms |
| Median enhanced fetch (chosen format) | 6.31 ms |
| Median describe + enhanced fetch | 11.9 ms |
| Median baseline bytes | 78 |
| Median enhanced bytes | 78 |
| Median ratio baseline_fetch / enhanced_fetch | ~1.02 |

**Enhanced `recommended_format`:** `json` 458, `parquet_blob` 42 (hint-driven under `min_latency`).

**Artifacts:** [`bird_e2e_gold.jsonl`](bird_e2e_gold.jsonl), [`bird_e2e_gold_summary.md`](bird_e2e_gold_summary.md), [`bird_e2e_gold_summary.json`](bird_e2e_gold_summary.json).

---

## Run B — `--sql-source jsonl` (frozen SQL file)

Same SQL strings as gold (exported via `jq` from `mini_dev_sqlite.json`). Validates the **jsonl join path**; numbers should match gold within localhost noise.

| Metric | Value |
|--------|------:|
| Query records | 500 |
| Exec OK / registration OK / transport measured | 500 / 500 / 500 |
| Frozen SQL missing | 0 |
| Median baseline fetch | **6.31 ms** |
| p95 baseline fetch | 42.4 ms |
| Median enhanced fetch | 6.48 ms |
| Median describe + enhanced fetch | 12.2 ms |
| Median baseline / enhanced bytes | 78 / 78 |
| `recommended_format` | `json` 458, `parquet_blob` 42 |

**Artifacts:** [`bird_mini_dev_frozen.jsonl`](bird_mini_dev_frozen.jsonl), [`bird_e2e_jsonl.jsonl`](bird_e2e_jsonl.jsonl), [`bird_e2e_jsonl_summary.md`](bird_e2e_jsonl_summary.md), [`bird_e2e_jsonl_summary.json`](bird_e2e_jsonl_summary.json).

---

## Run C — `--sql-source ollama` (secondary / appendix only)

**25 queries** from the start of the mini-dev list (first DB in file order). **Not** comparable to gold/jsonl for transport aggregates — mixes **NL2SQL quality** and long Ollama latency.

| Metric | Value |
|--------|------:|
| Query records | 25 |
| Exec OK | **12** |
| Exec failures (bad or empty SQL) | 13 |
| Transport measured | 12 |
| Median NL2SQL time | **0.79 s** |
| p95 NL2SQL time | 3.36 s |
| Median baseline fetch (successful runs) | 7.18 ms |

**Note:** The first Ollama call in this session incurred a **multi-minute** delay (model load / warm-up); subsequent calls were sub-second to a few seconds. For fair NL2SQL timing, document warm-up or discard the first query in future runs.

**Artifacts:** [`bird_e2e_ollama.jsonl`](bird_e2e_ollama.jsonl), [`bird_e2e_ollama_summary.md`](bird_e2e_ollama_summary.md), [`bird_e2e_ollama_summary.json`](bird_e2e_ollama_summary.json).

---

## Run D — Full dev (`dev.json`, 1534) — `--sql-source gold`

Same protocol as Run A on the **entire BIRD dev split** (all rows resolve to SQLite under `dev_databases/`).

| Metric | Value |
|--------|------:|
| Query records | 1534 |
| Exec OK / registration OK / transport measured | 1534 / 1534 / 1534 |
| Median baseline fetch (JSON) | **5.69 ms** |
| p95 baseline fetch | 43.3 ms |
| Median enhanced fetch (chosen format) | 5.39 ms |
| p95 enhanced fetch | 15.0 ms |
| Median describe + enhanced fetch | 10.3 ms |
| Median baseline / enhanced bytes | 57 / 57 |
| p95 baseline / enhanced bytes | 11,966 / 3,650 |

**Enhanced `recommended_format`:** `json` 1370, `parquet_blob` 164.

**Aggregate wire volume (sums over 1534 transports):** baseline **43,439,928** B vs enhanced **6,386,514** B (~**6.8×** less on the enhanced arm for this run).

**Artifacts:** [`bird_e2e_dev_full_gold.jsonl`](bird_e2e_dev_full_gold.jsonl), [`bird_e2e_dev_full_gold_summary.md`](bird_e2e_dev_full_gold_summary.md), [`bird_e2e_dev_full_gold_summary.json`](bird_e2e_dev_full_gold_summary.json).

---

## Interpretation (for the paper)

1. **Gold vs JSONL:** Identical SQL and near-identical transport stats — use **gold** as the default primary table; cite **jsonl** as “frozen SQL artifact” validation.
2. **Tiny results:** Median **78 B** JSON payloads — selector often keeps **JSON** for small tables; Parquet wins appear in larger row buckets (see stratified tables in [`summarize_nl2sql_materialized.py`](../summarize_nl2sql_materialized.py) runs if needed).
3. **Ollama run:** Illustrates **e2e agent flavor** only; many execution failures without `--allow-gold-fallback`. Do **not** blend these timings with core transport claims.

---

## See also

- [`docs/bird_transport_experiment.md`](../docs/bird_transport_experiment.md) — **methodology** for the paper (definitions, Mermaid diagrams, limitations).
- [`docs/nl2sql_benchmark.md`](../docs/nl2sql_benchmark.md) — full reproduction guide.
- Per-run caching discussion: bottom of each `bird_e2e_*_summary.md`.
