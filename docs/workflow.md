# Full workflow

From an NDTiff acquisition to a fused mosaic, with the places it usually goes wrong.

## 1. Export the image sequence

Open the NDTiff dataset in Fiji, then `File > Save As > Image Sequence…`

- **Format** TIFF
- **Digits** 4, **Start at** 0, **Name** empty → `0000.tif, 0001.tif, …`
- **Keep 16-bit.** If anything offers to scale or convert to 8-bit, decline. You'll lose dynamic
  range the stitcher needs for cross-correlation.
- **Large datasets: open as a virtual stack.** The `full-grid` example is 798 × 2048² × 16-bit
  ≈ 6.7 GB; loading that into RAM to immediately write it back out is a bad time.

Export into its own empty folder. The stitcher globs the directory, and stray TIFFs will confuse
the file matching.

## 2. Generate the positions file

Run `ndtiff_index_to_tileconfig.ijm` (`Plugins > Macros > Run…`) and pick the `.index`.

The header of the dialog shows what was parsed — tile count, column/row/z ranges, tile size,
number of data files, and a warning if the acquisition is sparse. Check this first; it's the
cheapest way to notice you grabbed the wrong `.index`.

Fill in the overlap (below) and make the naming fields match your export **exactly** — prefix,
digit count, first index, extension. A mismatch here produces a valid-looking file that the
stitcher then can't resolve to any image.

Confirm at the summary screen. Output lands next to the index: `TileConfiguration.txt` and
`tiles.csv`.

### Getting the overlap right

Not stored in the index, so you have to supply it. In order of preference:

1. **From the acquisition metadata.** Micro-Magellan records `GridPixelOverlapX` /
   `GridPixelOverlapY` **in pixels** in the summary metadata. Choose `pixels` in the dialog and
   paste them. Exact, no conversion.
2. **From the acquisition settings** you used at the microscope, usually as a percentage.
   Choose `percent of tile (%)`.
3. **Measured.** Open two adjacent tiles, find a feature in both, measure the offset. Tedious but
   reliable when the metadata is gone.

10 % is Micro-Magellan's default and what the committed examples assume — it is a *default*, not
your value.

You don't have to get it perfect. With **Compute overlap** enabled the stitcher treats these as
seed positions and refines them by cross-correlation; a few percent off is absorbed. Being off by
a lot is not — the search window is finite, and once the true offset falls outside it the tiles
snap to wrong positions with confident-looking correlation scores.

### Geometry flags

Leave them off, look at the result, come back if needed:

- Mosaic **mirrored left-right** → *Invert X*
- Mosaic **mirrored top-bottom** → *Invert Y*. Common: many stages have Y increasing upward while
  `row` increases downward.
- Mosaic **transposed** (a 38 × 21 grid came out 21 × 38) → *Swap row/column axes*

Rather than guessing, `--use-metadata` in the Python script derives the correct orientation from
the actual stage coordinates.

## 3. Verify before you fuse

Two minutes here saves an hour of fusing the wrong thing.

Open `tiles.csv`. It maps each exported filename to `(column, row, z)` and to the NDTiff data file
it came from. Pick a **serpentine turn** — a point where the scan reverses direction, which is
where an ordering bug shows up most obviously. In `examples/full-grid`, sequence 20 → 21 goes
`(column 0, row 20)` → `(column 1, row 20)`: two tiles that are side by side. Open `0020.tif` and
`0021.tif` and confirm they share an edge.

If they don't, the export order didn't match the index — re-export without reordering axes.

Also glance at the mosaic dimensions in the confirmation dialog. If they're wildly off from what
you expect for the sample, the overlap or the tile size is wrong.

## 4. Stitch

`Plugins > Stitching > Grid/Collection stitching`

- **Type:** `Positions from file`
- **Order:** `Defined by TileConfiguration`
- **Directory:** the image-sequence folder
- **Layout file:** `TileConfiguration.txt`
- **Compute overlap:** on — this is what turns nominal grid positions into a real registration
- **Fusion method:** `Linear Blending` is a good default
- **Save computed tile configuration:** on. It writes `TileConfiguration.registered.txt`, which
  lets you re-fuse later — different fusion method, different subset — without recomputing the
  registration. On an 800-tile dataset that's the difference between minutes and hours.

### If it runs out of memory

The `full-grid` example fuses to roughly 70 246 × 38 912 px, about 5.5 GB at 16-bit, and Fiji
needs headroom beyond that. Options, in order of how much they cost you:

- Raise the heap: `Edit > Options > Memory & Threads`
- Downsample before fusing
- Fuse in tiles/regions and reassemble
- Move to [BigStitcher](https://imagej.net/plugins/bigstitcher), which keeps everything virtual and
  exports to N5/HDF5 — see [alternatives.md](alternatives.md)

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Stitcher can't find the images | Naming fields don't match the export (digits, start index, prefix, extension) |
| Mosaic mirrored or transposed | Geometry flags — see above |
| Tiles land in a diagonal line | Row/column swapped, or a `dim = 3` file being read as 2D |
| Visible seams, tiles slightly off | Overlap value is close but not right; enable *Compute overlap* |
| Tiles snapped to obviously wrong places | Overlap badly wrong, so the true offset fell outside the search window |
| Right layout, garbage image content | Export converted to 8-bit or rescaled |
| Some tiles missing from the mosaic | Sparse acquisition — expected. Check the tile count in the dialog header against your export |
