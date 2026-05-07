"""
Compare transport for structured (tabular Parquet) vs unstructured (opaque blob) payloads.

Structured: POST Parquet to /materialized, then describe_result_formats + client fetch + large_result_auto.
Unstructured: POST raw bytes to /materialized-raw, then same (client uses HTTP /raw/{id} or /raw-gzip/{id}).

Usage (server running):

    uvicorn server_app:app --host 127.0.0.1 --port 8000
    python bench_structured_vs_unstructured.py --results results/structured_vs_unstructured.jsonl --overwrite

Docker (after compose up / run client container):

    ./scripts/tc_apply.sh WAN && python bench_structured_vs_unstructured.py \\
      --mcp-url http://server:8000/mcp/mcp --server-url http://server:8000 \\
      --results results/structured_vs_unstructured_network_wan.jsonl --overwrite
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse, urlunparse

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from client.mcp_client import (
    DEFAULT_MCP_URL,
    connect,
    call_describe_result_formats,
    call_large_arrow_ipc_blob,
    call_large_arrow_ipc_stream,
    call_large_json,
    call_large_parquet_blob,
    call_large_parquet_stream,
    call_large_result_auto,
    fetch_blob,
    fetch_stream_chunks,
    register_materialized,
    register_materialized_raw,
)
from format_selector import (
    OptimizationTarget,
    SelectionContext,
    select_format,
    select_format_with_hints,
)

log = logging.getLogger(__name__)

DEFAULT_RESULTS = Path("results/structured_vs_unstructured.jsonl")
N_COLS = 8
# Target Parquet sizes (bytes) — unstructured raw payload matched to same nominal target
SIZE_TARGETS: Tuple[int, ...] = (256 * 1024, 1024 * 1024, 5 * 1024 * 1024)


def _tc_profile_metadata() -> Dict[str, Any]:
    return {
        "net_profile": os.environ.get("NET_PROFILE", "").strip() or None,
        "tc_dev": os.environ.get("TC_DEV", "").strip() or None,
        "tc_delay": os.environ.get("TC_DELAY", "").strip() or None,
        "tc_rate": os.environ.get("TC_RATE", "").strip() or None,
        "tc_loss": os.environ.get("TC_LOSS", "").strip() or None,
    }


def _rewrite_server_url(url: str, server_url: str) -> str:
    """Map localhost blob URLs to --server-url (Docker: http://server:8000)."""
    if not url or not server_url:
        return url
    u = urlparse(url)
    if u.hostname not in ("localhost", "127.0.0.1"):
        return url
    su = urlparse(server_url.rstrip("/"))
    return urlunparse((su.scheme, su.netloc, u.path, u.params, u.query, u.fragment))


def _make_table(n_rows: int, n_cols: int) -> pa.Table:
    arrays: List[pa.Array] = [pa.array(range(n_rows), type=pa.int64())]
    cell = "x" * 96
    for j in range(n_cols - 1):
        arrays.append(pa.array([f"r{i}c{j}{cell}" for i in range(n_rows)], type=pa.string()))
    names = ["id"] + [f"s{j}" for j in range(n_cols - 1)]
    return pa.table(arrays, names=names)


def _parquet_bytes_for_rows(n_rows: int, n_cols: int) -> int:
    bio = BytesIO()
    pq.write_table(_make_table(n_rows, n_cols), bio, compression="snappy")
    return len(bio.getvalue())


def build_parquet_near_target(target_bytes: int, n_cols: int = N_COLS) -> Tuple[bytes, int, int]:
    """Binary-search n_rows so Parquet size is within ~15% of target_bytes."""
    lo, hi = 1, max(10, target_bytes // 50)
    best_rows, best_diff = 1, abs(_parquet_bytes_for_rows(1, n_cols) - target_bytes)
    while lo <= hi:
        mid = (lo + hi) // 2
        sz = _parquet_bytes_for_rows(mid, n_cols)
        diff = abs(sz - target_bytes)
        if diff < best_diff:
            best_diff = diff
            best_rows = mid
        if sz < target_bytes:
            lo = mid + 1
        else:
            hi = mid - 1
    # Local refine around best_rows
    for delta in range(-50, 51):
        r = max(1, best_rows + delta)
        d = abs(_parquet_bytes_for_rows(r, n_cols) - target_bytes)
        if d < best_diff:
            best_diff = d
            best_rows = r
    bio = BytesIO()
    pq.write_table(_make_table(best_rows, n_cols), bio, compression="snappy")
    return bio.getvalue(), best_rows, n_cols


async def _client_fetch_tabular(
    session: Any,
    http: httpx.AsyncClient,
    *,
    result_id: str,
    n_rows: int,
    n_cols: int,
    target: OptimizationTarget,
    rows_per_chunk: int,
    prefer_streaming: bool,
    server_url: str,
) -> Tuple[Optional[float], Optional[float], str, Optional[int], Optional[float]]:
    """Same as bench_bird_server_exec_e2e.client_fetch_recommended with URL rewrite."""
    t_desc0 = time.perf_counter()
    hints = await call_describe_result_formats(
        session,
        n_rows,
        n_cols,
        rows_per_chunk=rows_per_chunk,
        result_id=result_id,
        optimization_target=target.value,
        prefer_streaming=prefer_streaming,
    )
    describe_s = time.perf_counter() - t_desc0
    ctx = SelectionContext(
        n_rows=n_rows,
        n_cols=n_cols,
        target=target,
        prefer_streaming=prefer_streaming,
    )
    chosen = select_format_with_hints(ctx, hints) if hints else select_format(ctx)

    t0 = time.perf_counter()
    ttfr: Optional[float] = None
    nbytes: Optional[int] = None

    if chosen == "json":
        structured = await call_large_json(session, n_rows, n_cols, result_id=result_id)
        raw = json.dumps(structured)
        nbytes = len(raw.encode("utf-8"))
    elif chosen == "parquet_blob":
        desc = await call_large_parquet_blob(session, n_rows, n_cols, result_id=result_id)
        data = await fetch_blob(http, _rewrite_server_url(desc["url"], server_url))
        nbytes = len(data)
    elif chosen == "arrow_ipc_blob":
        desc = await call_large_arrow_ipc_blob(session, n_rows, n_cols, result_id=result_id)
        data = await fetch_blob(http, _rewrite_server_url(desc["url"], server_url))
        nbytes = len(data)
    elif chosen == "arrow_ipc_stream":
        desc = await call_large_arrow_ipc_stream(
            session, n_rows, n_cols, rows_per_chunk=rows_per_chunk, result_id=result_id
        )
        url = _rewrite_server_url(desc["url"], server_url)
        total = 0
        first = True
        async for chunk in fetch_stream_chunks(http, url):
            total += 8 + len(chunk)
            if first:
                ttfr = time.perf_counter() - t0
                first = False
        nbytes = total
    else:
        desc = await call_large_parquet_stream(
            session, n_rows, n_cols, rows_per_chunk=rows_per_chunk, result_id=result_id
        )
        url = _rewrite_server_url(desc["url"], server_url)
        total = 0
        first = True
        async for chunk in fetch_stream_chunks(http, url):
            total += 8 + len(chunk)
            if first:
                ttfr = time.perf_counter() - t0
                first = False
        nbytes = total

    fetch_s = time.perf_counter() - t0
    return describe_s, fetch_s, chosen, nbytes, ttfr


async def _client_fetch_unstructured(
    session: Any,
    http: httpx.AsyncClient,
    *,
    result_id: str,
    target: OptimizationTarget,
    prefer_streaming: bool,
    server_url: str,
) -> Tuple[Optional[float], Optional[float], str, Optional[int], Optional[float]]:
    """describe + hint-based selection + HTTP fetch for raw / gzip / inline-sized raw."""
    t_desc0 = time.perf_counter()
    hints = await call_describe_result_formats(
        session,
        1,
        1,
        rows_per_chunk=8192,
        result_id=result_id,
        optimization_target=target.value,
        prefer_streaming=prefer_streaming,
    )
    describe_s = time.perf_counter() - t_desc0
    ctx = SelectionContext(n_rows=0, n_cols=0, target=target, prefer_streaming=prefer_streaming)
    chosen = select_format_with_hints(ctx, hints) if hints else select_format(ctx)

    base = server_url.rstrip("/")
    t0 = time.perf_counter()
    nbytes: Optional[int] = None
    ttfr: Optional[float] = None

    if chosen == "gzip_blob":
        url = f"{base}/raw-gzip/{result_id}"
        data = await fetch_blob(http, url)
        nbytes = len(data)
    elif chosen in ("raw_blob", "text_inline"):
        url = f"{base}/raw/{result_id}"
        data = await fetch_blob(http, url)
        nbytes = len(data)
    else:
        # Should not happen for unstructured hints
        fetch_s = time.perf_counter() - t0
        return describe_s, fetch_s, chosen, None, None

    fetch_s = time.perf_counter() - t0
    ttfr = fetch_s
    return describe_s, fetch_s, chosen, nbytes, ttfr


async def _measure_server_auto_payload(
    http: httpx.AsyncClient,
    auto: Dict[str, Any],
    server_url: str,
) -> Tuple[Optional[float], Optional[int], Optional[float]]:
    payload = auto.get("payload") if isinstance(auto, dict) else None
    decode = auto.get("decode") if isinstance(auto, dict) else None

    if isinstance(payload, dict) and payload.get("kind") == "json":
        t0 = time.perf_counter()
        raw = json.dumps(payload.get("records"))
        fetch_s = time.perf_counter() - t0
        return fetch_s, len(raw.encode("utf-8")), None

    if isinstance(payload, dict) and payload.get("kind") == "text":
        t0 = time.perf_counter()
        text = payload.get("text") or ""
        fetch_s = time.perf_counter() - t0
        return fetch_s, len(str(text).encode("utf-8")), None

    if not isinstance(decode, dict) or not isinstance(decode.get("url"), str):
        return None, None, None

    url = _rewrite_server_url(decode["url"], server_url)
    transport = str(decode.get("transport") or "")
    t0 = time.perf_counter()
    if transport == "http_length_prefixed_stream":
        bytes_read = 0
        ttfr: Optional[float] = None
        async for chunk in fetch_stream_chunks(http, url):
            bytes_read += 8 + len(chunk)
            if ttfr is None:
                ttfr = time.perf_counter() - t0
        return time.perf_counter() - t0, bytes_read, ttfr
    data = await fetch_blob(http, url)
    return time.perf_counter() - t0, len(data), None


@dataclass
class PairRecord:
    payload_class: str  # structured | unstructured
    target_name: str
    nominal_target_bytes: int
    rows_per_chunk: int
    prefer_streaming: bool
    # structured
    n_rows: int = 0
    n_cols: int = 0
    register_s: Optional[float] = None
    parquet_bytes: Optional[int] = None
    unstructured_raw_bytes: Optional[int] = None
    # client path
    client_describe_s: Optional[float] = None
    client_fetch_s: Optional[float] = None
    client_chosen_format: str = ""
    client_bytes: Optional[int] = None
    client_ttfr_s: Optional[float] = None
    client_error: Optional[str] = None
    # server auto
    server_auto_call_s: Optional[float] = None
    server_auto_fetch_s: Optional[float] = None
    server_auto_chosen_format: str = ""
    server_auto_bytes: Optional[int] = None
    server_auto_ttfr_s: Optional[float] = None
    server_auto_error: Optional[str] = None


async def bench_structured(
    session: Any,
    http: httpx.AsyncClient,
    *,
    target: OptimizationTarget,
    nominal_bytes: int,
    rows_per_chunk: int,
    prefer_streaming: bool,
    server_url: str,
) -> PairRecord:
    rec = PairRecord(
        payload_class="structured",
        target_name=target.value,
        nominal_target_bytes=nominal_bytes,
        rows_per_chunk=rows_per_chunk,
        prefer_streaming=prefer_streaming,
    )
    try:
        t0 = time.perf_counter()
        pq_bytes, n_rows, n_cols = build_parquet_near_target(nominal_bytes)
        reg = await register_materialized(http, pq_bytes, base_url=server_url)
        rec.register_s = time.perf_counter() - t0
    except Exception as exc:
        rec.client_error = f"register: {exc}"
        return rec

    rec.n_rows = int(reg.get("n_rows") or 0)
    rec.n_cols = int(reg.get("n_cols") or 0)
    rec.parquet_bytes = len(pq_bytes)
    rid = str(reg.get("result_id") or "")

    try:
        ds, fs, fmt, nb, ttfr = await _client_fetch_tabular(
            session,
            http,
            result_id=rid,
            n_rows=rec.n_rows,
            n_cols=rec.n_cols,
            target=target,
            rows_per_chunk=rows_per_chunk,
            prefer_streaming=prefer_streaming,
            server_url=server_url,
        )
        rec.client_describe_s = ds
        rec.client_fetch_s = fs
        rec.client_chosen_format = fmt
        rec.client_bytes = nb
        rec.client_ttfr_s = ttfr
    except Exception as exc:
        rec.client_error = str(exc)

    try:
        t0 = time.perf_counter()
        auto = await call_large_result_auto(
            session,
            rec.n_rows,
            rec.n_cols,
            rows_per_chunk=rows_per_chunk,
            result_id=rid,
            optimization_target=target.value,
            prefer_streaming=prefer_streaming,
            use_mab=False,
        )
        rec.server_auto_call_s = time.perf_counter() - t0
        rec.server_auto_chosen_format = str(auto.get("chosen_format") or "")
        fs, nb, ttfr = await _measure_server_auto_payload(http, auto, server_url)
        rec.server_auto_fetch_s = fs
        rec.server_auto_bytes = nb
        rec.server_auto_ttfr_s = ttfr
    except Exception as exc:
        rec.server_auto_error = str(exc)

    return rec


def _compressible_payload(n_bytes: int) -> bytes:
    """Repeating pattern so gzip_blob is smaller than raw_blob when selected."""
    chunk = b"StructuredVsUnstructuredBench\n"
    return (chunk * (n_bytes // len(chunk) + 1))[:n_bytes]


async def bench_unstructured(
    session: Any,
    http: httpx.AsyncClient,
    *,
    target: OptimizationTarget,
    nominal_bytes: int,
    rows_per_chunk: int,
    prefer_streaming: bool,
    server_url: str,
) -> PairRecord:
    rec = PairRecord(
        payload_class="unstructured",
        target_name=target.value,
        nominal_target_bytes=nominal_bytes,
        rows_per_chunk=rows_per_chunk,
        prefer_streaming=prefer_streaming,
    )
    payload = _compressible_payload(nominal_bytes)
    try:
        t0 = time.perf_counter()
        reg = await register_materialized_raw(
            http,
            payload,
            base_url=server_url,
            content_type="text/plain; charset=utf-8",
        )
        rec.register_s = time.perf_counter() - t0
        rid = str(reg.get("result_id") or "")
        rec.unstructured_raw_bytes = len(payload)
    except Exception as exc:
        rec.client_error = f"register: {exc}"
        return rec

    try:
        ds, fs, fmt, nb, ttfr = await _client_fetch_unstructured(
            session,
            http,
            result_id=rid,
            target=target,
            prefer_streaming=prefer_streaming,
            server_url=server_url,
        )
        rec.client_describe_s = ds
        rec.client_fetch_s = fs
        rec.client_chosen_format = fmt
        rec.client_bytes = nb
        rec.client_ttfr_s = ttfr
    except Exception as exc:
        rec.client_error = str(exc)

    try:
        t0 = time.perf_counter()
        auto = await call_large_result_auto(
            session,
            1,
            1,
            rows_per_chunk=rows_per_chunk,
            result_id=rid,
            optimization_target=target.value,
            prefer_streaming=prefer_streaming,
            use_mab=False,
        )
        rec.server_auto_call_s = time.perf_counter() - t0
        rec.server_auto_chosen_format = str(auto.get("chosen_format") or "")
        fs, nb, ttfr = await _measure_server_auto_payload(http, auto, server_url)
        rec.server_auto_fetch_s = fs
        rec.server_auto_bytes = nb
        rec.server_auto_ttfr_s = ttfr
    except Exception as exc:
        rec.server_auto_error = str(exc)

    return rec


def _split_csv(s: str) -> List[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _parse_size_list(s: str) -> Tuple[int, ...]:
    if not s.strip():
        return SIZE_TARGETS
    out: List[int] = []
    for part in s.split(","):
        part = part.strip().lower()
        if part.endswith("mb"):
            out.append(int(float(part[:-2].strip()) * 1024 * 1024))
        elif part.endswith("kb"):
            out.append(int(float(part[:-2].strip()) * 1024))
        else:
            out.append(int(part))
    return tuple(out)


async def run_bench(args: argparse.Namespace) -> None:
    out_path = Path(args.results)
    if args.overwrite and out_path.exists():
        out_path.unlink()

    targets = [OptimizationTarget(x) for x in _split_csv(args.targets)]
    sizes = _parse_size_list(args.size_bytes_list)
    prefer_stream = bool(args.prefer_streaming)

    header = {
        "type": "structured_vs_unstructured_run_header",
        "targets": [t.value for t in targets],
        "nominal_size_bytes": list(sizes),
        "rows_per_chunk": int(args.rows_per_chunk),
        "prefer_streaming": prefer_stream,
        "mcp_url": args.mcp_url,
        "server_url": args.server_url,
        "PARQUET_ENCODING_STRATEGY": os.environ.get("PARQUET_ENCODING_STRATEGY", "data_driven"),
        "PARQUET_COMPRESSION": os.environ.get("PARQUET_COMPRESSION", "snappy"),
        "ARROW_IPC_COMPRESSION": os.environ.get("ARROW_IPC_COMPRESSION", "none"),
        "network": _tc_profile_metadata(),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json.dumps(header, ensure_ascii=False) + "\n")

    async with connect(base_url=args.mcp_url) as (session, http):
        for nominal in sizes:
            for target in targets:
                log.info(
                    "structured nominal=%s target=%s rpc=%s",
                    nominal,
                    target.value,
                    args.rows_per_chunk,
                )
                rec_s = await bench_structured(
                    session,
                    http,
                    target=target,
                    nominal_bytes=nominal,
                    rows_per_chunk=int(args.rows_per_chunk),
                    prefer_streaming=prefer_stream,
                    server_url=args.server_url,
                )
                with open(out_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(asdict(rec_s), ensure_ascii=False) + "\n")

                log.info(
                    "unstructured nominal=%s target=%s",
                    nominal,
                    target.value,
                )
                rec_u = await bench_unstructured(
                    session,
                    http,
                    target=target,
                    nominal_bytes=nominal,
                    rows_per_chunk=int(args.rows_per_chunk),
                    prefer_streaming=prefer_stream,
                    server_url=args.server_url,
                )
                with open(out_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(asdict(rec_u), ensure_ascii=False) + "\n")

    log.info("Wrote %s", out_path)


def main() -> None:
    ap = argparse.ArgumentParser(description="Structured vs unstructured transport benchmark")
    ap.add_argument("--mcp-url", default=os.environ.get("MCP_URL", DEFAULT_MCP_URL))
    ap.add_argument(
        "--server-url",
        default=os.environ.get("SERVER_URL", "http://localhost:8000"),
    )
    ap.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("--rows-per-chunk", type=int, default=8192)
    ap.add_argument("--prefer-streaming", action="store_true")
    ap.add_argument(
        "--targets",
        default="min_bytes,min_latency,min_time_to_first_rows",
        help="Comma-separated: min_bytes,min_latency,min_time_to_first_rows",
    )
    ap.add_argument(
        "--size-bytes-list",
        default="",
        help="Comma-separated sizes: e.g. 262144,1048576,5242880 or 256kb,1mb,5mb",
    )
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_bench(args))


if __name__ == "__main__":
    main()
