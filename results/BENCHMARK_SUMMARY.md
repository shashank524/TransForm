# MCP + Parquet Benchmarks: Full Workflow Summary

## Setup

- **Data**: TPC-DS `catalog_sales` (SF=1) or synthetic slices.
- **Server**: MCP control plane (localhost:8000) + Parquet blob/stream data plane.
- **LLM**: ollama (Ollama / Llama 3.2) for format selection and summary.

## Workflow

1. **LLM format choice**: Ask the model which format to use (json, parquet_blob, parquet_stream) for the given table size.
2. **MCP + fetch**: Call the chosen tool and download/stream the result.
3. **LLM summary**: One-sentence summary of what the workflow did.

## Full-Workflow Results (with LLM)

| n_rows | n_cols | mode chosen | LLM format (s) | MCP+fetch (s) | LLM summary (s) | total (s) |
|--------|--------|-------------|----------------|---------------|-----------------|-----------|
| 1,000 | 6 | json | 0.51 | 0.05 | 0.00 | 0.60 |
| 10,000 | 6 | parquet_blob | 0.23 | 0.25 | 0.50 | 1.00 |
| 1,000 | 20 | json | 0.27 | 0.07 | 0.00 | 0.37 |
| 10,000 | 20 | parquet_blob | 0.25 | 0.02 | 0.52 | 0.81 |

**How to read this table**  
Do **not** compare “json” rows to “parquet_blob” rows as if they were the same workload. The rows with **smaller total time** (0.37 s, 0.60 s) are for **1,000 rows**—the LLM chose JSON because the payload is small. The rows with **larger total time** (0.81 s, 1.00 s) are for **10,000 rows**—the LLM chose Parquet so that MCP+fetch stays low (~0.02–0.25 s). If we had used JSON for 10k rows, MCP+fetch alone would be **several seconds** (see micro-benchmarks below). So: smaller totals = smaller *data*; Parquet is what keeps the 10k totals around ~1 s instead of much higher.

## Takeaways

- **Same size, Parquet wins**: For a given (n_rows, n_cols), Parquet is faster and smaller than JSON (see micro-benchmarks). The workflow table above mixes sizes (1k vs 10k), so the smaller totals are from smaller data, not from JSON being faster.
- **Format choice**: The LLM selects format based on table size; typically prefers Parquet (blob or stream) for larger shapes.
- **End-to-end time** is dominated by LLM calls (format + summary); MCP + data transfer is a small fraction when using Parquet.
- **Streaming** (parquet_stream) keeps time-to-first-rows low and allows the pipeline to overlap with downstream processing.

## Micro-benchmarks (no LLM)

For raw transfer comparison (JSON vs Parquet blob vs Parquet stream), run:

```bash
python bench.py
```

Those results show large payload and latency gains for Parquet over JSON (e.g. ~3× smaller payload, ~20–30× faster end-to-end for large tables, millisecond time-to-first-rows for streaming).

## Comparison tables: Regular vs New (hint-driven) selection

To generate tables comparing **regular** (rule-based `select_format`, no hints) vs **new** (Workflow A: `describe_result_formats` + `select_format_with_hints`) for `min_bytes` and `min_latency`:

```bash
# With server running: uvicorn server_app:app --reload
python bench_compare.py
```

This writes:

- **results/bench_compare_min_bytes.md** — table for `FORMAT_SELECT_TARGET=min_bytes` (format chosen, bytes, latency for regular vs new).
- **results/bench_compare_min_latency.md** — table for `FORMAT_SELECT_TARGET=min_latency`.
- **results/bench_compare.json** — same data as JSON for scripting.
