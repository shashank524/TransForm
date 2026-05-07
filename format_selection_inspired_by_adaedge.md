# Format Selection Inspired by AdaEdge: Why Not “Number of Cells”

AdaEdge (ICDE’24) argues **dynamic, input-dependent** compression selection—**targets**, **data/constraints**, and **learned rewards**—instead of one fixed rule. This doc ties that lens to **our implementation** in `format_selector.py`, `describe_result_formats`, and optional `format_mab.py`.

---

## 1. Where selection runs (client-side)

- The **server** exposes `describe_result_formats` (byte hints per format, codecs) and separate `large_*` tools per representation.
- The **client** builds a `SelectionContext` (`n_rows`, `n_cols`, `OptimizationTarget`, `prefer_streaming`) and calls `select_format` (rules only) or `select_format_with_hints` (hints + rules) or `select_format_with_mab` (when `FORMAT_SELECT_MAB` is set).
- **`describe_result_formats`** now also returns **`recommended_format`** (and `recommendation_target`, `recommendation_prefer_streaming`) computed with the **same** `select_format_with_hints` logic on the server—useful for agents that read structured content without importing `format_selector`. The client still **chooses which tool to call**.

Default target: env **`FORMAT_SELECT_TARGET`** = `min_bytes` | `min_latency` | `min_time_to_first_rows` (default `min_latency`).

---

## 2. Formats (five “arms”)

| Mode | Role |
|------|------|
| `json` | Baseline; small tables; no extra HTTP fetch |
| `parquet_blob` | Compressed columnar; usually smallest bytes for analytics |
| `parquet_stream` | Length-prefixed Parquet chunks; TTFR / early stop |
| `arrow_ipc_blob` | Arrow IPC file; larger than Parquet often; fast decode in Arrow stacks |
| `arrow_ipc_stream` | Length-prefixed IPC file chunks; TTFR vs Parquet stream |

**Parquet inner encodings** (CodecDB-style) stay separate: `PARQUET_COMPRESSION`, `PARQUET_ENCODING_STRATEGY`, `codec_selector.py`.

---

## 3. `select_format` (no hints): cell thresholds only

Used when `describe_result_formats` is unavailable or lacks `json_bytes` / `parquet_bytes`.

- Uses **`CELLS_*`**, **`ROWS_STREAM_FAVOR`** bands over `n_rows * n_cols`.
- Does **not** select Arrow IPC (sizes unknown without hints).
- Still encodes **OptimizationTarget** (e.g. stream for large TTFR).

Legacy **`recommend_format_legacy`** is the oldest cell-only ladder.

---

## 4. `select_format_with_hints` (Workflow A)

Requires **`json_bytes`** and **`parquet_bytes`**; optionally **`arrow_ipc_bytes`**, **`parquet_stream_first_chunk_bytes`**, **`arrow_ipc_stream_first_chunk_bytes`**.

### `min_bytes`

Among **`json`**, **`parquet_blob`**, **`arrow_ipc_blob`** (if hinted): pick **minimum `approx_bytes`**. Tie-break order: json → parquet_blob → arrow_ipc_blob.

### `min_latency`

- **Default:** same as **`_min_blob_format`** (min bytes among blob formats)—a **transfer-size proxy**.
- **Optional ACE-style model (when `FORMAT_LATENCY_NETWORK_MBPS` > 0):**  
  For each blob format, score  
  `transfer_seconds = (bytes × 8) / (Mbps × 10^6)`  
  `decode_proxy = bytes × decode_ns_per_byte / 10^9`  
  **minimize** `transfer_seconds + decode_proxy`.  
  Decode ns/byte defaults are tunable via **`FORMAT_LATENCY_DECODE_NS_PER_BYTE_*`** or a JSON file **`FORMAT_LATENCY_CALIBRATION_JSON`** with `decode_ns_per_byte` keys (`json`, `parquet_blob`, `arrow_ipc_blob`).  
  When `FORMAT_LATENCY_NETWORK_MBPS` is **0** (default), behavior matches **min-bytes** among blobs.

### `min_time_to_first_rows`

If streaming is favored (`prefer_streaming` or `n_rows >= ROWS_STREAM_FAVOR`) and the table is not tiny:

- Compare **Parquet stream** vs **Arrow IPC stream** using **first-chunk byte sizes** when `FORMAT_LATENCY_NETWORK_MBPS` is 0; otherwise compare **ACE-style scores** on first-chunk sizes (same decode proxies as blob).
- If only one stream has hints, use that.
- Else fall back to blob choice via the same function as **`min_latency`** (`_min_blob_format_latency`).

---

## 5. Multi-armed bandit (`format_mab.py`)

Optional **epsilon-greedy** over all five formats; rewards from `record_outcome` match the target (e.g. −bytes, −latency, −TTFR). Aligns with AdaEdge’s **learned arm selection**; use **lower** exploration when privacy-sensitive traffic matters.

---

## 6. AdaEdge paper (summary, unchanged idea)

- **Inputs:** data characteristics, **constraints** (bandwidth, CPU), **optimization target**—not a single scalar like cell count.
- **Rewards:** compression ratio, throughput, task accuracy, or weighted combinations.
- **MAB:** explore/exploit over methods; robust to **distribution shift**.
- **Online/offline modes:** bandwidth vs storage pressure change the policy.

We map **methods** → **payload formats + Parquet codec**; **rewards** → benchmarked bytes/latency/TTFR (or MAB outcomes).

---

## 7. Practical checklist

| Goal | Mechanism |
|------|-----------|
| Smallest wire size | `min_bytes` + hints; Parquet often wins |
| True end-to-end latency | Set **`FORMAT_LATENCY_NETWORK_MBPS`** and optional decode calibration; or use **MAB** with measured latency outcomes |
| TTFR / streaming | `min_time_to_first_rows` + `prefer_streaming`; compare stream first chunks |
| Privacy | Orthogonal: TLS, auth, projection before encode; MAB exploration off for sensitive flows |
| Data-driven tuning | Fit **`FORMAT_LATENCY_CALIBRATION_JSON`** from `bench.py` JSONL; refresh `CELLS_*` from synthetic runs |

---

## 8. Short summary

- **Don’t use cell count alone** when hints exist—use **byte hints** and **targets**.
- **Arrow IPC** competes on **decode / interchange**; **Parquet** on **size**—VLDB’25-style trade-off; **`min_latency`** can mix **transfer + decode** when **`FORMAT_LATENCY_NETWORK_MBPS`** is set.
- **Selection is client-side**; **`recommended_format`** mirrors the policy on the server for convenience.
- **MAB** and **calibration JSON** are the natural **data-driven** and **AdaEdge-aligned** next steps beyond fixed thresholds.
