# Step-by-Step Implementation: AdaEdge-Inspired Format Selection

This plan implements format selection that uses **optimization target**, **data features** (beyond cell count), and optional **feedback**, as in `format_selection_inspired_by_adaedge.md`.

---

## Overview

| Phase | What we add | Where |
|-------|-------------|--------|
| **1** | Optimization target + multi-factor rule-based selector | New module `format_selector.py`; wire into `bench.py` and `run_workflow.py` |
| **2** | Data features: size estimates (server hints or client-side formula) | Server: optional tool/endpoint; client: use estimates in selector |
| **3** | Feedback: record outcomes and use history in selection | History file + selector reads/writes it |
| **4** | (Optional) MAB-style adaptive selection | Epsilon-greedy over formats with running reward estimates |

Selection stays **client-side**: the client decides which tool to call (json / parquet_blob / parquet_stream) and optionally asks the server for size hints.

---

## Phase 1: Optimization Target + Multi-Factor Rules

**Goal:** Replace the cell-count-only heuristic with a selector that takes **(n_rows, n_cols, optimization_target)** and uses simple rules that depend on the target.

### Step 1.1 — Add optimization target and selection context

- Create `format_selector.py` with:
  - **OptimizationTarget** enum: `min_bytes` | `min_latency` | `min_time_to_first_rows`
  - **SelectionContext** (dataclass or TypedDict): `n_rows`, `n_cols`, `target: OptimizationTarget`, optional `prefer_streaming: bool` (constraint hint)
  - **Default target**: e.g. from env `FORMAT_SELECT_TARGET` or `min_latency`

### Step 1.2 — Implement rule-based selector

- Function `select_format(context: SelectionContext) -> str` returning `"json"` | `"parquet_blob"` | `"parquet_stream"`.
- Rules (tunable constants):
  - **min_time_to_first_rows:** Prefer stream for large row counts (e.g. n_rows > 50k); else blob; JSON only for very small.
  - **min_bytes:** Prefer Parquet (blob or stream) once table is “large” (e.g. n_rows * n_cols > 50k); use stream for very large to allow early termination.
  - **min_latency:** Use benchmarks’ typical crossover: small tables JSON can win (no extra HTTP); medium/large Parquet blob or stream. Use (n_rows, n_cols) bands.
- Keep logic in one place and document the thresholds (so we can later replace with MAB or lookup table).

### Step 1.3 — Keep legacy heuristic as fallback

- Add `recommend_format_legacy(n_rows, n_cols)` (current cell-count logic) and call it from `select_format` when target is missing or as a fallback, so behavior is backward compatible.

### Step 1.4 — Wire into bench and workflow

- **bench.py:** Import `select_format` and `OptimizationTarget`; add optional `--target` (or env) to benchmark script. When printing “recommended” format, use `select_format(SelectionContext(n_rows=..., n_cols=..., target=...))`. Optionally run benchmarks with different targets and report which format was “recommended” for each.
- **run_workflow.py:** Use `select_format(SelectionContext(...))` instead of `recommend_format(n_rows, n_cols)`. Get target from env or argument (e.g. `FORMAT_SELECT_TARGET=min_time_to_first_rows`).

### Step 1.5 — Config / env

- Document: `FORMAT_SELECT_TARGET` = `min_bytes` | `min_latency` | `min_time_to_first_rows` (default e.g. `min_latency`).

**Deliverable:** Format choice depends on (n_rows, n_cols, target). No server change. Backward compatible.

---

## Phase 2: Data Features — Size Estimates

**Goal:** Use estimated payload sizes (and optionally shape) so the selector can choose “smaller format” when we have actual or estimated bytes, not only cell count.

### Step 2.1 — Server: optional size-hint tool (recommended)

- Add an MCP tool or HTTP endpoint, e.g. `get_format_hints(n_rows: int, n_cols: int)` that:
  - Uses the same data as the real tools (e.g. `_generate_dataframe(n_rows, n_cols)`),
  - Encodes to JSON and to Parquet (reuse existing helpers),
  - Returns `{"json_bytes": int, "parquet_bytes": int}` (and optionally `"parquet_stream_first_chunk_bytes": int` for first chunk).
- Caching: re-use existing Parquet/JSON generation caches so hint is cheap after first call per (n_rows, n_cols).

### Step 2.2 — Client: call hints when available

- In `format_selector.py`, add an optional **async** path: `select_format_with_hints(context, hints: dict)` where `hints = { "json_bytes", "parquet_bytes" }`.
- Rules: e.g. if target is `min_bytes` and `hints["parquet_bytes"] < hints["json_bytes"]` and n_rows large enough, prefer Parquet; else prefer JSON for small payloads.
- In `run_workflow.py` (and optionally bench): if server supports it, call `get_format_hints` first, then `select_format_with_hints(context, hints)`; otherwise fall back to `select_format(context)` (Phase 1).

### Step 2.3 — Client-only fallback (no server change)

- If we don’t add a server hint:
  - Maintain a small **lookup table** or **formula** from benchmark runs (e.g. “for this schema, JSON ≈ X bytes/cell, Parquet ≈ Y bytes/cell”) and use `n_rows * n_cols` to get estimated bytes per format. Then use the same rules as in Step 2.2 with estimated bytes.
