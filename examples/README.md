# Examples

Two real Micro-Magellan acquisitions, with their generated output committed alongside so you can
see what the tool produces without running anything.

Each folder holds the **index only** — no pixel data. An NDTiff index is metadata: axis
coordinates, byte offsets, and the data filenames. The `.tif` files themselves aren't here, which
is why `--use-metadata` can't be demonstrated on these fixtures.

## `full-grid/` — 798 tiles, complete grid

| | |
|---|---|
| Tiles | 798 |
| Grid | 38 columns × 21 rows — **complete**, 798 of 798 slots |
| Tile | 2048 × 2048, 16-bit (`pixelType 4`) |
| Data files | `new_NDTiffStack.tif`, `new_NDTiffStack_1.tif` — split at the 4 GB TIFF limit |
| Scan | Column-major serpentine: column 0 rows 0→20, column 1 rows 20→0, … |
| Raw size | ~6.7 GB |
| Fused @ 10 % overlap | 70 246 × 38 912 px (~5.5 GB at 16-bit) |

Being a complete regular grid, this one **doesn't strictly need a positions file** —
`Grid: snake by columns` + `Down & Right` describes it exactly. It's here as the
straightforward case, and because it exercises the multi-data-file path and the unsigned-offset
handling (its last first-file record sits at byte 4 281 244 908).

## `sparse-roi/` — 113 tiles, irregular region

| | |
|---|---|
| Tiles | 113 |
| Grid | 14 columns × 18 rows = 252 slots, **only 113 filled** |
| Tile | 2048 × 2048, 16-bit |
| Data files | `new_NDTiffStack.tif` |
| Scan | Column-major serpentine, but each column spans a different row range |
| Fused @ 10 % overlap | 26 010 × 33 382 px (~1.7 GB at 16-bit) |

This is the case the tool exists for. The acquired region is a ragged band — it starts at
`(column 0, row 16)`, and every column covers a different set of rows. No grid preset in the
stitching plugin can describe that, so an explicit positions file is the only way.

## Regenerating

Both were generated with 10 % overlap and 4-digit filenames starting at 0:

```bash
python python/ndtiff_index_to_tileconfig.py examples/full-grid/NDTiff.index \
    -o examples/full-grid/TileConfiguration.txt \
    --csv examples/full-grid/tiles.csv \
    --overlap 10 --digits 4 --start 0

python python/ndtiff_index_to_tileconfig.py examples/sparse-roi/NDTiff.index \
    -o examples/sparse-roi/TileConfiguration.txt \
    --csv examples/sparse-roi/tiles.csv \
    --overlap 10 --digits 4 --start 0
```

Those arguments live in [`expected.json`](expected.json), which is the single source of truth —
[`tests/test_examples.py`](../tests/test_examples.py) reads it, regenerates each example, and
diffs against the committed files. If you change the generator, run the tests; a stale example
fails the build.

**10 % is Micro-Magellan's default, not a measured value for these datasets.** It's a placeholder
so the examples have concrete numbers. Don't copy it for your own data — see
[`docs/workflow.md`](../docs/workflow.md#getting-the-overlap-right).

## Files in each folder

| File | What |
|---|---|
| `NDTiff.index` | The input, exactly as Micro-Manager wrote it |
| `TileConfiguration.txt` | Generated positions file for Grid/Collection stitching |
| `tiles.csv` | `seq_index, filename, ndtiff_file, column, row, z, x_px, y_px` — the verification table |
