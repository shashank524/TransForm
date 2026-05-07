"""
Generate two motivation figures:
1) JSON is often not the best option (bytes + latency)
2) Winner format is context-dependent (modality x objective/network)

Outputs:
  - results/modality_motivation_bench.json
  - results/figures/poster/fig_M1_json_not_best_by_modality.(png|pdf)
  - results/figures/poster/fig_M2_winner_map_modality_objective.(png|pdf)
"""

from __future__ import annotations

import base64
import gzip
import io
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt
import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc
import pyarrow.parquet as pq
from matplotlib.colors import ListedColormap


RESULTS_DIR = Path("results")
OUT_DIR = RESULTS_DIR / "figures" / "poster"
BENCH_JSON = RESULTS_DIR / "modality_motivation_bench.json"

NETWORK_MBPS = {
    "LAN": 1000.0,
    "BadWifi": 5.0,
}

# Fixed colors to keep poster consistency.
FORMAT_COLORS = {
    "json": "#4C78A8",
    "parquet_blob": "#F58518",
    "arrow_ipc_blob": "#54A24B",
    "raw_blob": "#B279A2",
    "gzip_blob": "#E45756",
}


@dataclass
class ModalityFormatMetric:
    modality: str
    format_name: str
    payload_bytes: int
    decode_s: float


def _payload_records(modality: str) -> List[Dict[str, Any]]:
    if modality == "integer":
        return [{"i": i} for i in range(2000)]
    if modality == "float":
        return [{"x": float(i) / 10.0, "y": np.sin(i / 37.0)} for i in range(2000)]
    if modality == "tabular_mixed":
        return [
            {
                "id": i,
                "group": f"g{i % 8}",
                "score": float(i % 100) / 7.0,
                "active": bool(i % 2),
            }
            for i in range(12000)
        ]
    if modality == "text":
        # Moderate sized documents; JSON includes key overhead.
        base = "agentic workload result chunk "
        return [{"text": (base + str(i) + " ") * 20} for i in range(1500)]
    if modality == "image":
        # Simulate binary payload chunks (e.g. image/tool artifacts).
        rng = np.random.default_rng(seed=7)
        blobs = [rng.integers(0, 256, size=16_384, dtype=np.uint8).tobytes() for _ in range(180)]
        return [{"name": f"img_{i}", "bytes": b} for i, b in enumerate(blobs)]
    raise ValueError(f"Unknown modality: {modality}")


def _json_metric(records: List[Dict[str, Any]], modality: str) -> ModalityFormatMetric:
    if modality == "image":
        # JSON path must base64 binary.
        serializable = [{"name": r["name"], "bytes_b64": base64.b64encode(r["bytes"]).decode("ascii")} for r in records]
    else:
        serializable = records
    raw = json.dumps(serializable, separators=(",", ":")).encode("utf-8")
    t0 = time.perf_counter()
    _ = json.loads(raw.decode("utf-8"))
    dec = time.perf_counter() - t0
    return ModalityFormatMetric(modality, "json", len(raw), dec)


def _raw_metric(records: List[Dict[str, Any]], modality: str) -> ModalityFormatMetric:
    if modality == "image":
        raw = b"".join([r["bytes"] for r in records])
    else:
        raw = "\n".join([r.get("text", "") for r in records]).encode("utf-8")
    # Assume trivial decode/parse for raw blob path (consumer-specific).
    t0 = time.perf_counter()
    _ = len(raw)
    dec = time.perf_counter() - t0
    return ModalityFormatMetric(modality, "raw_blob", len(raw), dec)


def _gzip_metric(raw_metric: ModalityFormatMetric) -> ModalityFormatMetric:
    # Re-compress raw bytes for unstructured compressed transport.
    # We only use this for text/image modalities.
    # Decode includes gzip inflate.
    modality = raw_metric.modality
    # No access to raw bytes here; reconstruct from modality records in caller.
    raise RuntimeError("Use _gzip_metric_from_bytes")


