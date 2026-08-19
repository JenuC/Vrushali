# Alternatives

This tool exists to fill one gap. It's worth knowing when you don't need it, and when something
else is a better fit.

## You may not need a positions file at all

If your acquisition is a **complete, regular grid**, Grid/Collection stitching can generate the
layout itself and there's nothing to convert.

For the `full-grid` example — 38 columns × 21 rows, column-major serpentine starting at
`(column 0, row 0)` and going down:

- **Type:** `Grid: snake by columns`
- **Order:** `Down & Right`
- **Grid size x = 38, y = 21**
- Tile overlap as usual, filenames `{iiii}.tif` starting at 0

That describes the dataset exactly, with fewer moving parts. Use this repo's output instead if you
want the layout pinned explicitly, or if you'd rather have `tiles.csv` for verification — the
geometry is identical either way.

**Check your scan pattern first.** `tiles.csv` (or the Python script's console output) tells you
whether it's row-major or column-major, serpentine or raster, and which corner it starts from.
Guessing wrong here produces a mosaic that looks plausible but has every other row reversed.

## When you do need one

- **Sparse or irregular acquisitions.** A hand-drawn ROI, a tissue-following region, an aborted
  run. The `sparse-roi` example has 113 of 252 grid slots filled, with a different row range in
  every column. No grid preset can express that.
- **Non-contiguous or multi-region acquisitions.**
- **When you want true stage coordinates** as seed positions rather than an idealised grid.

## Better positions: use the stage coordinates

A reconstructed grid assumes a perfect stage. Real ones have backlash, drift, and thermal creep,
and samples are sometimes tilted. The actual recorded positions are better starting points:

```bash
python python/ndtiff_index_to_tileconfig.py NDTiff.index --use-metadata
```

This reads `XPositionUm` / `YPositionUm` / `PixelSizeUm` from each image's JSON metadata inside the
`.tif` files, converts to pixels, and works out whether the stage axes run opposite to the
row/column indices. Needs the `.tif` files next to the index. It's one flag and it's the single
biggest quality improvement available here.

## BigStitcher — for large datasets

[BigStitcher](https://imagej.net/plugins/bigstitcher) is the modern successor to the classic
Preibisch plugin and what you want past a few hundred tiles:

- HDF5/N5-backed, stays virtual — no heap ceiling
- **Global optimisation** across all tiles rather than pairwise chaining, so registration error
  doesn't accumulate across the mosaic
- Non-rigid correction for sample deformation
- Interactive preview before committing to a fuse

`Plugins > BigStitcher > Define Dataset`, load the exported sequence as image stacks, then move
tiles to a grid or load positions from file. For the `full-grid` example this is what I'd actually
reach for.

## Skip Fiji: read NDTiff natively in Python

The image-sequence export is pure overhead — it duplicates the whole dataset and introduces the
ordering risk that `tiles.csv` exists to guard against. Python reads NDTiff directly:

```python
from ndstorage import Dataset       # pip install ndstorage
# older installs: from pycromanager import Dataset

d = Dataset(r"/path/to/ndtiff_folder")
img  = d.read_image(row=3, column=5)
meta = d.read_metadata(row=3, column=5)    # XPositionUm / YPositionUm / PixelSizeUm
arr  = d.as_array()                        # lazy dask array over the whole acquisition
```

From there you can write a positions file with true µm-derived coordinates, or stitch entirely in
Python. [**ashlar**](https://github.com/labsyspharm/ashlar) is the strongest option — it handles
sparse tile sets, scales to large mosaics, and reads stage positions directly.
[m2stitch](https://github.com/yfukai/m2stitch) implements MIST's algorithm in Python.

## Checked, and not recommended

**Bio-Formats.** Its Micro-Manager reader targets the older `_MMStack_` OME-TIFF layout. NDTiff
v2/v3 is a different container — don't count on Bio-Formats, or BigStitcher's Bio-Formats-based
automatic loader, to open these directly.

**MIST (NIST).** Often registers more accurately than the Preibisch plugin, and worth trying on
`full-grid`. But it requires a complete regular grid with a filename pattern, so it can't touch
`sparse-roi`.

**An existing NDTiff → TileConfiguration plugin.** I couldn't find one. The conversion is normally
done ad hoc in Python via `ndstorage`, which is why the Python script here is worth keeping around
even though the macro is the main deliverable.

## Choosing

| Situation | Use |
|---|---|
| Complete regular grid, moderate size | Grid/Collection stitching's built-in grid presets |
| Sparse or irregular acquisition | This tool |
| Hundreds of tiles, or fusion won't fit in RAM | BigStitcher |
| Stage drift / tilted sample / want real coordinates | This tool with `--use-metadata` |
| Already scripting in Python, want to skip the export | `ndstorage` + `ashlar` |
