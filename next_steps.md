# Next Steps for the Research Project

A practical order of work: **review papers → code workflows → run benchmarks aligned to those papers → analyze and write up**.

---

## 1. Review the papers (extract what matters for your idea)

**Goal:** Know exactly what each paper measures and how, so you can (a) argue your idea fits their use cases, and (b) align your benchmarks where possible.

### 1.1 For each paper, fill a short template

For every paper you cite (start with the peer-reviewed ones in `real_life_usecases_and_sources.md`), note:

| Question | What to write down |
|----------|--------------------|
| **What use case do they assume?** | e.g. “Text-to-SQL; agent gets full result set in context” vs “Agent gets only schema + sample rows.” |
| **How do they deliver “large” data to the model/agent?** | In-context JSON? Pagination? No large results (only execution accuracy)? |
| **What do they benchmark?** | Execution accuracy, latency, token count, retrieval quality, success rate, etc. |
| **What dataset/scale?** | DB size, # rows returned, # columns, schema size (e.g. BIRD 33.4 GB, 95 DBs). |
| **Gap your idea fills** | One sentence: “They don’t consider representation of large tool outputs; we do.” |

**Suggested order to read:**

1. **Gao et al. (PVLDB’24)** – Text-to-SQL benchmark; note how they handle result size and tokens.
2. **BIRD (NeurIPS’23)** – Scale of DBs and queries; whether they ever return large result sets to the LLM.
3. **Liu et al. (VLDB Journal’25)** – Parquet vs Arrow vs ORC; which knobs (encoding, compression) matter for “tool output” size/latency.
4. **ACL/EMNLP tool-use papers** – Whether they mention tool *result* size or format; if not, that’s your gap.
5. **Berkeley agentic speculation (arXiv:2509.00997)** – Latency/iteration requirements; map to your “time-to-first-rows” and end-to-end time.

### 1.2 One-page “Related work + gap” summary

After the table, write **one page** that:

- States the **common theme**: e.g. “Text-to-SQL and agent tool use focus on schema, prompts, and execution accuracy; few address how to represent and deliver large *result sets* from tools.”
- States **your gap**: “We evaluate whether Parquet (blob or stream) as the data plane for large MCP tool outputs improves payload size, latency, and time-to-first-rows vs JSON-in-MCP.”
- Lists 3–5 papers with one sentence each on how they relate and how you differ.

Use this later as the “Related work” and “Motivation” skeleton for a report or paper.

---

## 2. Code the workflow (make your setup match the use cases)

**Goal:** Have a single, clear workflow that mirrors “agent calls tool → gets large table → consumes it,” so your benchmarks are interpretable.

### 2.1 Keep your current core, extend it

- **Keep:** MCP server with three modes (JSON, Parquet blob, Parquet stream); Starlette data plane; `bench.py` client with your existing metrics (end-to-end, bytes, time-to-first-rows, early termination).
- **Extend in one or more of these directions** (pick by which paper you want to align with first):

  - **A. Text-to-SQL–style workflow (BIRD / Gao et al.)**
    - Add a **synthetic “query result” generator** that, given `(n_rows, n_cols, schema_id)`, produces a table that *looks* like a SQL result (e.g. mix of types, nulls, or simple distributions). Reuse your existing `_generate_dataframe` or replace it with a BIRD-inspired schema (e.g. a few fixed “tables” with names and column types from BIRD).
    - Optionally: run **real BIRD dev queries** (or a subset) against SQLite/Postgres, dump result sets, then replay them through your three modes (JSON vs blob vs stream) and measure size + latency. That gives you “same data, different representation” and a direct link to BIRD.

  - **B. Agentic speculation–style workflow (Berkeley / Firebolt)**
    - Add a **small “agent loop”** in the client: e.g. “call tool 10–50 times with different (n_rows, n_cols) and optionally rows_per_chunk; measure total wall time and total bytes.” Compare JSON vs Parquet blob vs stream when the “agent” requests many result sets in sequence (or in parallel). This tests “iteration speed” and “total payload” under repeated tool use.

  - **C. Observability / logs–style workflow**
    - Add a **log-like table** (e.g. columns: timestamp, level, message, service_id, trace_id); same three modes. Optional: use a public log sample (e.g. from a benchmark) and convert to Parquet/JSON to compare size and decode time. Keeps your “real-life use case” story without changing the protocol.

