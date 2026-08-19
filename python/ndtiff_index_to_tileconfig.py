#!/usr/bin/env python3
"""
ndtiff_index_to_tileconfig.py
------------------------------------------------------------------------------
Convert an NDTiff index file (Micro-Manager / Micro-Magellan / Pycro-Manager
NDTiffStorage) into a TileConfiguration.txt for the Fiji "Grid/Collection
stitching" plugin.

Two modes:

  grid mode (default)
      Positions are reconstructed from the row/column axes in the index plus
      an overlap percentage you supply. Needs nothing but the .index file.

  metadata mode  (--use-metadata)
      Positions are read from the true XPositionUm / YPositionUm in the
      per-image JSON metadata inside the NDTiffStack .tif files, and converted
      to pixels with PixelSizeUm. Needs the .tif files next to the index.
      This is the accurate option when the stage is not perfectly regular.

The output line order matches the order of records in the index, which is
acquisition order, which is the slice order of the stack, which is the order
of an ImageJ "Save As > Image Sequence" export. That is what makes the
filenames line up.

Index record layout (little-endian, repeated, no header):
    int32 keyLen | key (JSON axes) | int32 fnLen | filename
    int32 pixelOffset | int32 width | int32 height | int32 pixelType
    int32 pixelCompression | int32 metadataOffset | int32 metadataLength
    int32 metadataCompression

Examples
    python ndtiff_index_to_tileconfig.py NDTiff.index --overlap 10
    python ndtiff_index_to_tileconfig.py NDTiff.index --use-metadata
    python ndtiff_index_to_tileconfig.py "NDTiff (1).index" -o TileConfiguration_B.txt --digits 3
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import struct
import sys
from dataclasses import dataclass

RECORD_TAIL = struct.Struct("<8I")  # the 8 uint32 fields after the filename


@dataclass
class Entry:
    seq: int
    axes: dict
    filename: str
    pixel_offset: int
    width: int
    height: int
    pixel_type: int
    pixel_compression: int
    metadata_offset: int
    metadata_length: int
    metadata_compression: int

    @property
    def column(self) -> int:
        return int(self.axes.get("column", 0))

    @property
    def row(self) -> int:
        return int(self.axes.get("row", 0))

    @property
    def z(self) -> int:
        return int(self.axes.get("z", 0))


def parse_index(path: str) -> list[Entry]:
    with open(path, "rb") as fh:
        data = fh.read()

    entries: list[Entry] = []
    i, n = 0, len(data)
    while i + 4 <= n:
        (key_len,) = struct.unpack_from("<i", data, i)
        i += 4
        if key_len <= 0 or i + key_len > n:
            break
        key = data[i : i + key_len].decode("utf-8")
        i += key_len

        (fn_len,) = struct.unpack_from("<i", data, i)
        i += 4
        if fn_len <= 0 or i + fn_len > n:
            break
        filename = data[i : i + fn_len].decode("utf-8")
        i += fn_len

        if i + RECORD_TAIL.size > n:
            break
        vals = RECORD_TAIL.unpack_from(data, i)
        i += RECORD_TAIL.size

        entries.append(Entry(len(entries), json.loads(key), filename, *vals))

    if not entries:
        sys.exit(f"No records parsed from {path} - is this an NDTiff index?")
    return entries


def read_stage_positions(entries: list[Entry], base_dir: str):
    """Pull XPositionUm/YPositionUm/PixelSizeUm out of the .tif per-image metadata."""
    handles: dict[str, object] = {}
    out = []
    try:
        for e in entries:
            if e.metadata_compression != 0:
                sys.exit("Compressed image metadata is not supported by this script.")
            fh = handles.get(e.filename)
            if fh is None:
                p = os.path.join(base_dir, e.filename)
                if not os.path.exists(p):
                    sys.exit(
                        f"--use-metadata needs the NDTiff .tif files. Missing: {p}\n"
                        f"Drop this script next to the NDTiffStack .tif files, or use grid mode."
                    )
                fh = open(p, "rb")
                handles[e.filename] = fh
            fh.seek(e.metadata_offset)
            md = json.loads(fh.read(e.metadata_length).decode("utf-8"))
            out.append(md)
    finally:
        for fh in handles.values():
            fh.close()

    def pick(md, *names, default=None):
        for k in names:
            if k in md:
                return md[k]
        return default

    xs = [pick(md, "XPositionUm", "XPosition_um", "x_position_um") for md in out]
    ys = [pick(md, "YPositionUm", "YPosition_um", "y_position_um") for md in out]
    px = next(
        (pick(md, "PixelSizeUm", "PixelSize_um", "pixel_size_um") for md in out if pick(md, "PixelSizeUm", "PixelSize_um", "pixel_size_um")),
        None,
    )
    if any(v is None for v in xs) or any(v is None for v in ys):
        sys.exit(
            "Stage positions not found in the image metadata. Keys present in the "
            f"first image: {sorted(out[0])[:40]}"
        )
    if not px:
        sys.exit("PixelSizeUm not found in image metadata; pass --pixel-size instead.")
    return [float(v) for v in xs], [float(v) for v in ys], float(px)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("index", help="path to NDTiff.index")
    ap.add_argument("-o", "--output", default=None, help="output TileConfiguration path")
    ap.add_argument("--csv", default=None, help="also write a seq-index/row/column mapping CSV")
    ap.add_argument("--overlap", type=float, default=10.0, help="tile overlap %% (grid mode, default 10)")
    ap.add_argument("--overlap-y", type=float, default=None, help="separate Y overlap %% (default: same as --overlap)")
    ap.add_argument("--overlap-px", type=float, default=None,
                    help="tile overlap in PIXELS instead of %% (Micro-Magellan's GridPixelOverlapX)")
    ap.add_argument("--overlap-px-y", type=float, default=None,
                    help="separate Y overlap in pixels (default: same as --overlap-px)")
    ap.add_argument("--prefix", default="", help="image-sequence filename prefix")
    ap.add_argument("--digits", type=int, default=4, help="digits in the image-sequence numbering (default 4)")
    ap.add_argument("--start", type=int, default=0, help="first image-sequence number (default 0)")
    ap.add_argument("--ext", default=".tif", help="image-sequence extension (default .tif)")
    ap.add_argument("--invert-x", action="store_true", help="column increases to the left")
    ap.add_argument("--invert-y", action="store_true", help="row increases upward")
    ap.add_argument("--swap-axes", action="store_true", help="swap the row and column axes")
    ap.add_argument("--use-metadata", action="store_true", help="read true stage XY from the .tif files")
    ap.add_argument("--pixel-size", type=float, default=None, help="um/pixel override for --use-metadata")
    ap.add_argument("--z-step", type=float, default=1.0, help="z spacing in px when the dataset has >1 z (dim=3)")
    args = ap.parse_args()

    entries = parse_index(args.index)
    base_dir = os.path.dirname(os.path.abspath(args.index))
    out_path = args.output or os.path.join(base_dir, "TileConfiguration.txt")

    cols = [e.column for e in entries]
    rows = [e.row for e in entries]
    zs = [e.z for e in entries]
    col_min, col_max = min(cols), max(cols)
    row_min, row_max = min(rows), max(rows)
    z_min, z_max = min(zs), max(zs)
    n_z = z_max - z_min + 1
    tile_w = max(e.width for e in entries)
    tile_h = max(e.height for e in entries)

    if args.use_metadata:
        xs_um, ys_um, px_um = read_stage_positions(entries, base_dir)
        if args.pixel_size:
            px_um = args.pixel_size
        x0, y0 = min(xs_um), min(ys_um)
        xs = [(v - x0) / px_um for v in xs_um]
        ys = [(v - y0) / px_um for v in ys_um]
        # Stage axes may run opposite to the grid indices; align them so that
        # increasing column means increasing x and increasing row means increasing y.
        if _slope(cols, xs) < 0:
            m = max(xs)
            xs = [m - v for v in xs]
        if _slope(rows, ys) < 0:
            m = max(ys)
            ys = [m - v for v in ys]
        step_x = step_y = None
    else:
        if args.overlap_px is not None:
            ov_px_x = args.overlap_px
            ov_px_y = args.overlap_px if args.overlap_px_y is None else args.overlap_px_y
        else:
            ov_x = args.overlap
            ov_y = args.overlap if args.overlap_y is None else args.overlap_y
            ov_px_x = tile_w * ov_x / 100.0
            ov_px_y = tile_h * ov_y / 100.0
        step_x = tile_w - ov_px_x
        step_y = tile_h - ov_px_y
        if step_x <= 0 or step_y <= 0:
            sys.exit(f"Overlap >= tile size: step would be {step_x} x {step_y} px.")
        xs, ys = [], []
        for e in entries:
            c, r = e.column - col_min, e.row - row_min
            if args.swap_axes:
                c, r = r, c
            x, y = c * step_x, r * step_y
            if args.invert_x:
                x = (col_max - col_min) * step_x - x
            if args.invert_y:
                y = (row_max - row_min) * step_y - y
            xs.append(x)
            ys.append(y)

    dim = 3 if n_z > 1 else 2
    lines = ["# Define the number of dimensions we are working on", f"dim = {dim}", "", "# Define the image coordinates"]
    names = [f"{args.prefix}{args.start + i:0{args.digits}d}{args.ext}" for i in range(len(entries))]
    for i, e in enumerate(entries):
        if dim == 3:
            zpx = (e.z - z_min) * args.z_step
            lines.append(f"{names[i]}; ; ({xs[i]:.3f}, {ys[i]:.3f}, {zpx:.3f})")
        else:
            lines.append(f"{names[i]}; ; ({xs[i]:.3f}, {ys[i]:.3f})")

    with open(out_path, "w", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            # LF, not csv's default CRLF, so the file matches TileConfiguration.txt
            # and stays byte-identical across platforms.
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["seq_index", "filename", "ndtiff_file", "column", "row", "z", "x_px", "y_px"])
            for i, e in enumerate(entries):
                w.writerow([i, names[i], e.filename, e.column, e.row, e.z, f"{xs[i]:.3f}", f"{ys[i]:.3f}"])

    full = (col_max - col_min + 1) * (row_max - row_min + 1) * n_z
    print(f"{args.index}")
    print(f"  tiles        : {len(entries)}" + ("" if len(entries) == full else f"  (sparse: {full} grid slots)"))
    print(f"  columns      : {col_min}..{col_max}")
    print(f"  rows         : {row_min}..{row_max}")
    print(f"  z            : {z_min}..{z_max}")
    print(f"  tile size    : {tile_w} x {tile_h} px")
    print(f"  ndtiff files : {sorted({e.filename for e in entries})}")
    if step_x:
        print(f"  overlap      : X {ov_px_x:.1f} px / {100 * ov_px_x / tile_w:.2f} %"
              f"   Y {ov_px_y:.1f} px / {100 * ov_px_y / tile_h:.2f} %")
        print(f"  step         : {step_x:.1f} x {step_y:.1f} px")
    print(f"  mosaic       : {max(xs) + tile_w:.0f} x {max(ys) + tile_h:.0f} px")
    print(f"  wrote        : {out_path}")
    if args.csv:
        print(f"  wrote        : {args.csv}")


def _slope(a, b) -> float:
    """Sign-only least-squares slope of b vs a; used to detect flipped stage axes."""
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    den = sum((a[i] - ma) ** 2 for i in range(n)) or 1.0
    return num / den


if __name__ == "__main__":
    main()
