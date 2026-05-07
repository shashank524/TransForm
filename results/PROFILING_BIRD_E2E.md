# Profiling: why the enhanced pipeline is ~2x slower than the JSON baseline

This is a focused diagnostic of the BIRD end-to-end benchmark
([bench_bird_e2e.py](../bench_bird_e2e.py)) under `--sql-source gold`. The
problem statement (recorded in [BIRD_TRANSPORT_BENCHMARKS.md](BIRD_TRANSPORT_BENCHMARKS.md)
and [bird_e2e_dev_full_gold_summary.md](bird_e2e_dev_full_gold_summary.md)) is:

- Median **baseline** fetch (JSON only): ~5.7 ms
- Median **enhanced** describe + fetch (Workflow A): ~~10.3 ms (~~1.8x slower)

We also profiled `**--arms server`**: one MCP call to `large_result_auto`
(server-side format selection; same heuristics as `describe_result_formats`
internally) plus a tiny client-side step to size inline JSON or fetch a blob
URL when the server returns a descriptor. That path is much closer to the
baseline on the **client** because it avoids a second MCP round trip.

We used **pyinstrument** (statistical, async-aware) on both client and server
to attribute that overhead. All raw artifacts are under
[results/profiling/](profiling/) (HTML flamegraphs + speedscope JSON for sharing).

## Reproduction

Use a **fresh output directory per server run** so `profile_aggregate_server.py`
does not mix sessions. Example layout: `results/profiling/server_baseline/`,
`results/profiling/server_both/`, `results/profiling/server_run_server/`.

```bash
# 1) Server with per-request profile middleware (pick OUT_DIR per run)
PYINSTRUMENT_PROFILE=1 PYINSTRUMENT_OUT_DIR=results/profiling/server_run_server \
  .venv/bin/uvicorn server_app:app --host 127.0.0.1 --port 8000 --log-level warning &

# 2) Client wrapper around bench_bird_e2e.py (50 queries each; same hooks)
PYINSTRUMENT_PROFILE=1 PYINSTRUMENT_OUT_DIR=results/profiling/client \
PYINSTRUMENT_TAG=bird_e2e_baseline_50 \
  .venv/bin/python bench_bird_e2e.py --sql-source gold --max-queries 50 \
  --arms baseline --overwrite --results results/profiling/client/bird_e2e_baseline_50.jsonl

PYINSTRUMENT_PROFILE=1 PYINSTRUMENT_OUT_DIR=results/profiling/client \
PYINSTRUMENT_TAG=bird_e2e_both_50 \
  .venv/bin/python bench_bird_e2e.py --sql-source gold --max-queries 50 \
  --arms both --overwrite --results results/profiling/client/bird_e2e_both_50.jsonl

# Server-side selection: one MCP tool call (large_result_auto) per query
PYINSTRUMENT_PROFILE=1 PYINSTRUMENT_OUT_DIR=results/profiling/client \
PYINSTRUMENT_TAG=bird_e2e_server_50 \
  .venv/bin/python bench_bird_e2e.py --sql-source gold --max-queries 50 \
  --arms server --overwrite --results results/profiling/client/bird_e2e_server_50.jsonl

# 3) In-process micro-profile of describe / hint compute (no HTTP)
.venv/bin/python profile_hints_compute.py --max-queries 50

# 4) Roll up server per-request profiles by tool (pass the matching server dir)
.venv/bin/python profile_aggregate_server.py results/profiling/server_run_server
```

Both profile hooks are gated on `PYINSTRUMENT_PROFILE=1`, so existing
benchmarks are unaffected.

## End-to-end picture

Profile-attached timings inflate everything ~2x vs the recorded `summary.md`
runs (sampling adds work to every Python call), but the **shape** is preserved:


| Stage (median, profiled run)                   | Baseline arm | Both arms    | Server arm (`large_result_auto`) |
| ---------------------------------------------- | ------------ | ------------ | -------------------------------- |
| `baseline_fetch_s` (JSON)                      | 12.54 ms     | 11.27 ms     | —                                |
| `describe_s`                                   | —            | 11.44 ms     | —                                |
| `enhanced_fetch_s` (chosen format)             | —            | 11.57 ms     | —                                |
| **describe + enhanced**                        | —            | **22.78 ms** | —                                |
| `server_auto_call_s` + `server_auto_payload_s` | —            | —            | **12.27 ms**                     |


