"""
Summarize results/nl2sql_materialized.jsonl into markdown + JSON.

Usage:

    python summarize_nl2sql_materialized.py
    python summarize_nl2sql_materialized.py --input results/nl2sql_materialized.jsonl
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

DEFAULT_INPUT = Path("results/nl2sql_materialized.jsonl")
DEFAULT_MD = Path("results/nl2sql_materialized_summary.md")
DEFAULT_JSON = Path("results/nl2sql_materialized_summary.json")


def _row_bucket(n_rows: int) -> str:
    if n_rows <= 0:
        return "0"
    if n_rows <= 10:
        return "1-10"
    if n_rows <= 100:
        return "11-100"
    if n_rows <= 1000:
        return "101-1000"
    return "1001+"


def _median(vals: Sequence[Optional[float]]) -> Optional[float]:
    xs = [float(x) for x in vals if x is not None]
    if not xs:
        return None
    return float(statistics.median(xs))


def _p95(vals: Sequence[Optional[float]]) -> Optional[float]:
    xs = sorted(float(x) for x in vals if x is not None)
    if not xs:
        return None
    i = max(0, min(len(xs) - 1, int(round(0.95 * (len(xs) - 1)))))
    return xs[i]


def load_records(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def summarize(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    ok = [r for r in records if not r.get("error") and r.get("result_id")]
    failed = len(records) - len(ok)

    fmt_counts: Dict[str, int] = {}
    for r in ok:
        f = r.get("recommended_format") or "unknown"
        fmt_counts[f] = fmt_counts.get(f, 0) + 1

    def ratios_bytes(rs: List[Dict[str, Any]]) -> List[float]:
        xs: List[float] = []
        for r in rs:
            jb, pb = r.get("json_response_bytes"), r.get("parquet_blob_bytes")
            if jb is not None and pb is not None and pb > 0:
                xs.append(float(jb) / float(pb))
        return xs

    def ratios_latency(rs: List[Dict[str, Any]]) -> List[float]:
        xs: List[float] = []
        for r in rs:
            jt, rt = r.get("json_end_to_end_s"), r.get("recommended_end_to_end_s")
            if jt is not None and rt is not None and rt > 0:
                xs.append(float(jt) / float(rt))
        return xs

    all_bytes_ratios = ratios_bytes(ok)
    all_lat_ratios = ratios_latency(ok)

    buckets = ["all", "0", "1-10", "11-100", "101-1000", "1001+"]
    by_bucket: Dict[str, Any] = {}

    def slice_bucket(name: str) -> List[Dict[str, Any]]:
        if name == "all":
            return ok
        return [r for r in ok if _row_bucket(int(r.get("n_rows") or 0)) == name]

    for name in buckets:
        rs = slice_bucket(name)
        if name != "all" and not rs:
            continue
        jb = [r.get("json_response_bytes") for r in rs]
        pb = [r.get("parquet_blob_bytes") for r in rs]
        jt = [r.get("json_end_to_end_s") for r in rs]
        bt = [r.get("parquet_blob_end_to_end_s") for r in rs]
        rt = [r.get("recommended_end_to_end_s") for r in rs]
        sql_t = [r.get("sql_exec_s") for r in rs]
        reg_t = [r.get("register_s") for r in rs]
        desc_t = [r.get("describe_result_formats_s") for r in rs]
        br = ratios_bytes(rs)
        lr = ratios_latency(rs)

        baseline_e2e = []
        enhanced_e2e = []
        for r in rs:
            s = r.get("sql_exec_s")
            g = r.get("register_s")
            j = r.get("json_end_to_end_s")
            d = r.get("describe_result_formats_s")
            rec = r.get("recommended_end_to_end_s")
            if s is not None and g is not None and j is not None:
                baseline_e2e.append(float(s) + float(g) + float(j))
            if s is not None and g is not None and d is not None and rec is not None:
                enhanced_e2e.append(float(s) + float(g) + float(d) + float(rec))

        by_bucket[name] = {
            "count": len(rs),
            "median_json_bytes": _median(jb),
            "median_parquet_blob_bytes": _median(pb),
            "median_json_fetch_s": _median(jt),
            "median_parquet_blob_fetch_s": _median(bt),
            "median_recommended_fetch_s": _median(rt),
            "median_sql_exec_s": _median(sql_t),
            "median_register_s": _median(reg_t),
            "median_describe_s": _median(desc_t),
            "median_baseline_e2e_s": _median(baseline_e2e),
            "median_enhanced_e2e_s": _median(enhanced_e2e),
            "median_ratio_json_bytes_over_parquet_blob": _median(br) if br else None,
            "p95_ratio_json_bytes_over_parquet_blob": _p95(br) if br else None,
            "median_ratio_json_fetch_over_recommended_fetch": _median(lr) if lr else None,
            "p95_ratio_json_fetch_over_recommended_fetch": _p95(lr) if lr else None,
        }

    return {
        "total_lines": len(records),
        "successful_queries": len(ok),
        "failed_or_skipped": failed,
        "recommended_format_counts": fmt_counts,
        "overall_median_ratio_json_bytes_over_parquet_blob": _median(all_bytes_ratios)
        if all_bytes_ratios
        else None,
        "overall_median_ratio_json_fetch_over_recommended_fetch": _median(all_lat_ratios)
        if all_lat_ratios
        else None,
        "by_bucket": by_bucket,
    }


def write_markdown(summary: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# NL2SQL materialized MCP benchmark summary",
        "",
        f"- **Total records:** {summary['total_lines']}",
        f"- **Successful (with result_id, no error):** {summary['successful_queries']}",
        f"- **Failed / skipped:** {summary['failed_or_skipped']}",
        "",
        "## Recommended format (hint-driven selector)",
        "",
    ]
    for fmt, c in sorted(
        summary["recommended_format_counts"].items(), key=lambda x: -x[1]
    ):
        lines.append(f"- `{fmt}`: {c}")
    lines.extend(["", "## By row-count bucket", ""])
    header = (
        "| bucket | n | median json B | median pq blob B | "
        "median json fetch s | median rec fetch s | "
        "median baseline E2E s | median enhanced E2E s | "
        "median jsonB/pqB | median jsonLat/recLat |"
    )
    sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    lines.extend([header, sep])
    for name, row in summary["by_bucket"].items():
        lines.append(
            f"| {name} | {row['count']} | "
            f"{_fmt_opt_int(row.get('median_json_bytes'))} | "
            f"{_fmt_opt_int(row.get('median_parquet_blob_bytes'))} | "
            f"{_fmt_opt_f(row.get('median_json_fetch_s'), 4)} | "
            f"{_fmt_opt_f(row.get('median_recommended_fetch_s'), 4)} | "
            f"{_fmt_opt_f(row.get('median_baseline_e2e_s'), 4)} | "
            f"{_fmt_opt_f(row.get('median_enhanced_e2e_s'), 4)} | "
            f"{_fmt_opt_f(row.get('median_ratio_json_bytes_over_parquet_blob'), 2)} | "
            f"{_fmt_opt_f(row.get('median_ratio_json_fetch_over_recommended_fetch'), 2)} |"
        )
    lines.extend(
        [
            "",
            "**Baseline E2E (proxy):** `sql_exec_s + register_s + json_end_to_end_s`.",
            "",
            "**Enhanced E2E (proxy):** `sql_exec_s + register_s + describe_result_formats_s + recommended_end_to_end_s` "
            "(recommended path = json, parquet_blob, or parquet_stream per selector).",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt_opt_f(v: Optional[float], nd: int) -> str:
    if v is None:
        return "—"
    return f"{v:.{nd}f}"


def _fmt_opt_int(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return str(int(round(v)))


def main() -> None:
    p = argparse.ArgumentParser(description="Summarize nl2sql_materialized.jsonl")
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--markdown", type=Path, default=DEFAULT_MD)
    p.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    args = p.parse_args()

    records = load_records(args.input)
    summary = summarize(records)
    write_markdown(summary, args.markdown)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {args.markdown} and {args.json_out} ({len(records)} lines read)")


if __name__ == "__main__":
    main()
