"""
TPC-DS format-hint benchmark runner (catalog_sales).

Emits a reference table of per-format bytes and encode/decode timings for:
  - JSON (records)
  - Parquet blob (with PARQUET_COMPRESSION + PARQUET_ENCODING_STRATEGY)
  - Arrow IPC file blob (with ARROW_IPC_COMPRESSION)
  - Stream first-chunk bytes (Parquet + Arrow IPC) for a fixed rows_per_chunk

Optionally upserts the computed hint dict into results/format_hints.sqlite via HintStore.

Usage:
  python bench_tpcds_format_hints.py
  python bench_tpcds_format_hints.py --tpcds data/tpcds_catalog_sales_sf1.parquet
  python bench_tpcds_format_hints.py --write-sqlite
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass, asdict
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import pyarrow as pa
import pyarrow.ipc as ipc
import pyarrow.parquet as pq

from codec_selector import select_encoding_params
from hint_reference_table import HintStore

RESULTS_DIR = Path("results")

TPCDS_ROW_SIZES = [10_000, 100_000, 500_000]
TPCDS_COL_SIZES = [6, 20, 34]


def _get_env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _get_parquet_compression() -> str:
    return _get_env("PARQUET_COMPRESSION", "snappy").lower()


def _get_parquet_encoding_strategy() -> str:
    # Paper decision: default to data_driven unless explicitly overridden.
    return _get_env("PARQUET_ENCODING_STRATEGY", "data_driven").lower()


def _get_arrow_ipc_compression() -> str:
    return _get_env("ARROW_IPC_COMPRESSION", "none").lower()


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        import decimal

        if isinstance(o, decimal.Decimal):
            return float(o)
        return super().default(o)


def _slice_df(base_df: pd.DataFrame, n_rows: int, n_cols: int) -> pd.DataFrame:
    df = base_df.iloc[:n_rows].copy()
    cols = list(df.columns)[:n_cols]
    return df[cols]


def _encode_json_records(df: pd.DataFrame) -> tuple[bytes, float]:
    records = df.to_dict(orient="records")
    t0 = time.perf_counter()
    raw = json.dumps(records, cls=_DecimalEncoder).encode("utf-8")
    return raw, time.perf_counter() - t0


def _decode_json_records(raw: bytes) -> float:
    t0 = time.perf_counter()
    _ = json.loads(raw.decode("utf-8"))
    return time.perf_counter() - t0


def _encode_parquet(table: pa.Table, compression: str, encoding_strategy: str) -> tuple[bytes, float]:
    buf = BytesIO()
    write_kwargs: Dict[str, Any] = {"compression": compression}
    if encoding_strategy == "data_driven":
        params = select_encoding_params(table)
        dict_cols = params.get("use_dictionary", [])
        col_enc = params.get("column_encoding")
        write_kwargs["use_dictionary"] = dict_cols
        if col_enc:
            write_kwargs["column_encoding"] = col_enc
    t0 = time.perf_counter()
    pq.write_table(table, buf, **write_kwargs)
    return buf.getvalue(), time.perf_counter() - t0


def _decode_parquet(raw: bytes) -> float:
    t0 = time.perf_counter()
    _ = pq.read_table(BytesIO(raw))
    return time.perf_counter() - t0


def _encode_arrow_ipc_file(table: pa.Table, ipc_compression: str) -> tuple[bytes, float]:
    opts = pa.ipc.IpcWriteOptions(compression=ipc_compression) if ipc_compression != "none" else pa.ipc.IpcWriteOptions()
    sink = pa.BufferOutputStream()
    t0 = time.perf_counter()
    with ipc.new_file(sink, table.schema, options=opts) as writer:
        writer.write_table(table)
    return sink.getvalue().to_pybytes(), time.perf_counter() - t0


def _decode_arrow_ipc_file(raw: bytes) -> float:
    t0 = time.perf_counter()
    reader = ipc.open_file(pa.BufferReader(raw))
    _ = reader.read_all()
    return time.perf_counter() - t0


@dataclass
class SliceHintRecord:
    dataset: str
    source_path: str
    n_rows: int
    n_cols: int
    rows_per_chunk: int
    parquet_compression: str
    parquet_encoding_strategy: str
    arrow_ipc_compression: str
    json_bytes: int
    parquet_bytes: int
    arrow_ipc_bytes: int
    parquet_stream_first_chunk_bytes: int
    arrow_ipc_stream_first_chunk_bytes: int
    json_encode_s: float
    json_decode_s: float
    parquet_encode_s: float
    parquet_decode_s: float
    arrow_ipc_encode_s: float
    arrow_ipc_decode_s: float


def bench_one_slice(
    base_df: pd.DataFrame,
    *,
    source_path: Path,
    n_rows: int,
    n_cols: int,
    rows_per_chunk: int,
    dataset: str = "tpcds_catalog_sales",
) -> SliceHintRecord:
    comp = _get_parquet_compression()
    enc = _get_parquet_encoding_strategy()
    ipc_comp = _get_arrow_ipc_compression()

    df = _slice_df(base_df, n_rows, n_cols)
    table = pa.Table.from_pandas(df, preserve_index=False)

    json_raw, json_enc_s = _encode_json_records(df)
    json_dec_s = _decode_json_records(json_raw)

    pq_raw, pq_enc_s = _encode_parquet(table, comp, enc)
    pq_dec_s = _decode_parquet(pq_raw)

    ipc_raw, ipc_enc_s = _encode_arrow_ipc_file(table, ipc_comp)
    ipc_dec_s = _decode_arrow_ipc_file(ipc_raw)

    # First-chunk (stream proxy): encode first rows_per_chunk rows as a chunk/file.
    chunk_rows = min(rows_per_chunk, max(1, len(df)))
    df_fc = df.iloc[:chunk_rows].copy()
    tbl_fc = pa.Table.from_pandas(df_fc, preserve_index=False)
    pq_fc, _ = _encode_parquet(tbl_fc, comp, enc)
    ipc_fc, _ = _encode_arrow_ipc_file(tbl_fc, ipc_comp)

    return SliceHintRecord(
        dataset=dataset,
        source_path=str(source_path),
        n_rows=int(len(df)),
        n_cols=int(len(df.columns)),
        rows_per_chunk=int(rows_per_chunk),
        parquet_compression=comp,
        parquet_encoding_strategy=enc,
        arrow_ipc_compression=ipc_comp,
        json_bytes=len(json_raw),
        parquet_bytes=len(pq_raw),
        arrow_ipc_bytes=len(ipc_raw),
        parquet_stream_first_chunk_bytes=len(pq_fc),
        arrow_ipc_stream_first_chunk_bytes=len(ipc_fc),
        json_encode_s=float(json_enc_s),
        json_decode_s=float(json_dec_s),
        parquet_encode_s=float(pq_enc_s),
        parquet_decode_s=float(pq_dec_s),
        arrow_ipc_encode_s=float(ipc_enc_s),
        arrow_ipc_decode_s=float(ipc_dec_s),
    )


def to_hint_dict(r: SliceHintRecord) -> Dict[str, Any]:
    # Mirror the server's tabular hints shape where possible.
    return {
        "resolved_n_rows": r.n_rows,
        "resolved_n_cols": r.n_cols,
        "json_bytes": r.json_bytes,
        "parquet_bytes": r.parquet_bytes,
        "arrow_ipc_bytes": r.arrow_ipc_bytes,
        "parquet_stream_first_chunk_bytes": r.parquet_stream_first_chunk_bytes,
        "arrow_ipc_stream_first_chunk_bytes": r.arrow_ipc_stream_first_chunk_bytes,
        "parquet_compression": r.parquet_compression,
        "parquet_encoding_strategy": r.parquet_encoding_strategy,
        "arrow_ipc_compression": r.arrow_ipc_compression,
        "bench": {
            "json_encode_s": r.json_encode_s,
            "json_decode_s": r.json_decode_s,
            "parquet_encode_s": r.parquet_encode_s,
            "parquet_decode_s": r.parquet_decode_s,
            "arrow_ipc_encode_s": r.arrow_ipc_encode_s,
            "arrow_ipc_decode_s": r.arrow_ipc_decode_s,
        },
    }


def write_md(rows: List[SliceHintRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# TPC-DS format hint reference table (catalog_sales)",
        "",
        f"- Source: `{rows[0].source_path}`" if rows else "- Source: (none)",
        f"- PARQUET_COMPRESSION: `{_get_parquet_compression()}`",
        f"- PARQUET_ENCODING_STRATEGY: `{_get_parquet_encoding_strategy()}`",
        f"- ARROW_IPC_COMPRESSION: `{_get_arrow_ipc_compression()}`",
        "",
        "| n_rows | n_cols | json B | parquet B | arrow_ipc B | pq_fc B | ipc_fc B | json enc s | pq enc s | ipc enc s |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r.n_rows:,} | {r.n_cols} | {r.json_bytes:,} | {r.parquet_bytes:,} | {r.arrow_ipc_bytes:,} | "
            f"{r.parquet_stream_first_chunk_bytes:,} | {r.arrow_ipc_stream_first_chunk_bytes:,} | "
            f"{r.json_encode_s:.4f} | {r.parquet_encode_s:.4f} | {r.arrow_ipc_encode_s:.4f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="TPC-DS format hint benchmark")
    ap.add_argument("--tpcds", type=Path, default=Path("data/tpcds_catalog_sales_sf1.parquet"))
    ap.add_argument("--rows-per-chunk", type=int, default=8192)
    ap.add_argument("--write-sqlite", action="store_true", help="Upsert each hint row into results/format_hints.sqlite")
    ap.add_argument("--out-json", type=Path, default=RESULTS_DIR / "tpcds_format_hints.json")
    ap.add_argument("--out-md", type=Path, default=RESULTS_DIR / "tpcds_format_hints.md")
    args = ap.parse_args()

    tpcds_path: Path = args.tpcds.resolve()
    if not tpcds_path.is_file():
        raise FileNotFoundError(f"TPC-DS Parquet not found: {tpcds_path}")

    print(f"Loading TPC-DS from {tpcds_path} ...")
    base_df = pd.read_parquet(tpcds_path)
    print(f"Loaded {len(base_df):,} rows, {len(base_df.columns)} cols")

    out: List[SliceHintRecord] = []
    for n_rows in TPCDS_ROW_SIZES:
        for n_cols in TPCDS_COL_SIZES:
            df = _slice_df(base_df, n_rows, n_cols)
            if df.empty:
                continue
            r = bench_one_slice(
                base_df,
                source_path=tpcds_path,
                n_rows=n_rows,
                n_cols=n_cols,
                rows_per_chunk=args.rows_per_chunk,
            )
            out.append(r)
            print(
                f"slice rows={r.n_rows:,} cols={r.n_cols} "
                f"json={r.json_bytes:,}B pq={r.parquet_bytes:,}B ipc={r.arrow_ipc_bytes:,}B"
            )

            if args.write_sqlite:
                store = HintStore.default()
                key = {
                    "dataset": r.dataset,
                    "source_path": str(tpcds_path),
                    "n_rows": r.n_rows,
                    "n_cols": r.n_cols,
                    "rows_per_chunk": r.rows_per_chunk,
                    "parquet_compression": r.parquet_compression,
                    "parquet_encoding_strategy": r.parquet_encoding_strategy,
                    "arrow_ipc_compression": r.arrow_ipc_compression,
                }
                store.upsert(key, to_hint_dict(r))

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps([asdict(r) for r in out], indent=2), encoding="utf-8")
    write_md(out, args.out_md)
    print(f"Wrote {args.out_md} and {args.out_json}")


if __name__ == "__main__":
    main()

