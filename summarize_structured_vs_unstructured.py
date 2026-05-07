#!/usr/bin/env python3
"""Summarize results/structured_vs_unstructured*.jsonl into markdown + JSON."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _load(path: Path) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    header = None
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("type") == "structured_vs_unstructured_run_header":
            header = obj
        else:
            rows.append(obj)
    return header, rows


def _p95(xs: List[float]) -> float:
    if not xs:
        return float("nan")
    ys = sorted(xs)
    i = max(0, int(round(0.95 * (len(ys) - 1))))
    return ys[i]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--md", type=Path, default=None)
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()

    header, rows = _load(args.input)
    md_path = args.md or args.input.with_suffix("").with_name(
        args.input.stem + "_summary.md"
    )
    json_path = args.json_out or args.input.with_suffix("").with_name(
        args.input.stem + "_summary.json"
    )

    # Aggregate client total time (describe + fetch) by class × nominal × target
    buckets: Dict[str, List[float]] = {}
    bytes_buckets: Dict[str, List[int]] = {}
    for r in rows:
        cls = r.get("payload_class") or ""
        nom = r.get("nominal_target_bytes")
        tgt = r.get("target_name") or ""
        key = f"{cls}|{nom}|{tgt}"
        ds = r.get("client_describe_s")
        fs = r.get("client_fetch_s")
        if ds is not None and fs is not None:
            buckets.setdefault(key, []).append(float(ds) + float(fs))
        cb = r.get("client_bytes")
        if isinstance(cb, int):
            bytes_buckets.setdefault(key, []).append(cb)

    lines: List[str] = [
        "# Structured vs unstructured transport summary",
        "",
    ]
    if header:
        lines.append("## Run configuration")
        lines.append("")
        lines.append(f"- **targets:** {header.get('targets')}")
        lines.append(f"- **nominal sizes (bytes):** {header.get('nominal_size_bytes')}")
        lines.append(f"- **rows_per_chunk:** {header.get('rows_per_chunk')}")
        lines.append(f"- **prefer_streaming:** {header.get('prefer_streaming')}")
        lines.append(f"- **network:** `{header.get('network')}`")
        lines.append("")

    lines.append("## Client path (describe + fetch) — median / p95 seconds")
    lines.append("")
    lines.append("| payload_class | nominal_bytes | target | median_s | p95_s | median_client_bytes |")
    lines.append("|---|---:|---|---:|---:|---:|")

    keys_sorted = sorted(buckets.keys(), key=lambda k: (k.split("|")[1], k.split("|")[2], k.split("|")[0]))
    summary_json: Dict[str, Any] = {"header": header, "rows": rows, "aggregates": []}
    for key in keys_sorted:
        lat = buckets[key]
        med = statistics.median(lat) if lat else None
        p95v = _p95(lat) if lat else None
        parts = key.split("|")
        cls, nom, tgt = parts[0], parts[1], parts[2]
        bmed = statistics.median(bytes_buckets.get(key, [0])) if bytes_buckets.get(key) else None
        lines.append(
            f"| {cls} | {nom} | {tgt} | {med:.6f} | {p95v:.6f} | {bmed} |"
        )
        summary_json["aggregates"].append({
            "key": key,
            "median_client_latency_s": med,
            "p95_client_latency_s": p95v,
            "median_client_bytes": bmed,
            "n": len(lat),
        })

    lines.append("")
    lines.append("## Per-row detail")
    lines.append("")
    lines.append("See JSONL input for `client_chosen_format`, `server_auto_chosen_format`, and errors.")
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(json.dumps(summary_json, indent=2), encoding="utf-8")
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")


if __name__ == "__main__":
    main()
