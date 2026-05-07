#!/usr/bin/env sh
# Full BIRD dev (1534) × LAN/WAN/Cellular/BadWifi — run from repo root with Docker.
set -eu
cd "$(dirname "$0")/.."
for p in LAN WAN Cellular BadWifi; do
  out="results/bird_server_exec_e2e_network_$(echo "$p" | tr '[:upper:]' '[:lower:]')_capped_ttfr_rpc8192.jsonl"
  echo "=== BIRD E2E profile=$p -> $out ==="
  docker compose run --rm --entrypoint "" \
    -e MCP_URL=http://server:8000/mcp/mcp \
    -e SERVER_URL=http://server:8000 \
    client \
    /app/scripts/run_bird_network_e2e.sh "$p" "$out"
done
echo "All profiles complete."
