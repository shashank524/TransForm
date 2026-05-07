"""
Summarize results/bench_codec_tpcds.json into Pareto tables + JSON.

Pareto efficiency is computed over:
  - bytes (smaller is better)
  - total_time_s = encode_s + decode_s (smaller is better)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

DEFAULT_INPUT = Path("results/bench_codec_tpcds.json")
DEFAULT_MD = Path("results/bench_codec_tpcds_pareto.md")
DEFAULT_JSON = Path("results/bench_codec_tpcds_pareto.json")


def load_rows(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def pareto_front(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Remove obviously invalid.
    pts: List[Dict[str, Any]] = []
    for r in rows:
        b = r.get("bytes")
        es = r.get("encode_s")
        ds = r.get("decode_s")
        if not isinstance(b, (int, float)) or not isinstance(es, (int, float)) or not isinstance(ds, (int, float)):
            continue
        pts.append({**r, "total_time_s": float(es) + float(ds)})

    front: List[Dict[str, Any]] = []
    for p in pts:
        dominated = False
        for q in pts:
            if q is p:
                continue
            if (q["bytes"] <= p["bytes"] and q["total_time_s"] <= p["total_time_s"]) and (
                q["bytes"] < p["bytes"] or q["total_time_s"] < p["total_time_s"]
            ):
                dominated = True
                break
        if not dominated:
            front.append(p)
    front.sort(key=lambda r: (float(r["bytes"]), float(r["total_time_s"])))
    return front


def group_by_slice(rows: List[Dict[str, Any]]) -> Dict[Tuple[int, int], List[Dict[str, Any]]]:
    out: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for r in rows:
        nr = int(r.get("n_rows") or 0)
        nc = int(r.get("n_cols") or 0)
        if nr <= 0 or nc <= 0:
            continue
        out.setdefault((nr, nc), []).append(r)
    return out


def write_md(summary: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# TPC-DS Parquet codec/encoding Pareto summary",
        "",
        "Objective: minimize **bytes** and **total_time_s = encode_s + decode_s**.",
        "",
    ]
    for key in sorted(summary.keys(), key=lambda t: (int(t.split("x")[0]), int(t.split("x")[1]))):
        front = summary[key]
        lines.append(f"## Slice {key} (Pareto front)")
        lines.append("")
        lines.append("| codec | strategy | bytes | encode_s | decode_s | total_time_s |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for r in front:
            lines.append(
                f"| {r.get('codec')} | {r.get('encoding_strategy')} | {int(r.get('bytes')):,} | "
                f"{float(r.get('encode_s')):.6f} | {float(r.get('decode_s')):.6f} | {float(r.get('total_time_s')):.6f} |"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Summarize bench_codec_tpcds.json as Pareto fronts")
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--md", type=Path, default=DEFAULT_MD)
    ap.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    args = ap.parse_args()

    rows = load_rows(args.input)
    grouped = group_by_slice(rows)
    out: Dict[str, Any] = {}
    for (nr, nc), rs in grouped.items():
        front = pareto_front([r for r in rs if r.get("codec") != "json"])
        out[f"{nr}x{nc}"] = front

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    write_md(out, args.md)
    print(f"Wrote {args.md} and {args.json_out}")


if __name__ == "__main__":
    main()

