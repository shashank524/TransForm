#!/usr/bin/env bash
# Download and prepare Spider 1.0 for materialized benchmarks.
#
# Usage:
#   bash scripts/prepare_spider.sh [TARGET_DIR]
#
# After running, start the server and benchmark with:
#   uvicorn server_app:app --reload
#   python bench_nl2sql_materialized.py --dataset spider --data-dir data/datasets/spider
set -euo pipefail

TARGET_DIR="${1:-data/datasets/spider}"

if [ -d "$TARGET_DIR/database" ] && [ -f "$TARGET_DIR/dev.json" ]; then
    echo "Spider 1.0 already present at $TARGET_DIR — skipping download."
    exit 0
fi

mkdir -p "$TARGET_DIR"

SPIDER_URL="${SPIDER_URL:-https://drive.usercontent.google.com/download?id=1iRDVHLr6THDbL-p_8CN-RVKGsELBh3FK&confirm=t}"

echo "==> Downloading Spider 1.0..."
echo "If the default Google Drive URL fails, set SPIDER_URL manually:"
echo "  SPIDER_URL=https://... bash scripts/prepare_spider.sh"
echo ""
echo "You can also download manually from https://yale-lily.github.io/spider"
echo "and extract to $TARGET_DIR with the layout:"
echo "  $TARGET_DIR/dev.json"
echo "  $TARGET_DIR/database/<db_id>/<db_id>.sqlite"
echo ""

curl -L "$SPIDER_URL" -o "$TARGET_DIR/spider.zip" || {
    echo "Download failed. Please download Spider 1.0 manually."
    exit 1
}

echo "==> Extracting..."
unzip -o "$TARGET_DIR/spider.zip" -d "$TARGET_DIR/_tmp"
# Spider zip typically contains a top-level spider/ directory
if [ -d "$TARGET_DIR/_tmp/spider" ]; then
    cp -r "$TARGET_DIR/_tmp/spider/"* "$TARGET_DIR/"
else
    cp -r "$TARGET_DIR/_tmp/"* "$TARGET_DIR/"
fi
rm -rf "$TARGET_DIR/_tmp" "$TARGET_DIR/spider.zip"

echo "Done. Contents:"
ls "$TARGET_DIR"
