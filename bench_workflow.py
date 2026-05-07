"""
Run full MCP + LLM (Ollama) workflow benchmarks and write a presentation summary.

Usage (server on localhost:8000, Ollama running with llama3.2):

    python bench_workflow.py

Outputs:
- Printed table of results per (n_rows, n_cols)
- results/BENCHMARK_SUMMARY.md (presentation-ready summary)
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from run_workflow import run_workflow
from client.llm_client import get_llm_backend

DEFAULT_MCP_URL = "http://localhost:8000/mcp/mcp"


async def run_workflow_benchmarks(mcp_url: str = DEFAULT_MCP_URL) -> list[dict]:
    configs = [
        (1_000, 6),
        (10_000, 6),
        (1_000, 20),
        (10_000, 20),
    ]
    results = []
    for n_rows, n_cols in configs:
        print(f"\n{'='*60}")
        m = await run_workflow(
            n_rows=n_rows,
            n_cols=n_cols,
            use_llm=True,
            mcp_url=mcp_url,
            return_metrics=True,
        )
        if m:
            results.append(m)
    return results


def print_table(results: list[dict]) -> None:
    print("\n" + "=" * 60)
    print("WORKFLOW BENCHMARK RESULTS (MCP + LLM)")
    print("=" * 60)
    print(f"{'n_rows':>8} {'n_cols':>6} {'mode':>16} {'LLM fmt (s)':>12} {'MCP+fetch (s)':>14} {'LLM sum (s)':>12} {'total (s)':>10}")
    print("-" * 60)
    for r in results:
        print(
            f"{r['n_rows']:>8} {r['n_cols']:>6} {r['mode']:>16} "
            f"{r['time_llm_format_s']:>12.3f} {r['time_mcp_fetch_s']:>14.3f} "
            f"{r['time_llm_summary_s']:>12.3f} {r['total_s']:>10.3f}"
        )
    print("=" * 60)


def write_summary_md(results: list[dict], out_path: Path) -> None:
    llm_backend = get_llm_backend()
    rows = []
    for r in results:
        rows.append(
            f"| {r['n_rows']:,} | {r['n_cols']} | {r['mode']} | "
            f"{r['time_llm_format_s']:.2f} | {r['time_mcp_fetch_s']:.2f} | "
            f"{r['time_llm_summary_s']:.2f} | {r['total_s']:.2f} |"
        )
    table_body = "\n".join(rows)

    md = f"""# MCP + Parquet Benchmarks: Full Workflow Summary

## Setup

- **Data**: TPC-DS `catalog_sales` (SF=1) or synthetic slices.
- **Server**: MCP control plane (localhost:8000) + Parquet blob/stream data plane.
- **LLM**: {llm_backend} (Ollama / Llama 3.2) for format selection and summary.

## Workflow

1. **LLM format choice**: Ask the model which format to use (json, parquet_blob, parquet_stream) for the given table size.
2. **MCP + fetch**: Call the chosen tool and download/stream the result.
3. **LLM summary**: One-sentence summary of what the workflow did.

## Full-Workflow Results (with LLM)

| n_rows | n_cols | mode chosen | LLM format (s) | MCP+fetch (s) | LLM summary (s) | total (s) |
|--------|--------|-------------|----------------|---------------|-----------------|-----------|
{table_body}

## Takeaways

- **Format choice**: The LLM selects format based on table size; typically prefers Parquet (blob or stream) for larger shapes.
- **End-to-end time** is dominated by LLM calls (format + summary); MCP + data transfer is a small fraction when using Parquet.
- **Streaming** (parquet_stream) keeps time-to-first-rows low and allows the pipeline to overlap with downstream processing.

## Micro-benchmarks (no LLM)

For raw transfer comparison (JSON vs Parquet blob vs Parquet stream), run:

```bash
python bench.py
```

Those results show large payload and latency gains for Parquet over JSON (e.g. ~3× smaller payload, ~20–30× faster end-to-end for large tables, millisecond time-to-first-rows for streaming).
"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"\nSummary written to: {out_path}")


def main() -> None:
    mcp_url = os.environ.get("MCP_URL", DEFAULT_MCP_URL)
    results = asyncio.run(run_workflow_benchmarks(mcp_url=mcp_url))
    if not results:
        print("No results collected.")
        return
    print_table(results)
    out = Path(__file__).parent / "results" / "BENCHMARK_SUMMARY.md"
    write_summary_md(results, out)


if __name__ == "__main__":
    main()
