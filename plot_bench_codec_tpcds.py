"""
Generate paper-ready figures from results/bench_codec_tpcds.json.

Outputs to results/figures/:
  - fig_C1_codec_bytes_bars.(png|pdf)
  - fig_C2_codec_tradeoff_scatter.(png|pdf)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np

IN_PATH = Path("results/bench_codec_tpcds.json")
OUT_DIR = Path("results/figures")


def load_rows() -> List[Dict[str, Any]]:
    data = json.loads(IN_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def save(fig: plt.Figure, stem: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"{stem}.png", dpi=200)
    fig.savefig(OUT_DIR / f"{stem}.pdf")


def _key(r: Dict[str, Any]) -> Tuple[int, int]:
    return int(r.get("n_rows") or 0), int(r.get("n_cols") or 0)


def fig_c1_bytes_bars(rows: List[Dict[str, Any]]) -> None:
    # Focus on Parquet variants (codec x strategy), show for the largest slice.
    slices = sorted({_key(r) for r in rows if r.get("codec") != "json"})
    if not slices:
        raise RuntimeError("No parquet rows")
    nr, nc = slices[-1]
    rs = [r for r in rows if _key(r) == (nr, nc) and r.get("codec") != "json"]

    labels = [f"{r['codec']}/{r['encoding_strategy']}" for r in rs]
    bytes_vals = np.array([int(r["bytes"]) for r in rs], dtype=float)
    order = np.argsort(bytes_vals)
    labels = [labels[i] for i in order]
    bytes_vals = bytes_vals[order]

    fig, ax = plt.subplots(figsize=(7.8, 3.6))
    ax.bar(np.arange(len(labels)), bytes_vals, color="#4C78A8")
    ax.set_xticks(np.arange(len(labels)), labels, rotation=35, ha="right")
    ax.set_ylabel("bytes")
    ax.set_title(f"TPC-DS Parquet bytes by codec/strategy ({nr:,} rows, {nc} cols)")
    ax.grid(True, axis="y", linewidth=0.3, alpha=0.35)
    save(fig, "fig_C1_codec_bytes_bars")


def fig_c2_tradeoff_scatter(rows: List[Dict[str, Any]]) -> None:
    # Scatter all parquet variants across slices: bytes vs total_time_s, label by codec/strategy.
    xs, ys, colors = [], [], []
    labels = []
    color_map = {
        "snappy": "#4C78A8",
        "gzip": "#F58518",
        "zstd": "#54A24B",
        "none": "#B279A2",
    }
    for r in rows:
        if r.get("codec") == "json":
            continue
        b = int(r["bytes"])
        total = float(r["encode_s"]) + float(r["decode_s"])
        xs.append(b)
        ys.append(total)
        colors.append(color_map.get(str(r.get("codec")), "#999999"))
        labels.append(f"{r.get('codec')}/{r.get('encoding_strategy')}")

    fig, ax = plt.subplots(figsize=(5.4, 4.2))
    ax.scatter(xs, ys, c=colors, s=46, alpha=0.75, edgecolors="none")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("bytes (log)")
    ax.set_ylabel("encode+decode seconds (log)")
    ax.set_title("Codec trade-off: size vs (encode+decode)")
    ax.grid(True, which="both", linewidth=0.3, alpha=0.35)
    # Legend by codec only (avoid clutter)
    handles = []
    for codec, col in color_map.items():
        handles.append(plt.Line2D([], [], marker="o", linestyle="none", color=col, label=codec))
    ax.legend(handles=handles, frameon=False, title="codec", loc="best")
    save(fig, "fig_C2_codec_tradeoff_scatter")


def main() -> None:
    if not IN_PATH.exists():
        raise FileNotFoundError(f"Missing input: {IN_PATH}")
    rows = load_rows()
    fig_c1_bytes_bars(rows)
    fig_c2_tradeoff_scatter(rows)
    print(f"Wrote figures to {OUT_DIR}/")


if __name__ == "__main__":
    main()

