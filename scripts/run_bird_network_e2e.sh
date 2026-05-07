#!/usr/bin/env sh
# Apply tc profile then run full BIRD server-exec E2E (used from Docker client).
set -eu
PROFILE="${1:?Usage: $0 <LAN|WAN|Cellular|BadWifi> <results.jsonl> [extra bench args...]}"
RESULTS="${2:?results jsonl path}"
shift 2
# tc_apply.sh overwrites the shell variable PROFILE when sourced; keep CLI intent for JSONL headers.
CLI_PROFILE="$PROFILE"
MAXQ="${BENCH_MAX_QUERIES:-0}"
# Optional: set BENCH_REUSE_MATERIALIZED_FOR_AUTO=1 to avoid double SQL exec in server_auto arm
# (more reliable than extra CLI args under some docker compose invocations)
REUSE_FLAG=""
if [ "${BENCH_REUSE_MATERIALIZED_FOR_AUTO:-}" = "1" ]; then
  REUSE_FLAG="--reuse-materialized-for-auto"
fi
# Source so TC_* exports remain for Python JSONL headers.
# Export NET_PROFILE before sourcing: dotted scripts do not always receive $1 reliably under sh -c.
export NET_PROFILE="$CLI_PROFILE"
. ./scripts/tc_apply.sh
export NET_PROFILE="$CLI_PROFILE"
exec python bench_bird_server_exec_e2e.py \
  --data-dir /data/bird/dev \
  --bird-questions dev.json \
  --max-queries "$MAXQ" \
  --prefer-streaming \
  --targets min_time_to_first_rows \
  --rows-per-chunk-list 8192 \
  --mcp-url "${MCP_URL:-http://server:8000/mcp/mcp}" \
  --server-url "${SERVER_URL:-http://server:8000}" \
  --results "$RESULTS" \
  --overwrite \
  $REUSE_FLAG \
  "$@"