def _gzip_metric_from_bytes(modality: str, raw: bytes) -> ModalityFormatMetric:
    zipped = gzip.compress(raw, compresslevel=6)
    t0 = time.perf_counter()
    _ = gzip.decompress(zipped)
    dec = time.perf_counter() - t0
    return ModalityFormatMetric(modality, "gzip_blob", len(zipped), dec)


def _tabular_arrow_table(records: List[Dict[str, Any]], modality: str) -> pa.Table:
    if modality == "image":
        rows = [{"name": r["name"], "bytes": r["bytes"]} for r in records]
    else:
        rows = records
    return pa.Table.from_pylist(rows)


def _parquet_metric(table: pa.Table, modality: str) -> ModalityFormatMetric:
    bio = io.BytesIO()
    pq.write_table(table, bio, compression="snappy")
    data = bio.getvalue()
    t0 = time.perf_counter()
    _ = pq.read_table(io.BytesIO(data))
    dec = time.perf_counter() - t0
    return ModalityFormatMetric(modality, "parquet_blob", len(data), dec)


def _arrow_metric(table: pa.Table, modality: str) -> ModalityFormatMetric:
    bio = io.BytesIO()
    with ipc.new_file(bio, table.schema) as writer:
        writer.write_table(table)
    data = bio.getvalue()
    t0 = time.perf_counter()
    reader = ipc.open_file(io.BytesIO(data))
    _ = reader.read_all()
    dec = time.perf_counter() - t0
    return ModalityFormatMetric(modality, "arrow_ipc_blob", len(data), dec)


def _estimated_latency_s(payload_bytes: int, decode_s: float, mbps: float) -> float:
    transfer_s = (payload_bytes * 8.0) / (mbps * 1_000_000.0)
    return transfer_s + decode_s


def build_bench() -> List[ModalityFormatMetric]:
    out: List[ModalityFormatMetric] = []
    for modality in ["integer", "float", "tabular_mixed", "text", "image"]:
        records = _payload_records(modality)
        out.append(_json_metric(records, modality))

        if modality in {"text", "image"}:
            if modality == "image":
                raw_bytes = b"".join([r["bytes"] for r in records])
            else:
                raw_bytes = "\n".join([r.get("text", "") for r in records]).encode("utf-8")
            out.append(ModalityFormatMetric(modality, "raw_blob", len(raw_bytes), 0.0))
            out.append(_gzip_metric_from_bytes(modality, raw_bytes))
        else:
            table = _tabular_arrow_table(records, modality)
            out.append(_parquet_metric(table, modality))
            out.append(_arrow_metric(table, modality))
    return out


def fig_m1_json_not_best(metrics: List[ModalityFormatMetric]) -> None:
    """
    For each modality, show ratio JSON / best-format for:
      - payload bytes
      - estimated latency on BadWifi
    Ratio > 1 => JSON is worse.
    """
    modalities = ["integer", "float", "tabular_mixed", "text", "image"]
    ratio_bytes = []
    ratio_latency = []

    by_mod: Dict[str, List[ModalityFormatMetric]] = {}
    for m in metrics:
        by_mod.setdefault(m.modality, []).append(m)

    for mod in modalities:
        ms = by_mod[mod]
        json_m = [x for x in ms if x.format_name == "json"][0]
        best_bytes = min(x.payload_bytes for x in ms)
        best_lat = min(_estimated_latency_s(x.payload_bytes, x.decode_s, NETWORK_MBPS["BadWifi"]) for x in ms)
        json_lat = _estimated_latency_s(json_m.payload_bytes, json_m.decode_s, NETWORK_MBPS["BadWifi"])
        ratio_bytes.append(json_m.payload_bytes / best_bytes if best_bytes > 0 else np.nan)
        ratio_latency.append(json_lat / best_lat if best_lat > 0 else np.nan)

    x = np.arange(len(modalities))
    w = 0.36
    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    ax.bar(x - w / 2, ratio_bytes, width=w, label="JSON / best bytes", color="#4C78A8")
    ax.bar(x + w / 2, ratio_latency, width=w, label="JSON / best latency (BadWifi)", color="#E45756")
    ax.axhline(1.0, color="gray", linestyle="--", linewidth=1.2)
    ax.set_xticks(x, ["integer", "float", "tabular", "text", "image"])
    ax.set_ylabel("Ratio (higher is worse for JSON)")
    ax.set_title("JSON is not always best across modalities")
    ax.grid(True, axis="y", linewidth=0.35, alpha=0.4)
    ax.legend(frameon=False, loc="upper left")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig_M1_json_not_best_by_modality.png", dpi=280)
    fig.savefig(OUT_DIR / "fig_M1_json_not_best_by_modality.pdf")
    plt.close(fig)


