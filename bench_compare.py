"""
Compare regular (rule-based, no hints) vs new (hint-driven Workflow A) format selection.

Generates two markdown tables and optional JSON:
- results/bench_compare_min_bytes.md
- results/bench_compare_min_latency.md
- results/bench_compare.json

Usage (server running on localhost:8000):

    python bench_compare.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from client.mcp_client import (
    connect,
    call_describe_result_formats,
    DEFAULT_MCP_URL,
)
from format_selector import (
    OptimizationTarget,
    SelectionContext,
    select_format,
    select_format_with_hints,
)
from bench import (
    run_json_case,
    run_parquet_blob_case,
    run_parquet_stream_case,
    run_arrow_ipc_blob_case,
    run_arrow_ipc_stream_case,
)

RESULTS_DIR = Path(__file__).parent / "results"
DEFAULT_ROWS_PER_CHUNK = 8192

# Same grid as bench.py
ROW_SIZES = [10_000, 100_000]
COL_SIZES = [6, 20]


def _bytes_and_latency(metrics: Any) -> tuple[int, float]:
    """Extract (bytes, end_to_end_s) from any of the bench metrics."""
    if hasattr(metrics, "response_bytes"):
        return metrics.response_bytes, metrics.end_to_end_s
    if hasattr(metrics, "bytes_downloaded"):
        return metrics.bytes_downloaded, metrics.end_to_end_s
    if hasattr(metrics, "bytes_read"):
        return metrics.bytes_read, metrics.end_to_end_s
    return 0, 0.0


async def _run_mode(
    session: Any,
    client: Any,
    mode: str,
    n_rows: int,
    n_cols: int,
    rows_per_chunk: int,
) -> tuple[int, float]:
    """Run the given mode and return (bytes, latency_s)."""
    if mode == "json":
        m = await run_json_case(session, n_rows, n_cols)
    elif mode == "parquet_blob":
        m = await run_parquet_blob_case(session, client, n_rows, n_cols)
    elif mode == "arrow_ipc_blob":
        m = await run_arrow_ipc_blob_case(session, client, n_rows, n_cols)
    elif mode == "parquet_stream":
        m = await run_parquet_stream_case(
            session, client, n_rows, n_cols, rows_per_chunk=rows_per_chunk
        )
    elif mode == "arrow_ipc_stream":
        m = await run_arrow_ipc_stream_case(
            session, client, n_rows, n_cols, rows_per_chunk=rows_per_chunk
        )
    else:
        m = await run_parquet_stream_case(
            session, client, n_rows, n_cols, rows_per_chunk=rows_per_chunk
        )
    return _bytes_and_latency(m)


async def _run_comparison_for_target(
    session: Any,
    client: Any,
    target: OptimizationTarget,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for n_rows in ROW_SIZES:
        for n_cols in COL_SIZES:
            ctx = SelectionContext(n_rows=n_rows, n_cols=n_cols, target=target)

            # Regular: rule-based, no hints
            mode_regular = select_format(ctx)
            bytes_regular, latency_regular = await _run_mode(
                session, client, mode_regular, n_rows, n_cols, DEFAULT_ROWS_PER_CHUNK
            )

            # New: hint-driven
            hints = await call_describe_result_formats(
                session,
                n_rows,
                n_cols,
                optimization_target=target.value,
                prefer_streaming=ctx.prefer_streaming,
            )
            mode_new = (
                select_format_with_hints(ctx, hints) if hints else select_format(ctx)
            )
            bytes_new, latency_new = await _run_mode(
                session, client, mode_new, n_rows, n_cols, DEFAULT_ROWS_PER_CHUNK
            )

            rows.append({
                "n_rows": n_rows,
                "n_cols": n_cols,
                "regular_format": mode_regular,
                "regular_bytes": bytes_regular,
                "regular_latency_s": round(latency_regular, 4),
                "new_format": mode_new,
                "new_bytes": bytes_new,
                "new_latency_s": round(latency_new, 4),
            })
    return rows


def _write_markdown_table(rows: list[dict], target_label: str, path: Path) -> None:
    title = f"# Compare: Regular (rule-based) vs New (hint-driven) — FORMAT_SELECT_TARGET={target_label}"
    header = "| n_rows | n_cols | regular_format | regular_bytes | regular_latency_s | new_format | new_bytes | new_latency_s |"
    sep = "|--------|--------|----------------|---------------|-------------------|------------|-----------|----------------|"
    lines = [title, "", header, sep]
    for r in rows:
        lines.append(
            f"| {r['n_rows']} | {r['n_cols']} | {r['regular_format']} | {r['regular_bytes']} | {r['regular_latency_s']} | {r['new_format']} | {r['new_bytes']} | {r['new_latency_s']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main(mcp_url: str = DEFAULT_MCP_URL) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    async with connect(base_url=mcp_url) as (session, client):
        min_bytes_rows = await _run_comparison_for_target(
            session, client, OptimizationTarget.MIN_BYTES
        )
        min_latency_rows = await _run_comparison_for_target(
            session, client, OptimizationTarget.MIN_LATENCY
        )

    _write_markdown_table(
        min_bytes_rows,
        "min_bytes",
        RESULTS_DIR / "bench_compare_min_bytes.md",
    )
    _write_markdown_table(
        min_latency_rows,
        "min_latency",
        RESULTS_DIR / "bench_compare_min_latency.md",
    )
    (RESULTS_DIR / "bench_compare.json").write_text(
        json.dumps({"min_bytes": min_bytes_rows, "min_latency": min_latency_rows}, indent=2),
        encoding="utf-8",
    )

    print(
        "Wrote results/bench_compare_min_bytes.md, results/bench_compare_min_latency.md, results/bench_compare.json"
    )


if __name__ == "__main__":
    asyncio.run(main())
