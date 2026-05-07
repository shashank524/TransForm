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
| Baseline fetch (JSON only) | 0.005694 | 0.043281 |
| Describe (enhanced) | 0.004793 | — |
| Enhanced fetch (chosen format) | 0.00539 | 0.014991 |
| Enhanced describe + fetch | 0.010297 | — |
| Optional summary LLM | — | — |

## Payload sizes (bytes)

| | Median | p95 |
|---|---:|---:|
| Baseline JSON | 57 | 11966 |
| Enhanced (chosen format) | 57 | 3650 |

- **Queries with equal baseline vs enhanced bytes:** 1370
- **Queries where enhanced payload is smaller than baseline:** 164
- **Queries where baseline is smaller than enhanced:** 0
- **Sum of baseline bytes (all successful transport rows):** 43439928
- **Sum of enhanced bytes (same):** 6386514

## Ratios (median)

| baseline_fetch_s / enhanced_fetch_s | 1.070704 |
| baseline_bytes / enhanced_bytes | 1 |

## Recommended format (enhanced arm)

- `json`: 1370
- `parquet_blob`: 164

## Example LLM summaries (first records with summary data)

## Caching and measurement fairness

- **Server LRU** (`_get_json_byte_size`, `_get_parquet_blob_bytes`, … in `server_app.py`) applies only when `describe_result_formats` is called **without** a materialized `result_id`. This benchmark passes `result_id`, so hints are computed from the registered Parquet each time; those caches do not shorten describe latency for BIRD materialized results.
- **HTTP keep-alive** (httpx) may shave a small amount off repeated localhost RPCs; baseline and enhanced runs share the same session per query, so relative comparison on the **same** `result_id` remains meaningful.
- **SQLite / OS page cache** can speed up repeated access to the same DB file across queries; absolute SQL times are “warm-ish” after the first touch on a given database.
- **Ollama** may reuse KV cache for similar prompt prefixes; NL2SQL prompts share a template, so later queries might be slightly faster. Report the model name and note whether the daemon was restarted between experiments if you need stricter cold behavior.
