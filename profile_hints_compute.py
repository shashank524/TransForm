"""
In-process micro-profile of `_compute_tabular_size_hints` against real BIRD results.

Why: per-query `result_id` defeats the `@lru_cache` LRUs in server_app.py
(`_get_json_byte_size`, `_get_parquet_blob_bytes`, `_get_arrow_ipc_blob_bytes`),
so every `describe_result_formats` call falls through to a fresh JSON +
Parquet + Arrow IPC encode of the materialized DataFrame. This script isolates
that cost without HTTP / MCP-SDK noise.

Usage:

    .venv/bin/python profile_hints_compute.py \
        --bird-questions data/datasets/bird/dev/mini_dev_sqlite.json \
        --data-dir data/datasets/bird/dev \
        --max-queries 50 \
        --out-dir results/profiling/server_micro

Outputs (under --out-dir):
  - hints_compute.html         pyinstrument flamegraph
  - hints_compute.speedscope.json
  - hints_compute_summary.json (per-query bytes + per-encode timings)
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import uuid
from pathlib import Path
from typing import List

from pyinstrument import Profiler
from pyinstrument.renderers import SpeedscopeRenderer

import server_app
from bench_nl2sql_materialized import (
    bird_sql_for_sqlite,
    df_to_parquet_bytes,
    execute_sql_sqlite,
    resolve_bird_sqlite_path,
)


def _register_results(
    questions_path: Path,
    data_dir: Path,
    max_queries: int,
) -> List[str]:
    """Execute up to N BIRD gold queries, write Parquet, register in RESULT_REGISTRY."""
    server_app.MATERIALIZED_DIR.mkdir(parents=True, exist_ok=True)
    items = json.loads(questions_path.read_text(encoding="utf-8"))
    out: List[str] = []
    for item in items:
        if len(out) >= max_queries:
            break
        db_id = item.get("db_id", "")
        gold = item.get("SQL") or item.get("sql") or ""
        if not db_id or not gold:
            continue
        sqlite_path = resolve_bird_sqlite_path(data_dir, db_id)
        if sqlite_path is None:
            continue
        try:
            df = execute_sql_sqlite(str(sqlite_path), bird_sql_for_sqlite(gold))
        except Exception:
            continue
        if df is None or df.empty:
            continue
        try:
            pq_bytes = df_to_parquet_bytes(df)
        except Exception:
            continue
        rid = str(uuid.uuid4())
        path = server_app.MATERIALIZED_DIR / f"{rid}.parquet"
        path.write_bytes(pq_bytes)
        server_app.RESULT_REGISTRY[rid] = server_app.ResultConfig(
            n_rows=len(df),
            n_cols=len(df.columns),
            payload_kind="tabular",
            materialized_path=path,
        )
        out.append(rid)
    return out


def _time_call(fn, *args, **kwargs) -> tuple[float, dict]:
    t = time.perf_counter()
    res = fn(*args, **kwargs)
    return time.perf_counter() - t, res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--bird-questions",
        default="data/datasets/bird/dev/mini_dev_sqlite.json",
    )
    ap.add_argument("--data-dir", default="data/datasets/bird/dev")
    ap.add_argument("--max-queries", type=int, default=50)
    ap.add_argument("--rows-per-chunk", type=int, default=8192)
    ap.add_argument("--out-dir", default="results/profiling/server_micro")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Registering up to {args.max_queries} BIRD results...")
    rids = _register_results(
        Path(args.bird_questions), Path(args.data_dir), args.max_queries
    )
    print(f"Registered {len(rids)} result_ids.")
    if not rids:
        print("No results registered; aborting.")
        return

    comp = server_app._get_default_compression()
    enc_strat = server_app._get_default_encoding_strategy()
    ipc_comp = server_app._get_default_arrow_ipc_compression()

    print("Warm-up: one untimed pass to exercise imports / JIT paths...")
    server_app._compute_tabular_size_hints(
        n_rows=0,
        n_cols=0,
        rows_per_chunk=args.rows_per_chunk,
        result_id=rids[0],
        comp=comp,
        enc_strat=enc_strat,
        ipc_comp=ipc_comp,
    )

    print("Timed pass (per-query latency, no cache shortcut)...")
    per_query_ms: list[float] = []
    payloads: list[dict] = []
    for rid in rids:
        elapsed_s, hints = _time_call(
            server_app._compute_tabular_size_hints,
            n_rows=0,
            n_cols=0,
            rows_per_chunk=args.rows_per_chunk,
            result_id=rid,
            comp=comp,
            enc_strat=enc_strat,
            ipc_comp=ipc_comp,
        )
        per_query_ms.append(elapsed_s * 1000.0)
        payloads.append({
            "result_id": rid,
            "elapsed_ms": elapsed_s * 1000.0,
            "n_rows": int(hints.get("resolved_n_rows", 0)),
            "n_cols": int(hints.get("resolved_n_cols", 0)),
            "json_bytes": int(hints["json_bytes"]),
            "parquet_bytes": int(hints["parquet_bytes"]),
            "arrow_ipc_bytes": int(hints["arrow_ipc_bytes"]),
        })

    print("Profiled pass (pyinstrument)...")
    profiler = Profiler(interval=0.0005)
    profiler.start()
    for rid in rids:
        server_app._compute_tabular_size_hints(
            n_rows=0,
            n_cols=0,
            rows_per_chunk=args.rows_per_chunk,
            result_id=rid,
            comp=comp,
            enc_strat=enc_strat,
            ipc_comp=ipc_comp,
        )
    profiler.stop()

    # Second profile: full describe_result_formats() entry point (no HTTP / MCP framing)
    # to show the *upper bound* for "describe" work that is NOT transport.
    describe_profiler = Profiler(interval=0.0005)
    describe_profiler.start()
    for rid in rids:
        server_app.describe_result_formats(
            n_rows=0,
            n_cols=0,
            rows_per_chunk=args.rows_per_chunk,
            result_id=rid,
            optimization_target="min_latency",
            prefer_streaming=False,
        )
    describe_profiler.stop()
    (out_dir / "describe_inproc.html").write_text(
        describe_profiler.output_html(), encoding="utf-8",
    )
    (out_dir / "describe_inproc.txt").write_text(
        describe_profiler.output_text(unicode=True, color=False, show_all=False),
        encoding="utf-8",
    )
    (out_dir / "describe_inproc.speedscope.json").write_text(
        describe_profiler.output(renderer=SpeedscopeRenderer()),
        encoding="utf-8",
    )

    html_path = out_dir / "hints_compute.html"
    speedscope_path = out_dir / "hints_compute.speedscope.json"
    text_path = out_dir / "hints_compute.txt"
    html_path.write_text(profiler.output_html(), encoding="utf-8")
    speedscope_path.write_text(
        profiler.output(renderer=SpeedscopeRenderer()), encoding="utf-8"
    )
    text_path.write_text(
        profiler.output_text(unicode=True, color=False, show_all=False),
        encoding="utf-8",
    )

    summary = {
        "n_queries": len(rids),
        "median_ms": statistics.median(per_query_ms) if per_query_ms else None,
        "p95_ms": (
            statistics.quantiles(per_query_ms, n=20)[18]
            if len(per_query_ms) >= 20
            else max(per_query_ms)
            if per_query_ms
            else None
        ),
        "min_ms": min(per_query_ms) if per_query_ms else None,
        "max_ms": max(per_query_ms) if per_query_ms else None,
        "rows_per_chunk": args.rows_per_chunk,
        "parquet_compression": comp,
        "parquet_encoding_strategy": enc_strat,
        "arrow_ipc_compression": ipc_comp,
        "per_query": payloads,
    }
    (out_dir / "hints_compute_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    print(f"\nResults written to {out_dir}/")
    print(
        "Per-query _compute_tabular_size_hints latency (ms): "
        f"median={summary['median_ms']:.2f} "
        f"p95={summary['p95_ms']:.2f} "
        f"min={summary['min_ms']:.2f} max={summary['max_ms']:.2f}"
    )
    print(profiler.output_text(unicode=True, color=False, show_all=False))


if __name__ == "__main__":
    main()
