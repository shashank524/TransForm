#!/usr/bin/env sh
# Apply tc then run structured vs unstructured benchmark (Docker client).
set -eu
PROFILE="${1:?Usage: $0 <LAN|WAN|Cellular|BadWifi> <results.jsonl>}"
RESULTS="${2:?results jsonl path}"
export NET_PROFILE="$PROFILE"
. ./scripts/tc_apply.sh "$PROFILE"
exec python bench_structured_vs_unstructured.py \
  --mcp-url "${MCP_URL:-http://server:8000/mcp/mcp}" \
  --server-url "${SERVER_URL:-http://server:8000}" \
  --results "$RESULTS" \
  --overwrite \
  --prefer-streaming
