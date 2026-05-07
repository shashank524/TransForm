#!/usr/bin/env sh
# Structured vs unstructured × four tc profiles.
set -eu
cd "$(dirname "$0")/.."
for p in LAN WAN Cellular BadWifi; do
  out="results/structured_vs_unstructured_network_$(echo "$p" | tr '[:upper:]' '[:lower:]').jsonl"
  echo "=== structured vs unstructured profile=$p -> $out ==="
  docker compose run --rm --entrypoint "" \
    -e MCP_URL=http://server:8000/mcp/mcp \
    -e SERVER_URL=http://server:8000 \
    client \
    /app/scripts/run_structured_vs_unstructured_network.sh "$p" "$out"
done
echo "All structured vs unstructured runs complete."
