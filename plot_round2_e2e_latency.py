"""Plot end-to-end median latency per arm: round-1 vs round-2 vs baseline.

Reads the existing post-fix and round-2 JSONL files and produces a
paired bar chart at results/figures/round2_e2e_latency.png. The
"baseline arm" (`register` + `large_json`) is highlighted as a
horizontal reference line so the inline-arm win against it is obvious.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Iterable, List, Optional

import matplotlib.pyplot as plt
import numpy as np


def _load(path: Path) -> List[dict]:
    rows: List[dict] = []
    if not path.is_file():
        return rows
    for ln in path.read_text().splitlines():
        try:
            o = json.loads(ln)
        except Exception:
            continue
        if o.get("type") == "bird_e2e_run_header":
            continue
        rows.append(o)
    return rows


def _med(xs: Iterable[Optional[float]]) -> Optional[float]:
    vals = [float(x) for x in xs if x is not None]
    return float(statistics.median(vals)) if vals else None


def _p95(xs: Iterable[Optional[float]]) -> Optional[float]:
    vals = sorted(float(x) for x in xs if x is not None)
    if not vals:
        return None
    i = max(0, min(len(vals) - 1, int(round(0.95 * (len(vals) - 1)))))
    return vals[i]


def _arm_total_per_query(rows: List[dict], *keys: str) -> List[float]:
    """For each row that has *all* `keys` populated, return the sum (seconds)."""
    out: List[float] = []
    for r in rows:
        if not r.get("exec_ok"):
            continue
        if not all(r.get(k) is not None for k in keys):
            continue
        out.append(sum(float(r[k]) for k in keys))
    return out


def main() -> None:
    base = Path("results")
    fig_dir = base / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    # Round-1 (post-fix): both/server arms are the relevant fair-end-to-end runs
    r1_both = _load(base / "bird_e2e_dev_full_gold_postfix.jsonl")
    r1_server = _load(base / "bird_e2e_dev_full_gold_postfix_server.jsonl")
    # Round-2: both/server/inline
    r2_both = _load(base / "bird_e2e_dev_full_gold_round2_both.jsonl")
    r2_server = _load(base / "bird_e2e_dev_full_gold_round2_server.jsonl")
    r2_inline = _load(base / "bird_e2e_dev_full_gold_round2_inline.jsonl")

    arms = ["baseline", "enhanced", "server", "inline"]

    # baseline = register_s + baseline_fetch_s (both arm contains baseline)
    r1_baseline = _arm_total_per_query(r1_both, "register_s", "baseline_fetch_s")
    r2_baseline = _arm_total_per_query(r2_both, "register_s", "baseline_fetch_s")

    # enhanced = register_s + describe_s + enhanced_fetch_s
    r1_enhanced = _arm_total_per_query(
        r1_both, "register_s", "describe_s", "enhanced_fetch_s"
    )
    r2_enhanced = _arm_total_per_query(
        r2_both, "register_s", "describe_s", "enhanced_fetch_s"
    )

    # server = register_s + server_auto_call_s + server_auto_payload_s
    r1_server_e2e = _arm_total_per_query(
        r1_server, "register_s", "server_auto_call_s", "server_auto_payload_s"
    )
    r2_server_e2e = _arm_total_per_query(
        r2_server, "register_s", "server_auto_call_s", "server_auto_payload_s"
    )

    # inline = inline_call_s + inline_payload_s (no register; round-2 only)
    r2_inline_e2e = _arm_total_per_query(r2_inline, "inline_call_s", "inline_payload_s")

    def _ms(x: Optional[float]) -> Optional[float]:
        return None if x is None else x * 1000.0

    r1_med = [_ms(_med(r1_baseline)), _ms(_med(r1_enhanced)), _ms(_med(r1_server_e2e)), None]
    r2_med = [
        _ms(_med(r2_baseline)),
        _ms(_med(r2_enhanced)),
        _ms(_med(r2_server_e2e)),
        _ms(_med(r2_inline_e2e)),
    ]
    r1_p95 = [_ms(_p95(r1_baseline)), _ms(_p95(r1_enhanced)), _ms(_p95(r1_server_e2e)), None]
    r2_p95 = [
        _ms(_p95(r2_baseline)),
        _ms(_p95(r2_enhanced)),
        _ms(_p95(r2_server_e2e)),
        _ms(_p95(r2_inline_e2e)),
    ]

    print("Median ms per arm:")
    for a, m1, m2 in zip(arms, r1_med, r2_med):
        print(f"  {a:9s}  round-1={m1!s:>8}  round-2={m2!s:>8}")

    # --- Plot -----------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(9.0, 5.0), dpi=140)
    x = np.arange(len(arms))
    w = 0.36

    r1_vals = [v if v is not None else 0.0 for v in r1_med]
    r2_vals = [v if v is not None else 0.0 for v in r2_med]
    r1_err = [
        (0, (p - m)) if (p is not None and m is not None) else (0, 0)
        for p, m in zip(r1_p95, r1_med)
    ]
    r2_err = [
        (0, (p - m)) if (p is not None and m is not None) else (0, 0)
        for p, m in zip(r2_p95, r2_med)
    ]
    # matplotlib expects (lower, upper) as 2xN arrays
    r1_err_arr = np.array(r1_err).T
    r2_err_arr = np.array(r2_err).T

    bars1 = ax.bar(
        x - w / 2,
        r1_vals,
        w,
        color="#9aa0a6",
        edgecolor="black",
        linewidth=0.6,
        label="Round-1 (post-fix)",
    )
    bars2 = ax.bar(
        x + w / 2,
        r2_vals,
        w,
        color="#1a73e8",
        edgecolor="black",
        linewidth=0.6,
        label="Round-2",
    )

    # Annotate median + p95 on top of each bar (p95 small/grey).
    for bars, meds, p95s in ((bars1, r1_med, r1_p95), (bars2, r2_med, r2_p95)):
        for bar, m, p in zip(bars, meds, p95s):
            if m is None or m == 0.0:
                continue
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                m + 0.18,
                f"{m:.2f}",
                ha="center",
                va="bottom",
                fontsize=10,
                fontweight="bold",
            )
            if p is not None:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    m + 0.95,
                    f"p95 {p:.1f}",
                    ha="center",
                    va="bottom",
                    fontsize=7.5,
                    color="#555",
                )

    # Reference: the round-2 baseline-arm median as a horizontal line so we can
    # visually compare every other arm against the simplest (BIRD baseline).
    ref = r2_med[0]
    if ref is not None:
        ax.axhline(
            ref,
            color="#d93025",
            linestyle="--",
            linewidth=1.0,
            label=f"BIRD baseline median = {ref:.2f} ms",
        )

    ax.set_xticks(x)
    ax.set_xticklabels(
        [
            "baseline\n(register + large_json)",
            "enhanced\n(register + describe + fetch)",
            "server\n(register + large_result_auto)",
            "inline\n(bird_query_run_inline)",
        ],
        fontsize=9,
    )
    ax.set_ylabel("End-to-end median latency (ms)")
    ax.set_title(
        "BIRD dev gold — end-to-end median latency per arm "
        "(p95 shown as label)\nRound-1 (post-fix) vs Round-2, n = 1534 queries",
        fontsize=11,
    )
    ax.grid(axis="y", linestyle=":", linewidth=0.5, color="#bbb")
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", framealpha=0.95)
    # Cap the axis to a reasonable headroom over the largest median so the
    # comparison reads clearly. p95 is in the bar labels.
    cap = max(filter(None, r1_med + r2_med)) * 1.4
    ax.set_ylim(0, cap)

    fig.tight_layout()
    out_png = fig_dir / "round2_e2e_latency.png"
    out_pdf = fig_dir / "round2_e2e_latency.pdf"
    fig.savefig(out_png)
    fig.savefig(out_pdf)
    print(f"\nWrote {out_png} and {out_pdf}")


if __name__ == "__main__":
    main()
