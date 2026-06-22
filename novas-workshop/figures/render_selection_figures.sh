#!/usr/bin/env bash
# Regenerate Figure 2 (selection placement) from Mermaid sources.
set -euo pipefail
cd "$(dirname "$0")"
for name in fig_selection_client_driven fig_selection_transform; do
  mmdc -i "${name}.mmd" -o "${name}.png" -b white -s 3.6
done
python3 << 'PY'
from pathlib import Path
import numpy as np
from PIL import Image

pad = 12
for path in Path(".").glob("fig_selection_*.png"):
    im = Image.open(path).convert("RGB")
    arr = np.array(im)
    mask = (arr < 250).any(axis=2)
    ys, xs = np.where(mask)
    if ys.size == 0:
        continue
    box = (max(xs.min() - pad, 0), max(ys.min() - pad, 0),
           min(xs.max() + pad, im.width - 1), min(ys.max() + pad, im.height - 1))
    im.crop(box).save(path)
    print(f"trimmed {path.name} -> {im.crop(box).size}")
PY