You don’t have to do A, B, and C at once. **Pick one (e.g. A for BIRD/Gao, or B for Berkeley) and implement it first.**

### 2.2 Make benchmarks reproducible

- **Config file:** Put `n_rows`, `n_cols`, `rows_per_chunk`, and list of `(n_rows, n_cols)` pairs in a small JSON or YAML (e.g. `bench_config.json`). `bench.py` reads it so you can re-run the same grid for the paper and for rebuttals.
- **Seeds:** If you add randomness (e.g. sampling rows from a real DB), set a seed and document it.
- **Artifacts:** Write one CSV or JSON per run (e.g. `results_2025-02-10.json`) with all metrics, config, and a short description. That becomes your “benchmark results” artifact for the write-up.

### 2.3 Optional but useful code steps

- **Parameterize base URL and port** in `bench.py` and `server_app.py` (env or config) so you can run server and client on different machines later (e.g. for network experiments).
- **Add a “warmup” run** (e.g. one small JSON + one small blob + one small stream) before the timed runs to reduce cold-start effects in reported numbers.
- **Log server-side encode time** (e.g. time to build DataFrame + write Parquet) and expose it in `_meta` or headers so you can report “server encode vs client decode vs network.”

---

## 3. Benchmark for the use cases described in the papers

**Goal:** Produce numbers that you can directly tie to “use case X from paper Y” and to your research question (JSON vs Parquet blob vs stream).

### 3.1 Align metrics to the papers

- **From BIRD / Gao et al.:** If you run BIRD-style queries, report **execution accuracy** (same SQL, same DB) plus **payload size and latency** for the result set in each representation (JSON vs blob vs stream). That shows “same task, different delivery cost.”
- **From Berkeley / Firebolt:** Report **end-to-end time for N tool calls** (e.g. N=20 or 50) and **total bytes** when the “agent” requests many result sets; optionally **time-to-first-rows** per call. That shows “iteration speed” and “total data transfer” under agentic-style workload.
- **From VLDB Journal (formats):** Report **bytes (on-wire)** and **decode time** for the same logical table in JSON vs Parquet (and, if you add it, e.g. gzipped JSON). That matches their “trade-offs” narrative (size vs decode cost).

Keep your **existing metrics** (end_to_end_s, response_bytes / bytes_downloaded / bytes_read, time_to_first_rows_s, json_encode_s, json_decode_s, decode_s) and add any of the above that you don’t already have.

### 3.2 Suggested benchmark tiers

- **Tier 1 – Your current grid (already done):**  
  `n_rows ∈ {10k, 100k}`, `n_cols ∈ {6, 20}`, `rows_per_chunk ∈ {8k, 64k, 256k}`.  
  Use this as the **main table** in the write-up: “We compare three delivery modes across dataset sizes and chunk sizes.”

- **Tier 2 – Paper-aligned:**  
  One or two setups that mirror a paper (e.g. BIRD table sizes, or “50 small result sets” for agentic).  
  Report in a short subsection: “To compare with the scale assumed in BIRD / Berkeley-style workloads, we …”

- **Tier 3 – Sensitivity (optional):**  
  Vary one thing (e.g. `rows_per_chunk` only, or `n_cols` only) and show a small plot or table.  
  Good for “streaming chunk size trade-off” or “wide vs narrow table.”

### 3.3 Run and store results

- Re-run Tier 1 (and Tier 2 when you add it) at least 2–3 times; report **mean and std** (or min/max) for latency and, if relevant, bytes.
- Save each run’s config + results (e.g. `results/run_2025-02-10_tier1.json`).  
  This gives you a clear “we ran this config on this date” trail for the professor or reviewers.

---

## 4. After benchmarks: analyze and write up

