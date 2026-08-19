# The NDTiff index format

Reverse-read from real acquisitions (both examples in this repo) and cross-checked against
[NDStorage](https://github.com/micro-manager/NDStorage). Written down here because it isn't
documented anywhere convenient, and because the ordering guarantee at the bottom is the thing the
whole tool rests on.

## Layout

An NDTiff index is a flat sequence of variable-length records, little-endian, **no file header and
no record count**. You parse it by walking to the end. One record per image:

| Field | Type | Notes |
|---|---|---|
| `keyLength` | `int32` | byte length of the next field |
| `key` | `char[keyLength]` | UTF-8 JSON of the axes, e.g. `{"column":0,"z":0,"row":3}` |
| `filenameLength` | `int32` | |
| `filename` | `char[filenameLength]` | the data file, e.g. `new_NDTiffStack.tif` |
| `pixelOffset` | `uint32` | byte offset of the pixel data within that file |
| `imageWidth` | `int32` | |
| `imageHeight` | `int32` | |
| `pixelType` | `int32` | `4` = 16-bit monochrome |
| `pixelCompression` | `int32` | `0` = none |
| `metadataOffset` | `uint32` | byte offset of this image's JSON metadata |
| `metadataLength` | `int32` | |
| `metadataCompression` | `int32` | `0` = none |

So each record is `4 + keyLength + 4 + filenameLength + 32` bytes. For the examples here
(26-byte key, 19-byte filename) that's 85 bytes per image.

### Read the offsets as unsigned

`pixelOffset` and `metadataOffset` are **unsigned**. A single NDTiff data file runs right up to
the 4 GB TIFF limit before rolling over, so both routinely exceed 2³¹ and come out negative if you
read them signed. In `examples/full-grid`, the last record in the first data file sits at
`4 281 244 908` — read as a signed int that's `-13 722 388`, and you get nonsense.

### Sanity check

`metadataOffset − pixelOffset` should equal the image size in bytes. For the examples:
`0x00801708 − 0x1708 = 0x800000 = 8 388 608 = 2048 × 2048 × 2`, confirming 16-bit and confirming
the field order.

## The axes

The `key` is a flat JSON object of axis name → integer. Micro-Magellan tile acquisitions use
`row`, `column`, and `z`; other acquisition types add `channel`, `time`, `position`. Values can be
negative — Magellan's explore mode grows the grid outward from wherever you started, so `row: -3`
is normal. Anything reading these must normalise against the observed minimum rather than assuming
0 is the origin.

**The index stores grid indices only.** There are no stage coordinates in µm and no pixel size.
Those live in the per-image JSON at `metadataOffset` *inside the `.tif` files*
(`XPositionUm`, `YPositionUm`, `PixelSizeUm`), and the acquisition-wide settings — including
`GridPixelOverlapX` / `GridPixelOverlapY` — live in the summary metadata in the first data file's
header. This is why the overlap has to be supplied by hand, and why
`--use-metadata` needs the `.tif` files present.

## Why index order == export order

This is load-bearing: the tool assumes **record N of the index is image N of an ImageJ
"Save As > Image Sequence" export**, and emits positions in index order without sorting anything.

Records are appended as images are written, so index order is acquisition order. That it's also
*storage* order is verifiable directly from the index, and
[`tests/test_examples.py`](../tests/test_examples.py) asserts both halves on the real fixtures:

1. **`pixelOffset` increases strictly within each data file.** Images are appended, never
   backfilled.
2. **A data file is never revisited.** NDTiff fills one file until it nears the 4 GB TIFF limit,
   rolls over to `..._1.tif`, and never writes to the previous one again. So the data files
   themselves are in order too.

Together those mean the index is the storage order of the pixels, which is the slice order of the
stack, which is the order Fiji writes an image sequence in.

The scan pattern itself is *not* assumed anywhere — it's just whatever the index says. Both
examples happen to be column-major serpentine (column 0 rows 0→20, column 1 rows 20→0, …), which
is Magellan's default, but nothing in the tool depends on that.

### What could still break it

The guarantee is about the index and the file on disk. It says nothing about what happens between
opening the dataset and exporting it — if the dataset is opened as a hyperstack and an axis gets
reordered, or a subset is exported, the mapping is off. That's exactly what `tiles.csv` is for:
one spot-check at a serpentine turn confirms the export order in seconds.

## Reference implementation

`parse_index()` in [`python/ndtiff_index_to_tileconfig.py`](../python/ndtiff_index_to_tileconfig.py)
is about 30 lines and is the clearest statement of the above.

The macro does the same thing in the ImageJ macro language, with one wrinkle:
`File.openAsRawString()` corrupts bytes above 127, which makes it useless for binary. The macro
instead imports the index as an **8-bit raw image of width = filesize, height = 1** and reads the
exact byte values back with `getProfile()`. It's a fully in-language way to get at bytes with no
Java, no scripting-language dependency, and no charset in the path.
