# BIRD end-to-end benchmark summary

## Run configuration

- **Query records:** 500
- **Exec OK:** 500
- **Registration OK:** 500
- **Transport measured (both arms attempted):** 500
- **Gold SQL used for transport (fallback):** 0
- **NL2SQL errors:** 0
- **Strict exec failures (no row):** 0
- **Frozen SQL missing (jsonl key):** 0
- **sql_source counts:** {'jsonl': 500}
- **SQL source:** jsonl
- **Frozen SQL file:** /Users/shashank/Documents/ChunweiLiuPapers/MultiModalMCP/results/bird_mini_dev_frozen.jsonl
- **Arms:** both
- **Allow gold fallback:** False
- **With summary LLM:** False
- **Format select target:** min_latency
- **MCP URL:** http://localhost:8000/mcp/mcp

## Latency (seconds, median / p95 where noted)

| Stage | Median | p95 |
|---|---:|---:|
| NL2SQL | — | — |
| Baseline fetch (JSON only) | 0.006307 | 0.042368 |
| Describe (enhanced) | 0.005501 | — |
| Enhanced fetch (chosen format) | 0.006481 | 0.024482 |
| Enhanced describe + fetch | 0.012159 | — |
| Optional summary LLM | — | — |

## Payload sizes (bytes, median)

| Baseline JSON bytes | 78 |
| Enhanced chosen-format bytes | 78 |

## Ratios (median)

| baseline_fetch_s / enhanced_fetch_s | 1.023898 |
| baseline_bytes / enhanced_bytes | 1 |

## Recommended format (enhanced arm)

- `json`: 458
- `parquet_blob`: 42

## Example LLM summaries (first records with summary data)

## Caching and measurement fairness

- **Server LRU** (`_get_json_byte_size`, `_get_parquet_blob_bytes`, … in `server_app.py`) applies only when `describe_result_formats` is called **without** a materialized `result_id`. This benchmark passes `result_id`, so hints are computed from the registered Parquet each time; those caches do not shorten describe latency for BIRD materialized results.
- **HTTP keep-alive** (httpx) may shave a small amount off repeated localhost RPCs; baseline and enhanced runs share the same session per query, so relative comparison on the **same** `result_id` remains meaningful.
- **SQLite / OS page cache** can speed up repeated access to the same DB file across queries; absolute SQL times are “warm-ish” after the first touch on a given database.
- **Ollama** may reuse KV cache for similar prompt prefixes; NL2SQL prompts share a template, so later queries might be slightly faster. Report the model name and note whether the daemon was restarted between experiments if you need stricter cold behavior.
