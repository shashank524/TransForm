"""
Generate six poster-ready figures for the network-shaped benchmark story.

Outputs to results/figures/poster/:
  - fig_P1_tpcds_payload_scaling.(png|pdf)
  - fig_P2_tpcds_transfer_time_proxy_scaling.(png|pdf)
  - fig_P3_network_latency_by_arm.(png|pdf)
  - fig_P4_network_payload_by_arm.(png|pdf)
  - fig_P5_server_auto_format_mix_by_network.(png|pdf)
  - fig_P6_structured_vs_unstructured_latency.(png|pdf)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt
import numpy as np

RESULTS_DIR = Path("results")
OUT_DIR = RESULTS_DIR / "figures" / "poster"

TPCDS_HINTS = RESULTS_DIR / "tpcds_format_hints.json"
BIRD_NETWORK_FILES = {
    "LAN": RESULTS_DIR / "bird_server_exec_e2e_network_lan_capped_ttfr_rpc8192.jsonl",
    "WAN": RESULTS_DIR / "bird_server_exec_e2e_network_wan_capped_ttfr_rpc8192.jsonl",
    "Cellular": RESULTS_DIR / "bird_server_exec_e2e_network_cellular_capped_ttfr_rpc8192.jsonl",
    "BadWifi": RESULTS_DIR / "bird_server_exec_e2e_network_badwifi_capped_ttfr_rpc8192.jsonl",
}
STRUCTURED_FILES = {
    "LAN": RESULTS_DIR / "structured_vs_unstructured_network_lan.jsonl",
    "WAN": RESULTS_DIR / "structured_vs_unstructured_network_wan.jsonl",
    "Cellular": RESULTS_DIR / "structured_vs_unstructured_network_cellular.jsonl",
    "BadWifi": RESULTS_DIR / "structured_vs_unstructured_network_badwifi.jsonl",
}
RATE_MBIT = {
    "LAN": 1000.0,
    "WAN": 50.0,
    "Cellular": 10.0,
    "BadWifi": 5.0,
}


def _save(fig: plt.Figure, stem: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"{stem}.png", dpi=240)
    fig.savefig(OUT_DIR / f"{stem}.pdf")
    plt.close(fig)


def _median(vals: List[float]) -> float:
    if not vals:
        return float("nan")
    return float(np.median(np.array(vals, dtype=float)))


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        obj = json.loads(line)
        if obj.get("type"):
            continue
        out.append(obj)
    return out


def _load_tpcds_rows() -> List[Dict[str, Any]]:
    rows = json.loads(TPCDS_HINTS.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise RuntimeError("Unexpected tpcds_format_hints.json structure")
    return rows


def fig_p1_tpcds_payload_scaling(rows: List[Dict[str, Any]]) -> None:
    col_values = sorted({int(r["n_cols"]) for r in rows})
    fig, axes = plt.subplots(1, len(col_values), figsize=(4.8 * len(col_values), 3.6), sharey=True)
    if len(col_values) == 1:
        axes = [axes]

    for ax, n_cols in zip(axes, col_values):
        rs = sorted([r for r in rows if int(r["n_cols"]) == n_cols], key=lambda x: int(x["n_rows"]))
        x = np.array([int(r["n_rows"]) for r in rs], dtype=float)
        ax.plot(x, [int(r["json_bytes"]) for r in rs], marker="o", linewidth=1.8, label="JSON")
        ax.plot(x, [int(r["parquet_bytes"]) for r in rs], marker="o", linewidth=1.8, label="Parquet blob")
        ax.plot(x, [int(r["arrow_ipc_bytes"]) for r in rs], marker="o", linewidth=1.8, label="Arrow IPC blob")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_title(f"{n_cols} columns")
        ax.set_xlabel("Rows (log)")
        ax.grid(True, which="both", linewidth=0.35, alpha=0.4)

    axes[0].set_ylabel("Payload bytes (log)")
    axes[-1].legend(frameon=False, loc="best")
    fig.suptitle("TPC-DS payload size scaling by format", y=1.03)
    _save(fig, "fig_P1_tpcds_payload_scaling")


def fig_p2_tpcds_transfer_proxy_scaling(rows: List[Dict[str, Any]]) -> None:
    """
    Transfer-time proxy based on payload bytes and shaped-link rates:
      transfer_s ~= bytes * 8 / (rate_mbit * 1e6)
    This isolates network transfer effects from server compute.
    """
    ncols = [6, 20, 34]
    fig, axes = plt.subplots(1, len(ncols), figsize=(4.8 * len(ncols), 3.6), sharey=True)
    if len(ncols) == 1:
        axes = [axes]

    format_keys = [
        ("json_bytes", "JSON", "#4C78A8"),
        ("parquet_bytes", "Parquet blob", "#F58518"),
        ("arrow_ipc_bytes", "Arrow IPC blob", "#54A24B"),
    ]
    rate = RATE_MBIT["WAN"]

    for ax, n_cols in zip(axes, ncols):
        rs = sorted([r for r in rows if int(r["n_cols"]) == n_cols], key=lambda x: int(x["n_rows"]))
        x = np.array([int(r["n_rows"]) for r in rs], dtype=float)
        for key, label, color in format_keys:
            y = np.array([(int(r[key]) * 8.0) / (rate * 1e6) for r in rs], dtype=float)
            ax.plot(x, y, marker="o", linewidth=1.9, color=color, label=label)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_title(f"{n_cols} columns")
        ax.set_xlabel("Rows (log)")
        ax.grid(True, which="both", linewidth=0.35, alpha=0.4)

    axes[0].set_ylabel("Estimated transfer time on WAN (s, log)")
    axes[-1].legend(frameon=False, loc="best")
    fig.suptitle("TPC-DS transfer-time proxy from payload size", y=1.03)
    _save(fig, "fig_P2_tpcds_transfer_time_proxy_scaling")


def _bird_network_summary() -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for profile, path in BIRD_NETWORK_FILES.items():
        rows = _read_jsonl(path)
        baseline = [float(r["baseline_s"]) for r in rows if r.get("baseline_s") is not None]
        client = [
            float(r["materialize_s"]) + float(r["describe_s"]) + float(r["client_fetch_s"])
            for r in rows
            if r.get("materialize_s") is not None
            and r.get("describe_s") is not None
            and r.get("client_fetch_s") is not None
            and not r.get("client_error")
        ]
        auto = [
            float(r["server_auto_call_s"]) + float(r["server_auto_fetch_s"])
            for r in rows
            if r.get("server_auto_call_s") is not None
            and r.get("server_auto_fetch_s") is not None
            and not r.get("server_auto_error")
        ]
        out[profile] = {
            "baseline_latency_median": _median(baseline),
            "client_latency_median": _median(client),
            "auto_latency_median": _median(auto),
            "baseline_bytes_median": _median([float(r["baseline_bytes"]) for r in rows if r.get("baseline_bytes") is not None]),
            "client_bytes_median": _median(
                [float(r["client_bytes"]) for r in rows if r.get("client_bytes") is not None and not r.get("client_error")]
            ),
            "auto_bytes_median": _median(
                [float(r["server_auto_bytes"]) for r in rows if r.get("server_auto_bytes") is not None and not r.get("server_auto_error")]
            ),
            "stream_share_auto": (
                sum(1 for r in rows if r.get("server_auto_chosen_format") in {"parquet_stream", "arrow_ipc_stream"})
                / max(len(rows), 1)
            ),
        }
    return out


def fig_p3_network_latency_by_arm(net: Dict[str, Dict[str, float]]) -> None:
    profiles = ["LAN", "WAN", "Cellular", "BadWifi"]
    x = np.arange(len(profiles), dtype=float)
    w = 0.34

    fig, ax = plt.subplots(figsize=(7.0, 3.9))
    ax.bar(x - w / 2, [net[p]["baseline_latency_median"] for p in profiles], width=w, label="Baseline JSON", color="#4C78A8")
    ax.bar(x + w / 2, [net[p]["auto_latency_median"] for p in profiles], width=w, label="Adaptive pipeline", color="#F58518")
    ax.set_yscale("log")
    ax.set_xticks(x, profiles)
    ax.set_ylabel("Median end-to-end latency (s, log)")
    ax.set_title("BIRD E2E latency under network shaping")
    ax.grid(True, axis="y", which="both", linewidth=0.35, alpha=0.4)
    ax.legend(frameon=False, loc="best")
    _save(fig, "fig_P3_network_latency_by_arm")


def fig_p4_network_payload_by_arm(net: Dict[str, Dict[str, float]]) -> None:
    profiles = ["LAN", "WAN", "Cellular", "BadWifi"]
    x = np.arange(len(profiles), dtype=float)
    w = 0.34

    fig, ax = plt.subplots(figsize=(7.0, 3.9))
    ax.bar(x - w / 2, [net[p]["baseline_bytes_median"] for p in profiles], width=w, label="Baseline JSON", color="#4C78A8")
    ax.bar(x + w / 2, [net[p]["auto_bytes_median"] for p in profiles], width=w, label="Adaptive pipeline", color="#F58518")
    ax.set_xticks(x, profiles)
    ax.set_ylabel("Median payload bytes")
    ax.set_title("BIRD E2E payload size by network profile")
    ax.grid(True, axis="y", linewidth=0.35, alpha=0.4)
    ax.legend(
        frameon=True,
        facecolor="white",
        framealpha=0.9,
        edgecolor="#DDDDDD",
        fontsize=13,
        loc="upper right",
    )
    _save(fig, "fig_P4_network_payload_by_arm")


def fig_p5_format_mix_streaming_share() -> None:
    profiles = ["LAN", "WAN", "Cellular", "BadWifi"]
    categories = ["json", "parquet_blob", "parquet_stream", "arrow_ipc_blob", "arrow_ipc_stream"]
    colors = ["#4C78A8", "#F58518", "#54A24B", "#B279A2", "#FF9DA6"]

    fig, ax = plt.subplots(figsize=(7.4, 4.0))
    bottoms = np.zeros(len(profiles), dtype=float)
    total_counts = []

    per_profile_counts: Dict[str, Dict[str, int]] = {}
    for p in profiles:
        rows = _read_jsonl(BIRD_NETWORK_FILES[p])
        counts = {k: 0 for k in categories}
        for r in rows:
            k = str(r.get("server_auto_chosen_format") or "")
            if k in counts:
                counts[k] += 1
        per_profile_counts[p] = counts
        total_counts.append(max(len(rows), 1))

    for cat, color in zip(categories, colors):
        vals = np.array([per_profile_counts[p][cat] / total_counts[i] for i, p in enumerate(profiles)], dtype=float)
        ax.bar(profiles, vals, bottom=bottoms, label=cat, color=color)
        bottoms += vals

    ax.set_ylim(0.0, 1.0)
    ax.set_ylabel("Share of queries")
    ax.set_title("Server-auto chosen format mix (network runs)")
    ax.grid(True, axis="y", linewidth=0.35, alpha=0.4)
    ax.legend(frameon=False, loc="center left", bbox_to_anchor=(1.02, 0.5))
    _save(fig, "fig_P5_server_auto_format_mix_by_network")


def fig_p6_structured_vs_unstructured_latency() -> None:
    profiles = ["LAN", "WAN", "Cellular", "BadWifi"]
    size = 5_242_880
    target = "min_latency"
    vals_struct = []
    vals_unstruct = []

    for p in profiles:
        rows = _read_jsonl(STRUCTURED_FILES[p])
        s = [
            float(r["client_describe_s"]) + float(r["client_fetch_s"])
            for r in rows
            if r.get("payload_class") == "structured"
            and int(r.get("nominal_target_bytes") or 0) == size
            and str(r.get("target_name")) == target
            and r.get("client_describe_s") is not None
            and r.get("client_fetch_s") is not None
            and not r.get("client_error")
        ]
        u = [
            float(r["client_describe_s"]) + float(r["client_fetch_s"])
            for r in rows
            if r.get("payload_class") == "unstructured"
            and int(r.get("nominal_target_bytes") or 0) == size
            and str(r.get("target_name")) == target
            and r.get("client_describe_s") is not None
            and r.get("client_fetch_s") is not None
            and not r.get("client_error")
        ]
        vals_struct.append(_median(s))
        vals_unstruct.append(_median(u))

    x = np.arange(len(profiles), dtype=float)
    w = 0.32
    fig, ax = plt.subplots(figsize=(7.0, 3.9))
    ax.bar(x - w / 2, vals_struct, width=w, label="Structured (Parquet-backed)")
    ax.bar(x + w / 2, vals_unstruct, width=w, label="Unstructured (raw/text)")
    ax.set_xticks(x, profiles)
    ax.set_ylabel("Median client describe+fetch latency (s)")
    ax.set_title("Structured vs unstructured at 5 MiB (min_latency)")
    ax.grid(True, axis="y", linewidth=0.35, alpha=0.4)
    ax.legend(frameon=False, loc="best")
    _save(fig, "fig_P6_structured_vs_unstructured_latency")


def main() -> None:
    missing = [str(p) for p in [TPCDS_HINTS, *BIRD_NETWORK_FILES.values(), *STRUCTURED_FILES.values()] if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required inputs: {missing}")

    tpcds_rows = _load_tpcds_rows()
    if not tpcds_rows:
        raise RuntimeError("No rows in TPC-DS hints data")

    fig_p1_tpcds_payload_scaling(tpcds_rows)
    fig_p2_tpcds_transfer_proxy_scaling(tpcds_rows)

    net = _bird_network_summary()
    fig_p3_network_latency_by_arm(net)
    fig_p4_network_payload_by_arm(net)
    fig_p5_format_mix_streaming_share()
    fig_p6_structured_vs_unstructured_latency()
    print(f"Wrote poster figures to {OUT_DIR}/")


if __name__ == "__main__":
    main()