The **server** column is from
[bird_e2e_server_50.jsonl](profiling/client/bird_e2e_server_50.jsonl) (50 gold
SQL queries, same mini-dev slice as the other profiled runs): median
`server_auto_call_s` ≈ **12.13 ms**, median `server_auto_payload_s` ≈ **0.01 ms**
(inline JSON: only `json.dumps` for byte counting). Chosen formats:
**49× `json`**, **1× `parquet_blob`** (one extra HTTP GET for that row; still
one MCP tool call).

Same conclusion as [bird_e2e_dev_full_gold_summary.md](bird_e2e_dev_full_gold_summary.md):
the enhanced arm pays for **two MCP roundtrips instead of one**, and the
per-roundtrip cost on each side is essentially identical. The server arm
removes the separate `describe_result_formats` **client** round trip, so end-to-end
client time drops to roughly **one** `jsonschema.validate` + one MCP POST—i.e.
on par with the baseline column, not the doubled enhanced column.

**Caveat:** `large_result_auto` still runs `_get_tabular_size_hints_cached` on
the server (same Parquet re-read + encodes + `HintStore` as `describe_result_formats`).
So server CPU for “selection” is **not** free; you mainly save **one** MCP
request/response and one client validation pass. See the server aggregate below.

Server-side, aggregating per-request profiles by tool ([profile_aggregate_server.py](../profile_aggregate_server.py)):

**Earlier session (baseline + both arms, same server process):**


| Route / tool                   | Count | Median (ms) | Total (ms) |
| ------------------------------ | ----- | ----------- | ---------- |
| `large_json`                   | 99    | 8.17        | 1123.6     |
| `describe_result_formats`      | 50    | 9.14        | 626.6      |
| `materialized` (POST register) | 50    | 0.76        | 46.2       |


**Server-arm-only session** (`results/profiling/server_run_server/`, 50 queries):


| Route / tool                   | Count | Median (ms) | Total (ms) |
| ------------------------------ | ----- | ----------- | ---------- |
| `large_result_auto`            | 50    | 10.16       | 939.1      |
| `materialized` (POST register) | 50    | 0.76        | 65.4       |


So on the server, `**large_result_auto` ≈ `describe_result_formats` in cost**
(median ~10 ms vs ~9 ms)—both paths compute the same hint block. The win for
the server arm is almost entirely on the **client**: one MCP tool result to
validate instead of two when the chosen format is JSON.

The describe call is **slightly more expensive** server-side than the JSON
fetch itself, despite returning a tiny dict — i.e. the extra hop is *not*
free, even on localhost. The two sources of cost are dissected below.

## Where the time actually goes — client side

Top of the call tree from
[results/profiling/client/bird_e2e_both_50.txt](profiling/client/bird_e2e_both_50.txt)
(50 queries, both arms, total 3.49 s wall, 1.26 s CPU):

```
3.4888 main
└─ 1.4684 Handle._run
   ├─ 1.1077 run_bench
   │  └─ 1.0636 run_one  bench_bird_e2e.py:375
   │     ├─ 0.7585 execute_sql_sqlite      ← SQLite, irrelevant to MCP comparison
   │     ├─ 0.0952 enhanced_fetch_recommended
   │     │  └─ 0.0712 call_large_json
   │     │     └─ 0.0712 ClientSession.call_tool
   │     │        └─ 0.0607 _validate_tool_result
   │     │           └─ 0.0597 jsonschema.validate            ← 85% of MCP cost
   │     ├─ 0.0950 register_materialized   ← httpx POST
   │     └─ 0.0851 baseline_fetch_json
   │        └─ 0.0836 call_large_json
   │           └─ 0.0705 jsonschema.validate                  ← same hotspot
```

