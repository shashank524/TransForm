# BIRD end-to-end benchmark summary

## Run configuration

- **Query records:** 1534
- **Exec OK:** 1534
- **Registration OK:** 1534
- **Transport measured (both arms attempted):** 1534
- **Gold SQL used for transport (fallback):** 0
- **NL2SQL errors:** 0
- **Strict exec failures (no row):** 0
- **Frozen SQL missing (jsonl key):** 0
- **sql_source counts:** {'gold': 1534}
- **SQL source:** gold
- **Frozen SQL file:** None
- **Arms:** both
- **Allow gold fallback:** False
- **With summary LLM:** False
- **Format select target:** min_latency
- **MCP URL:** http://localhost:8000/mcp/mcp

## Latency (seconds, median / p95 where noted)

| Stage | Median | p95 |
|---|---:|---:|
| NL2SQL | — | — |
| Baseline fetch (JSON only) | 0.002856 | 0.005801 |
| Describe (enhanced) | 0.002552 | 0.003669 |
| Enhanced fetch (chosen format) | 0.002537 | 0.004667 |
| Enhanced describe + fetch | 0.005154 | 0.008082 |
| `large_result_auto` call (server arm) | — | — |
| Server auto payload fetch / size | — | — |
| Server auto call + payload | — | — |
| `bird_query_run_inline` call (inline arm) | — | — |
| Inline payload fetch / size | — | — |
| Inline call + payload | — | — |
| Optional summary LLM | — | — |

## Payload sizes (bytes)

| | Median | p95 |
|---|---:|---:|
| Baseline JSON | 57 | 11966 |
| Enhanced (chosen format) | 57 | 3774 |

- **Queries with equal baseline vs enhanced bytes:** 1413
- **Queries where enhanced payload is smaller than baseline:** 121
- **Queries where baseline is smaller than enhanced:** 0
- **Sum of baseline bytes (all successful transport rows):** 43442403
- **Sum of enhanced bytes (same):** 6420236

## Ratios (median)

| baseline_fetch_s / enhanced_fetch_s | 1.081641 |
| baseline_bytes / enhanced_bytes | 1 |

## Recommended format (enhanced arm)

- `json`: 1413
- `parquet_blob`: 121

## Example LLM summaries (first records with summary data)

## Caching and measurement fairness

- **Materialized hints + payload cache (round-2):** for `POST /materialized` and `bird_query_materialize`/`bird_query_run_inline` results, both size hints AND the materialized DataFrame, Arrow table, JSON records (small payloads), and encoded Parquet/Arrow IPC bytes are pre-computed at registration (`ResultConfig.cached_*` fields in `server_app.py`), so `describe_result_formats`, `large_result_auto`, `large_json`, and the parquet/IPC HTTP blob endpoints all avoid re-reading Parquet and re-encoding on the hot path. The cache is bounded by `RESULT_CACHE_MAX_BYTES` (default 64 MB). Synthetic (no `result_id`) LRU caches still apply only when `describe_result_formats` is called without a materialized `result_id`.
- **JSON-Schema validation backend (round-2):** the python-sdk client/server now picks the fastest available validator at import: `MCP_VALIDATOR_BACKEND={auto|jsonschema-rs|fastjsonschema|jsonschema|skip}` (or `MCP_SKIP_VALIDATE=1` for the no-op fast path). Default `auto` prefers `jsonschema-rs` then `fastjsonschema` then `jsonschema`. See `mcp.shared._validation`.
- **HTTP keep-alive** (httpx) may shave a small amount off repeated localhost RPCs; arms share the same session per query, so relative comparison on the **same** `result_id` remains meaningful.
- **SQLite / OS page cache** can speed up repeated access to the same DB file across queries; absolute SQL times are “warm-ish” after the first touch on a given database.
- **Ollama** may reuse KV cache for similar prompt prefixes; NL2SQL prompts share a template, so later queries might be slightly faster. Report the model name and note whether the daemon was restarted between experiments if you need stricter cold behavior.
