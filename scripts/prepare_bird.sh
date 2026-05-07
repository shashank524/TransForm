#!/usr/bin/env bash
# Download and prepare the BIRD dev split for materialized benchmarks.
#
# Usage:
#   bash scripts/prepare_bird.sh [TARGET_DIR]
#
# After running, start the server and benchmark with:
#   uvicorn server_app:app --reload
#   python bench_nl2sql_materialized.py --dataset bird --data-dir data/datasets/bird/dev
set -euo pipefail

TARGET_DIR="${1:-data/datasets/bird}"
DEV_DIR="$TARGET_DIR/dev"

if [ -d "$DEV_DIR" ] && [ -f "$DEV_DIR/dev.json" ]; then
    echo "BIRD dev split already present at $DEV_DIR — skipping download."
    exit 0
fi

mkdir -p "$TARGET_DIR"

echo "==> Downloading BIRD dev databases + questions..."
echo ""
echo "BIRD requires manual download from https://bird-bench.github.io/"
echo "Please download the following and extract to $DEV_DIR:"
echo "  1. dev.json           (questions + SQL)"
echo "  2. dev_databases/     (SQLite databases per db_id)"
echo ""
echo "Alternatively, if a community mirror URL is available, set BIRD_DEV_URL:"
echo "  BIRD_DEV_URL=https://... bash scripts/prepare_bird.sh"
echo ""

if [ -n "${BIRD_DEV_URL:-}" ]; then
    echo "Downloading from BIRD_DEV_URL=$BIRD_DEV_URL ..."
    mkdir -p "$DEV_DIR"
    curl -L "$BIRD_DEV_URL" -o "$TARGET_DIR/bird_dev.zip"
    unzip -o "$TARGET_DIR/bird_dev.zip" -d "$DEV_DIR"
    rm -f "$TARGET_DIR/bird_dev.zip"
    echo "Done. Contents:"
    ls "$DEV_DIR"
else
    echo "No BIRD_DEV_URL set. After manual download, ensure this layout:"
    echo "  $DEV_DIR/dev.json"
    echo "  $DEV_DIR/dev_databases/<db_id>/<db_id>.sqlite"
    exit 1
fi
