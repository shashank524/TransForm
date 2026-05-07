"""
Generate paper-ready figures from results/tpcds_format_hints.json.

Outputs to results/figures/:
  - fig_A1_tpcds_size_scaling.(png|pdf)
  - fig_A2_tpcds_first_chunk_bytes.(png|pdf)
  - fig_A3_tpcds_decode_ns_per_byte.(png|pdf)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt
import numpy as np

IN_PATH = Path("results/tpcds_format_hints.json")
OUT_DIR = Path("results/figures")


def load_rows() -> List[Dict[str, Any]]:
    data = json.loads(IN_PATH.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def save(fig: plt.Figure, stem: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"{stem}.png", dpi=200)
    fig.savefig(OUT_DIR / f"{stem}.pdf")


def fig_a1_size_scaling(rows: List[Dict[str, Any]]) -> None:
    # Group by n_cols, plot bytes vs n_rows for each format.
    cols = sorted({int(r["n_cols"]) for r in rows})
    fig, axes = plt.subplots(1, len(cols), figsize=(4.6 * len(cols), 3.6), sharey=True)
    if len(cols) == 1:
        axes = [axes]
    for ax, n_cols in zip(axes, cols):
        rs = [r for r in rows if int(r["n_cols"]) == n_cols]
        rs = sorted(rs, key=lambda x: int(x["n_rows"]))
        x = np.array([int(r["n_rows"]) for r in rs], dtype=float)
        for key, label in [
            ("json_bytes", "JSON"),
            ("parquet_bytes", "Parquet"),
            ("arrow_ipc_bytes", "Arrow IPC"),
        ]:
            y = np.array([int(r[key]) for r in rs], dtype=float)
            ax.plot(x, y, marker="o", linewidth=1.8, label=label)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_title(f"{n_cols} columns")
        ax.set_xlabel("rows (log)")
        ax.grid(True, which="both", linewidth=0.3, alpha=0.35)
    axes[0].set_ylabel("bytes (log)")
    axes[-1].legend(frameon=False, loc="best")
    fig.suptitle("TPC-DS catalog_sales: payload size scaling", y=1.02)
    save(fig, "fig_A1_tpcds_size_scaling")


def fig_a2_first_chunk(rows: List[Dict[str, Any]]) -> None:
    # Scatter: first-chunk bytes vs total bytes (per format), colored by n_cols.
    fig, ax = plt.subplots(figsize=(5.2, 4.2))
    ncols = np.array([int(r["n_cols"]) for r in rows], dtype=int)
    cmap = plt.get_cmap("viridis")
    norm = plt.Normalize(vmin=min(ncols), vmax=max(ncols))

    for fc_key, total_key, label, marker in [
        ("parquet_stream_first_chunk_bytes", "parquet_bytes", "Parquet stream (first chunk)", "o"),
        ("arrow_ipc_stream_first_chunk_bytes", "arrow_ipc_bytes", "Arrow IPC stream (first chunk)", "s"),
    ]:
        x = np.array([int(r[total_key]) for r in rows], dtype=float)
        y = np.array([int(r[fc_key]) for r in rows], dtype=float)
        ax.scatter(x, y, c=cmap(norm(ncols)), s=48, marker=marker, alpha=0.9, label=label, edgecolors="none")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("total bytes (log)")
    ax.set_ylabel("first-chunk bytes (log)")
    ax.set_title("First-chunk size vs total size (TTFR proxy)")
    ax.grid(True, which="both", linewidth=0.3, alpha=0.35)
    ax.legend(frameon=False, loc="best")
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.02)
    cbar.set_label("n_cols")
    save(fig, "fig_A2_tpcds_first_chunk_bytes")


def fig_a3_decode_ns(rows: List[Dict[str, Any]]) -> None:
    # Bar chart: ns/byte per format per slice; show median and range.
    def ns_per_b(decode_s: float, num_bytes: int) -> float:
        return float(decode_s) * 1e9 / float(num_bytes)

    json_vals, pq_vals, ipc_vals = [], [], []
    for r in rows:
        json_vals.append(ns_per_b(float(r["json_decode_s"]), int(r["json_bytes"])))
        pq_vals.append(ns_per_b(float(r["parquet_decode_s"]), int(r["parquet_bytes"])))
        ipc_vals.append(ns_per_b(float(r["arrow_ipc_decode_s"]), int(r["arrow_ipc_bytes"])))

    series = [
        ("json", json_vals),
        ("parquet_blob", pq_vals),
        ("arrow_ipc_blob", ipc_vals),
    ]
    med = [float(np.median(v)) for _, v in series]
    p25 = [float(np.percentile(v, 25)) for _, v in series]
    p75 = [float(np.percentile(v, 75)) for _, v in series]

    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    x = np.arange(len(series))
    ax.bar(x, med, width=0.6, color=["#4C78A8", "#F58518", "#54A24B"])
    ax.errorbar(x, med, yerr=[np.array(med) - np.array(p25), np.array(p75) - np.array(med)], fmt="none", ecolor="black", capsize=4, linewidth=1)
    ax.set_xticks(x, [s[0] for s in series], rotation=0)
    ax.set_ylabel("decode ns/byte (median, IQR)")
    ax.set_title("Decode proxy for min_latency model (TPC-DS)")
    ax.grid(True, axis="y", linewidth=0.3, alpha=0.35)
    save(fig, "fig_A3_tpcds_decode_ns_per_byte")


def main() -> None:
    if not IN_PATH.exists():
        raise FileNotFoundError(f"Missing input: {IN_PATH}")
    rows = load_rows()
    if not rows:
        raise RuntimeError("No rows in tpcds_format_hints.json")
    fig_a1_size_scaling(rows)
    fig_a2_first_chunk(rows)
    fig_a3_decode_ns(rows)
    print(f"Wrote figures to {OUT_DIR}/")


if __name__ == "__main__":
    main()

