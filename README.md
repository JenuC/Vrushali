# ndtiff-tileconfig

**Turn an NDTiff index into a `TileConfiguration.txt` for Fiji's Grid/Collection stitching.**

An ImageJ macro that reads the `NDTiff.index` written by Micro-Manager / Micro-Magellan /
Pycro-Manager and emits a positions file for the
[Grid/Collection stitching](https://imagej.net/plugins/grid-collection-stitching) plugin, matched
to an exported image sequence (`0000.tif`, `0001.tif`, …).

No dependencies, no Python required, no update site — one `.ijm` file you drop into the script
editor. A Python port is included as a supplement for batch use and for reading true stage
coordinates.

```
NDTiff.index ──► ndtiff_index_to_tileconfig.ijm ──► TileConfiguration.txt
                                                    tiles.csv
```

---

## Why

Fiji's stitcher can lay out a grid on its own, but only a *complete, regular* one. The moment an
acquisition is sparse — a hand-drawn ROI, a tissue-following region, an aborted run — no grid
preset can describe it, and you need an explicit positions file. The NDTiff index already knows
exactly which `(row, column)` slots were acquired and in what order; this just translates that
into the stitcher's format.

It also handles the mundane-but-fiddly part: getting the *order* right, so line N of the
positions file refers to the same tile as image N of your export.

## Install

Download [`ndtiff_index_to_tileconfig.ijm`](ndtiff_index_to_tileconfig.ijm) and either

- drag it onto the Fiji main window, then **Run** in the script editor, or
- `Plugins > Macros > Run…` and pick the file, or
- drop it in `Fiji.app/macros/` to have it in `Plugins > Macros`.

Requires ImageJ 1.52 or newer. Nothing else.

## Use

1. **Export the image sequence.** Open the NDTiff dataset in Fiji, then
   `File > Save As > Image Sequence…` — TIFF, 4 digits, start at 0, no prefix. Keep 16-bit; don't
   let it convert. Large datasets: open as a **virtual stack** first.

2. **Run the macro** and pick the `.index` file. It reports what it found, asks for the overlap
   and your filename pattern, shows you the resulting geometry, and writes
   `TileConfiguration.txt` + `tiles.csv` next to the index.

3. **Stitch.** `Plugins > Stitching > Grid/Collection stitching`
   - Type: **Positions from file**
   - Order: **Defined by TileConfiguration**
   - Directory: your image-sequence folder · Layout file: `TileConfiguration.txt`
   - Tick **Compute overlap** so it refines the nominal positions by cross-correlation.

### Overlap is a per-run input

The index does not store the overlap, so the macro asks every time. Enter it however you have it:

| Option | Example | Step for a 2048 px tile |
|---|---|---|
| `percent of tile (%)` | `10` | 1843.2 px |
| `pixels` | `205` | 1843 px |

Micro-Magellan records the true value as **`GridPixelOverlapX` / `GridPixelOverlapY`, in pixels**,
in the acquisition summary metadata — so the pixels option usually lets you paste the exact number
instead of converting it. X and Y are entered separately.

Nothing is written until you confirm: after OK you get the overlap resolved both ways, the step,
the final mosaic dimensions, and the filename range, with **Write it** / **Change settings**.
Wrong number → *Change settings* → the dialog reopens with your values intact. Your entries are
remembered between runs.

### Dialog reference

| Field | Notes |
|---|---|
| Tile width / height | Pre-filled from the index; editable |
| Overlap given in | `percent of tile (%)` or `pixels` |
| Overlap X / Y | Per-dataset, entered separately, remembered between runs |
| Prefix / digits / first index / extension | Must match your Image Sequence export exactly |
| Invert X / Invert Y | Flip if the mosaic comes out mirrored |
| Swap row/column axes | Flip if the mosaic comes out transposed |
| Z step (px) | Only shown when the dataset has >1 z; writes `dim = 3` |
| Write tiles.csv | The verification table — keep it on |

### Verify the export order

`tiles.csv` maps each exported filename to its `(column, row, z)` and the NDTiff data file it came
from. Pick a serpentine turn — in [`examples/full-grid`](examples/full-grid), sequence 20 → 21 is
`(column 0, row 20)` → `(column 1, row 20)` — and confirm those two images really are neighbours.
If your export came out in a different order than the index, that check catches it in seconds,
before you spend an hour fusing.

## Examples

Two real acquisitions, with their generated output committed alongside:

| Example | Tiles | Grid | Notes |
|---|---|---|---|
| [`examples/full-grid`](examples/full-grid) | 798 | 38 × 21, complete | Serpentine, split across two NDTiff data files |
| [`examples/sparse-roi`](examples/sparse-roi) | 113 | 14 × 18, **113 of 252 filled** | Ragged ROI — a positions file is mandatory here |

See [`examples/README.md`](examples/README.md) for how they were generated.

## Python supplement

[`python/ndtiff_index_to_tileconfig.py`](python/ndtiff_index_to_tileconfig.py) is the same
conversion as a CLI — standard library only, no install. Use it for batch runs, for CI, or for
the one thing the macro can't do:

```bash
# same as the macro
python python/ndtiff_index_to_tileconfig.py NDTiff.index --overlap 10

# overlap in pixels, straight from GridPixelOverlapX
python python/ndtiff_index_to_tileconfig.py NDTiff.index --overlap-px 205

# true stage coordinates instead of an assumed-perfect grid  <-- the good one
python python/ndtiff_index_to_tileconfig.py NDTiff.index --use-metadata
```

`--use-metadata` seeks into the NDTiff `.tif` files, reads `XPositionUm` / `YPositionUm` /
`PixelSizeUm` from each image's JSON metadata, converts to pixels, and auto-detects whether the
stage axes run opposite to the row/column indices (common — plenty of stages have Y increasing
upward while `row` increases downward). If your stage has backlash, drift, or a tilted sample,
these are much better seed positions than a reconstructed grid. It needs the `.tif` files present
next to the index.

`--help` lists the rest: `--overlap-y`, `--overlap-px-y`, `--pixel-size`, `--invert-x/-y`,
`--swap-axes`, `--prefix`, `--digits`, `--start`, `--ext`, `--z-step`, `--csv`.

## Is there something better?

Depends on the dataset — see [`docs/alternatives.md`](docs/alternatives.md) for the full rundown.
The short version:

- **Complete regular grid?** You may not need this at all. Grid/Collection stitching's
  `Grid: snake by columns` + `Down & Right` describes the `full-grid` example exactly.
- **Sparse acquisition?** A positions file is the only option. That's what this is for.
- **Very large mosaic?** [BigStitcher](https://imagej.net/plugins/bigstitcher) stays virtual,
  optimises globally instead of pairwise, and won't run you out of heap.
- **Comfortable in Python?** [`ndstorage`](https://github.com/micro-manager/NDStorage) reads
  NDTiff natively — you can skip the image-sequence export entirely and stitch with
  [ashlar](https://github.com/labsyspharm/ashlar), which handles sparse mosaics and reads stage
  positions directly.

## Docs

- [`docs/ndtiff-index-format.md`](docs/ndtiff-index-format.md) — the binary layout, and why index
  order is guaranteed to match export order
- [`docs/workflow.md`](docs/workflow.md) — the full Fiji walkthrough, overlap sourcing, troubleshooting
- [`docs/alternatives.md`](docs/alternatives.md) — other tools, and which ones not to bother with

## Status

The Python script and its parser are covered by tests (`python -m unittest discover -s tests`),
which also assert that the committed example outputs still regenerate byte for byte.

**The `.ijm` itself is not automatically tested** — there's no ImageJ in CI — and it mirrors the
Python logic by hand. It's had a careful read but treat your first run as a smoke test: check the
confirmation dialog's numbers and spot-check `tiles.csv` against your export.

## Licence

MIT — see [LICENSE](LICENSE).
