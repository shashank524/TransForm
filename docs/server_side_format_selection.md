## Server-side format selection (one MCP round trip)

This repo supports **two** ways to choose output formats:

- **Client-side (Workflow A)**: client calls `describe_result_formats` (gets hints) → client picks a `large_*` tool.
- **Server-side (one-shot)**: client calls **one** MCP tool, `large_result_auto`, providing an **optimization target**; the server picks the format internally and returns the payload **plus** metadata saying which format was used and how to decode it.

### What “one round trip” means here

**One round trip** means **one MCP control-plane** `call_tool`. For blob/stream payloads, the response can include a `url`; fetching that URL is on the **HTTP data plane** and does **not** require a second MCP tool call.

### Server-side tool: `large_result_auto`

Defined in [`server_app.py`](../server_app.py).

**Inputs**

- **`result_id`**: preferred for real workflows (e.g. BIRD): you run SQL locally, materialize, upload, then ask the server to return it in the best format.
- **`optimization_target`**: `min_bytes` | `min_latency` | `min_time_to_first_rows`
- Optional knobs: `rows_per_chunk`, `prefer_streaming`, `use_mab`

**Outputs**

The tool returns `structured_content` shaped like:

```json
{
  "payload_kind": "tabular | unstructured",
  "chosen_format": "json | parquet_blob | parquet_stream | arrow_ipc_blob | arrow_ipc_stream | text_inline | raw_blob | gzip_blob",
  "optimization_target": "min_bytes | min_latency | min_time_to_first_rows",
  "payload": { "kind": "json|descriptor|text", "...": "..." },
  "decode": { "encoding": "...", "transport": "...", "url": "..." }
}
```

Decode is intentionally minimal and machine-readable:

- **`decode.transport`**:
  - `inline` (no HTTP fetch)
  - `http_blob` (download whole file from `decode.url`)
  - `http_length_prefixed_stream` (read `[8-byte big-endian length][chunk bytes]` repeatedly from `decode.url`)
- **`decode.encoding`**:
  - `json_records` (tabular inline)
  - `parquet`
  - `arrow_ipc`
  - `text` (unstructured inline)
  - `raw_bytes` (unstructured blob)

### Unstructured outputs (text / arbitrary bytes)

The server supports unstructured outputs as a first-class “payload_kind”.

**Register unstructured bytes**

- `POST /materialized-raw` with body = raw bytes and a `Content-Type` (e.g. `text/plain; charset=utf-8`)
- Response includes `result_id`

**Unstructured arms**

- `text_inline`: small UTF-8 text inline (capped by `MAX_INLINE_TEXT_BYTES` in `server_app.py`)
- `raw_blob`: URL `GET /raw/{id}`
- `gzip_blob`: URL `GET /raw-gzip/{id}` with `Content-Encoding: gzip`

`large_result_auto` chooses among these based on `optimization_target` and internal byte estimates.

### How the server “estimates” sizes (internal hints)

For tabular payloads, the server computes the same hint fields that `describe_result_formats` returns, but it can keep them internal in the one-shot path:

- `json_bytes`: UTF-8 length of `json.dumps(records)`
- `parquet_bytes`: length of Parquet blob bytes
- `arrow_ipc_bytes`: length of Arrow IPC file bytes
- `*_first_chunk_bytes`: encode the first `rows_per_chunk` rows as a chunk and take its byte length

To avoid recomputing these repeatedly, the server uses:

- **In-process cache**
- Optional persisted **SQLite reference table**: [`hint_reference_table.py`](../hint_reference_table.py)
  - env: `FORMAT_HINTS_DB_PATH` (default `results/format_hints.sqlite`)
  - disable: `FORMAT_HINTS_DB_DISABLE=1`

### Optional server-side MAB

If `use_mab=true`, `large_result_auto` will use server-side MAB state when choosing formats.

- State path env: `FORMAT_MAB_STATE_PATH` (default `results/format_mab_state.json`)
- Benchmark helper tool: `record_format_outcome` (updates server MAB state from measured bytes/latency/TTFR)

### Benchmarking: client vs server selection

[`bench_nl2sql_materialized.py`](../bench_nl2sql_materialized.py) now records server-side one-shot metrics alongside the existing client-side path:

- **Client-side**: `describe_result_formats` + `large_*` (+ HTTP fetch)
- **Server-side**: `large_result_auto` (+ optional HTTP fetch)

Key fields added:

- `server_auto_chosen_format`
- `server_auto_end_to_end_s`
- `server_auto_time_to_first_rows_s`
- `server_auto_bytes`

