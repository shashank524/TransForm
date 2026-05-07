"""
BIRD end-to-end benchmark where the MCP server executes SQL.

Baseline (B0): one MCP tool call returns inline JSON (bird_query_json).
Client-side selection (B1): materialize once -> describe_result_formats -> client selects -> large_* fetch.
Server-side auto (B2): one MCP tool call executes and selects (bird_query_auto) + optional HTTP fetch.

Results: results/bird_server_exec_e2e.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

import httpx

from client.mcp_client import (
    DEFAULT_MCP_URL,
    connect,
    call_bird_query_json,
    call_bird_query_materialize,
    call_bird_query_auto,
    call_large_result_auto,
    call_describe_result_formats,
    call_large_json,
    call_large_parquet_blob,
    call_large_parquet_stream,
    call_large_arrow_ipc_blob,
    call_large_arrow_ipc_stream,
    fetch_blob,
    fetch_stream_chunks,
)
from format_selector import (
    OptimizationTarget,
    SelectionContext,
    get_default_target,
    select_format,
    select_format_with_hints,
)

log = logging.getLogger(__name__)

DEFAULT_DATA_DIR = Path("data/datasets/bird/dev")
DEFAULT_QUESTIONS = "dev.json"
DEFAULT_RESULTS = Path("results/bird_server_exec_e2e.jsonl")
MAX_RESULT_ROWS = 500_000


@dataclass
class BirdServerExecRecord:
    question_id: str
    db_id: str
    sql: str
    target: str
    max_rows: int
    parquet_encoding_strategy: str
    parquet_compression: str
    arrow_ipc_compression: str
    # Baseline (server executes + inline JSON)
    baseline_s: Optional[float] = None
    baseline_bytes: Optional[int] = None
    baseline_wire_bytes: Optional[int] = None
    baseline_error: Optional[str] = None
    # Materialize (server executes + writes parquet + returns result_id)
    materialize_s: Optional[float] = None
    result_id: str = ""
    n_rows: int = 0
    n_cols: int = 0
    materialize_error: Optional[str] = None
    # Client-side selection (describe + chosen fetch)
    describe_s: Optional[float] = None
    client_chosen_format: str = ""
    client_fetch_s: Optional[float] = None
    client_bytes: Optional[int] = None
    client_wire_bytes: Optional[int] = None
    client_ttfr_s: Optional[float] = None
    client_error: Optional[str] = None
    # Server-side auto (one MCP call + optional fetch)
    server_auto_call_s: Optional[float] = None
    server_auto_chosen_format: str = ""
    server_auto_fetch_s: Optional[float] = None
    server_auto_bytes: Optional[int] = None
    server_auto_wire_bytes: Optional[int] = None
    server_auto_ttfr_s: Optional[float] = None
    server_auto_error: Optional[str] = None
    # Normalized logical payload metric (records-only JSON bytes; same logical payload across arms).
    logical_json_records_bytes: Optional[int] = None


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def load_bird_questions(data_dir: Path, questions_file: str, max_queries: int) -> List[Dict[str, Any]]:
    qpath = Path(questions_file)
    if not qpath.is_absolute():
        qpath = (data_dir / questions_file).resolve()
    items = json.loads(qpath.read_text(encoding="utf-8"))
    out: List[Dict[str, Any]] = []
    for item in items:
        if max_queries > 0 and len(out) >= max_queries:
            break
        db_id = str(item.get("db_id") or "").strip()
        sql = str(item.get("SQL") or item.get("sql") or "").strip()
        if not db_id or not sql:
            continue
        out.append(
            {
                "question_id": str(item.get("question_id") or len(out)),
                "db_id": db_id,
                "sql": sql,
            }
        )
    return out


def _split_csv(s: str) -> List[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _rewrite_data_plane_url(url: str, server_url: str) -> str:
    """
    MCP tools return fetch URLs with host localhost; inside Docker the client must use
    the real server host (e.g. http://server:8000) or blob/stream GETs fail.
    """
    if not url or not server_url:
        return url
    u = urlparse(url)
    if u.hostname not in ("localhost", "127.0.0.1"):
        return url
    su = urlparse(server_url.rstrip("/"))
    return urlunparse((su.scheme, su.netloc, u.path, u.params, u.query, u.fragment))


def _tc_profile_metadata() -> Dict[str, Any]:
    """
    Record network-shaping metadata when running under Docker+tc.
    This is best-effort: values come from env (NET_PROFILE, TC_*).
    """
    return {
        "net_profile": os.environ.get("NET_PROFILE", "").strip() or None,
        "tc_dev": os.environ.get("TC_DEV", "").strip() or None,
        "tc_delay": os.environ.get("TC_DELAY", "").strip() or None,
        "tc_rate": os.environ.get("TC_RATE", "").strip() or None,
        "tc_loss": os.environ.get("TC_LOSS", "").strip() or None,
    }


def _extract_records_payload(obj: Any) -> Any:
    """
    Normalize tool outputs into a records-only payload for apples-to-apples JSON sizing.
    """
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        if isinstance(obj.get("records"), list):
            return obj.get("records")
        if isinstance(obj.get("result"), dict) and isinstance(obj["result"].get("records"), list):
            return obj["result"].get("records")
    return obj


def _logical_json_records_size(obj: Any) -> int:
    records = _extract_records_payload(obj)
    return len(json.dumps(records).encode("utf-8"))


async def measure_server_auto_payload(
    http: httpx.AsyncClient,
    auto: Dict[str, Any],
    *,
    server_url: str,
    logical_json_records_bytes: Optional[int] = None,
) -> tuple[Optional[float], Optional[int], Optional[float]]:
    """
    Return (fetch_s, bytes, ttfr_s) for the payload described by large_result_auto output.
    """
    payload = auto.get("payload") if isinstance(auto, dict) else None
    decode = auto.get("decode") if isinstance(auto, dict) else None

    # Inline payload
    if isinstance(payload, dict) and payload.get("kind") == "json":
        nbytes = logical_json_records_bytes
        if nbytes is None:
            nbytes = _logical_json_records_size(payload.get("records"))
        # Inline payload is already part of the MCP response measured by server_auto_call_s.
        return 0.0, nbytes, None

    if isinstance(payload, dict) and payload.get("kind") == "text":
        text = payload.get("text") or ""
        return 0.0, len(str(text).encode("utf-8")), None

    if not isinstance(decode, dict) or not isinstance(decode.get("url"), str):
        return None, None, None

    url = _rewrite_data_plane_url(decode["url"], server_url)
    transport = str(decode.get("transport") or "")
    t0 = time.perf_counter()
    if transport == "http_length_prefixed_stream":
        # Measure time-to-first chunk and total bytes including 8-byte prefix per chunk.
        bytes_read = 0
        ttfr: Optional[float] = None
        async for chunk in fetch_stream_chunks(http, url):
            bytes_read += 8 + len(chunk)
            if ttfr is None:
                ttfr = time.perf_counter() - t0
        return time.perf_counter() - t0, bytes_read, ttfr
    else:
        data = await fetch_blob(http, url)
        return time.perf_counter() - t0, len(data), None


async def client_fetch_recommended(
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
) -> tuple[Optional[float], Optional[float], str, Optional[int], Optional[float]]:
    """
    Returns (describe_s, fetch_s, chosen_format, bytes, ttfr_s).
    """
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
    ctx = SelectionContext(n_rows=n_rows, n_cols=n_cols, target=target, prefer_streaming=prefer_streaming)
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
        data = await fetch_blob(http, _rewrite_data_plane_url(desc["url"], server_url))
        nbytes = len(data)
    elif chosen == "arrow_ipc_blob":
        desc = await call_large_arrow_ipc_blob(session, n_rows, n_cols, result_id=result_id)
        data = await fetch_blob(http, _rewrite_data_plane_url(desc["url"], server_url))
        nbytes = len(data)
    elif chosen == "arrow_ipc_stream":
        desc = await call_large_arrow_ipc_stream(
            session, n_rows, n_cols, rows_per_chunk=rows_per_chunk, result_id=result_id
        )
        stream_url = _rewrite_data_plane_url(desc["url"], server_url)
        total = 0
        first = True
        async for chunk in fetch_stream_chunks(http, stream_url):
            total += 8 + len(chunk)
            if first:
                ttfr = time.perf_counter() - t0
                first = False
        nbytes = total
    else:
        desc = await call_large_parquet_stream(
            session, n_rows, n_cols, rows_per_chunk=rows_per_chunk, result_id=result_id
        )
        stream_url = _rewrite_data_plane_url(desc["url"], server_url)
        total = 0
        first = True
        async for chunk in fetch_stream_chunks(http, stream_url):
            total += 8 + len(chunk)
            if first:
                ttfr = time.perf_counter() - t0
                first = False
        nbytes = total

    fetch_s = time.perf_counter() - t0
    return describe_s, fetch_s, chosen, nbytes, ttfr


def append_jsonl(path: Path, rec: BirdServerExecRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")


async def run_bench(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir).resolve()
    rows = load_bird_questions(data_dir, args.bird_questions, args.max_queries)
    log.info("Loaded %d BIRD questions (max_queries=%s)", len(rows), args.max_queries)

    targets = _split_csv(args.targets) if args.targets else [get_default_target().value]
    rows_per_chunks = [int(x) for x in _split_csv(args.rows_per_chunk_list)] if args.rows_per_chunk_list else [int(args.rows_per_chunk)]

    async with connect(base_url=args.mcp_url) as (session, http):
        for tname in targets:
            target = OptimizationTarget(tname)
            for rpc in rows_per_chunks:
                out_path = Path(args.results)
                if Path(args.results) == DEFAULT_RESULTS:
                    # Default results path: shard by target/chunk to avoid overwrites.
                    out_path = Path("results") / f"bird_server_exec_e2e_{tname}_rpc{rpc}.jsonl"
                if args.overwrite and out_path.exists():
                    out_path.unlink()

                header = {
                    "type": "bird_server_exec_e2e_run_header",
                    "format_select_target": target.value,
                    "max_queries": args.max_queries,
                    "mcp_url": args.mcp_url,
                    "server_url": args.server_url,
                    "bird_questions": args.bird_questions,
                    "max_rows": args.max_rows,
                    "rows_per_chunk": rpc,
                    "prefer_streaming": bool(args.prefer_streaming),
                    "PARQUET_ENCODING_STRATEGY": _env("PARQUET_ENCODING_STRATEGY", "data_driven"),
                    "PARQUET_COMPRESSION": _env("PARQUET_COMPRESSION", "snappy"),
                    "ARROW_IPC_COMPRESSION": _env("ARROW_IPC_COMPRESSION", "none"),
                    "network": _tc_profile_metadata(),
                }
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with open(out_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(header, ensure_ascii=False) + "\n")

                for i, item in enumerate(rows):
                    qid = item["question_id"]
                    db_id = item["db_id"]
                    sql = item["sql"]
                    log.info(
                        "[%s rpc=%d] [%d/%d] qid=%s db=%s",
                        target.value,
                        rpc,
                        i + 1,
                        len(rows),
                        qid,
                        db_id,
                    )

                    rec = BirdServerExecRecord(
                        question_id=qid,
                        db_id=db_id,
                        sql=sql[:4000],
                        target=target.value,
                        max_rows=int(args.max_rows),
                        parquet_encoding_strategy=_env("PARQUET_ENCODING_STRATEGY", "data_driven"),
                        parquet_compression=_env("PARQUET_COMPRESSION", "snappy"),
                        arrow_ipc_compression=_env("ARROW_IPC_COMPRESSION", "none"),
                    )

                    # --- Baseline: execute + inline JSON ---
                    try:
                        t0 = time.perf_counter()
                        structured = await call_bird_query_json(
                            session, db_id=db_id, sql=sql, max_rows=args.max_rows
                        )
                        raw = json.dumps(structured)
                        rec.baseline_s = time.perf_counter() - t0
                        rec.baseline_bytes = len(raw.encode("utf-8"))
                        rec.logical_json_records_bytes = _logical_json_records_size(structured)
                        # Normalized wire metric: for JSON, use records-only payload size.
                        rec.baseline_wire_bytes = rec.logical_json_records_bytes
                    except Exception as exc:
                        rec.baseline_error = str(exc)

                    # --- Materialize once for client-selection arm ---
                    try:
                        t0 = time.perf_counter()
                        mat = await call_bird_query_materialize(
                            session, db_id=db_id, sql=sql, max_rows=args.max_rows
                        )
                        rec.materialize_s = time.perf_counter() - t0
                        rec.result_id = str(mat.get("result_id") or "")
                        rec.n_rows = int(mat.get("n_rows") or 0)
                        rec.n_cols = int(mat.get("n_cols") or 0)
                    except Exception as exc:
                        rec.materialize_error = str(exc)

                    # --- Client-side selection ---
                    if rec.result_id and rec.n_rows and rec.n_cols:
                        try:
                            ds, fs, fmt, nb, ttfr = await client_fetch_recommended(
                                session,
                                http,
                                result_id=rec.result_id,
                                n_rows=rec.n_rows,
                                n_cols=rec.n_cols,
                                target=target,
                                rows_per_chunk=rpc,
                                prefer_streaming=bool(args.prefer_streaming),
                                server_url=str(args.server_url),
                            )
                            rec.describe_s = ds
                            rec.client_fetch_s = fs
                            rec.client_chosen_format = fmt
                            rec.client_bytes = nb
                            rec.client_ttfr_s = ttfr
                            rec.client_wire_bytes = nb
                            if fmt == "json" and rec.logical_json_records_bytes is not None:
                                rec.client_wire_bytes = rec.logical_json_records_bytes
                        except Exception as exc:
                            rec.client_error = str(exc)

                    # --- Server-side auto: execute + select in one tool call ---
                    try:
                        t0 = time.perf_counter()
                        if bool(args.reuse_materialized_for_auto) and rec.result_id and rec.n_rows and rec.n_cols:
                            auto = await call_large_result_auto(
                                session,
                                rec.n_rows,
                                rec.n_cols,
                                rows_per_chunk=rpc,
                                result_id=rec.result_id,
                                optimization_target=target.value,
                                prefer_streaming=bool(args.prefer_streaming),
                                use_mab=False,
                            )
                        else:
                            auto = await call_bird_query_auto(
                                session,
                                db_id=db_id,
                                sql=sql,
                                optimization_target=target.value,
                                rows_per_chunk=rpc,
                                prefer_streaming=bool(args.prefer_streaming),
                                use_mab=False,
                                max_rows=args.max_rows,
                            )
                        rec.server_auto_call_s = time.perf_counter() - t0
                        rec.server_auto_chosen_format = str(auto.get("chosen_format") or "")
                        fs, nb, ttfr = await measure_server_auto_payload(
                            http,
                            auto,
                            server_url=str(args.server_url),
                            logical_json_records_bytes=rec.logical_json_records_bytes,
                        )
                        rec.server_auto_fetch_s = fs
                        rec.server_auto_bytes = nb
                        rec.server_auto_ttfr_s = ttfr
                        rec.server_auto_wire_bytes = nb
                        if rec.server_auto_chosen_format == "json" and rec.logical_json_records_bytes is not None:
                            rec.server_auto_wire_bytes = rec.logical_json_records_bytes
                    except Exception as exc:
                        rec.server_auto_error = str(exc)

                    append_jsonl(out_path, rec)


def main() -> None:
    ap = argparse.ArgumentParser(description="BIRD server-exec end-to-end benchmark")
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--bird-questions", default=DEFAULT_QUESTIONS)
    ap.add_argument(
        "--max-queries",
        type=int,
        default=0,
        help="0 = all queries in questions file (full BIRD); otherwise limit to N",
    )
    ap.add_argument("--max-rows", type=int, default=MAX_RESULT_ROWS)
    ap.add_argument("--rows-per-chunk", type=int, default=8192)
    ap.add_argument(
        "--rows-per-chunk-list",
        default="",
        help="Comma-separated rows_per_chunk values to run (overrides --rows-per-chunk when set)",
    )
    ap.add_argument("--prefer-streaming", action="store_true", help="Pass prefer_streaming=true to selector/auto tools")
    ap.add_argument(
        "--targets",
        default="",
        help="Comma-separated targets to run: min_bytes,min_latency,min_time_to_first_rows. Default: FORMAT_SELECT_TARGET",
    )
    ap.add_argument("--mcp-url", default=DEFAULT_MCP_URL)
    ap.add_argument("--server-url", default="http://localhost:8000")
    ap.add_argument(
        "--reuse-materialized-for-auto",
        action="store_true",
        help="Benchmark optimization: have server_auto reuse the materialized result_id instead of re-executing SQL.",
    )
    ap.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    ap.add_argument("--overwrite", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_bench(args))


if __name__ == "__main__":
    main()

