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
- **Arms:** server
- **Allow gold fallback:** False
- **With summary LLM:** False
- **Format select target:** min_latency
- **MCP URL:** http://localhost:8000/mcp/mcp

## Latency (seconds, median / p95 where noted)

| Stage | Median | p95 |
|---|---:|---:|
| NL2SQL | — | — |
| Baseline fetch (JSON only) | — | — |
| Describe (enhanced) | — | — |
| Enhanced fetch (chosen format) | — | — |
| Enhanced describe + fetch | — | — |
| `large_result_auto` call (server arm) | 0.004999 | 0.035063 |
| Server auto payload fetch / size | 0.000009 | 0.00233 |
| Server auto call + payload | 0.005208 | 0.036261 |
| Optional summary LLM | — | — |

## Payload sizes (bytes)

| | Median | p95 |
|---|---:|---:|
| Baseline JSON | — | — |
| Enhanced (chosen format) | — | — |

- **Queries with equal baseline vs enhanced bytes:** 0
- **Queries where enhanced payload is smaller than baseline:** 0
- **Queries where baseline is smaller than enhanced:** 0
- **Sum of baseline bytes (all successful transport rows):** 0
- **Sum of enhanced bytes (same):** 0

## Ratios (median)

| baseline_fetch_s / enhanced_fetch_s | — |
| baseline_bytes / enhanced_bytes | — |

## Recommended format (enhanced arm)


## Chosen format (server arm, `large_result_auto`)

- `json`: 1413
- `parquet_blob`: 121

- **Median payload bytes (after call):** 45

## Example LLM summaries (first records with summary data)

## Caching and measurement fairness

- **Materialized hints:** for `POST /materialized` results, size hints for the default codec / `rows_per_chunk` are pre-computed at registration (`ResultConfig.cached_hints` in `server_app.py`), so `describe_result_formats` / `large_result_auto` avoid re-reading Parquet and skip SQLite `HintStore` on the hot path. The synthetic (no `result_id`) LRU caches in `server_app.py` still apply only when `describe_result_formats` is called without a materialized `result_id`.
- **HTTP keep-alive** (httpx) may shave a small amount off repeated localhost RPCs; baseline and enhanced runs share the same session per query, so relative comparison on the **same** `result_id` remains meaningful.
- **SQLite / OS page cache** can speed up repeated access to the same DB file across queries; absolute SQL times are “warm-ish” after the first touch on a given database.
- **Ollama** may reuse KV cache for similar prompt prefixes; NL2SQL prompts share a template, so later queries might be slightly faster. Report the model name and note whether the daemon was restarted between experiments if you need stricter cold behavior.