- **Short report / memo:**  
  - Problem (large MCP tool outputs; JSON doesn’t scale).  
  - Approach (control plane MCP + data plane Parquet blob/stream).  
  - Setup (server, client, modes, config).  
  - Results (Tier 1 table + Tier 2 if done; 1–2 paragraphs interpretation).  
  - Related work (your one-page summary).  
  - Limitations (localhost, synthetic data, single client, etc.).  
  - Next steps (real BIRD execution, network tests, other formats).

- **Optional:** One simple figure (e.g. bar chart: end-to-end time by mode and size; or time-to-first-rows vs rows_per_chunk).  
  Helps the professor see the takeaway quickly.

- **Optional:** Add 1–2 ablations (e.g. “What if we use gzipped JSON?” or “What if we stream 10 small Parquet files instead of one blob?”) and one short paragraph each.  
  Strengthens “we thought about alternatives.”

---

## 4.5 Compression as an explicit dimension (see also `compression_focus_and_adaedge.md`)

**Status: DONE.** Parquet compression codec and column-encoding strategy are now explicit, configurable dimensions. See `codec_selector.py`, `bench_codec.py`, and updated `compression_focus_and_adaedge.md`.

**Lessons from AdaEdge (Liu et al., ICDE 2024):** Dynamic, workload- and constraint-aware compression selection matters; “one size fits all” fails when data, workload, or hardware vary. AdaEdge uses MAB for lossless/lossy selection on edge devices; we can adopt the **trade-off lens** (size vs decode time vs latency) without building adaptive selection.

**Concrete steps:**

- **Document:** State in benchmark docs which Parquet codec is used; treat codec as a dimension.
- **Parameterize:** In the server (and config), allow Parquet compression to be set (e.g. `snappy` | `gzip` | `zstd` | `none`). Keep Snappy as default for existing runs.
- **Ablation:** Same data and mode (blob and/or stream), vary codec; report bytes, encode_s, decode_s, end_to_end_s, time_to_first_rows_s. One table + short interpretation.
- **Related work:** Cite AdaEdge (ICDE 2024) and format/encoding papers (Liu et al. VLDB J.’25, Zeng et al.) for compression/encoding trade-offs; position our work as applying that trade-off lens to **tool-output representation** in MCP.

---

## 5. Minimal order of execution (checklist)

1. **Review**  
   - [ ] Fill the “per-paper” table for 3–5 papers (start with Gao, BIRD, Liu et al., one ACL/EMNLP tool paper, Berkeley).  
   - [ ] Write the one-page “Related work + gap” summary.

2. **Code**  
   - [ ] Choose one workflow to add first (A: BIRD-style, B: agentic loop, or C: log-like).  
   - [ ] Implement it (synthetic data or small BIRD subset).  
   - [ ] Add config file + artifact output (JSON/CSV per run).  
   - [ ] (Optional) Warmup, parameterized URL, server-side encode time.

3. **Benchmark**  
   - [ ] Re-run Tier 1 (current grid) 2–3 times; save results.  
   - [ ] Run Tier 2 (paper-aligned) when the workflow is ready; save results.  
   - [ ] Compute mean ± std for key metrics; build the main table (and optional figure).

4. **Write**  
   - [ ] Short report (problem, approach, setup, results, related work, limitations, next steps).  
   - [ ] (Optional) One figure; 1–2 ablation paragraphs.

5. **Compression (explicit dimension)** — DONE  
   - [x] Document which Parquet codec is used; parameterize codec in server/config.  
   - [x] Run codec ablation (Snappy vs Gzip vs Zstd; bytes, encode/decode) — see `results/bench_codec_ablation.md`.  
   - [x] Add CodecDB-inspired per-column encoding selection — see `codec_selector.py`.  
   - [x] Cite CodecDB, AdaEdge, and format/encoding papers in Related Work (see `compression_focus_and_adaedge.md`).

This order keeps “review papers → code workflow → benchmark for those use cases” explicit and gives you a clear path from “my idea” to “evidence that it works” and “how it relates to prior work.”
