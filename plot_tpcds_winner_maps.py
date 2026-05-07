"""
Generate winner-map plots for TPC-DS format selection objectives.

Outputs to results/figures/poster/:
  - fig_P7_tpcds_winner_map_min_bytes.(png|pdf)
  - fig_P8_tpcds_winner_map_min_latency.(png|pdf)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap

from format_selector import OptimizationTarget, SelectionContext, select_format_with_hints

IN_PATH = Path("results/tpcds_format_hints.json")
CAL_PATH = Path("results/format_latency_calibration_tpcds.json")
OUT_DIR = Path("results/figures/poster")

FORMATS = ["json", "parquet_blob", "arrow_ipc_blob"]
FMT_TO_IDX = {f: i for i, f in enumerate(FORMATS)}
FMT_TO_LABEL = {"json": "JSON", "parquet_blob": "Parquet", "arrow_ipc_blob": "Arrow IPC"}
COLORS = ["#4C78A8", "#F58518", "#54A24B"]


def _load_rows() -> List[Dict[str, Any]]:
    data = json.loads(IN_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError("Unexpected tpcds_format_hints.json structure")
    return data


def _build_hints(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "json_bytes": int(r["json_bytes"]),
        "parquet_bytes": int(r["parquet_bytes"]),
        "arrow_ipc_bytes": int(r["arrow_ipc_bytes"]),
        "parquet_stream_first_chunk_bytes": int(r["parquet_stream_first_chunk_bytes"]),
        "arrow_ipc_stream_first_chunk_bytes": int(r["arrow_ipc_stream_first_chunk_bytes"]),
    }


def _winner_map(rows: List[Dict[str, Any]], target: OptimizationTarget) -> tuple[np.ndarray, List[int], List[int]]:
    row_vals = sorted({int(r["n_rows"]) for r in rows})
    col_vals = sorted({int(r["n_cols"]) for r in rows})
    mat = np.full((len(row_vals), len(col_vals)), fill_value=np.nan)

    for r in rows:
        rr = row_vals.index(int(r["n_rows"]))
        cc = col_vals.index(int(r["n_cols"]))
        ctx = SelectionContext(
            n_rows=int(r["n_rows"]),
            n_cols=int(r["n_cols"]),
            target=target,
            prefer_streaming=False,
        )
        winner = select_format_with_hints(ctx, _build_hints(r))
        if winner not in FMT_TO_IDX:
            winner = "parquet_blob"
        mat[rr, cc] = FMT_TO_IDX[winner]
    return mat, row_vals, col_vals


def _draw_map(mat: np.ndarray, row_vals: List[int], col_vals: List[int], title: str, out_stem: str) -> None:
    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    cmap = ListedColormap(COLORS)
    ax.imshow(mat, cmap=cmap, aspect="auto", interpolation="nearest", vmin=0, vmax=len(FORMATS) - 1)

    ax.set_xticks(np.arange(len(col_vals)))
    ax.set_xticklabels([str(x) for x in col_vals])
    ax.set_xlabel("Columns")
    ax.set_yticks(np.arange(len(row_vals)))
    ax.set_yticklabels([f"{x:,}" for x in row_vals])
    ax.set_ylabel("Rows")
    ax.set_title(title)

    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            fidx = int(mat[i, j])
            ax.text(j, i, FMT_TO_LABEL[FORMATS[fidx]], ha="center", va="center", fontsize=9, color="white")

    handles = [
        plt.Line2D([], [], marker="s", linestyle="none", markersize=10, color=COLORS[i], label=FMT_TO_LABEL[f])
        for i, f in enumerate(FORMATS)
    ]
    ax.legend(handles=handles, frameon=False, loc="upper left", bbox_to_anchor=(1.02, 1.0))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"{out_stem}.png", dpi=260)
    fig.savefig(OUT_DIR / f"{out_stem}.pdf")
    plt.close(fig)


def main() -> None:
    if not IN_PATH.exists():
        raise FileNotFoundError(f"Missing input: {IN_PATH}")
    rows = _load_rows()
    if not rows:
        raise RuntimeError("No rows in tpcds_format_hints.json")

    # Use calibrated ACE-style proxy for min_latency to match selector logic under shaped networks.
    if CAL_PATH.exists():
        os.environ["FORMAT_LATENCY_CALIBRATION_JSON"] = str(CAL_PATH)
    os.environ.setdefault("FORMAT_LATENCY_NETWORK_MBPS", "50")

    mat_b, row_vals, col_vals = _winner_map(rows, OptimizationTarget.MIN_BYTES)
    _draw_map(
        mat_b,
        row_vals,
        col_vals,
        title="Winning format by slice (objective: min_bytes)",
        out_stem="fig_P7_tpcds_winner_map_min_bytes",
    )

    mat_l, row_vals, col_vals = _winner_map(rows, OptimizationTarget.MIN_LATENCY)
    _draw_map(
        mat_l,
        row_vals,
        col_vals,
        title="Winning format by slice (objective: min_latency)",
        out_stem="fig_P8_tpcds_winner_map_min_latency",
    )
    print(f"Wrote winner maps to {OUT_DIR}/")


if __name__ == "__main__":
    main()
