# Compression Focus: Current State and Lessons from AdaEdge

This document reviews **how the project handles compression**, where the **gap** is, and what we can learn from **AdaEdge: A Dynamic Compression Selection Framework for Resource-Constrained Devices** (Liu et al., ICDE 2024) to add a focused compression dimension to the research.

---

## 1. Where We Stand on Compression Today

### What the project already does

- **Format comparison**: JSON (baseline) vs Parquet blob vs Parquet stream. Metrics include payload size, latency, time-to-first-rows, and decode time.
- **Parquet usage**: The data plane serves Parquet over HTTP (blob or stream). In code, Parquet is written via `pyarrow.parquet.write_table(table, buf)` **with no explicit compression argument** — so the implementation relies on PyArrow’s default (typically Snappy).
- **Mentions in docs**:
  - `next_steps.md`: Suggests reporting “bytes (on-wire) and decode time” and optionally adding **gzipped JSON** as an ablation.
  - `real_life_usecases_and_sources.md`: Cites Liu et al. (VLDB Journal’25) and Zeng et al. on Parquet/ORC trade-offs (encoding, decoding speed vs compression).

### What is missing (the compression gap)

- **No explicit treatment of the Parquet compression codec**: Snappy vs Gzip vs Zstd (and possibly “none”) are not varied or reported. So “Parquet” is effectively one opaque choice.
- **No compression ablations**: No systematic comparison of “same schema, different codec” for size vs encode/decode time.
- **No workload- or constraint-aware angle**: The narrative does not yet say how to choose compression when the client is bandwidth-limited vs CPU-limited (e.g. edge agents, mobile).
- **No citation or positioning** of adaptive compression selection work (e.g. AdaEdge) in related work.

So **compression is under-specified**: we compare formats (JSON vs Parquet) but not compression strategies *within* Parquet or across the pipeline.

---

## 2. What AdaEdge Does (Summary)

**AdaEdge** (Chunwei Liu, John Paparrizos, Aaron J. Elmore — ICDE 2024) targets **resource-constrained edge/IoT devices** with a **dynamic, hardware-conscious compression selection** framework.

### Main ideas

- **No one-size-fits-all**: Data characteristics, workloads, and hardware limits vary; a single compression choice is suboptimal.
- **Lossless vs lossy**: When storage or bandwidth is insufficient, lossless alone may be impossible (entropy bound). AdaEdge selects lossy methods (PAA, PLA, FFT, BUFF-lossy, RRD-sample) to meet constraints while optimizing **workload accuracy** (aggregation, ML).
- **Multi-Armed Bandit (MAB)**: Lightweight, O(K) selection over compression “arms.” Reward = optimization target (e.g. compression ratio, throughput, aggregation accuracy, **ML task accuracy**, or weighted combinations). Handles distribution shift.
- **Online vs offline modes**:
  - **Online**: Maximize data transfer within given bandwidth; target compression ratio R = bandwidth / (ingestion rate × bits per sample). Prefer lossless; switch to lossy when R is unreachable.
  - **Offline**: Maximize retention within storage budget; when full, **recode** older/less important segments more aggressively (LRU-based policy), with “virtual decompression” to avoid full decode when recoding.
- **Multiple optimization targets**: Compression ratio, compression throughput, aggregation query accuracy, ML task accuracy, or weighted combinations (e.g. `w1×Acc_agg + w2×Acc_ML + w3×C_thr`).
- **Supported methods**: Gzip, Snappy, Zlib, Gorilla, Sprintz, BUFF, dictionary (lossless); PAA, PLA, FFT, BUFF-lossy, RRD-sample (lossy).

### Results (relevant to us)

- Up to **~30% better ML accuracy** within the same storage budget; up to **~20%** when lossless cannot meet low compression ratios.
- Robust to **data shift** and **hardware variability** (e.g. different ε in MAB, smaller edge hardware).
- Reinforces that **workload-aware** and **constraint-aware** compression selection matters, not just “smaller is better.”

---

## 3. Lessons for Our Project (MCP + Parquet Tool Outputs)

We are not building an edge IoT compression engine; we are evaluating **how to represent and deliver large tool outputs** (format + delivery). AdaEdge still gives us:

1. **Compression as a first-class dimension**  
   “Parquet” is not one choice. Parquet supports multiple codecs (Snappy, Gzip, Zstd, etc.) with different **size vs encode/decode speed** trade-offs. We should make codec explicit and, at minimum, report which one we use and add a **compression ablation**.

2. **Workload- and constraint-aware narrative**  
   Different clients may care more about:
   - **Bytes on wire** (bandwidth-limited, e.g. mobile/edge agents),
   - **Decode time** (CPU-limited, fast iteration),
   - **Time-to-first-rows** (streaming, agentic speculation).  
   AdaEdge’s “optimization target” idea maps to our setting: we can frame our benchmarks as varying **what we optimize for** (size vs decode vs latency-to-first-rows) and show how codec choice affects that.

3. **Related work positioning**  
   Cite AdaEdge (and similar work, e.g. CodecDB, VLDB Journal formats paper) in Related Work: *“Compression selection for resource-constrained and workload-aware systems (e.g. AdaEdge) focuses on edge/IoT and time-series; we focus on protocol-level representation of tool outputs (JSON vs Parquet) and delivery (blob vs stream), but we incorporate codec trade-offs as an explicit dimension and report size vs decode time.”*

