"""
Summarize results/bird_server_exec_e2e.jsonl into markdown + JSON.

Focuses on end-to-end comparisons:
  - baseline (one MCP call, inline JSON)
  - client-side selection (materialize + describe + chosen fetch)
  - server auto (one MCP call + optional fetch)
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

DEFAULT_INPUT = Path("results/bird_server_exec_e2e.jsonl")


def _median(vals: Sequence[Optional[float]]) -> Optional[float]:
    xs = [float(v) for v in vals if v is not None]
    if not xs:
        return None
    return float(statistics.median(xs))


def _p95(vals: Sequence[Optional[float]]) -> Optional[float]:
    xs = sorted(float(v) for v in vals if v is not None)
    if not xs:
        return None
    i = max(0, min(len(xs) - 1, int(round(0.95 * (len(xs) - 1)))))
    return xs[i]


def load(path: Path) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    if not path.exists():
        return [], None
    rows: List[Dict[str, Any]] = []
    header: Optional[Dict[str, Any]] = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("type") == "bird_server_exec_e2e_run_header":
            header = obj
        else:
            rows.append(obj)
    return rows, header


def summarize(rows: List[Dict[str, Any]], header: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    ok = [r for r in rows if not r.get("baseline_error") and r.get("baseline_s") is not None]
    baseline_failed = [r for r in rows if r.get("baseline_error")]

    def total_client_s(r: Dict[str, Any]) -> Optional[float]:
        ms, ds, fs = r.get("materialize_s"), r.get("describe_s"), r.get("client_fetch_s")
        if ms is None or ds is None or fs is None:
            return None
        return float(ms) + float(ds) + float(fs)

    def total_server_auto_s(r: Dict[str, Any]) -> Optional[float]:
        cs, fs = r.get("server_auto_call_s"), r.get("server_auto_fetch_s")
        if cs is None:
            return None
        return float(cs) + float(fs or 0.0)

    baseline_s = [r.get("baseline_s") for r in rows]
    client_s = [total_client_s(r) for r in rows]
    auto_s = [total_server_auto_s(r) for r in rows]

    baseline_b = [r.get("baseline_bytes") for r in rows]
    client_b = [r.get("client_bytes") for r in rows]
    auto_b = [r.get("server_auto_bytes") for r in rows]
    baseline_wire_b = [r.get("baseline_wire_bytes") for r in rows]
    client_wire_b = [r.get("client_wire_bytes") for r in rows]
    auto_wire_b = [r.get("server_auto_wire_bytes") for r in rows]
    logical_b = [r.get("logical_json_records_bytes") for r in rows]

    # Ratios where both exist
    ratio_base_over_client_lat: List[float] = []
    ratio_base_over_auto_lat: List[float] = []
    ratio_base_over_client_bytes: List[float] = []
    ratio_base_over_auto_bytes: List[float] = []
    ratio_base_over_client_wire_bytes: List[float] = []
    ratio_base_over_auto_wire_bytes: List[float] = []

    for r in rows:
        b = r.get("baseline_s")
        c = total_client_s(r)
        a = total_server_auto_s(r)
        if b is not None and c is not None and c > 0:
            ratio_base_over_client_lat.append(float(b) / float(c))
        if b is not None and a is not None and a > 0:
            ratio_base_over_auto_lat.append(float(b) / float(a))
        bb = r.get("baseline_bytes")
        cb = r.get("client_bytes")
        ab = r.get("server_auto_bytes")
        if isinstance(bb, int) and isinstance(cb, int) and cb > 0:
            ratio_base_over_client_bytes.append(float(bb) / float(cb))
        if isinstance(bb, int) and isinstance(ab, int) and ab > 0:
            ratio_base_over_auto_bytes.append(float(bb) / float(ab))
        bw = r.get("baseline_wire_bytes")
        cw = r.get("client_wire_bytes")
        aw = r.get("server_auto_wire_bytes")
        if isinstance(bw, int) and isinstance(cw, int) and cw > 0:
            ratio_base_over_client_wire_bytes.append(float(bw) / float(cw))
        if isinstance(bw, int) and isinstance(aw, int) and aw > 0:
            ratio_base_over_auto_wire_bytes.append(float(bw) / float(aw))

    fmt_client: Dict[str, int] = {}
    fmt_auto: Dict[str, int] = {}
    for r in rows:
        fc = r.get("client_chosen_format") or ""
        fa = r.get("server_auto_chosen_format") or ""
        if fc:
            fmt_client[fc] = fmt_client.get(fc, 0) + 1
        if fa:
            fmt_auto[fa] = fmt_auto.get(fa, 0) + 1

    # TTFR distributions (streaming story)
    ttfr_client = [r.get("client_ttfr_s") for r in rows if r.get("client_ttfr_s") is not None]
    ttfr_auto = [r.get("server_auto_ttfr_s") for r in rows if r.get("server_auto_ttfr_s") is not None]

    # Baseline failure rate vs size bucket (use materialized n_rows*n_cols when available).
    def bucket_cells(cells: int) -> str:
        if cells <= 0:
            return "0"
        if cells <= 10_000:
            return "1-1e4"
        if cells <= 100_000:
            return "1e4-1e5"
        if cells <= 1_000_000:
            return "1e5-1e6"
        return "1e6+"

    by_bucket: Dict[str, Dict[str, int]] = {}
    for r in rows:
        nr = int(r.get("n_rows") or 0)
        nc = int(r.get("n_cols") or 0)
        cells = nr * nc
        b = bucket_cells(cells)
        by_bucket.setdefault(b, {"total": 0, "baseline_failed": 0})
        by_bucket[b]["total"] += 1
        if r.get("baseline_error"):
            by_bucket[b]["baseline_failed"] += 1

    return {
        "run_header": header,
        "total_records": len(rows),
        "baseline_ok": len(ok),
        "baseline_failed": len(baseline_failed),
        "baseline_failed_rate": (len(baseline_failed) / len(rows)) if rows else None,
        "median_baseline_s": _median(baseline_s),
        "p95_baseline_s": _p95(baseline_s),
        "median_client_total_s": _median(client_s),
        "p95_client_total_s": _p95(client_s),
        "median_server_auto_total_s": _median(auto_s),
        "p95_server_auto_total_s": _p95(auto_s),
        "median_baseline_bytes": _median([float(x) for x in baseline_b if x is not None]),
        "median_client_bytes": _median([float(x) for x in client_b if x is not None]),
        "median_server_auto_bytes": _median([float(x) for x in auto_b if x is not None]),
        "median_logical_json_records_bytes": _median([float(x) for x in logical_b if x is not None]),
        "median_baseline_wire_bytes": _median([float(x) for x in baseline_wire_b if x is not None]),
        "median_client_wire_bytes": _median([float(x) for x in client_wire_b if x is not None]),
        "median_server_auto_wire_bytes": _median([float(x) for x in auto_wire_b if x is not None]),
        "median_ratio_baseline_over_client_latency": _median(ratio_base_over_client_lat) if ratio_base_over_client_lat else None,
        "median_ratio_baseline_over_auto_latency": _median(ratio_base_over_auto_lat) if ratio_base_over_auto_lat else None,
        "median_ratio_baseline_over_client_bytes": _median(ratio_base_over_client_bytes) if ratio_base_over_client_bytes else None,
        "median_ratio_baseline_over_auto_bytes": _median(ratio_base_over_auto_bytes) if ratio_base_over_auto_bytes else None,
        "median_ratio_baseline_over_client_wire_bytes": _median(ratio_base_over_client_wire_bytes)
        if ratio_base_over_client_wire_bytes
        else None,
        "median_ratio_baseline_over_auto_wire_bytes": _median(ratio_base_over_auto_wire_bytes)
        if ratio_base_over_auto_wire_bytes
        else None,
        "median_client_ttfr_s": _median(ttfr_client) if ttfr_client else None,
        "p95_client_ttfr_s": _p95(ttfr_client) if ttfr_client else None,
        "median_server_auto_ttfr_s": _median(ttfr_auto) if ttfr_auto else None,
        "p95_server_auto_ttfr_s": _p95(ttfr_auto) if ttfr_auto else None,
        "baseline_failure_by_cells_bucket": by_bucket,
        "client_chosen_format_counts": fmt_client,
        "server_auto_chosen_format_counts": fmt_auto,
    }


def write_md(summary: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    h = summary.get("run_header") or {}
    lines = [
        "# BIRD server-exec E2E benchmark summary",
        "",
        "## Run configuration",
        "",
        f"- **Records:** {summary.get('total_records', 0)}",
        f"- **Target:** {h.get('format_select_target', 'n/a')}",
        f"- **rows_per_chunk:** {h.get('rows_per_chunk', 'n/a')}",
        f"- **max_rows:** {h.get('max_rows', 'n/a')}",
        f"- **PARQUET_ENCODING_STRATEGY:** {h.get('PARQUET_ENCODING_STRATEGY', 'n/a')}",
        f"- **PARQUET_COMPRESSION:** {h.get('PARQUET_COMPRESSION', 'n/a')}",
        f"- **ARROW_IPC_COMPRESSION:** {h.get('ARROW_IPC_COMPRESSION', 'n/a')}",
        f"- **prefer_streaming:** {h.get('prefer_streaming', 'n/a')}",
        f"- **network:** {h.get('network', 'n/a')}",
        "",
        "## Latency (seconds, end-to-end)",
        "",
        "| arm | median | p95 |",
        "|---|---:|---:|",
        f"| baseline (inline json) | {_fmt(summary.get('median_baseline_s'))} | {_fmt(summary.get('p95_baseline_s'))} |",
        f"| client (materialize+describe+fetch) | {_fmt(summary.get('median_client_total_s'))} | {_fmt(summary.get('p95_client_total_s'))} |",
        f"| server_auto (call+fetch) | {_fmt(summary.get('median_server_auto_total_s'))} | {_fmt(summary.get('p95_server_auto_total_s'))} |",
        "",
        "## Payload sizes (bytes, median)",
        "",
        f"- baseline: {_fmt(summary.get('median_baseline_bytes'))}",
        f"- client: {_fmt(summary.get('median_client_bytes'))}",
        f"- server_auto: {_fmt(summary.get('median_server_auto_bytes'))}",
        "",
        "## Normalized payload metrics (bytes, median)",
        "",
        "- `logical_json_records_bytes`: records-only JSON size (same logical payload baseline for all arms).",
        "- `*_wire_bytes`: normalized wire payload where JSON uses records-only bytes; stream includes framing overhead.",
        "",
        f"- logical_json_records_bytes: {_fmt(summary.get('median_logical_json_records_bytes'))}",
        f"- baseline_wire_bytes: {_fmt(summary.get('median_baseline_wire_bytes'))}",
        f"- client_wire_bytes: {_fmt(summary.get('median_client_wire_bytes'))}",
        f"- server_auto_wire_bytes: {_fmt(summary.get('median_server_auto_wire_bytes'))}",
        "",
        "## Ratios (median)",
        "",
        f"- baseline/client latency: {_fmt(summary.get('median_ratio_baseline_over_client_latency'))}",
        f"- baseline/server_auto latency: {_fmt(summary.get('median_ratio_baseline_over_auto_latency'))}",
        f"- baseline/client bytes: {_fmt(summary.get('median_ratio_baseline_over_client_bytes'))}",
        f"- baseline/server_auto bytes: {_fmt(summary.get('median_ratio_baseline_over_auto_bytes'))}",
        f"- baseline/client wire_bytes: {_fmt(summary.get('median_ratio_baseline_over_client_wire_bytes'))}",
        f"- baseline/server_auto wire_bytes: {_fmt(summary.get('median_ratio_baseline_over_auto_wire_bytes'))}",
        "",
        "## Chosen format counts",
        "",
        f"- client: {summary.get('client_chosen_format_counts')}",
        f"- server_auto: {summary.get('server_auto_chosen_format_counts')}",
        "",
        "## Baseline feasibility",
        "",
        f"- **Baseline failed:** {summary.get('baseline_failed', 0)}",
        f"- **Baseline failed rate:** {_fmt(summary.get('baseline_failed_rate'))}",
        "",
        "## Baseline failure rate by result size (cells bucket = n_rows*n_cols from materialize arm)",
        "",
        "| bucket | total | baseline_failed |",
        "|---|---:|---:|",
    ]
    for b, row in (summary.get("baseline_failure_by_cells_bucket") or {}).items():
        lines.append(f"| {b} | {row.get('total', 0)} | {row.get('baseline_failed', 0)} |")
    lines.extend(
        [
            "",
            "## Time to first rows (TTFR, seconds) — streaming only",
            "",
            f"| arm | median | p95 |",
            f"|---|---:|---:|",
            f"| client | {_fmt(summary.get('median_client_ttfr_s'))} | {_fmt(summary.get('p95_client_ttfr_s'))} |",
            f"| server_auto | {_fmt(summary.get('median_server_auto_ttfr_s'))} | {_fmt(summary.get('p95_server_auto_ttfr_s'))} |",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.6f}".rstrip("0").rstrip(".")
    return str(v)


def main() -> None:
    ap = argparse.ArgumentParser(description="Summarize bird_server_exec_e2e.jsonl")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument(
        "--md",
        type=Path,
        default=None,
        help="Default: alongside --input as <stem>_summary.md",
    )
    ap.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Default: alongside --input as <stem>_summary.json",
    )
    args = ap.parse_args()

    rows, header = load(args.input)
    summary = summarize(rows, header)
    md_path = args.md or args.input.with_name(f"{args.input.stem}_summary.md")
    json_path = args.json_out or args.input.with_name(f"{args.input.stem}_summary.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_md(summary, md_path)
    print(f"Wrote {md_path} and {json_path} ({len(rows)} records)")


if __name__ == "__main__":
    main()

