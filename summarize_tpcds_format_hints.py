"""
Summarize results/tpcds_format_hints.json into markdown + JSON.

Also emits a FORMAT_LATENCY_CALIBRATION_JSON-compatible snippet derived from
measured decode times (ns/byte) for json/parquet_blob/arrow_ipc_blob.
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

DEFAULT_INPUT = Path("results/tpcds_format_hints.json")
DEFAULT_MD = Path("results/tpcds_format_hints_summary.md")
DEFAULT_JSON = Path("results/tpcds_format_hints_summary.json")
DEFAULT_CAL_JSON = Path("results/format_latency_calibration_tpcds.json")


def _median(xs: Sequence[float]) -> Optional[float]:
    ys = [float(x) for x in xs if x is not None]  # type: ignore[truthy-bool]
    if not ys:
        return None
    return float(statistics.median(ys))


def _p95(xs: Sequence[float]) -> Optional[float]:
    ys = sorted(float(x) for x in xs if x is not None)  # type: ignore[truthy-bool]
    if not ys:
        return None
    i = max(0, min(len(ys) - 1, int(round(0.95 * (len(ys) - 1)))))
    return ys[i]


def load_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    json_over_pq = []
    json_over_ipc = []
    pq_over_ipc = []

    json_ns_per_b = []
    pq_ns_per_b = []
    ipc_ns_per_b = []

    for r in rows:
        jb = r.get("json_bytes")
        pb = r.get("parquet_bytes")
        ib = r.get("arrow_ipc_bytes")
        if isinstance(jb, int) and isinstance(pb, int) and pb > 0:
            json_over_pq.append(jb / pb)
        if isinstance(jb, int) and isinstance(ib, int) and ib > 0:
            json_over_ipc.append(jb / ib)
        if isinstance(pb, int) and isinstance(ib, int) and ib > 0:
            pq_over_ipc.append(pb / ib)

        jd = r.get("json_decode_s")
        pd = r.get("parquet_decode_s")
        idc = r.get("arrow_ipc_decode_s")
        if isinstance(jd, (int, float)) and isinstance(jb, int) and jb > 0:
            json_ns_per_b.append(float(jd) * 1e9 / float(jb))
        if isinstance(pd, (int, float)) and isinstance(pb, int) and pb > 0:
            pq_ns_per_b.append(float(pd) * 1e9 / float(pb))
        if isinstance(idc, (int, float)) and isinstance(ib, int) and ib > 0:
            ipc_ns_per_b.append(float(idc) * 1e9 / float(ib))

    return {
        "n_slices": len(rows),
        "median_ratio_json_over_parquet": _median(json_over_pq),
        "p95_ratio_json_over_parquet": _p95(json_over_pq),
        "median_ratio_json_over_arrow_ipc": _median(json_over_ipc),
        "median_ratio_parquet_over_arrow_ipc": _median(pq_over_ipc),
        "decode_ns_per_byte": {
            "json": _median(json_ns_per_b),
            "parquet_blob": _median(pq_ns_per_b),
            "arrow_ipc_blob": _median(ipc_ns_per_b),
        },
    }


def write_md(summary: Dict[str, Any], md_path: Path) -> None:
    md_path.parent.mkdir(parents=True, exist_ok=True)
    dns = summary.get("decode_ns_per_byte") or {}
    lines = [
        "# TPC-DS format hints summary",
        "",
        f"- **Slices:** {summary.get('n_slices', 0)}",
        "",
        "## Size ratios",
        "",
        f"- **median(json/parquet)**: {summary.get('median_ratio_json_over_parquet')}",
        f"- **p95(json/parquet)**: {summary.get('p95_ratio_json_over_parquet')}",
        f"- **median(json/arrow_ipc)**: {summary.get('median_ratio_json_over_arrow_ipc')}",
        f"- **median(parquet/arrow_ipc)**: {summary.get('median_ratio_parquet_over_arrow_ipc')}",
        "",
        "## Decode proxy (ns/byte)",
        "",
        f"- json: {dns.get('json')}",
        f"- parquet_blob: {dns.get('parquet_blob')}",
        f"- arrow_ipc_blob: {dns.get('arrow_ipc_blob')}",
        "",
        "This `decode_ns_per_byte` dict is directly usable as `FORMAT_LATENCY_CALIBRATION_JSON`.",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Summarize TPC-DS format hints")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--md", type=Path, default=DEFAULT_MD)
    ap.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--calibration-json", type=Path, default=DEFAULT_CAL_JSON)
    args = ap.parse_args()

    rows = load_rows(args.input)
    summary = summarize(rows)
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_md(summary, args.md)
    args.calibration_json.parent.mkdir(parents=True, exist_ok=True)
    args.calibration_json.write_text(
        json.dumps({"decode_ns_per_byte": summary.get("decode_ns_per_byte") or {}}, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {args.md}, {args.json_out}, and {args.calibration_json}")


if __name__ == "__main__":
    main()

