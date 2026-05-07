"""
Full workflow: MCP client + lightweight LLM.

1. Connect to the MCP server.
2. Choose transport format with heuristics only (MAB if enabled, else server hints, else rules).
3. Call the appropriate MCP tool (json / parquet_blob / parquet_stream / arrow_ipc_blob / arrow_ipc_stream).
4. Optionally have the LLM summarize or reason over a small sample (when use_llm is true).

Usage (server running on localhost:8000):

    # Ollama (free, local Llama): install Ollama, run `ollama run llama3.2`, then:
    python run_workflow.py

    # Deep Seek (set API key):
    LLM_BACKEND=deepseek DEEPSEEK_API_KEY=sk-... python run_workflow.py
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from io import BytesIO
from typing import Any, Dict, Optional

import pyarrow.ipc as ipc
import pyarrow.parquet as pq

from client.mcp_client import (
    connect,
    call_large_json,
    call_large_parquet_blob,
    call_large_parquet_stream,
    call_large_arrow_ipc_blob,
    call_large_arrow_ipc_stream,
    call_describe_result_formats,
    fetch_blob,
    fetch_stream_chunks,
    DEFAULT_MCP_URL,
)
from client.llm_client import chat, get_llm_backend
from format_selector import (
    SelectionContext,
    get_default_target,
    select_format,
    select_format_with_hints,
)
from format_mab import (
    load_mab_state,
    save_mab_state,
    select_format_with_mab,
    record_outcome,
    mab_enabled,
    DEFAULT_MAB_STATE_PATH,
)


async def run_workflow(
    n_rows: int = 1000,
    n_cols: int = 6,
    use_llm: bool = True,
    mcp_url: str = DEFAULT_MCP_URL,
    return_metrics: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Run full MCP + optional LLM summary workflow. Format is always chosen by
    heuristics (MAB / hints / rules), not the LLM. If return_metrics=True, returns
    a dict with mode, rows_seen, time_llm_format_s (always 0), time_mcp_fetch_s,
    time_llm_summary_s, total_s.
    """
    t_start = time.perf_counter()
    print(f"Workflow: n_rows={n_rows}, n_cols={n_cols}, use_llm={use_llm}")
    print(f"MCP URL: {mcp_url}")
    print(f"LLM backend: {get_llm_backend()}\n")

    mab_state = load_mab_state(DEFAULT_MAB_STATE_PATH) if mab_enabled() else None

    async with connect(base_url=mcp_url) as (session, client):
        # Step 1: decide format (MAB if enabled, else Workflow A: hint -> select_with_hints, else rule-based)
        ctx = SelectionContext(
            n_rows=n_rows,
            n_cols=n_cols,
            target=get_default_target(),
        )
        hints = await call_describe_result_formats(
            session,
            n_rows,
            n_cols,
            optimization_target=ctx.target.value,
            prefer_streaming=ctx.prefer_streaming,
        )
        if mab_state is not None:
            recommended = select_format_with_mab(ctx, hints, mab_state)
            print("Using MAB for format selection.")
        elif hints:
            recommended = select_format_with_hints(ctx, hints)
            print("Using hints from server for format selection.")
        else:
            recommended = select_format(ctx)
            print("No hints; using rule-based selection.")
        mode = recommended
        time_llm_format_s = 0.0  # format selection is heuristic-only; no LLM round trip

        print(f"Using mode: {mode} (heuristic)\n")

        # Step 2: call MCP and fetch data (capture bytes, latency, time_to_first_rows for outcome)
        t_mcp_start = time.perf_counter()
        response_bytes: Optional[int] = None
        time_to_first_rows_s: Optional[float] = None
        prefix_len = 8

        if mode == "json":
            data = await call_large_json(session, n_rows, n_cols)
            if isinstance(data, list):
                sample = data[:3]
                rows_seen = len(data)
            else:
                sample = data
                rows_seen = 0
            response_bytes = len(json.dumps(data).encode("utf-8"))
            print("JSON sample (first 3 rows):", json.dumps(sample, indent=2)[:500])
        elif mode == "parquet_blob":
            desc = await call_large_parquet_blob(session, n_rows, n_cols)
            raw = await fetch_blob(client, desc["url"])
            response_bytes = len(raw)
            table = pq.read_table(BytesIO(raw))
            rows_seen = table.num_rows
            print(f"Parquet blob: {rows_seen} rows, {len(raw)} bytes")
        elif mode == "arrow_ipc_blob":
            desc = await call_large_arrow_ipc_blob(session, n_rows, n_cols)
            raw = await fetch_blob(client, desc["url"])
            response_bytes = len(raw)
            reader = ipc.open_file(BytesIO(raw))
            table = reader.read_all()
            rows_seen = table.num_rows
            print(f"Arrow IPC blob: {rows_seen} rows, {len(raw)} bytes")
        elif mode == "parquet_stream":
            rows_per_chunk = min(8192, n_rows)
            desc = await call_large_parquet_stream(
                session, n_rows, n_cols, rows_per_chunk
            )
            rows_seen = 0
            chunk_count = 0
            total_stream_bytes = 0
            async for chunk in fetch_stream_chunks(client, desc["url"], length_prefix_bytes=prefix_len):
                if time_to_first_rows_s is None:
                    time_to_first_rows_s = time.perf_counter() - t_mcp_start
                total_stream_bytes += prefix_len + len(chunk)
                table = pq.read_table(BytesIO(chunk))
                rows_seen += table.num_rows
                chunk_count += 1
                if chunk_count == 1:
                    print(f"First chunk: {table.num_rows} rows")
            response_bytes = total_stream_bytes
            print(f"Parquet stream: {rows_seen} rows in {chunk_count} chunks")
        else:
            # arrow_ipc_stream
            rows_per_chunk = min(8192, n_rows)
            desc = await call_large_arrow_ipc_stream(
                session, n_rows, n_cols, rows_per_chunk
            )
            rows_seen = 0
            chunk_count = 0
            total_stream_bytes = 0
            async for chunk in fetch_stream_chunks(client, desc["url"], length_prefix_bytes=prefix_len):
                if time_to_first_rows_s is None:
                    time_to_first_rows_s = time.perf_counter() - t_mcp_start
                total_stream_bytes += prefix_len + len(chunk)
                reader = ipc.open_file(BytesIO(chunk))
                table = reader.read_all()
                rows_seen += table.num_rows
                chunk_count += 1
                if chunk_count == 1:
                    print(f"First chunk: {table.num_rows} rows")
            response_bytes = total_stream_bytes
            print(f"Arrow IPC stream: {rows_seen} rows in {chunk_count} chunks")

        time_mcp_fetch_s = time.perf_counter() - t_mcp_start

        # Step 3: optional LLM summary over a tiny description
        time_llm_summary_s = 0.0
        if use_llm and rows_seen > 0:
            try:
                t_summary_start = time.perf_counter()
                summary_prompt = (
                    f"The user just requested a table with {n_rows} rows and {n_cols} columns "
                    f"and received {rows_seen} rows via {mode}. "
                    "In one short sentence, say what this workflow did."
                )
                reply = await chat([{"role": "user", "content": summary_prompt}])
                time_llm_summary_s = time.perf_counter() - t_summary_start
                print("\nLLM summary:", reply.strip())
            except Exception as e:
                print("\nLLM summary skipped:", e)

    total_s = time.perf_counter() - t_start
    print("\nWorkflow done.")

    # Record outcome for MAB (and history); use latency as proxy for time_to_first_rows when not stream
    if time_to_first_rows_s is None:
        time_to_first_rows_s = time_mcp_fetch_s
    outcome = {
        "bytes": response_bytes,
        "latency_s": time_mcp_fetch_s,
        "time_to_first_rows_s": time_to_first_rows_s,
    }
    record_outcome(ctx, mode, outcome, mab_state=mab_state)
    if mab_state is not None:
        save_mab_state(mab_state, DEFAULT_MAB_STATE_PATH)

    if return_metrics:
        return {
            "n_rows": n_rows,
            "n_cols": n_cols,
            "mode": mode,
            "rows_seen": rows_seen,
            "bytes": response_bytes,
            "time_llm_format_s": time_llm_format_s,
            "time_mcp_fetch_s": time_mcp_fetch_s,
            "time_to_first_rows_s": time_to_first_rows_s,
            "time_llm_summary_s": time_llm_summary_s,
            "total_s": total_s,
        }
    return None


def main() -> None:
    mcp_url = os.environ.get("MCP_URL", DEFAULT_MCP_URL)
    asyncio.run(
        run_workflow(
            n_rows=1000,
            n_cols=6,
            use_llm=os.environ.get("USE_LLM", "1").strip().lower() in ("1", "true", "yes"),
            mcp_url=mcp_url,
        )
    )


if __name__ == "__main__":
    main()
