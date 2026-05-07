## Architecture (what you’re building)

### Control plane (MCP / JSON-RPC over streamable-http)

*   Client calls MCP tools at **`/mcp`**
    
*   Tools return a **`CallToolResult`** (or dict) with:
    
    *   model-visible `content` (small text)
        
    *   `structured_content` (JSON descriptor the client reads)
        
    *   optional `_meta` (client-only metrics / IDs)
        

### Data plane (HTTP endpoints you add)

*   For big results, tools return **a URL** to fetch bytes:
    
    *   **Parquet blob:** `GET /blobs/{id}.parquet`
        
    *   **Parquet stream:** `GET /streams/{id}` (length-prefixed micro-Parquet chunks)
        

So the pipeline is:

1.  **MCP tool call** → returns descriptor `{mode, endpoint, params...}`
    
2.  **Client fetches endpoint** → receives bytes (blob or streaming chunks)
    
3.  Client measures **size / encode / decode / latency**
    

* * *

## Security (API key authentication)

*   **Server:** If the environment variable **`MCP_API_KEY`** is set, the server requires every request (MCP, blobs, streams) to include:
    
    `Authorization: Bearer <MCP_API_KEY>`
    
    Missing or invalid token returns **401** with a JSON body `{ "error": "unauthorized", "detail": "..." }`.
    
*   **Client:** The benchmark and workflow clients read **`MCP_API_KEY`** from the environment and send it as a Bearer token on all requests. You can also pass `api_key=...` into `connect()`.
    
*   **Optional:** If `MCP_API_KEY` is not set on the server, no authentication is required (backward compatible).
    
*   **Best practice:** Do not hardcode keys; use env vars or a secrets manager. Rotate keys periodically.

* * *

## Benchmark modes (what you compare)

### Mode A — JSON baseline

*   Tool returns full data as JSON (`records: [...]`)
    
*   Metrics:
    
    *   response bytes
        
    *   JSON parse time
        
    *   end-to-end time (call → parsed)
        

### Mode B — Parquet blob

*   Tool creates Parquet bytes, stores them, returns URL
    
*   Client downloads whole file and decodes
    
*   Metrics:
    
    *   bytes downloaded
        
    *   download time
        
    *   Parquet decode time
        
    *   end-to-end time (call → decoded)
        

### Mode C — Parquet “true streaming” (micro-Parquet chunks)

*   Tool returns stream URL + chunking params
    
*   Server streams multiple **independent Parquet files** back-to-back with **length prefix**
    
*   Client decodes each chunk as it arrives
    
*   Metrics:
    
    *   **time-to-first-rows** (first chunk decoded)
        
    *   bytes seen
        
    *   throughput (rows/sec)
        
    *   early termination savings (cancel after first chunk)
        

* * *

## Step-by-step instructions to run the benchmark (tonight)

### 0) Install deps

In your venv / uv env:

*   `mcp[cli]`
    
*   `uvicorn`
    
*   `starlette`
    
*   `httpx`
    
*   `pyarrow`
    
*   `pandas`
    
*   `numpy`
    

### 1) Start the server

Run:

`uvicorn server_app:app --reload`

Optional (enable API key auth):

`MCP_API_KEY=your-secret-key uvicorn server_app:app --reload`

Then run clients with the same key: `MCP_API_KEY=your-secret-key python bench.py`

Sanity check:

*   MCP endpoint: `http://localhost:8000/mcp`
    
*   Blob endpoint exists after you call the blob tool
    
*   Stream endpoint exists after you call the stream tool
    

### 2) Run the benchmark client

Run:

`python bench.py`

You should see 3 result dicts per test case: `json`, `parquet_blob`, `parquet_stream`.

### 3) Optional: full workflow with lightweight LLM

- **Client package** lives in `client/`: `mcp_client.py` (MCP session + tool calls + blob/stream fetch) and `llm_client.py` (Ollama/Llama or Deep Seek).
- **Run workflow** (MCP + optional LLM): `python run_workflow.py`
  - Default: Ollama (free local Llama). Start with `ollama run llama3.2` then run the script.
  - Deep Seek: `LLM_BACKEND=deepseek DEEPSEEK_API_KEY=sk-... python run_workflow.py`
- **Benchmark** uses the same client: `bench.py` imports from `client.mcp_client` only (no LLM).
- **Comparison tables (regular vs hint-driven):** Run `python bench_compare.py` (server must be running). Writes `results/bench_compare_min_bytes.md`, `results/bench_compare_min_latency.md`, and `results/bench_compare.json`.

* * *

## What to benchmark (choose a small sweep)

Do a grid like this:

### Dataset sizes

*   `n_rows`: 10k, 100k, 500k (if your laptop can handle)
    
*   `n_cols`: 6 (narrow), 20 (wide)
    

### Streaming chunk sizes (Mode C)

*   `rows_per_chunk`: 8k, 64k, 256k
    

This lets you show the tradeoff:

*   smaller chunks → lower **time-to-first-rows**, more overhead
    
*   larger chunks → better throughput, worse latency-to-first
    

* * *

## What metrics to record (minimum set)

For every run, print/save:

### JSON

*   `json_bytes`
    
*   `resp_roundtrip_ms`
    
*   `json_parse_ms`
    

### Parquet blob

*   `bytes`
    
*   `resp_roundtrip_ms`
    
*   `download_ms`
    
*   `decode_ms`
    

### Parquet stream

*   `time_to_first_rows_ms` ✅ your key streaming metric
    
*   `bytes_seen`
    
*   `n_rows_consumed`
    
*   `stream_total_ms`
    
*   `rows_per_chunk`
    

Optional but nice:

*   server-side build times from `_meta` (encode cost)
    
*   peak memory (rough estimate via `psutil`)

### Compression dimension

Parquet compression codec and column-encoding strategy are now **explicit, configurable dimensions**:

*   **Codec**: controlled by `PARQUET_COMPRESSION` env var or per-request MCP tool parameter. Supported values: `snappy` (default), `gzip`, `zstd`, `brotli`, `lz4`, `none`.
*   **Encoding strategy**: controlled by `PARQUET_ENCODING_STRATEGY` env var or per-request parameter. Values: `default` (PyArrow defaults) or `data_driven` (CodecDB-inspired per-column selection via `codec_selector.py`).
*   **Codec ablation**: `bench_codec.py` benchmarks all codec × strategy combinations and writes results to `results/bench_codec_ablation.md`.
*   **Related work**: CodecDB (Jiang et al., SIGMOD '21) — data-driven encoding selection; AdaEdge (Liu et al., ICDE '24) — workload-aware compression selection for edge/IoT. See `compression_focus_and_adaedge.md`.