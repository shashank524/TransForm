"""
Generate paper-ready figures from results/bird_server_exec_e2e.jsonl.

Outputs to results/figures/:
  - fig_B1_bird_latency_paired.(png|pdf)
  - fig_B3_bird_overhead_breakdown.(png|pdf)
  - fig_S1_baseline_failure_rate.(png|pdf)
  - fig_S2_ttfr_cdf.(png|pdf)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np

OUT_DIR = Path("results/figures")
_STEM_SUFFIX = ""


def load_rows(path: Path) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    header = None
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("type") == "bird_server_exec_e2e_run_header":
            header = obj
        else:
            rows.append(obj)
    return rows, header


def save(fig: plt.Figure, stem: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    s = f"{stem}{_STEM_SUFFIX}"
    fig.savefig(OUT_DIR / f"{s}.png", dpi=200)
    fig.savefig(OUT_DIR / f"{s}.pdf")


def _total_client_s(r: Dict[str, Any]) -> Optional[float]:
    ms, ds, fs = r.get("materialize_s"), r.get("describe_s"), r.get("client_fetch_s")
    if ms is None or ds is None or fs is None:
        return None
    return float(ms) + float(ds) + float(fs)


def _total_auto_s(r: Dict[str, Any]) -> Optional[float]:
    cs, fs = r.get("server_auto_call_s"), r.get("server_auto_fetch_s")
    if cs is None:
        return None
    return float(cs) + float(fs or 0.0)


def fig_b1_latency_paired(rows: List[Dict[str, Any]]) -> None:
    # Scatter of baseline vs client/server_auto totals (log-log), with diagonal.
    baseline = []
    client = []
    auto = []
    for r in rows:
        b = r.get("baseline_s")
        c = _total_client_s(r)
        a = _total_auto_s(r)
        if b is None:
            continue
        baseline.append(float(b))
        client.append(float(c) if c is not None else np.nan)
        auto.append(float(a) if a is not None else np.nan)

    x = np.array(baseline)
    fig, ax = plt.subplots(figsize=(4.8, 4.2))
    ax.scatter(x, np.array(client), s=40, label="client (materialize+describe+fetch)", alpha=0.85)
    ax.scatter(x, np.array(auto), s=40, label="server_auto (call+fetch)", alpha=0.85)
    lo = np.nanmin(x)
    hi = np.nanmax(x)
    ax.plot([lo, hi], [lo, hi], linewidth=1.2, linestyle="--", color="gray")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("baseline latency (s, log)")
    ax.set_ylabel("variant latency (s, log)")
    ax.set_title("BIRD E2E latency vs baseline (paired per query)")
    ax.grid(True, which="both", linewidth=0.3, alpha=0.35)
    ax.legend(frameon=False, loc="best")
    save(fig, "fig_B1_bird_latency_paired")


def fig_b3_overhead_breakdown(rows: List[Dict[str, Any]]) -> None:
    # Stacked bars for median overhead components.
    ms = [r.get("materialize_s") for r in rows if r.get("materialize_s") is not None]
    ds = [r.get("describe_s") for r in rows if r.get("describe_s") is not None]
    cf = [r.get("client_fetch_s") for r in rows if r.get("client_fetch_s") is not None]
    ac = [r.get("server_auto_call_s") for r in rows if r.get("server_auto_call_s") is not None]
    af = [r.get("server_auto_fetch_s") for r in rows if r.get("server_auto_fetch_s") is not None]
    b = [r.get("baseline_s") for r in rows if r.get("baseline_s") is not None]

    def med(xs: List[Any]) -> float:
        return float(np.median([float(x) for x in xs])) if xs else 0.0

    med_ms, med_ds, med_cf = med(ms), med(ds), med(cf)
    med_ac, med_af = med(ac), med(af)
    med_b = med(b)

    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    labels = ["baseline", "client_select", "server_auto"]
    x = np.arange(len(labels))
    width = 0.55

    ax.bar([x[0]], [med_b], width=width, label="baseline_total", color="#4C78A8")

    ax.bar([x[1]], [med_ms], width=width, label="materialize", color="#F58518")
    ax.bar([x[1]], [med_ds], width=width, bottom=[med_ms], label="describe", color="#E45756")
    ax.bar([x[1]], [med_cf], width=width, bottom=[med_ms + med_ds], label="fetch", color="#72B7B2")

    ax.bar([x[2]], [med_ac], width=width, label="auto_call", color="#54A24B")
    ax.bar([x[2]], [med_af], width=width, bottom=[med_ac], label="auto_fetch", color="#B279A2")

    ax.set_xticks(x, labels)
    ax.set_ylabel("median seconds")
    ax.set_title("Median overhead breakdown (BIRD server-exec)")
    ax.grid(True, axis="y", linewidth=0.3, alpha=0.35)
    ax.legend(frameon=False, ncol=3, fontsize=8, loc="upper right")
    save(fig, "fig_B3_bird_overhead_breakdown")


def fig_s1_baseline_failure_rate(rows: List[Dict[str, Any]]) -> None:
    # Failure rate by cells bucket (cells = n_rows*n_cols from materialize arm)
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

    buckets = ["0", "1-1e4", "1e4-1e5", "1e5-1e6", "1e6+"]
    total = {b: 0 for b in buckets}
    failed = {b: 0 for b in buckets}

    for r in rows:
        nr = int(r.get("n_rows") or 0)
        nc = int(r.get("n_cols") or 0)
        b = bucket_cells(nr * nc)
        total[b] += 1
        if r.get("baseline_error"):
            failed[b] += 1

    xs = np.arange(len(buckets))
    rates = [
        (failed[b] / total[b]) if total[b] > 0 else np.nan
        for b in buckets
    ]
    fig, ax = plt.subplots(figsize=(6.2, 3.6))
    ax.bar(xs, rates, color="#E45756")
    ax.set_xticks(xs, buckets)
    ax.set_ylim(0, 1)
    ax.set_ylabel("failure rate")
    ax.set_title("Baseline (inline JSON) infeasibility vs result size")
    ax.grid(True, axis="y", linewidth=0.3, alpha=0.35)
    save(fig, "fig_S1_baseline_failure_rate")


def fig_s2_ttfr_cdf(rows: List[Dict[str, Any]]) -> None:
    # TTFR CDF for client vs server_auto streaming (only where ttfr exists)
    client = np.array([float(r["client_ttfr_s"]) for r in rows if r.get("client_ttfr_s") is not None], dtype=float)
    auto = np.array([float(r["server_auto_ttfr_s"]) for r in rows if r.get("server_auto_ttfr_s") is not None], dtype=float)

    fig, ax = plt.subplots(figsize=(5.2, 3.8))
    for vals, label, color in [
        (client, "client_select (streaming)", "#4C78A8"),
        (auto, "server_auto (streaming)", "#54A24B"),
    ]:
        if vals.size == 0:
            continue
        xs = np.sort(vals)
        ys = np.arange(1, xs.size + 1) / xs.size
        ax.plot(xs, ys, linewidth=2.0, label=label, color=color)
    ax.set_xscale("log")
    ax.set_xlabel("TTFR seconds (log)")
    ax.set_ylabel("CDF")
    ax.set_title("TTFR distribution (streaming only)")
    ax.grid(True, which="both", linewidth=0.3, alpha=0.35)
    ax.legend(frameon=False, loc="best")
    save(fig, "fig_S2_ttfr_cdf")


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Plot bird_server_exec_e2e results")
    ap.add_argument(
        "--inputs",
        default="results/bird_server_exec_e2e.jsonl",
        help="Comma-separated JSONL paths. Produces figures per input (network-profile faceting via filenames).",
    )
    args = ap.parse_args()

    inputs = [Path(x.strip()) for x in args.inputs.split(",") if x.strip()]
    for p in inputs:
        if not p.exists():
            raise FileNotFoundError(f"Missing input: {p}")
        rows, header = load_rows(p)
        if not rows:
            raise RuntimeError(f"No rows in {p}")
        # Suffix figures by input stem so multiple runs don't overwrite outputs.
        global _STEM_SUFFIX
        _STEM_SUFFIX = f"_{p.stem}"
        fig_b1_latency_paired(rows)
        fig_b3_overhead_breakdown(rows)
        fig_s1_baseline_failure_rate(rows)
        fig_s2_ttfr_cdf(rows)
    print(f"Wrote figures to {OUT_DIR}/")


if __name__ == "__main__":
    main()