**Headline client finding:** ~80–85% of the MCP client's per-call cost is
`jsonschema.validate` inside `ClientSession._validate_tool_result`
([python-sdk MCP client `session.py:325](../python-sdk)`). For tiny BIRD
payloads (median 78 B JSON) this is *much* larger than the network/JSON
serialization cost — every tool result goes through full JSON-Schema
structural validation, even when the result is essentially empty.

The same hotspot fires for both `baseline_fetch_json` and
`enhanced_fetch_recommended`, so it explains why each MCP roundtrip costs
~10 ms regardless of which tool is being called.

## Where the time actually goes — server side

In-process profile of `describe_result_formats(...)` over 50 real BIRD
result_ids ([results/profiling/server_micro/describe_inproc.txt](profiling/server_micro/describe_inproc.txt)):

```
0.1722 describe_result_formats  server_app.py:1094
└─ 0.1692 _get_tabular_size_hints_cached  server_app.py:592
   ├─ 0.0904 _compute_tabular_size_hints  server_app.py:517   ← 52% (encode work)
   │  ├─ 0.0494 _resolve_dataframe → read_parquet              (re-reads disk)
   │  ├─ 0.0147 _encode_parquet
   │  ├─ 0.0122 DataFrame.to_dict                              (for JSON size)
   │  ├─ 0.0096 dataframe_to_arrays
   │  └─ 0.0020 _encode_arrow_ipc_file
   ├─ 0.0473 HintStore.upsert  hint_reference_table.py:93     ← 27% (SQLite write)
   │  ├─ 0.0211 Connection.close
   │  ├─ 0.0186 _connect (open + PRAGMA + ensure_schema)
   │  └─ 0.0044 Connection.commit
   └─ 0.0305 HintStore.get  hint_reference_table.py:73        ← 18% (SQLite read)
      ├─ 0.0197 Connection.close
      └─ 0.0097 _connect
```

Two separate problems show up here:

1. **`_compute_tabular_size_hints` re-reads the materialized Parquet from
  disk on every describe call.** ~50% of compute time is `pq.read_parquet`
   in `[_load_materialized_dataframe](../server_app.py)` (line 356). The rest
   is encoding the same data three different ways — full Parquet, Arrow IPC,
   and `DataFrame.to_dict` for the JSON size — even though for tiny BIRD
   results we throw all three numbers away to pick "json" anyway.
2. **`HintStore` (SQLite reference table) opens and closes a connection per
  call, twice.** The intent in [hint_reference_table.py](../hint_reference_table.py)
   was to *cache* expensive hints; in practice for BIRD's per-query unique
   `result_id`s the cache always misses, so we pay both `get` (open/select/
   close) and `upsert` (open/insert/commit/close) for **every** describe call
   — ~45% of the describe call time is wasted reopening a SQLite connection
   we already had.

Standalone `_compute_tabular_size_hints` micro-bench
([results/profiling/server_micro/hints_compute_summary.json](profiling/server_micro/hints_compute_summary.json)):
median **2.24 ms**, p95 **32.21 ms**, range 0.75–42.36 ms over 50 BIRD
gold-SQL results. The SQLite roundtrip on top adds ~1.5 ms more, so a
"fresh" describe call lower-bounds at ~3.5–4 ms before MCP framing.

## Putting the ~22 ms describe + fetch together

For a typical small-result BIRD query under the profiled run:


| Bucket                                        | Approx ms | Source                                       |
| --------------------------------------------- | --------- | -------------------------------------------- |
| Client `jsonschema.validate` × 2              | ~12       | python-sdk MCP client validates every result |
| HTTP/MCP framing × 2                          | ~3        | httpx + JSON-RPC envelope                    |
| Server compute hints (read_parquet + encodes) | ~3        | `_compute_tabular_size_hints`                |
| Server `HintStore` SQLite open/close × 2      | ~2        | `hint_reference_table.py`                    |
| Server `large_json` work (build payload)      | ~2        | tool body                                    |
| **Total (describe + fetch)**                  | **~22**   |                                              |


The baseline single-roundtrip path skips everything in the "× 2" rows that's
attributable to describe and skips `HintStore` entirely → ~11 ms. That's the
~2x ratio we see.

## Ranked fix candidates

Ordered by expected payoff for the BIRD workload (small results, per-query
unique `result_id`).

1. **Drop `HintStore.get` / `.upsert` from the per-call path when
  `result_id` is supplied.** A per-`result_id` in-memory dict on
   `RESULT_REGISTRY[result_id]` is enough; nothing else can ever invalidate
   that entry within a process. Eliminates two SQLite open/close trips
   (~2 ms) and the schema check from every describe call.
2. **Pre-compute hints at `register_materialized` time and stash them in
  `ResultConfig`.** Today the bench already pays Parquet encode / read at
   registration; computing JSON / Arrow IPC sizes there makes describe O(1)
   dict lookup. Eliminates the ~3 ms server-side encode work and removes
   `read_parquet` from the describe hot path entirely.
3. **Cheap-out the JSON byte-size estimate.** `DataFrame.to_dict` +
  `json.dumps` to *measure* JSON bytes is the second-largest server cost
   per describe and is throwaway. A close-enough estimate is
   `n_rows * sum(per-column avg width)`; or just call `df.memory_usage`.
   Saves ~1 ms median, more on wide rows.
4. **Skip Arrow IPC / Parquet hints when JSON size is obviously the winner
  under `min_latency`.** On full BIRD dev,
   [bird_e2e_dev_full_gold_summary.md](bird_e2e_dev_full_gold_summary.md)
   line 53 shows the selector picks `json` 1370/1534 times; we currently
   compute every alternative for all of them. Add an early-out when
   `json_bytes <= small_payload_cutoff`.
5. **Fold describe + fetch into one MCP roundtrip via `large_result_auto`.**
  Implemented in [server_app.py](../server_app.py) (`large_result_auto`).
   [bench_bird_e2e.py](../bench_bird_e2e.py) now exposes this as `**--arms server`**
   (one `call_large_result_auto` per query, then optional HTTP fetch for blob
   descriptors). Profiling shows client median **~12 ms** for call + payload vs
   **~23 ms** for describe + fetch on the same 50-query slice—consistent with
   removing one MCP round trip and one `jsonschema.validate`. Best paired with
   #2 so the server-side hint work inside `large_result_auto` is also cheap.
6. **Reduce the cost of `jsonschema.validate` in the python-sdk MCP
  client.** This is the dominant cost on the client and applies to *both*
   arms. Options: cache a compiled validator per tool name (`jsonschema`
   has `Draft7Validator(...).validate(...)` which is much faster than the
   one-shot `validate()`); or skip validation entirely for trusted servers
   via an `MCP_SKIP_VALIDATE=1` env knob. Estimated win: ~6–8 ms per
   roundtrip on this workload, i.e. larger than any server-side fix. May
   require a small patch to `python-sdk/src/mcp/client/session.py`.

Fixes 1, 2, and 6 together should drop the enhanced pipeline below the
current baseline (because fix 6 also speeds up the baseline, but the
enhanced arm gets the relative win twice).

## Out of scope here

- Implementing any of the above — this report is the diagnosis pass; a
follow-up plan should pick which fixes to land first.
- Profiling [run_workflow.py](../run_workflow.py) (LLM-in-the-loop) and the
synthetic [bench.py](../bench.py) — same hooks (`PYINSTRUMENT_PROFILE=1`)
will work, but the dominant cost there is Ollama, not MCP transport.

## Results after fixes

Five fixes from the ranked list above were implemented (1, 2, 3, 4, 6) per
the project fix plan (tracked in Cursor; not committed as a repo file):

- **Fix 1** — drop `HintStore.get`/`.upsert` from the `result_id` path in
`_get_tabular_size_hints_cached` ([server_app.py](../server_app.py)).
- **Fix 2** — `ResultConfig.cached_hints` populated at `POST /materialized`;
describe / `large_result_auto` short-circuit through it for the default
codec / rows_per_chunk tuple ([server_app.py](../server_app.py)).
- **Fix 3** — `_estimate_json_bytes_from_df` (per-dtype-width estimator) above
`SMALL_PAYLOAD_CELLS=4096`; exact `json.dumps` below.
- **Fix 4** — JSON-obvious-winner short-circuit in `select_format_with_hints`
([format_selector.py](../format_selector.py)) and a server-side encode skip in
`_compute_tabular_size_hints_from_df` (env
`FORMAT_HINTS_SKIP_LARGE_FORMATS_FOR_SMALL=1`, default on) so for tiny payloads
we never encode Parquet/Arrow IPC at all.
- **Fix 6** — vendored python-sdk patch ([session.py](../python-sdk/src/mcp/client/session.py)):
cache compiled `jsonschema` validators per `(session, tool)` and add an opt-in
`MCP_SKIP_VALIDATE=1` bypass for trusted-server benchmarking.

### Profiled 50-query slice (`bench_bird_e2e.py --max-queries 50 --sql-source gold`)

Profiled re-run; same `pyinstrument` hooks as before, sampling overhead inflates
all numbers ~2x relative to no-profile runs, so before/after deltas are what
matters. Artifacts: `results/profiling/client/bird_e2e_*_50_postfix.{html,speedscope.json,txt,jsonl}`.


| Stage (median over 50 q)                       | Before              | After               | Δ    |
| ---------------------------------------------- | ------------------- | ------------------- | ---- |
| `baseline_fetch_s` (baseline arm)              | 12.54 ms            | **9.92 ms**         | −21% |
| `baseline_fetch_s` (both arm)                  | 11.27 ms            | 11.43 ms            | ≈    |
| `describe_s` (both arm)                        | 11.44 ms            | 11.95 ms            | ≈    |
| `enhanced_fetch_s` (both arm)                  | 11.57 ms            | 12.68 ms            | ≈    |
| `**describe_s + enhanced_fetch_s`** (both arm) | **22.78 ms**        | **24.63 ms**        | ≈    |
| `server_auto_call_s` (server arm)              | 12.13 ms            | **9.43 ms**         | −22% |
| `server_auto_payload_s` (server arm)           | 0.01 ms             | 0.01 ms             | =    |
| Server-arm chosen formats                      | 49 json / 1 parquet | 49 json / 1 parquet | =    |


Key takeaway: under the profiler, the validator cache + estimator + skip-large
combo cut **~2.5 ms / MCP roundtrip** on the single-roundtrip paths
(baseline arm, server arm). The "both" arm has two roundtrips; the per-roundtrip
saving is similar but profile-attached run-to-run noise (±2 ms on a 12 ms
median) makes it noisy at this sample size — we compare the unprofiled full-dev
numbers below for a cleaner read.

Server-side per-request aggregates from
[results/profiling/server_postfix/](profiling/server_postfix/) (50 queries,
post-fix server, includes baseline + both + server arms in one process):


| Route / tool                   | Count | Median (ms) | Δ vs pre-fix        |
| ------------------------------ | ----- | ----------- | ------------------- |
| `large_json`                   | 149   | 8.82        | ≈ (8.17)            |
| `describe_result_formats`      | 50    | **7.54**    | −17% (was 9.14)     |
| `large_result_auto`            | 50    | **7.91**    | −22% (was 10.16)    |
| `materialized` (POST register) | 150   | 1.51        | +0.75 ms (was 0.76) |


`describe_result_formats` and `large_result_auto` both dropped meaningfully
because Fixes 1+2+3+4 collapse the `_get_tabular_size_hints_cached` path to a
dict lookup for the default codec — the SQLite trip is gone, the Parquet
re-read is gone, and on small payloads (49/50 BIRD queries) the Parquet/IPC
encodes are skipped entirely. The cost is amortised onto registration:
`POST /materialized` is now ~0.75 ms slower because it pre-encodes hints once
per result. That trade is profitable as soon as a result_id is described or
auto-served *at all*, which is true for every BIRD query.

### Full BIRD dev (1534 queries, no profiler)

Artifacts: `--arms both` →
[bird_e2e_dev_full_gold_postfix.jsonl](bird_e2e_dev_full_gold_postfix.jsonl) +
[bird_e2e_dev_full_gold_postfix_summary.md](bird_e2e_dev_full_gold_postfix_summary.md);
`--arms server` →
[bird_e2e_dev_full_gold_postfix_server.jsonl](bird_e2e_dev_full_gold_postfix_server.jsonl) +
[bird_e2e_dev_full_gold_postfix_server_summary.md](bird_e2e_dev_full_gold_postfix_server_summary.md).
Baseline for comparison: [bird_e2e_dev_full_gold_summary.md](bird_e2e_dev_full_gold_summary.md)
(`bird_e2e_dev_full_gold.jsonl`).

**Important:** an initial post-fix full-dev run showed *no* describe speedup
because `cached_hints` was keyed with `rows_per_chunk=8192` at registration while
the bench passes `rows_per_chunk=min(8192, n_rows)` to `describe_result_formats` /
`large_result_auto`, so the cache never hit. The lookup now treats two chunk
sizes as equivalent when `min(rows_per_chunk, n_rows)` matches (same effective
first-chunk row count). Numbers below are from a **re-run after that fix**.


| Metric (median)                                 | Pre-fix (`bird_e2e_dev_full_gold`) | Post-fix (`*_postfix`) | Δ         |
| ----------------------------------------------- | ---------------------------------- | ---------------------- | --------- |
| Baseline fetch (`baseline_fetch_s`)             | 5.69 ms                            | **5.61 ms**            | −1%       |
| Describe (`describe_s`)                         | 4.79 ms                            | **3.69 ms**            | **−23%**  |
| Enhanced fetch (`enhanced_fetch_s`)             | 5.39 ms                            | 5.39 ms                | ≈         |
| **Describe + enhanced**                         | 10.30 ms                           | **9.25 ms**            | **−10%**  |
| `large_result_auto` call (`server_auto_call_s`) | —                                  | **5.00 ms**            | (new row) |
| Server call + payload (`server_auto_total`)     | —                                  | **5.21 ms**            | (new row) |


p95 (same sources): baseline fetch 43.3 ms → 53.4 ms; describe+enhanced total
41.2 ms → 53.9 ms — tail latency is noisy on localhost; medians are the stable
signal here.

Chosen formats (enhanced arm / server arm): **1413× `json`**, **121× `parquet_blob`**
(post-fix), vs **1370 / 164** pre-fix — the JSON-byte estimator + obvious-winner
short-circuit steer a few more small/wide rows to JSON without changing the
overall transport story.

## Artifact index

- Client flamegraphs (pre-fix): [results/profiling/client/](profiling/client/)
  - `bird_e2e_baseline_50.html` / `.txt` / `.speedscope.json`
  - `bird_e2e_both_50.html` / `.txt` / `.speedscope.json`
  - `bird_e2e_server_50.html` / `.txt` / `.speedscope.json` + `bird_e2e_server_50.jsonl`
- Client flamegraphs (post-fix): same dir, `bird_e2e_*_50_postfix.`* files
- Server per-request flamegraphs (pre-fix): [results/profiling/server/](profiling/server/) (208 from baseline run, 200 from both run after labelling)
- Server profiles (pre-fix `--arms server` run): [results/profiling/server_run_server/](profiling/server_run_server/)
- Server profiles (post-fix all arms): [results/profiling/server_postfix/](profiling/server_postfix/)
- Stashed baseline-only server profiles: [results/profiling/server_baseline/](profiling/server_baseline/)
- Server in-process micro-profiles: [results/profiling/server_micro/](profiling/server_micro/)
  - `hints_compute.html` / `.txt` / `.speedscope.json`
  - `describe_inproc.html` / `.txt` / `.speedscope.json`
  - `hints_compute_summary.json`
- Full BIRD dev post-fix JSONL + summaries:
  - [bird_e2e_dev_full_gold_postfix.jsonl](bird_e2e_dev_full_gold_postfix.jsonl),
  [bird_e2e_dev_full_gold_postfix_summary.md](bird_e2e_dev_full_gold_postfix_summary.md)
  - [bird_e2e_dev_full_gold_postfix_server.jsonl](bird_e2e_dev_full_gold_postfix_server.jsonl),
  [bird_e2e_dev_full_gold_postfix_server_summary.md](bird_e2e_dev_full_gold_postfix_server_summary.md)

