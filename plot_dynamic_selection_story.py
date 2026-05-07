"""
Plots that emphasize "different formats win in different situations".

Outputs to results/figures/poster/:
  - fig_P9_min_latency_winner_by_bandwidth.(png|pdf)
  - fig_P10_bandwidth_crossover_json_parquet_arrow.(png|pdf)
  - fig_P11_structured_unstructured_tradeoff.(png|pdf)
  - fig_P12_payload_vs_latency_by_bandwidth.(png|pdf)
  - fig_P13_simple_payload_latency_tradeoff.(png|pdf)
  - fig_P14_streaming_ttfr_parquet_vs_arrow.(png|pdf)
  - fig_P15_structured_unstructured_simple.(png|pdf)
  - fig_P16_story_json_weakness_and_output_tradeoff.(png|pdf)
  - fig_P17_clean_story_tradeoffs.(png|pdf)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap

from format_selector import OptimizationTarget, SelectionContext, select_format_with_hints

RESULTS = Path("results")
OUT_DIR = RESULTS / "figures" / "poster"
TPCDS = RESULTS / "tpcds_format_hints.json"
CAL = RESULTS / "format_latency_calibration_tpcds.json"
STRUCTURED_FILES = {
    "LAN": RESULTS / "structured_vs_unstructured_network_lan.jsonl",
    "WAN": RESULTS / "structured_vs_unstructured_network_wan.jsonl",
    "Cellular": RESULTS / "structured_vs_unstructured_network_cellular.jsonl",
    "BadWifi": RESULTS / "structured_vs_unstructured_network_badwifi.jsonl",
}

FORMATS = ["json", "parquet_blob", "arrow_ipc_blob"]
FMT_LABEL = {"json": "JSON", "parquet_blob": "Parquet", "arrow_ipc_blob": "Arrow IPC"}
FMT_IDX = {k: i for i, k in enumerate(FORMATS)}
FMT_COLORS = ["#4C78A8", "#F58518", "#54A24B"]


def _save(fig: plt.Figure, stem: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"{stem}.png", dpi=260)
    fig.savefig(OUT_DIR / f"{stem}.pdf")
    plt.close(fig)


def _load_tpcds() -> List[Dict[str, Any]]:
    rows = json.loads(TPCDS.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError("Unexpected tpcds_format_hints.json structure")
    return rows


def _build_hints(r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "json_bytes": int(r["json_bytes"]),
        "parquet_bytes": int(r["parquet_bytes"]),
        "arrow_ipc_bytes": int(r["arrow_ipc_bytes"]),
        "parquet_stream_first_chunk_bytes": int(r["parquet_stream_first_chunk_bytes"]),
        "arrow_ipc_stream_first_chunk_bytes": int(r["arrow_ipc_stream_first_chunk_bytes"]),
    }


def _winner_for(rows: List[Dict[str, Any]], mbps: float, target: OptimizationTarget) -> List[str]:
    os.environ["FORMAT_LATENCY_CALIBRATION_JSON"] = str(CAL)
    os.environ["FORMAT_LATENCY_NETWORK_MBPS"] = str(mbps)
    winners: List[str] = []
    for r in rows:
        ctx = SelectionContext(
            n_rows=int(r["n_rows"]),
            n_cols=int(r["n_cols"]),
            target=target,
            prefer_streaming=False,
        )
        winners.append(select_format_with_hints(ctx, _build_hints(r)))
    return winners


def fig_p9_min_latency_winner_by_bandwidth(rows: List[Dict[str, Any]]) -> None:
    """
    Heatmap: rows are TPC-DS slices, columns are bandwidth regimes, color=winning format.
    This explicitly shows when Arrow IPC can beat Parquet on latency.
    """
    bandwidths = [5, 10, 50, 1000, 100000]  # Mbps
    slice_labels = [f"{int(r['n_rows']):,}x{int(r['n_cols'])}" for r in rows]

    mat = np.zeros((len(rows), len(bandwidths)))
    for j, b in enumerate(bandwidths):
        winners = _winner_for(rows, float(b), OptimizationTarget.MIN_LATENCY)
        for i, w in enumerate(winners):
            if w not in FMT_IDX:
                w = "parquet_blob"
            mat[i, j] = FMT_IDX[w]

    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    cmap = ListedColormap(FMT_COLORS)
    ax.imshow(mat, cmap=cmap, aspect="auto", interpolation="nearest", vmin=0, vmax=len(FORMATS) - 1)
    ax.set_xticks(np.arange(len(bandwidths)))
    ax.set_xticklabels([f"{b} Mbps" for b in bandwidths], rotation=0)
    ax.set_yticks(np.arange(len(slice_labels)))
    ax.set_yticklabels(slice_labels)
    ax.set_xlabel("Network bandwidth regime")
    ax.set_ylabel("TPC-DS slice (rows x columns)")
    ax.set_title("Winning format changes with bandwidth (objective: min_latency)")

    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            f = FORMATS[int(mat[i, j])]
            ax.text(j, i, FMT_LABEL[f], ha="center", va="center", fontsize=8, color="white")

    handles = [
        plt.Line2D([], [], marker="s", linestyle="none", markersize=10, color=FMT_COLORS[i], label=FMT_LABEL[f])
        for i, f in enumerate(FORMATS)
    ]
    ax.legend(handles=handles, frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1.0))
    _save(fig, "fig_P9_min_latency_winner_by_bandwidth")


def fig_p10_bandwidth_crossover(rows: List[Dict[str, Any]]) -> None:
    """
    Show one representative crossover curve: estimated min_latency score vs bandwidth.
    """
    # Use the largest/highest-column slice where crossover is most visible.
    rows_sorted = sorted(rows, key=lambda r: (int(r["n_rows"]), int(r["n_cols"])))
    r = rows_sorted[-1]
    hints = _build_hints(r)
    bws = np.array([1, 2, 5, 10, 20, 50, 100, 500, 1000, 5000, 10000, 50000, 100000], dtype=float)

    # Pull calibration directly.
    cal = json.loads(CAL.read_text(encoding="utf-8")).get("decode_ns_per_byte", {})
    d_json = float(cal.get("json", 4.8))
    d_pq = float(cal.get("parquet_blob", 2.16))
    d_ipc = float(cal.get("arrow_ipc_blob", 0.0044))

    def est(bytes_: int, ns_per_byte: float, mbps: float) -> float:
        return (bytes_ * 8.0) / (mbps * 1_000_000.0) + (bytes_ * ns_per_byte) / 1e9

    y_json = [est(int(hints["json_bytes"]), d_json, b) for b in bws]
    y_pq = [est(int(hints["parquet_bytes"]), d_pq, b) for b in bws]
    y_ipc = [est(int(hints["arrow_ipc_bytes"]), d_ipc, b) for b in bws]

    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    ax.plot(bws, y_json, marker="o", linewidth=1.8, label="JSON", color=FMT_COLORS[0])
    ax.plot(bws, y_pq, marker="o", linewidth=1.8, label="Parquet blob", color=FMT_COLORS[1])
    ax.plot(bws, y_ipc, marker="o", linewidth=1.8, label="Arrow IPC blob", color=FMT_COLORS[2])
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Bandwidth (Mbps, log)")
    ax.set_ylabel("Estimated end-to-end latency score (s, log)")
    ax.set_title(f"Bandwidth crossover on {int(r['n_rows']):,}x{int(r['n_cols'])} slice")
    ax.grid(True, which="both", linewidth=0.35, alpha=0.4)
    ax.legend(frameon=False, loc="best")
    _save(fig, "fig_P10_bandwidth_crossover_json_parquet_arrow")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        if obj.get("type"):
            continue
        out.append(obj)
    return out


def fig_p11_structured_unstructured_tradeoff() -> None:
    """
    Scatter plot across networks: client latency vs payload bytes for structured vs unstructured.
    Shows why one static choice cannot optimize both objectives.
    """
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    for prof, path in STRUCTURED_FILES.items():
        rows = _read_jsonl(path)
        for payload_class, marker, color in [
            ("structured", "o", "#F58518"),
            ("unstructured", "s", "#4C78A8"),
        ]:
            xs = []
            ys = []
            for r in rows:
                if r.get("payload_class") != payload_class:
                    continue
                if r.get("client_bytes") is None or r.get("client_describe_s") is None or r.get("client_fetch_s") is None:
                    continue
                xs.append(float(r["client_bytes"]))
                ys.append(float(r["client_describe_s"]) + float(r["client_fetch_s"]))
            if xs:
                ax.scatter(xs, ys, marker=marker, s=46, alpha=0.75, label=f"{prof} {payload_class}", color=color)

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Client payload bytes (log)")
    ax.set_ylabel("Client describe+fetch latency (s, log)")
    ax.set_title("Structured vs unstructured tradeoff across network profiles")
    ax.grid(True, which="both", linewidth=0.35, alpha=0.4)

    # De-duplicate legend labels
    handles, labels = ax.get_legend_handles_labels()
    seen = set()
    h2, l2 = [], []
    for h, l in zip(handles, labels):
        if l in seen:
            continue
        seen.add(l)
        h2.append(h)
        l2.append(l)
    ax.legend(h2, l2, frameon=False, fontsize=8, loc="best")
    _save(fig, "fig_P11_structured_unstructured_tradeoff")


def fig_p12_payload_vs_latency_by_bandwidth(rows: List[Dict[str, Any]]) -> None:
    """
    Combined payload+latency tradeoff: x=payload bytes, y=estimated latency score.
    Facet by bandwidth regime to show how winner changes.
    """
    cal = json.loads(CAL.read_text(encoding="utf-8")).get("decode_ns_per_byte", {})
    d_json = float(cal.get("json", 4.8))
    d_pq = float(cal.get("parquet_blob", 2.16))
    d_ipc = float(cal.get("arrow_ipc_blob", 0.0044))

    def est(bytes_: int, ns_per_byte: float, mbps: float) -> float:
        return (bytes_ * 8.0) / (mbps * 1_000_000.0) + (bytes_ * ns_per_byte) / 1e9

    bandwidths = [5, 50, 1000, 100000]
    fig, axes = plt.subplots(2, 2, figsize=(10.2, 7.2), sharex=True, sharey=True)
    axes = axes.flatten()

    for ax, mbps in zip(axes, bandwidths):
        x_json = [int(r["json_bytes"]) for r in rows]
        x_pq = [int(r["parquet_bytes"]) for r in rows]
        x_ipc = [int(r["arrow_ipc_bytes"]) for r in rows]
        y_json = [est(b, d_json, mbps) for b in x_json]
        y_pq = [est(b, d_pq, mbps) for b in x_pq]
        y_ipc = [est(b, d_ipc, mbps) for b in x_ipc]

        ax.scatter(x_json, y_json, s=44, alpha=0.8, color=FMT_COLORS[0], label="JSON")
        ax.scatter(x_pq, y_pq, s=44, alpha=0.8, color=FMT_COLORS[1], label="Parquet blob")
        ax.scatter(x_ipc, y_ipc, s=44, alpha=0.8, color=FMT_COLORS[2], label="Arrow IPC blob")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_title(f"{mbps} Mbps")
        ax.grid(True, which="both", linewidth=0.3, alpha=0.4)

    axes[0].set_ylabel("Estimated end-to-end latency score (s, log)")
    axes[2].set_ylabel("Estimated end-to-end latency score (s, log)")
    axes[2].set_xlabel("Payload bytes (log)")
    axes[3].set_xlabel("Payload bytes (log)")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, 1.01))
    fig.suptitle("Payload vs latency tradeoff by bandwidth regime", y=0.995)
    _save(fig, "fig_P12_payload_vs_latency_by_bandwidth")


def fig_p13_simple_payload_latency_tradeoff(rows: List[Dict[str, Any]]) -> None:
    """
    Simpler, poster-friendly figure:
      - Top: payload bytes by format (single representative slice).
      - Bottom: estimated latency vs bandwidth for same slice.
    """
    # Choose largest slice to make transfer-vs-decode tradeoff visible.
    rows_sorted = sorted(rows, key=lambda r: (int(r["n_rows"]), int(r["n_cols"])))
    r = rows_sorted[-1]
    n_rows = int(r["n_rows"])
    n_cols = int(r["n_cols"])

    b_json = int(r["json_bytes"])
    b_pq = int(r["parquet_bytes"])
    b_ipc = int(r["arrow_ipc_bytes"])

    cal = json.loads(CAL.read_text(encoding="utf-8")).get("decode_ns_per_byte", {})
    d_json = float(cal.get("json", 4.8))
    d_pq = float(cal.get("parquet_blob", 2.16))
    d_ipc = float(cal.get("arrow_ipc_blob", 0.0044))

    def est(bytes_: int, ns_per_byte: float, mbps: float) -> float:
        return (bytes_ * 8.0) / (mbps * 1_000_000.0) + (bytes_ * ns_per_byte) / 1e9

    bandwidths = np.array([5, 10, 50, 100, 1000, 10000, 100000], dtype=float)
    y_json = [est(b_json, d_json, b) for b in bandwidths]
    y_pq = [est(b_pq, d_pq, b) for b in bandwidths]
    y_ipc = [est(b_ipc, d_ipc, b) for b in bandwidths]

    fig, axes = plt.subplots(2, 1, figsize=(8.0, 6.6), gridspec_kw={"height_ratios": [1, 1.35]})
    ax0, ax1 = axes

    formats = ["JSON", "Parquet blob", "Arrow IPC blob"]
    bytes_vals = [b_json, b_pq, b_ipc]
    ax0.bar(formats, bytes_vals, color=FMT_COLORS)
    ax0.set_yscale("log")
    ax0.set_ylabel("Payload bytes (log)")
    ax0.set_title(f"Representative slice: {n_rows:,} rows x {n_cols} cols")
    ax0.grid(True, axis="y", which="both", linewidth=0.3, alpha=0.4)

    ax1.plot(bandwidths, y_json, marker="o", linewidth=2.0, color=FMT_COLORS[0], label="JSON")
    ax1.plot(bandwidths, y_pq, marker="o", linewidth=2.0, color=FMT_COLORS[1], label="Parquet blob")
    ax1.plot(bandwidths, y_ipc, marker="o", linewidth=2.0, color=FMT_COLORS[2], label="Arrow IPC blob")
    ax1.set_xscale("log")
    ax1.set_yscale("log")
    ax1.set_xlabel("Bandwidth (Mbps, log)")
    ax1.set_ylabel("Estimated end-to-end latency (s, log)")
    ax1.grid(True, which="both", linewidth=0.3, alpha=0.4)
    ax1.legend(frameon=False, loc="best")

    fig.suptitle("Payload vs latency: no single format wins all regimes", y=0.995)
    _save(fig, "fig_P13_simple_payload_latency_tradeoff")


def fig_p14_streaming_ttfr_parquet_vs_arrow(rows: List[Dict[str, Any]]) -> None:
    """
    Streaming-focused comparison:
      estimate time-to-first-rows proxy from first-chunk bytes + decode proxy.
    """
    # Use the largest slice to make streaming contrast visible.
    rows_sorted = sorted(rows, key=lambda r: (int(r["n_rows"]), int(r["n_cols"])))
    r = rows_sorted[-1]
    n_rows = int(r["n_rows"])
    n_cols = int(r["n_cols"])
    pq_fc = int(r["parquet_stream_first_chunk_bytes"])
    ipc_fc = int(r["arrow_ipc_stream_first_chunk_bytes"])

    cal = json.loads(CAL.read_text(encoding="utf-8")).get("decode_ns_per_byte", {})
    # For stream first-row proxy, reuse per-byte decode estimates from blob variants.
    d_pq = float(cal.get("parquet_blob", 2.16))
    d_ipc = float(cal.get("arrow_ipc_blob", 0.0044))

    def est_ttfr(bytes_: int, ns_per_byte: float, mbps: float) -> float:
        transfer = (bytes_ * 8.0) / (mbps * 1_000_000.0)
        decode = (bytes_ * ns_per_byte) / 1e9
        return transfer + decode

    bws = np.array([5, 10, 50, 100, 1000, 10000, 100000], dtype=float)
    y_pq = [est_ttfr(pq_fc, d_pq, b) for b in bws]
    y_ipc = [est_ttfr(ipc_fc, d_ipc, b) for b in bws]

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.8), gridspec_kw={"width_ratios": [1, 1.35]})
    ax0, ax1 = axes

    ax0.bar(["Parquet stream", "Arrow IPC stream"], [pq_fc, ipc_fc], color=["#F58518", "#54A24B"])
    ax0.set_yscale("log")
    ax0.set_ylabel("First-chunk bytes (log)")
    ax0.set_title(f"Streaming first-chunk size\n{n_rows:,} rows x {n_cols} cols")
    ax0.grid(True, axis="y", which="both", linewidth=0.3, alpha=0.4)

    ax1.plot(bws, y_pq, marker="o", linewidth=2.0, color="#F58518", label="Parquet stream")
    ax1.plot(bws, y_ipc, marker="o", linewidth=2.0, color="#54A24B", label="Arrow IPC stream")
    ax1.set_xscale("log")
    ax1.set_yscale("log")
    ax1.set_xlabel("Bandwidth (Mbps, log)")
    ax1.set_ylabel("Estimated TTFR proxy (s, log)")
    ax1.set_title("Streaming TTFR comparison")
    ax1.grid(True, which="both", linewidth=0.3, alpha=0.4)
    ax1.legend(frameon=False, loc="best")

    fig.suptitle("Streaming choice matters: Parquet vs Arrow IPC", y=1.02)
    _save(fig, "fig_P14_streaming_ttfr_parquet_vs_arrow")


def fig_p15_structured_unstructured_simple() -> None:
    """
    Simple, easy-to-read structured vs unstructured comparison:
      top: median client latency by network
      bottom: median client payload bytes by network
    """
    profiles = ["LAN", "WAN", "Cellular", "BadWifi"]
    med_latency_struct = []
    med_latency_unstruct = []
    med_bytes_struct = []
    med_bytes_unstruct = []

    for p in profiles:
        rows = _read_jsonl(STRUCTURED_FILES[p])
        s_lat = []
        u_lat = []
        s_b = []
        u_b = []
        for r in rows:
            if r.get("client_describe_s") is None or r.get("client_fetch_s") is None or r.get("client_bytes") is None:
                continue
            lat = float(r["client_describe_s"]) + float(r["client_fetch_s"])
            b = float(r["client_bytes"])
            if r.get("payload_class") == "structured":
                s_lat.append(lat)
                s_b.append(b)
            elif r.get("payload_class") == "unstructured":
                u_lat.append(lat)
                u_b.append(b)

        med_latency_struct.append(float(np.median(s_lat)) if s_lat else np.nan)
        med_latency_unstruct.append(float(np.median(u_lat)) if u_lat else np.nan)
        med_bytes_struct.append(float(np.median(s_b)) if s_b else np.nan)
        med_bytes_unstruct.append(float(np.median(u_b)) if u_b else np.nan)

    x = np.arange(len(profiles), dtype=float)
    w = 0.36
    fig, axes = plt.subplots(2, 1, figsize=(8.0, 6.2), sharex=True)
    ax0, ax1 = axes

    ax0.bar(x - w / 2, med_latency_struct, width=w, label="Structured", color="#F58518")
    ax0.bar(x + w / 2, med_latency_unstruct, width=w, label="Unstructured", color="#4C78A8")
    ax0.set_yscale("log")
    ax0.set_ylabel("Median client latency (s, log)")
    ax0.set_title("Structured vs unstructured: client latency by network")
    ax0.grid(True, axis="y", which="both", linewidth=0.3, alpha=0.4)
    ax0.legend(frameon=False, loc="best")

    ax1.bar(x - w / 2, med_bytes_struct, width=w, label="Structured", color="#F58518")
    ax1.bar(x + w / 2, med_bytes_unstruct, width=w, label="Unstructured", color="#4C78A8")
    ax1.set_yscale("log")
    ax1.set_xticks(x, profiles)
    ax1.set_ylabel("Median payload bytes (log)")
    ax1.set_xlabel("Network profile")
    ax1.set_title("Structured vs unstructured: payload by network")
    ax1.grid(True, axis="y", which="both", linewidth=0.3, alpha=0.4)

    fig.suptitle("Structured vs unstructured tradeoff", y=0.995)
    _save(fig, "fig_P15_structured_unstructured_simple")


def fig_p16_story_json_and_output_tradeoff(rows: List[Dict[str, Any]]) -> None:
    """
    One compact story figure:
      Left: JSON weakness (Pareto cloud at WAN bandwidth).
      Right: structured vs unstructured tradeoff (bytes-latency arrows per network).
    """
    cal = json.loads(CAL.read_text(encoding="utf-8")).get("decode_ns_per_byte", {})
    d_json = float(cal.get("json", 4.8))
    d_pq = float(cal.get("parquet_blob", 2.16))
    d_ipc = float(cal.get("arrow_ipc_blob", 0.0044))

    def est(bytes_: int, ns_per_byte: float, mbps: float) -> float:
        return (bytes_ * 8.0) / (mbps * 1_000_000.0) + (bytes_ * ns_per_byte) / 1e9

    fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.4))
    ax0, ax1 = axes

    # --- Left panel: JSON weakness (dominated in bytes-latency space) ---
    bw = 50.0  # WAN-like regime
    x_json = [int(r["json_bytes"]) for r in rows]
    y_json = [est(int(r["json_bytes"]), d_json, bw) for r in rows]
    x_pq = [int(r["parquet_bytes"]) for r in rows]
    y_pq = [est(int(r["parquet_bytes"]), d_pq, bw) for r in rows]
    x_ipc = [int(r["arrow_ipc_bytes"]) for r in rows]
    y_ipc = [est(int(r["arrow_ipc_bytes"]), d_ipc, bw) for r in rows]

    ax0.scatter(x_json, y_json, s=52, alpha=0.85, color="#4C78A8", label="JSON")
    ax0.scatter(x_pq, y_pq, s=52, alpha=0.85, color="#F58518", label="Parquet blob")
    ax0.scatter(x_ipc, y_ipc, s=52, alpha=0.85, color="#54A24B", label="Arrow IPC blob")
    ax0.set_xscale("log")
    ax0.set_yscale("log")
    ax0.set_xlabel("Payload bytes (log)")
    ax0.set_ylabel("Estimated latency score (s, log)")
    ax0.set_title("JSON weakness (WAN-like regime)")
    ax0.grid(True, which="both", linewidth=0.3, alpha=0.4)
    ax0.legend(frameon=False, fontsize=8, loc="best")

    # --- Right panel: structured vs unstructured tradeoff with arrows ---
    network_colors = {
        "LAN": "#4C78A8",
        "WAN": "#F58518",
        "Cellular": "#54A24B",
        "BadWifi": "#B279A2",
    }
    target = "min_latency"
    size = 1_048_576  # 1 MiB nominal, readable mid-size comparison

    for prof in ["LAN", "WAN", "Cellular", "BadWifi"]:
        rws = _read_jsonl(STRUCTURED_FILES[prof])
        s_points = []
        u_points = []
        for r in rws:
            if str(r.get("target_name")) != target:
                continue
            if int(r.get("nominal_target_bytes") or 0) != size:
                continue
            if r.get("client_describe_s") is None or r.get("client_fetch_s") is None or r.get("client_bytes") is None:
                continue
            lat = float(r["client_describe_s"]) + float(r["client_fetch_s"])
            b = float(r["client_bytes"])
            if r.get("payload_class") == "structured":
                s_points.append((b, lat))
            elif r.get("payload_class") == "unstructured":
                u_points.append((b, lat))
        if not s_points or not u_points:
            continue
        sx, sy = float(np.median([p[0] for p in s_points])), float(np.median([p[1] for p in s_points]))
        ux, uy = float(np.median([p[0] for p in u_points])), float(np.median([p[1] for p in u_points]))
        c = network_colors[prof]

        ax1.scatter([ux], [uy], marker="s", s=58, color=c)
        ax1.scatter([sx], [sy], marker="o", s=58, color=c)
        ax1.annotate("", xy=(sx, sy), xytext=(ux, uy), arrowprops={"arrowstyle": "->", "lw": 1.6, "color": c})
        ax1.text(ux, uy, f" {prof} U", fontsize=8, va="bottom")
        ax1.text(sx, sy, f" {prof} S", fontsize=8, va="bottom")

    ax1.set_xscale("log")
    ax1.set_yscale("log")
    ax1.set_xlabel("Client payload bytes (log)")
    ax1.set_ylabel("Client latency (s, log)")
    ax1.set_title("Structured vs unstructured tradeoff")
    ax1.grid(True, which="both", linewidth=0.3, alpha=0.4)

    fig.suptitle("Why dynamic selection: bytes-latency tradeoffs across regimes", y=1.02)
    _save(fig, "fig_P16_story_json_weakness_and_output_tradeoff")


def fig_p17_clean_story_tradeoffs(rows: List[Dict[str, Any]]) -> None:
    """
    Cleaner poster figure with explicit messages:
      A) Payload bars (one representative slice)
      B) Latency vs bandwidth with winner crossover
      C) Structured vs unstructured latency dumbbell by network
    """
    rows_sorted = sorted(rows, key=lambda r: (int(r["n_rows"]), int(r["n_cols"])))
    r = rows_sorted[-1]  # largest slice for strong separation
    n_rows = int(r["n_rows"])
    n_cols = int(r["n_cols"])
    b_json = int(r["json_bytes"])
    b_pq = int(r["parquet_bytes"])
    b_ipc = int(r["arrow_ipc_bytes"])

    cal = json.loads(CAL.read_text(encoding="utf-8")).get("decode_ns_per_byte", {})
    d_json = float(cal.get("json", 4.8))
    d_pq = float(cal.get("parquet_blob", 2.16))
    d_ipc = float(cal.get("arrow_ipc_blob", 0.0044))

    def est(bytes_: int, ns_per_byte: float, mbps: float) -> float:
        return (bytes_ * 8.0) / (mbps * 1_000_000.0) + (bytes_ * ns_per_byte) / 1e9

    fig = plt.figure(figsize=(12.0, 4.6))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.0, 1.2, 1.1], wspace=0.42)
    ax0 = fig.add_subplot(gs[0, 0])
    ax1 = fig.add_subplot(gs[0, 1])
    ax2 = fig.add_subplot(gs[0, 2])

    # A) Payload bars
    labels = ["JSON", "Parquet", "Arrow IPC"]
    vals = [b_json, b_pq, b_ipc]
    cols = ["#4C78A8", "#F58518", "#54A24B"]
    bars = ax0.bar(labels, vals, color=cols)
    ax0.set_yscale("log")
    ax0.set_ylabel("Payload bytes (log)")
    ax0.set_title("A) Payload size")
    ax0.grid(True, axis="y", which="both", linewidth=0.3, alpha=0.4)
    for b, v in zip(bars, vals):
        ax0.text(b.get_x() + b.get_width() / 2, v * 1.08, f"{v/1e6:.1f}M", ha="center", va="bottom", fontsize=8)

    # B) Latency vs bandwidth with crossover
    bws = np.array([5, 10, 20, 50, 100, 500, 1000, 5000, 10000, 50000, 100000], dtype=float)
    y_json = np.array([est(b_json, d_json, b) for b in bws])
    y_pq = np.array([est(b_pq, d_pq, b) for b in bws])
    y_ipc = np.array([est(b_ipc, d_ipc, b) for b in bws])
    ax1.plot(bws, y_json, color=cols[0], linewidth=2.2, label="JSON")
    ax1.plot(bws, y_pq, color=cols[1], linewidth=2.2, label="Parquet")
    ax1.plot(bws, y_ipc, color=cols[2], linewidth=2.2, label="Arrow IPC")
    ax1.set_xscale("log")
    ax1.set_yscale("log")
    ax1.set_xlabel("Bandwidth (Mbps, log)")
    ax1.set_ylabel("Estimated latency (s, log)")
    ax1.set_title("B) Latency crossover")
    ax1.grid(True, which="both", linewidth=0.3, alpha=0.4)
    ax1.legend(frameon=False, fontsize=8, loc="best")
    # winner callouts
    ax1.text(7, y_pq[0] * 1.2, "Parquet wins\n(low bandwidth)", fontsize=8)
    ax1.text(20000, y_ipc[-1] * 1.8, "Arrow wins\n(high bandwidth)", fontsize=8, ha="center")

    # C) Structured vs unstructured dumbbell (latency only, min_latency target, 1MiB)
    profiles = ["LAN", "WAN", "Cellular", "BadWifi"]
    size = 1_048_576
    target = "min_latency"
    y_idx = np.arange(len(profiles))
    u_vals = []
    s_vals = []
    for p in profiles:
        rows_u = _read_jsonl(STRUCTURED_FILES[p])
        s_lat = []
        u_lat = []
        for rr in rows_u:
            if str(rr.get("target_name")) != target or int(rr.get("nominal_target_bytes") or 0) != size:
                continue
            if rr.get("client_describe_s") is None or rr.get("client_fetch_s") is None:
                continue
            lat = float(rr["client_describe_s"]) + float(rr["client_fetch_s"])
            if rr.get("payload_class") == "structured":
                s_lat.append(lat)
            elif rr.get("payload_class") == "unstructured":
                u_lat.append(lat)
        s_vals.append(float(np.median(s_lat)) if s_lat else np.nan)
        u_vals.append(float(np.median(u_lat)) if u_lat else np.nan)

    for i in range(len(profiles)):
        ax2.plot([u_vals[i], s_vals[i]], [y_idx[i], y_idx[i]], color="#777777", linewidth=1.8)
    ax2.scatter(u_vals, y_idx, marker="s", color="#4C78A8", s=50, label="Unstructured")
    ax2.scatter(s_vals, y_idx, marker="o", color="#F58518", s=50, label="Structured")
    ax2.set_xscale("log")
    ax2.set_yticks(y_idx, profiles)
    ax2.set_xlabel("Client latency (s, log)")
    ax2.set_title("C) Structured vs unstructured")
    ax2.grid(True, axis="x", which="both", linewidth=0.3, alpha=0.4)
    ax2.legend(frameon=False, fontsize=8, loc="best")

    fig.suptitle(f"Tradeoff story ({n_rows:,}x{n_cols} slice + 1MiB network comparison)", y=1.02)
    _save(fig, "fig_P17_clean_story_tradeoffs")


def main() -> None:
    if not TPCDS.exists():
        raise FileNotFoundError(f"Missing input: {TPCDS}")
    rows = _load_tpcds()
    # Deterministic order
    rows = sorted(rows, key=lambda r: (int(r["n_rows"]), int(r["n_cols"])))

    fig_p9_min_latency_winner_by_bandwidth(rows)
    fig_p10_bandwidth_crossover(rows)
    fig_p11_structured_unstructured_tradeoff()
    fig_p12_payload_vs_latency_by_bandwidth(rows)
    fig_p13_simple_payload_latency_tradeoff(rows)
    fig_p14_streaming_ttfr_parquet_vs_arrow(rows)
    fig_p15_structured_unstructured_simple()
    fig_p16_story_json_and_output_tradeoff(rows)
    fig_p17_clean_story_tradeoffs(rows)
    print(f"Wrote dynamic-selection plots to {OUT_DIR}/")


if __name__ == "__main__":
    main()
