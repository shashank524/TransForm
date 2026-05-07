#!/usr/bin/env bash
# Download and prepare WikiSQL for materialized benchmarks.
#
# Usage:
#   bash scripts/prepare_wikisql.sh [TARGET_DIR]
#
# After running, start the server and benchmark with:
#   uvicorn server_app:app --reload
#   python bench_nl2sql_materialized.py --dataset wikisql --data-dir data/datasets/wikisql
set -euo pipefail

TARGET_DIR="${1:-data/datasets/wikisql}"

if [ -f "$TARGET_DIR/dev.jsonl" ] && [ -f "$TARGET_DIR/dev.tables.jsonl" ]; then
    echo "WikiSQL already present at $TARGET_DIR — skipping download."
    exit 0
fi

mkdir -p "$TARGET_DIR"

WIKISQL_URL="${WIKISQL_URL:-https://github.com/salesforce/WikiSQL/raw/master/data.tar.bz2}"

echo "==> Downloading WikiSQL data archive..."
curl -L "$WIKISQL_URL" -o "$TARGET_DIR/data.tar.bz2" || {
    echo "Download failed. Get the archive manually from:"
    echo "  https://github.com/salesforce/WikiSQL"
    exit 1
}

echo "==> Extracting..."
tar -xjf "$TARGET_DIR/data.tar.bz2" -C "$TARGET_DIR"
# Archive usually extracts into a data/ subdirectory
if [ -d "$TARGET_DIR/data" ]; then
    mv "$TARGET_DIR/data/"* "$TARGET_DIR/" 2>/dev/null || true
    rmdir "$TARGET_DIR/data" 2>/dev/null || true
fi
rm -f "$TARGET_DIR/data.tar.bz2"

echo "Done. Contents:"
ls "$TARGET_DIR"
echo ""
echo "Per-table SQLite DBs will be built on-the-fly by the benchmark runner"
echo "under $TARGET_DIR/wikisql_tmp/."
