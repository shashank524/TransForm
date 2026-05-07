"""
Codec and encoding-strategy ablation benchmark (standalone, no server needed).

Compares Parquet compression codecs (snappy, gzip, zstd, none) and encoding
strategies (default vs data_driven) on the same data grid used by bench.py.
Also includes a JSON baseline for reference.

Usage:
    python bench_codec.py                          # synthetic data
    python bench_codec.py --tpcds data/tpcds_catalog_sales.parquet  # real TPC-DS data

Results are written to:
    results/bench_codec_ablation.md          (synthetic)
    results/bench_codec_ablation.json
    results/bench_codec_tpcds.md             (TPC-DS)
    results/bench_codec_tpcds.json
"""

from __future__ import annotations

import argparse
import json
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from codec_selector import compute_column_features, select_encoding_params

RESULTS_DIR = Path(__file__).parent / "results"

ROW_SIZES = [10_000, 100_000]
COL_SIZES = [6, 20]
CODECS = ["snappy", "gzip", "zstd", "none"]
STRATEGIES = ["default", "data_driven"]

TPCDS_ROW_SIZES = [10_000, 100_000, 500_000]
TPCDS_COL_SIZES = [6, 20, 34]


def _generate_dataframe(n_rows: int, n_cols: int) -> pd.DataFrame:
    """Same synthetic data generator as server_app._generate_dataframe."""
    index = np.arange(0, n_rows, dtype=np.int64)
    data: Dict[str, Any] = {"row_id": index}
    for j in range(n_cols):
        data[f"col_{j}"] = index * (j + 1) + j
    return pd.DataFrame(data)


def _load_tpcds_slice(
    base_df: pd.DataFrame, n_rows: int, n_cols: int
) -> pd.DataFrame:
    """Slice TPC-DS base table to (n_rows, n_cols)."""
    df = base_df.iloc[:n_rows].copy()
    cols = list(df.columns)
    if len(cols) > n_cols:
        cols = cols[:n_cols]
    return df[cols]


def _encode_parquet(
    table: pa.Table,
    compression: str,
    encoding_strategy: str,
) -> bytes:
    """Encode Arrow table → Parquet bytes (mirrors server_app._encode_parquet)."""
    buf = BytesIO()
    write_kwargs: Dict[str, Any] = {"compression": compression}

    if encoding_strategy == "data_driven":
        params = select_encoding_params(table)
        dict_cols = params.get("use_dictionary", [])
        col_enc = params.get("column_encoding")
        write_kwargs["use_dictionary"] = dict_cols
        if col_enc:
            write_kwargs["column_encoding"] = col_enc

    pq.write_table(table, buf, **write_kwargs)
    return buf.getvalue()


