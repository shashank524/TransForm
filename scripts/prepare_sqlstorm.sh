#!/usr/bin/env bash
# Download and prepare SQLStorm v1.0 for materialized benchmarks.
#
# SQLStorm queries target PostgreSQL/DuckDB/etc. on StackOverflow, TPC-H,
# and JOB schemas.  For local benchmarks we use DuckDB where possible.
#
# Usage:
#   bash scripts/prepare_sqlstorm.sh [TARGET_DIR]
#
# Set SKIP_SQLSTORM=1 to skip this dataset (default if no DuckDB schema available).
#
# After running, the benchmark runner needs an adapter (not yet integrated):
#   python bench_nl2sql_materialized.py --dataset sqlstorm --data-dir data/datasets/sqlstorm
set -euo pipefail

if [ "${SKIP_SQLSTORM:-0}" = "1" ]; then
    echo "SKIP_SQLSTORM=1 — skipping SQLStorm setup."
    exit 0
fi

TARGET_DIR="${1:-data/datasets/sqlstorm}"

if [ -d "$TARGET_DIR/queries" ]; then
    echo "SQLStorm already present at $TARGET_DIR — skipping download."
    exit 0
fi

mkdir -p "$TARGET_DIR"

SQLSTORM_REPO="https://github.com/SQL-Storm/SQLStorm.git"

echo "==> Cloning SQLStorm repository..."
git clone --depth 1 "$SQLSTORM_REPO" "$TARGET_DIR/repo" || {
    echo "Clone failed. Check network and try again."
    exit 1
}

# Copy relevant query sets to a flat layout
mkdir -p "$TARGET_DIR/queries"
if [ -d "$TARGET_DIR/repo/queries" ]; then
    cp -r "$TARGET_DIR/repo/queries/"* "$TARGET_DIR/queries/"
elif [ -d "$TARGET_DIR/repo/sqlstorm" ]; then
    cp -r "$TARGET_DIR/repo/sqlstorm/"* "$TARGET_DIR/queries/"
fi

echo ""
echo "Done. SQLStorm queries downloaded to $TARGET_DIR/queries."
echo ""
echo "NOTE: SQLStorm targets large-scale engines (PostgreSQL, DuckDB on GB-class data)."
echo "Full integration into bench_nl2sql_materialized.py requires:"
echo "  1. Loading the schema (StackOverflow / TPC-H / JOB) into DuckDB"
echo "  2. Adding an iter_sqlstorm_queries() function to bench_nl2sql_materialized.py"
echo ""
echo "For now, set SKIP_SQLSTORM=1 to skip this dataset in automated runs."
echo "See the repo README for schema creation scripts: $TARGET_DIR/repo/"