4. **Concrete ablations (no MAB required)**  
   - **Codec ablation**: Same Parquet schema and data; vary codec (e.g. Snappy, Gzip, Zstd, or none). Report: bytes on wire, server encode time, client decode time, end-to-end and time-to-first-rows (for stream). One table or small figure.  
   - **Optional**: “Gzipped JSON” (as already suggested in `next_steps.md`) as a baseline to show that format (columnar + codec) beats “just compress JSON.”

5. **Optional future direction**  
   For a “dynamic selection” angle (not required for the current evaluation): one could imagine selecting codec (or even lossy vs lossless for numeric columns) per request or per table based on client hints (e.g. “minimize bytes” vs “minimize decode time”) or observed metrics — analogous to AdaEdge’s MAB but for tool-output delivery. This is a natural “future work” sentence.

---

## 4. Recommended Next Steps (Compression) — STATUS

| Step | Action | Status |
|------|--------|--------|
| **Document** | In `project_steps.md` or a “Benchmark dimensions” section: state that Parquet is currently written with PyArrow default codec (e.g. Snappy), and that **compression codec** is a dimension we vary in ablations. |
| **Implement** | In `server_app.py` (and any config): parameterize Parquet write with a **compression** option (e.g. `compression='snappy' | 'gzip' | 'zstd' | None`). Keep default Snappy for existing benchmarks. |
| **Benchmark** | Add a **compression ablation**: same grid (e.g. n_rows, n_cols, rows_per_chunk), same mode (blob and/or stream), vary codec. Record: bytes, encode_s, decode_s, end_to_end_s, time_to_first_rows_s. One table + one short paragraph in the write-up. |
| **Optional** | Add **gzipped JSON** as a baseline (as in `next_steps.md`) and report size + decode time vs raw JSON and vs Parquet (Snappy/Gzip/Zstd). |
| **Related work** | Add 2–3 sentences: cite **AdaEdge** (ICDE 2024) and, if applicable, **Liu et al. VLDB Journal’25** and **Zeng et al.** for “compression/encoding selection and trade-offs”; state that we apply the same trade-off lens (size vs decode vs latency) to **tool-output representation** in MCP. |

---

## 5. Related Work (Compression / Encoding Selection)

Compression selection for resource-constrained and workload-aware systems has been studied in both database and IoT contexts:

- **CodecDB** (Jiang, Liu, Paparrizos, Chien, Ma, Elmore -- SIGMOD '21) demonstrates that data-driven, per-column encoding selection using learned features (cardinality, sortedness, entropy, value length) achieves ~90% accuracy in picking the best lightweight encoding and improves compression ratio by up to 40% over rule-based approaches. Its encoding-aware query engine further achieves 10x speedups by operating directly on encoded data. We integrate a rule-based variant of CodecDB's feature-driven encoding selection in `codec_selector.py`.

- **AdaEdge** (Liu, Paparrizos, Elmore -- ICDE '24) targets edge/IoT devices with a dynamic, hardware-conscious compression selection framework using multi-armed bandits. It supports both lossy and lossless compression and optimizes for workload-specific targets (compression ratio, throughput, ML accuracy). We adopt AdaEdge's trade-off lens and apply it to tool-output representation in MCP.

- **Liu et al. (VLDB Journal '25)** and **Zeng et al.** empirically evaluate Parquet/ORC format trade-offs (encoding, decoding speed, compression ratio) for analytical and ML workloads.

We apply these insights to protocol-level representation of tool outputs: rather than treating Parquet as a single opaque choice, we make the compression codec and column-encoding strategy explicit dimensions and benchmark their trade-offs.

---

## 6. One-Paragraph Summary for the Professor

**Compression:** We now treat Parquet compression codec (Snappy, Gzip, Zstd, none) and column-encoding strategy (default vs CodecDB-inspired data-driven) as **explicit benchmark dimensions**. The server is parameterized via `PARQUET_COMPRESSION` and `PARQUET_ENCODING_STRATEGY` env vars (with per-request overrides on the MCP tools). A standalone codec ablation benchmark (`bench_codec.py`) measures bytes, encode time, and decode time across all codec x strategy combinations. The data-driven encoding strategy (`codec_selector.py`) extracts per-column features -- cardinality ratio, sortedness, type -- and selects dictionary, delta, or plain encoding per column, following CodecDB (Jiang et al., SIGMOD '21). We cite both CodecDB and AdaEdge (Liu et al., ICDE '24) as related work on data-driven and workload-aware compression selection.

(Previous text for reference: We previously compared JSON vs Parquet (blob/stream) and report bytes and decode time, but we do not vary or document the **Parquet compression codec** (we use PyArrow’s default, typically Snappy). A clear next step is to add **compression as an explicit dimension**: (1) document and parameterize the codec (Snappy, Gzip, Zstd, none), (2) run a **codec ablation** (same data, same format; report size vs encode/decode vs time-to-first-rows), and (3) cite **AdaEdge** (ICDE 2024) and format/encoding literature in Related Work. AdaEdge shows that workload- and constraint-aware compression selection matters (e.g. bandwidth vs CPU vs accuracy); we can mirror that by framing our results as “which codec under which objective” (minimize bytes vs minimize decode time vs minimize latency-to-first-rows) without implementing adaptive selection ourselves.