def fig_m2_winner_map(metrics: List[ModalityFormatMetric]) -> None:
    """
    Winner map across modalities and objectives/conditions.
    Conditions:
      - min_bytes
      - min_latency @ LAN
      - min_latency @ BadWifi
    """
    modalities = ["integer", "float", "tabular_mixed", "text", "image"]
    conditions = ["min_bytes", "min_latency@LAN", "min_latency@BadWifi"]
    winner_matrix = np.zeros((len(modalities), len(conditions)))

    by_mod: Dict[str, List[ModalityFormatMetric]] = {}
    for m in metrics:
        by_mod.setdefault(m.modality, []).append(m)

    # Limit palette to formats that can appear.
    formats = ["json", "parquet_blob", "arrow_ipc_blob", "raw_blob", "gzip_blob"]
    fidx = {f: i for i, f in enumerate(formats)}
    cmap = ListedColormap([FORMAT_COLORS[f] for f in formats])

    for i, mod in enumerate(modalities):
        ms = by_mod[mod]
        # min bytes
        best_b = min(ms, key=lambda x: x.payload_bytes).format_name
        winner_matrix[i, 0] = fidx[best_b]
        # min latency LAN
        best_lan = min(ms, key=lambda x: _estimated_latency_s(x.payload_bytes, x.decode_s, NETWORK_MBPS["LAN"])).format_name
        winner_matrix[i, 1] = fidx[best_lan]
        # min latency BadWifi
        best_bw = min(ms, key=lambda x: _estimated_latency_s(x.payload_bytes, x.decode_s, NETWORK_MBPS["BadWifi"])).format_name
        winner_matrix[i, 2] = fidx[best_bw]

    fig, ax = plt.subplots(figsize=(7.4, 4.0))
    ax.imshow(winner_matrix, cmap=cmap, aspect="auto", interpolation="nearest", vmin=0, vmax=len(formats) - 1)
    ax.set_xticks(np.arange(len(conditions)))
    ax.set_xticklabels(conditions)
    ax.set_yticks(np.arange(len(modalities)))
    ax.set_yticklabels(["integer", "float", "tabular", "text", "image"])
    ax.set_title("Best format depends on modality and objective")
    ax.set_xlabel("Objective / condition")
    ax.set_ylabel("Modality")

    for i in range(winner_matrix.shape[0]):
        for j in range(winner_matrix.shape[1]):
            fmt = formats[int(winner_matrix[i, j])]
            lbl = fmt.replace("_blob", "").replace("_", " ")
            ax.text(j, i, lbl, ha="center", va="center", fontsize=8, color="white")

    handles = [
        plt.Line2D([], [], marker="s", linestyle="none", markersize=9, color=FORMAT_COLORS[f], label=f.replace("_", " "))
        for f in formats
    ]
    ax.legend(handles=handles, frameon=False, loc="upper left", bbox_to_anchor=(1.02, 1.0))

    fig.tight_layout()
    fig.savefig(OUT_DIR / "fig_M2_winner_map_modality_objective.png", dpi=280)
    fig.savefig(OUT_DIR / "fig_M2_winner_map_modality_objective.pdf")
    plt.close(fig)


def main() -> None:
    metrics = build_bench()
    BENCH_JSON.write_text(json.dumps([asdict(x) for x in metrics], indent=2), encoding="utf-8")
    fig_m1_json_not_best(metrics)
    fig_m2_winner_map(metrics)
    print(f"Wrote {BENCH_JSON}")
    print(f"Wrote figures to {OUT_DIR}/")


if __name__ == "__main__":
    main()
