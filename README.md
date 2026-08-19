# ndtiff-tileconfig

An ImageJ macro that converts an NDTiff index — the `NDTiff.index` written by Micro-Manager,
Micro-Magellan, and Pycro-Manager — into a `TileConfiguration.txt` for Fiji's
[Grid/Collection stitching](https://imagej.net/plugins/grid-collection-stitching) plugin.

One file, no dependencies, no update site.

```
NDTiff.index ──► ndtiff_index_to_tileconfig.ijm ──► TileConfiguration.txt
                                                    tiles.csv
```

## Why

Fiji's stitcher can lay out a grid by itself, but only a complete, regular one. A sparse
acquisition — a hand-drawn ROI, a tissue-following region, an aborted run — needs an explicit
positions file. The NDTiff index already records exactly which `(row, column)` slots were
acquired and in what order; this translates that into the stitcher's format, keeping the tile
order aligned with an exported image sequence.

## Install

Requires ImageJ 1.52 or newer. Nothing else.

Download **[`ndtiff_index_to_tileconfig.ijm`](ndtiff_index_to_tileconfig.ijm)**, then either:

- drag it onto the Fiji main window and press **Run** in the script editor,
- `Plugins > Macros > Run…` and select it, or
- drop it in `Fiji.app/macros/` so it appears under `Plugins > Macros`.

## Usage

### 1. Export an image sequence

Open the NDTiff dataset in Fiji, then `File > Save As > Image Sequence…`

- Format **TIFF**, **Digits** 4, **Start at** 0, **Name** empty → `0000.tif`, `0001.tif`, …
- **Keep 16-bit.** Decline anything offering to scale or convert to 8-bit.
- Large datasets: open as a **virtual stack** first, or you'll load the whole acquisition into
  RAM just to write it back out.
- Export into its own empty folder — the stitcher globs the directory, and stray TIFFs confuse
  the file matching.

### 2. Run the macro

`Plugins > Macros > Run…`, select the `.index` file.

The dialog header reports what was parsed — tile count, column/row/z ranges, tile size, number of
data files, and a warning if the acquisition is sparse. Check it first; it's the cheapest way to
notice you picked the wrong `.index`.

Fill in the overlap and make the naming fields match your export **exactly**. Output is written
next to the index: `TileConfiguration.txt` and `tiles.csv`.

### 3. Stitch

`Plugins > Stitching > Grid/Collection stitching`

| Setting | Value |
|---|---|
| Type | **Positions from file** |
| Order | **Defined by TileConfiguration** |
| Directory | your image-sequence folder |
| Layout file | `TileConfiguration.txt` |
| Compute overlap | **on** — refines the nominal positions by cross-correlation |
| Fusion method | `Linear Blending` is a good default |
| Save computed tile configuration | on — lets you re-fuse later without re-registering |

## Overlap

The index does not store the overlap, so the macro asks every run. Enter it in whichever form you
have it:

| Option | Example | Step for a 2048 px tile |
|---|---|---|
| `percent of tile (%)` | `10` | 1843.2 px |
| `pixels` | `205` | 1843 px |

Micro-Magellan records the true value as **`GridPixelOverlapX` / `GridPixelOverlapY`, in pixels**,
in the acquisition summary metadata — so the pixels option usually lets you paste the exact number
rather than converting it. X and Y are entered separately.

Nothing is written until you confirm. After OK you get the overlap resolved both ways, the step
size, the final mosaic dimensions, and the filename range, with **Write it** / **Change
settings**. Wrong number → *Change settings* → the dialog reopens with your values intact, so you
can dial it in without re-running the macro.

Your entries are remembered between runs.

It refuses obviously-broken input: overlap ≥ tile size, negative overlap, non-positive tile size,
absurd digit counts.

## Dialog reference

| Field | Notes |
|---|---|
| Tile width / height | Pre-filled from the index; editable |
| Overlap given in | `percent of tile (%)` or `pixels` |
| Overlap X / Y | Entered separately; remembered between runs |
| Filename prefix | Must match your Image Sequence export |
| Number of digits | `4` → `0000.tif` |
| First index | Usually `0` |
| Extension | Usually `.tif` |
| Invert X | Mosaic came out mirrored left-right |
| Invert Y | Mosaic came out mirrored top-bottom (common — many stages run Y upward while `row` runs downward) |
| Swap row/column axes | Mosaic came out transposed |
| Z step (px) | Only shown when the dataset has more than one z; writes `dim = 3` |
| Write tiles.csv | The verification table — keep it on |

## Output

**`TileConfiguration.txt`** — the positions file:

```
# Define the number of dimensions we are working on
dim = 2

# Define the image coordinates
0000.tif; ; (0.000, 0.000)
0001.tif; ; (0.000, 1843.200)
0002.tif; ; (0.000, 3686.400)
```

**`tiles.csv`** — the verification table, one row per tile:

```
seq_index,filename,ndtiff_file,column,row,z,x_px,y_px
0,0000.tif,new_NDTiffStack.tif,0,0,0,0.000,0.000
1,0001.tif,new_NDTiffStack.tif,0,1,0,0.000,1843.200
```

### Verify the order before you fuse

Line N of the positions file refers to image N of your export. That holds because NDTiff appends
records in acquisition order and never rewrites a closed data file — but it says nothing about
what happened between opening the dataset and exporting it.

So spot-check one **serpentine turn**, where the scan reverses direction and an ordering bug is
most obvious. Find two consecutive rows in `tiles.csv` that share a `row` but differ by one
`column`, open those two TIFFs, and confirm they share an edge. Two minutes here saves an hour of
fusing the wrong thing.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Stitcher can't find the images | Naming fields don't match the export — digits, start index, prefix, extension |
| Mosaic mirrored or transposed | *Invert X* / *Invert Y* / *Swap row/column axes* |
| Tiles land in a diagonal line | Row/column swapped, or a `dim = 3` file being read as 2D |
| Visible seams, tiles slightly off | Overlap close but not right — enable *Compute overlap* |
| Tiles snapped to obviously wrong places | Overlap badly wrong, so the true offset fell outside the search window |
| Right layout, garbage image content | Export converted to 8-bit or rescaled |
| Some tiles missing | Sparse acquisition — expected. Compare the tile count in the dialog header against your export |

## Notes and limits

- Tile positions are a **regular grid** reconstructed from the index's `(row, column)` plus the
  overlap you supply. The index has no stage coordinates and no pixel size — those live in the
  per-image metadata inside the `.tif` files.
- The macro reads binary through an 8-bit raw import rather than `File.openAsRawString()`, which
  corrupts bytes above 127.
- Negative row/column indices are handled (Magellan's explore mode grows the grid outward from
  wherever you started).
- The macro has been carefully reviewed but is not automatically tested — there's no ImageJ in
  CI. Check the confirmation dialog's numbers on your first run.

## More

The **[`dev`](../../tree/dev)** branch has a Python port of the same conversion — including a
`--use-metadata` mode that reads true stage coordinates from the `.tif` files instead of assuming
a perfect grid — plus example datasets, tests, and notes on the NDTiff index format and on
alternative stitching tools.
