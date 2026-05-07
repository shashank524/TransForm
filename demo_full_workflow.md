# Full Workflow Demo (for Professor)

## What This Project Shows

1. **MCP as control plane** – Tool calls over MCP return a *descriptor* (e.g. URL), not the full table.
2. **Parquet as data plane** – Large results are fetched via HTTP (blob or stream) in Parquet format.
3. **LLM in the loop** – Ollama (Llama 3.2) chooses the format and summarizes the result; full pipeline is: LLM → MCP → data fetch → LLM.

## Quick Demo (3 terminals)

### Terminal 1: Start server (TPC-DS data)
```bash
cd /Users/shashank/Documents/ChunweiLiuPapers/MultiModalMCP
export TPCDS_PARQUET_PATH="$PWD/data/tpcds_catalog_sales_sf1.parquet"
.venv/bin/uvicorn server_app:app --host 127.0.0.1 --port 8000
```

### Terminal 2: Start Ollama (if not running)
```bash
ollama run llama3.2
```

### Terminal 3: Run full workflow
```bash
cd /Users/shashank/Documents/ChunweiLiuPapers/MultiModalMCP
.venv/bin/python run_workflow.py
```

**Point out in the output:**
- "LLM backend: ollama" → we use a local LLM.
- "Using mode: parquet_blob" (or json/parquet_stream) → **LLM chose** the format.
- "Parquet blob: 10000 rows, 262056 bytes" → **data delivered** via Parquet, not inline JSON.
- "LLM summary: ..." → **full loop** (LLM → MCP → data → LLM) completed.

## What to Show on Paper / Screen

1. **Summary document:** `results/BENCHMARK_SUMMARY.md` – setup, workflow, results table, and note that smaller times are for smaller data (1k vs 10k), not JSON faster than Parquet.
2. **Optional:** Saved micro-benchmark output – `python bench.py` – to show JSON vs Parquet on the *same* table size (Parquet much faster and smaller).

## One-Line Pitch

"We have a full workflow: the LLM decides whether to request JSON or Parquet (blob/stream), the MCP server returns a descriptor, the client fetches the data over HTTP, and the LLM summarizes the result—all on TPC-DS data with Ollama."
