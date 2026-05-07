"""
End-to-end benchmarks for large MCP tool outputs.

Usage (from project root, with server running on localhost:8000):

    uvicorn server_app:app --reload
    python bench.py
    python bench.py --jsonl-out results/bench_synthetic_payload.jsonl

Optional `--jsonl-out` writes one JSON object per metric row (payload + latency) for tables.

You will see printed result dicts for each mode:
- json
- parquet_blob
- parquet_stream
- arrow_ipc_blob
- arrow_ipc_stream
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
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
from format_selector import (
    OptimizationTarget,
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


@dataclass
class JsonMetrics:
    mode: str
    n_rows: int
    n_cols: int
    end_to_end_s: float
    response_bytes: int
    json_encode_s: float
    json_decode_s: float


@dataclass
class ParquetBlobMetrics:
    mode: str
    n_rows: int
    n_cols: int
    end_to_end_s: float
    mcp_call_s: float
    download_s: float
    decode_s: float
    bytes_downloaded: int


@dataclass
class ParquetStreamMetrics:
    mode: str
    n_rows: int
    n_cols: int
    rows_per_chunk: int
    end_to_end_s: float
    time_to_first_rows_s: float
    bytes_read: int
    rows_read: int
    chunks_read: int


@dataclass
class ArrowIpcBlobMetrics:
    mode: str
    n_rows: int
    n_cols: int
    end_to_end_s: float
    mcp_call_s: float
    download_s: float
    decode_s: float
    bytes_downloaded: int


@dataclass
class ArrowIpcStreamMetrics:
    mode: str
    n_rows: int
    n_cols: int
    rows_per_chunk: int
    end_to_end_s: float
    time_to_first_rows_s: float
    bytes_read: int
    rows_read: int
    chunks_read: int


async def run_json_case(
    session: Any,
    n_rows: int,
    n_cols: int,
) -> JsonMetrics:
    t0 = time.perf_counter()
    structured = await call_large_json(session, n_rows, n_cols)
    t1 = time.perf_counter()

    raw_json_start = time.perf_counter()
    raw_json = json.dumps(structured)
    raw_json_end = time.perf_counter()

    decode_start = time.perf_counter()
    _ = json.loads(raw_json)
    decode_end = time.perf_counter()

    response_bytes = len(raw_json.encode("utf-8"))

    return JsonMetrics(
        mode="json",
        n_rows=n_rows,
        n_cols=n_cols,
        end_to_end_s=t1 - t0,
        response_bytes=response_bytes,
        json_encode_s=raw_json_end - raw_json_start,
        json_decode_s=decode_end - decode_start,
    )


async def run_parquet_blob_case(
    session: Any,
    client: httpx.AsyncClient,
    n_rows: int,
    n_cols: int,
) -> ParquetBlobMetrics:
    t0 = time.perf_counter()
    desc = await call_large_parquet_blob(session, n_rows, n_cols)
    t1 = time.perf_counter()

    url = desc["url"]
    dl_start = time.perf_counter()
    data = await fetch_blob(client, url)
    dl_end = time.perf_counter()

    bytes_downloaded = len(data)
    decode_start = time.perf_counter()
    table = pq.read_table(BytesIO(data))
    _ = table.num_rows
    decode_end = time.perf_counter()

    return ParquetBlobMetrics(
        mode="parquet_blob",
        n_rows=n_rows,
        n_cols=n_cols,
        end_to_end_s=(decode_end - t0),
        mcp_call_s=t1 - t0,
        download_s=dl_end - dl_start,
        decode_s=decode_end - decode_start,
        bytes_downloaded=bytes_downloaded,
    )


async def run_parquet_stream_case(
    session: Any,
    client: httpx.AsyncClient,
    n_rows: int,
    n_cols: int,
    rows_per_chunk: int,
    early_terminate_after_first_chunk: bool = False,
) -> ParquetStreamMetrics:
    t0 = time.perf_counter()
    desc = await call_large_parquet_stream(
        session, n_rows, n_cols, rows_per_chunk
    )
    t1 = time.perf_counter()

    url = desc["url"]
    bytes_read = 0
    rows_read = 0
    chunks_read = 0
    time_to_first_rows: Optional[float] = None
    prefix_len = 8

    async for chunk in fetch_stream_chunks(client, url, length_prefix_bytes=prefix_len):
        chunks_read += 1
        bytes_read += prefix_len + len(chunk)

        t_decode_start = time.perf_counter()
        table = pq.read_table(BytesIO(chunk))
        _ = table.num_rows
        t_decode_end = time.perf_counter()

        if time_to_first_rows is None:
            time_to_first_rows = t_decode_end - t1
        rows_read += table.num_rows

        if early_terminate_after_first_chunk:
            end = time.perf_counter()
            return ParquetStreamMetrics(
                mode="parquet_stream",
                n_rows=n_rows,
                n_cols=n_cols,
                rows_per_chunk=rows_per_chunk,
                end_to_end_s=end - t0,
                time_to_first_rows_s=time_to_first_rows or (end - t1),
                bytes_read=bytes_read,
                rows_read=rows_read,
                chunks_read=chunks_read,
            )

    end = time.perf_counter()
    return ParquetStreamMetrics(
        mode="parquet_stream",
        n_rows=n_rows,
        n_cols=n_cols,
        rows_per_chunk=rows_per_chunk,
        end_to_end_s=end - t0,
        time_to_first_rows_s=time_to_first_rows or (end - t1),
        bytes_read=bytes_read,
        rows_read=rows_read,
        chunks_read=chunks_read,
    )


async def run_arrow_ipc_blob_case(
    session: Any,
    client: httpx.AsyncClient,
    n_rows: int,
    n_cols: int,
) -> ArrowIpcBlobMetrics:
    t0 = time.perf_counter()
    desc = await call_large_arrow_ipc_blob(session, n_rows, n_cols)
    t1 = time.perf_counter()

    url = desc["url"]
    dl_start = time.perf_counter()
    data = await fetch_blob(client, url)
    dl_end = time.perf_counter()

    bytes_downloaded = len(data)
    decode_start = time.perf_counter()
    reader = ipc.open_file(BytesIO(data))
    table = reader.read_all()
    _ = table.num_rows
    decode_end = time.perf_counter()

    return ArrowIpcBlobMetrics(
        mode="arrow_ipc_blob",
        n_rows=n_rows,
        n_cols=n_cols,
        end_to_end_s=(decode_end - t0),
        mcp_call_s=t1 - t0,
        download_s=dl_end - dl_start,
        decode_s=decode_end - decode_start,
        bytes_downloaded=bytes_downloaded,
    )


async def run_arrow_ipc_stream_case(
    session: Any,
    client: httpx.AsyncClient,
    n_rows: int,
    n_cols: int,
    rows_per_chunk: int,
    early_terminate_after_first_chunk: bool = False,
) -> ArrowIpcStreamMetrics:
    t0 = time.perf_counter()
    desc = await call_large_arrow_ipc_stream(
        session, n_rows, n_cols, rows_per_chunk
    )
    t1 = time.perf_counter()

    url = desc["url"]
    bytes_read = 0
    rows_read = 0
    chunks_read = 0
    time_to_first_rows: Optional[float] = None
    prefix_len = 8

    async for chunk in fetch_stream_chunks(client, url, length_prefix_bytes=prefix_len):
        chunks_read += 1
        bytes_read += prefix_len + len(chunk)

        t_decode_start = time.perf_counter()
        reader = ipc.open_file(BytesIO(chunk))
        table = reader.read_all()
        _ = table.num_rows
        t_decode_end = time.perf_counter()

        if time_to_first_rows is None:
            time_to_first_rows = t_decode_end - t1
        rows_read += table.num_rows

        if early_terminate_after_first_chunk:
            end = time.perf_counter()
            return ArrowIpcStreamMetrics(
                mode="arrow_ipc_stream",
                n_rows=n_rows,
                n_cols=n_cols,
                rows_per_chunk=rows_per_chunk,
                end_to_end_s=end - t0,
                time_to_first_rows_s=time_to_first_rows or (end - t1),
                bytes_read=bytes_read,
                rows_read=rows_read,
                chunks_read=chunks_read,
            )

    end = time.perf_counter()
    return ArrowIpcStreamMetrics(
        mode="arrow_ipc_stream",
        n_rows=n_rows,
        n_cols=n_cols,
        rows_per_chunk=rows_per_chunk,
        end_to_end_s=end - t0,
        time_to_first_rows_s=time_to_first_rows or (end - t1),
        bytes_read=bytes_read,
        rows_read=rows_read,
        chunks_read=chunks_read,
    )


def _outcome_from_metrics(
    recommended: str,
    json_metrics: Optional[JsonMetrics],
    parquet_blob_metrics: Optional[ParquetBlobMetrics],
    parquet_stream_metrics: Optional[ParquetStreamMetrics],
    arrow_ipc_blob_metrics: Optional[ArrowIpcBlobMetrics] = None,
    arrow_ipc_stream_metrics: Optional[ArrowIpcStreamMetrics] = None,
) -> Dict[str, Any]:
    """Build outcome dict for record_outcome from benchmark metrics."""
    if recommended == "json" and json_metrics:
        return {
            "bytes": json_metrics.response_bytes,
            "latency_s": json_metrics.end_to_end_s,
            "time_to_first_rows_s": json_metrics.end_to_end_s,
        }
    if recommended == "parquet_blob" and parquet_blob_metrics:
        return {
            "bytes": parquet_blob_metrics.bytes_downloaded,
            "latency_s": parquet_blob_metrics.end_to_end_s,
            "time_to_first_rows_s": parquet_blob_metrics.end_to_end_s,
        }
    if recommended == "parquet_stream" and parquet_stream_metrics:
        return {
            "bytes": parquet_stream_metrics.bytes_read,
            "latency_s": parquet_stream_metrics.end_to_end_s,
            "time_to_first_rows_s": parquet_stream_metrics.time_to_first_rows_s,
        }
    if recommended == "arrow_ipc_blob" and arrow_ipc_blob_metrics:
        return {
            "bytes": arrow_ipc_blob_metrics.bytes_downloaded,
            "latency_s": arrow_ipc_blob_metrics.end_to_end_s,
            "time_to_first_rows_s": arrow_ipc_blob_metrics.end_to_end_s,
        }
    if recommended == "arrow_ipc_stream" and arrow_ipc_stream_metrics:
        return {
            "bytes": arrow_ipc_stream_metrics.bytes_read,
            "latency_s": arrow_ipc_stream_metrics.end_to_end_s,
            "time_to_first_rows_s": arrow_ipc_stream_metrics.time_to_first_rows_s,
        }
    return {}


def _jsonl_append(path: Optional[Path], obj: Dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


async def run_benchmarks(
    mcp_url: str = DEFAULT_MCP_URL,
    *,
    jsonl_out: Optional[Path] = None,
) -> None:
    row_sizes = [10_000, 100_000]
    col_sizes = [6, 20]
    stream_chunk_sizes = [8_000, 64_000, 256_000]

    target = get_default_target()
    mab_state = load_mab_state(DEFAULT_MAB_STATE_PATH) if mab_enabled() else None

    if jsonl_out and jsonl_out.exists():
        jsonl_out.unlink()
    _jsonl_append(
        jsonl_out,
        {
            "type": "bench_synthetic_header",
            "format_select_target": target.value,
            "mcp_url": mcp_url,
            "row_sizes": row_sizes,
            "col_sizes": col_sizes,
            "stream_chunk_sizes": stream_chunk_sizes,
        },
    )

    async with connect(base_url=mcp_url) as (session, client):
        for n_rows in row_sizes:
            for n_cols in col_sizes:
                ctx = SelectionContext(n_rows=n_rows, n_cols=n_cols, target=target)
                hints = await call_describe_result_formats(
                    session,
                    n_rows,
                    n_cols,
                    optimization_target=ctx.target.value,
                    prefer_streaming=ctx.prefer_streaming,
                )
                if mab_state is not None:
                    recommended = select_format_with_mab(ctx, hints, mab_state)
                    selection_source = "mab"
                elif hints:
                    recommended = select_format_with_hints(ctx, hints)
                    selection_source = "hints"
                else:
                    recommended = select_format(ctx)
                    selection_source = "rules"
                print(
                    f"\n=== Benchmark n_rows={n_rows}, n_cols={n_cols} "
                    f"(target={target.value}, recommended_format={recommended}, source={selection_source}) ==="
                )

                json_metrics = await run_json_case(session, n_rows, n_cols)
                print(json.dumps(asdict(json_metrics), indent=2))
                _jsonl_append(
                    jsonl_out,
                    {
                        **asdict(json_metrics),
                        "n_rows": n_rows,
                        "n_cols": n_cols,
                        "format_select_target": target.value,
                        "recommended_format": recommended,
                        "selection_source": selection_source,
                    },
                )

                parquet_blob_metrics = await run_parquet_blob_case(
                    session, client, n_rows, n_cols
                )
                print(json.dumps(asdict(parquet_blob_metrics), indent=2))
                _jsonl_append(
                    jsonl_out,
                    {
                        **asdict(parquet_blob_metrics),
                        "n_rows": n_rows,
                        "n_cols": n_cols,
                        "format_select_target": target.value,
                        "recommended_format": recommended,
                        "selection_source": selection_source,
                    },
                )

                arrow_ipc_blob_metrics = await run_arrow_ipc_blob_case(
                    session, client, n_rows, n_cols
                )
                print(json.dumps(asdict(arrow_ipc_blob_metrics), indent=2))
                _jsonl_append(
                    jsonl_out,
                    {
                        **asdict(arrow_ipc_blob_metrics),
                        "n_rows": n_rows,
                        "n_cols": n_cols,
                        "format_select_target": target.value,
                        "recommended_format": recommended,
                        "selection_source": selection_source,
                    },
                )

                first_stream_metrics: Optional[ParquetStreamMetrics] = None
                for rows_per_chunk in stream_chunk_sizes:
                    parquet_stream_metrics = await run_parquet_stream_case(
                        session,
                        client,
                        n_rows,
                        n_cols,
                        rows_per_chunk=rows_per_chunk,
                        early_terminate_after_first_chunk=False,
                    )
                    if first_stream_metrics is None:
                        first_stream_metrics = parquet_stream_metrics
                    print(json.dumps(asdict(parquet_stream_metrics), indent=2))
                    _jsonl_append(
                        jsonl_out,
                        {
                            **asdict(parquet_stream_metrics),
                            "n_rows": n_rows,
                            "n_cols": n_cols,
                            "format_select_target": target.value,
                            "recommended_format": recommended,
                            "selection_source": selection_source,
                        },
                    )

                first_arrow_stream_metrics: Optional[ArrowIpcStreamMetrics] = None
                for rows_per_chunk in stream_chunk_sizes:
                    arrow_ipc_stream_metrics = await run_arrow_ipc_stream_case(
                        session,
                        client,
                        n_rows,
                        n_cols,
                        rows_per_chunk=rows_per_chunk,
                        early_terminate_after_first_chunk=False,
                    )
                    if first_arrow_stream_metrics is None:
                        first_arrow_stream_metrics = arrow_ipc_stream_metrics
                    print(json.dumps(asdict(arrow_ipc_stream_metrics), indent=2))
                    _jsonl_append(
                        jsonl_out,
                        {
                            **asdict(arrow_ipc_stream_metrics),
                            "n_rows": n_rows,
                            "n_cols": n_cols,
                            "format_select_target": target.value,
                            "recommended_format": recommended,
                            "selection_source": selection_source,
                        },
                    )

                outcome = _outcome_from_metrics(
                    recommended,
                    json_metrics,
                    parquet_blob_metrics,
                    first_stream_metrics,
                    arrow_ipc_blob_metrics,
                    first_arrow_stream_metrics,
                )
                if outcome:
                    record_outcome(ctx, recommended, outcome, mab_state=mab_state)
                if mab_state is not None:
                    save_mab_state(mab_state, DEFAULT_MAB_STATE_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthetic MCP JSON vs Parquet benchmarks")
    parser.add_argument(
        "--jsonl-out",
        type=Path,
        default=None,
        help="Append one JSON object per metric row (for payload/latency tables)",
    )
    parser.add_argument("--mcp-url", default=DEFAULT_MCP_URL)
    args = parser.parse_args()
    asyncio.run(run_benchmarks(mcp_url=args.mcp_url, jsonl_out=args.jsonl_out))


if __name__ == "__main__":
    main()