class _DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types that appear in TPC-DS data."""
    def default(self, o: Any) -> Any:
        import decimal
        if isinstance(o, decimal.Decimal):
            return float(o)
        return super().default(o)


def _run_json_baseline(df: pd.DataFrame) -> Dict[str, Any]:
    records = df.to_dict(orient="records")

    t0 = time.perf_counter()
    raw = json.dumps(records, cls=_DecimalEncoder)
    encode_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    _ = json.loads(raw)
    decode_s = time.perf_counter() - t1

    return {
        "codec": "json",
        "encoding_strategy": "n/a",
        "bytes": len(raw.encode("utf-8")),
        "encode_s": round(encode_s, 6),
        "decode_s": round(decode_s, 6),
    }


def _run_parquet_case(
    table: pa.Table,
    codec: str,
    strategy: str,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    raw = _encode_parquet(table, codec, strategy)
    encode_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    _ = pq.read_table(BytesIO(raw))
    decode_s = time.perf_counter() - t1

    return {
        "codec": codec,
        "encoding_strategy": strategy,
        "bytes": len(raw),
        "encode_s": round(encode_s, 6),
        "decode_s": round(decode_s, 6),
    }


def _features_summary(table: pa.Table) -> str:
    feats = compute_column_features(table)
    n_dict = sum(1 for f in feats.values() if f.get("cardinality_ratio", 1) < 0.3)
    n_sorted = sum(1 for f in feats.values() if f.get("is_sorted"))
    return f"{len(feats)} cols, {n_dict} low-cr, {n_sorted} sorted"


def _run_grid(
    row_sizes: List[int],
    col_sizes: List[int],
    df_loader,
    label: str,
) -> List[Dict[str, Any]]:
    """Run codec × strategy ablation for every (n_rows, n_cols) pair."""
    all_results: List[Dict[str, Any]] = []

    for n_rows in row_sizes:
        for n_cols in col_sizes:
            df = df_loader(n_rows, n_cols)
            actual_rows = len(df)
            actual_cols = len(df.columns)
            if actual_rows == 0:
                print(f"\n=== SKIP n_rows={n_rows}, n_cols={n_cols} (empty) ===")
                continue

            table = pa.Table.from_pandas(df, preserve_index=False)
            feat_summary = _features_summary(table)

            print(
                f"\n=== {label} n_rows={actual_rows:,}, n_cols={actual_cols} "
                f"({feat_summary}) ==="
            )

            json_result = _run_json_baseline(df)
            json_result.update({
                "dataset": label,
                "n_rows": actual_rows,
                "n_cols": actual_cols,
            })
            all_results.append(json_result)
            print(
                f"  json: {json_result['bytes']:>12,} B  "
                f"enc={json_result['encode_s']:.4f}s  "
                f"dec={json_result['decode_s']:.4f}s"
            )

            for codec in CODECS:
                for strategy in STRATEGIES:
                    result = _run_parquet_case(table, codec, strategy)
                    result.update({
                        "dataset": label,
                        "n_rows": actual_rows,
                        "n_cols": actual_cols,
                    })
                    all_results.append(result)
                    print(
                        f"  {codec:>8s}/{strategy:<12s}: "
                        f"{result['bytes']:>12,} B  "
                        f"enc={result['encode_s']:.4f}s  "
                        f"dec={result['decode_s']:.4f}s"
                    )

    return all_results


def _write_results(
    results: List[Dict[str, Any]],
    md_path: Path,
    json_path: Path,
    title: str,
) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    lines = [
        f"# {title}",
        "",
        "Compression codecs: snappy, gzip, zstd, none.  ",
        "Encoding strategies: default (PyArrow defaults), "
        "data_driven (CodecDB-inspired per-column selection).  ",
        "JSON baseline included for reference.",
        "",
        "| dataset | n_rows | n_cols | codec | encoding_strategy | bytes | encode_s | decode_s |",
        "|---------|--------|--------|-------|-------------------|-------|----------|----------|",
    ]
    for r in results:
        lines.append(
            f"| {r.get('dataset','?')} | {r['n_rows']:,} | {r['n_cols']} "
            f"| {r['codec']} | {r['encoding_strategy']} "
            f"| {r['bytes']:,} | {r['encode_s']:.4f} | {r['decode_s']:.4f} |"
        )

    lines.append("")
    lines.append("## Interpretation")
    lines.append("")

    json_rows = [r for r in results if r["codec"] == "json"]
    parquet_rows = [r for r in results if r["codec"] != "json"]

    if json_rows and parquet_rows:
        avg_json_bytes = sum(r["bytes"] for r in json_rows) / len(json_rows)
        avg_pq_bytes = sum(r["bytes"] for r in parquet_rows) / len(parquet_rows)
        ratio = avg_json_bytes / avg_pq_bytes if avg_pq_bytes else 0
        lines.append(
            f"- Average JSON size is {ratio:.1f}x larger than average Parquet size "
            f"across all codec/strategy combinations."
        )

    dd_rows = [r for r in results if r["encoding_strategy"] == "data_driven"]
    def_rows = [
        r for r in results
        if r["encoding_strategy"] == "default" and r["codec"] != "json"
    ]
    if dd_rows and def_rows:
        avg_dd = sum(r["bytes"] for r in dd_rows) / len(dd_rows)
        avg_def = sum(r["bytes"] for r in def_rows) / len(def_rows)
        pct = (1 - avg_dd / avg_def) * 100 if avg_def else 0
        direction = "smaller" if pct > 0 else "larger"
        lines.append(
            f"- data_driven encoding is on average {abs(pct):.1f}% {direction} "
            f"than default encoding (across all codecs)."
        )

    lines.append(
        "- See CodecDB (Jiang et al., SIGMOD '21) and AdaEdge (Liu et al., ICDE '24) "
        "for data-driven and workload-aware compression selection."
    )
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {md_path}")
    print(f"Wrote {json_path}")


def run_synthetic() -> None:
    """Original synthetic-data ablation."""
    results = _run_grid(
        ROW_SIZES,
        COL_SIZES,
        lambda nr, nc: _generate_dataframe(nr, nc),
        label="synthetic",
    )
    _write_results(
        results,
        RESULTS_DIR / "bench_codec_ablation.md",
        RESULTS_DIR / "bench_codec_ablation.json",
        title="Codec & Encoding-Strategy Ablation (Synthetic Data)",
    )


def run_tpcds(parquet_path: str) -> None:
    """TPC-DS ablation using real catalog_sales data."""
    path = Path(parquet_path)
    if not path.is_file():
        raise FileNotFoundError(f"TPC-DS Parquet not found: {path}")

    print(f"Loading TPC-DS data from {path} ...")
    base_df = pd.read_parquet(path)
    total_rows = len(base_df)
    total_cols = len(base_df.columns)
    print(f"Loaded {total_rows:,} rows, {total_cols} columns")
    print(f"Columns: {', '.join(base_df.columns[:10])}{'...' if total_cols > 10 else ''}")

    results = _run_grid(
        TPCDS_ROW_SIZES,
        TPCDS_COL_SIZES,
        lambda nr, nc: _load_tpcds_slice(base_df, nr, nc),
        label="tpcds_catalog_sales",
    )
    _write_results(
        results,
        RESULTS_DIR / "bench_codec_tpcds.md",
        RESULTS_DIR / "bench_codec_tpcds.json",
        title="Codec & Encoding-Strategy Ablation (TPC-DS catalog_sales SF=1)",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Codec ablation benchmark")
    parser.add_argument(
        "--tpcds",
        metavar="PATH",
        help="Path to TPC-DS Parquet file (e.g. data/tpcds_catalog_sales.parquet)",
    )
    parser.add_argument(
        "--synthetic", action="store_true", default=False,
        help="Also run the synthetic-data ablation (default if --tpcds not given)",
    )
    args = parser.parse_args()

    if args.tpcds:
        run_tpcds(args.tpcds)
        if args.synthetic:
            run_synthetic()
    else:
        run_synthetic()


if __name__ == "__main__":
    main()