- This avoids server changes but is less accurate than real encode sizes.

**Deliverable:** Selector can use estimated or actual bytes (and optionally shape) so “which format is smaller/faster” is data-driven for the current table.

---

**Workflow A status:** Implemented. Server exposes `describe_result_formats(n_rows, n_cols, rows_per_chunk)`; client uses `call_describe_result_formats` and `select_format_with_hints` in `run_workflow.py` and `bench.py`. General API: `describe_result_formats(tool, args)`; this server implements it for synthetic data as `(n_rows, n_cols, rows_per_chunk)`.

## Phase 3: Feedback — Record Outcomes and Use History

**Goal:** After each tool use, record (context, format used, outcome). When selecting, optionally use past outcomes for the same or similar (n_rows, n_cols) and target to pick the format with best historical reward.

### Step 3.1 — Define outcome record

- One record: `(n_rows, n_cols, format, target, bytes, latency_s, time_to_first_rows_s)` (or a subset). Store as JSON lines or a small JSON array in e.g. `results/format_selection_history.json` (or in-memory for single process).

### Step 3.2 — Record after each run

- In `bench.py` and `run_workflow.py`: after getting metrics for the chosen format, call e.g. `record_outcome(context, format_used, metrics)`. Append to history file (or in-memory store).

### Step 3.3 — Use history in selection

- In `format_selector.py`: add `select_format_with_history(context, history: list) -> str`.
  - For the given `(n_rows, n_cols, target)`, filter history to “similar” rows (e.g. same target and same (n_rows, n_cols) or binned).
  - Compute average reward per format (e.g. for `min_bytes` → reward = -bytes; for `min_latency` → reward = -latency_s).
  - Choose format with best average reward; if no history, fall back to Phase 1 (or Phase 2 if hints available).
- Load history at start of bench/workflow; pass into selector. Keep file small (e.g. last N records or by date).

**Deliverable:** Selection can improve over time using observed outcomes; same or similar requests get the format that performed best historically for the chosen target.

---

## Phase 4 (Optional): MAB-Style Adaptive Selection

**Goal:** Maintain a running estimate of reward per format (per target and optionally per bucket). Use epsilon-greedy: with probability ε explore (random format), else choose format with highest estimated reward. After each response, update the estimate.

### Step 4.1 — Reward definition

- For each target, define reward from metrics: e.g. `min_bytes` → reward = -bytes (or 1/(1+bytes)); `min_latency` → -latency_s; `min_time_to_first_rows` → -time_to_first_rows_s.

### Step 4.2 — Running estimates

- Store per (target, format): `(sum_reward, count)` or running average. Can bucket by (n_rows_bucket, n_cols_bucket) to keep estimates relevant (e.g. 10k–50k rows, 6–20 cols).
- Update: after each outcome, `sum_reward[format] += reward`, `count[format] += 1` (or exponential moving average).

### Step 4.3 — Epsilon-greedy selection

- With probability `epsilon` (e.g. 0.1): choose uniformly among json, parquet_blob, parquet_stream.
- Else: choose format with highest average reward (or UCB if you want). Use Phase 1 rules when count is 0 for all.

### Step 4.4 — Persist state

- Save/load running estimates to a small JSON file so we don’t lose learning across runs.

**Deliverable:** Truly adaptive selection that explores and exploits; good for reporting “we use an AdaEdge-inspired MAB for format selection.”

---

## Implementation Order (Checklist)

- [x] **Phase 1:** `format_selector.py` with OptimizationTarget, SelectionContext, rule-based `select_format`, legacy `recommend_format_legacy`; wired into `bench.py` and `run_workflow.py`. Default target from env `FORMAT_SELECT_TARGET` (default `min_latency`). Try: `FORMAT_SELECT_TARGET=min_time_to_first_rows python bench.py` or `FORMAT_SELECT_TARGET=min_bytes python run_workflow.py`.
- [x] **Phase 2 (Workflow A):** Server: `describe_result_formats(n_rows, n_cols, rows_per_chunk)`; client: `call_describe_result_formats` + `select_format_with_hints`; wired into `run_workflow.py` and `bench.py`. General API is `describe_result_formats(tool, args)`; this server implements it for benchmark as `(n_rows, n_cols, rows_per_chunk)`.
- [ ] **Phase 3:** Outcome record schema; `record_outcome` after each run; `select_format_with_history` and load history in bench/workflow.
- [ ] **Phase 4 (optional):** Reward per target; running estimates; epsilon-greedy; persist MAB state.

---

## File Layout (after Phase 1)

```
format_selector.py       # OptimizationTarget, SelectionContext, select_format (and later with_hints, with_history)
bench.py                # uses format_selector; optional --target
run_workflow.py         # uses format_selector; FORMAT_SELECT_TARGET
server_app.py           # (Phase 2) describe_result_formats hint tool
results/                # (Phase 3) format_selection_history.json
```

Phase 1 is sufficient to “implement it” in the sense of using target and multi-factor rules; Phases 2–3 make it data-driven and adaptive.
