"""Aggregate per-request server profiles by inferred tool/route name.

Reads every `*.speedscope.json` written by the pyinstrument middleware,
groups them by the trailing tool/route name (encoded in the file name by
`PyinstrumentMiddleware`), and prints count + total/median duration per group.

Usage:
    .venv/bin/python profile_aggregate_server.py [profile_dir ...]
    # default: results/profiling/server and results/profiling/server_baseline
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path


_UUID_RE = re.compile(
    r"[_-][0-9a-f]{8}[_-][0-9a-f]{4}[_-][0-9a-f]{4}[_-][0-9a-f]{4}[_-][0-9a-f]{12}"
)


def _label(stem: str) -> str:
    """File names look like '00110_POST_mcp_mcp_describe_result_formats'.

    HTTP blob/IPC paths embed a result_id UUID — strip it so files for
    different result_ids aggregate under a single label.
    """
    m = re.match(r"\d+_(?P<method>[A-Z]+)_(?P<rest>.+)$", stem)
    if not m:
        return stem
    rest = m.group("rest")
    if rest.startswith("mcp_mcp_"):
        rest = rest[len("mcp_mcp_"):]
    rest = _UUID_RE.sub("_<id>", rest)
    rest = rest.replace(".speedscope", "")
    return rest


def _duration_s(path: Path) -> float | None:
    try:
        d = json.loads(path.read_text())
        prof = d["profiles"][0]
        return float(prof["endValue"]) - float(prof["startValue"])
    except Exception:
        return None


def main() -> None:
    dirs = [Path(p) for p in sys.argv[1:]] or [
        Path("results/profiling/server"),
        Path("results/profiling/server_baseline"),
        Path("results/profiling/server_run_server"),
    ]
    for d in dirs:
        if not d.is_dir():
            print(f"== {d} : (missing)")
            continue
        groups: dict[str, list[float]] = defaultdict(list)
        for p in sorted(d.glob("*.speedscope.json")):
            dur = _duration_s(p)
            if dur is None:
                continue
            groups[_label(p.stem)].append(dur)
        print(f"\n== {d} ==")
        rows = []
        for label, vals in groups.items():
            rows.append((label, len(vals), statistics.median(vals) * 1000.0,
                         max(vals) * 1000.0, sum(vals) * 1000.0))
        rows.sort(key=lambda r: -r[4])
        print(f"{'route/tool':45s} {'count':>6s} {'median_ms':>10s} {'max_ms':>10s} {'total_ms':>10s}")
        for r in rows:
            print(f"{r[0]:45s} {r[1]:6d} {r[2]:10.2f} {r[3]:10.2f} {r[4]:10.2f}")


if __name__ == "__main__":
    main()
