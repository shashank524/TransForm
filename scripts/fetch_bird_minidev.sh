#!/usr/bin/env bash
# Download official BIRD mini-dev zip (~760 MB) with real SQLite databases.
# Extracts to: data/datasets/bird/minidev/MINIDEV/...
# bench_nl2sql_materialized.py resolves: <bird>/minidev/MINIDEV/dev_databases/<db_id>/<db_id>.sqlite
#
# Upstream: https://github.com/bird-bench/mini_dev (data links in README / llm/mini_dev_data)
#
# Usage:
#   bash scripts/fetch_bird_minidev.sh [BIRD_DATA_ROOT]
#
# BIRD_DATA_ROOT defaults to data/datasets/bird
set -euo pipefail

ROOT="${1:-data/datasets/bird}"
mkdir -p "$ROOT/_downloads"
ZIP="$ROOT/_downloads/minidev.zip"
URL="${BIRD_MINIDEV_URL:-https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip}"

echo "==> Downloading mini-dev (SQLite DBs) from $URL"
curl -fL -o "$ZIP" "$URL"

echo "==> Extracting under $ROOT/ (creates minidev/MINIDEV/)"
# Zip root is minidev/MINIDEV/... — extract next to dev/
unzip -q -o "$ZIP" -d "$ROOT"
echo "==> Done. Example DB: $ROOT/minidev/MINIDEV/dev_databases/debit_card_specializing/debit_card_specializing.sqlite"
echo "==> Run: python bench_nl2sql_materialized.py --dataset bird --data-dir $ROOT/dev --bird-questions mini_dev_sqlite.json"
