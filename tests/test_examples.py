"""
Regression tests for ndtiff-tileconfig.

Two things are checked:

  1. The parser agrees with what we know about the two example datasets
     (tile counts, axis ranges, tile size, data-file split, scan order).
  2. Regenerating each example from its .index reproduces the committed
     TileConfiguration.txt and tiles.csv byte for byte, so the examples in the
     repo can never silently drift away from the code.

Run:  python -m unittest discover -s tests -v
  or: pytest
No third-party dependencies; standard library only.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "python" / "ndtiff_index_to_tileconfig.py"
EXAMPLES = REPO / "examples"

sys.path.insert(0, str(REPO / "python"))
from ndtiff_index_to_tileconfig import parse_index  # noqa: E402


def load_manifest():
    with open(EXAMPLES / "expected.json") as fh:
        return json.load(fh)["examples"]


class TestParser(unittest.TestCase):
    """The index parser reads what we expect out of the two real datasets."""

    def test_example_datasets_parse_as_documented(self):
        for ex in load_manifest():
            with self.subTest(example=ex["dir"]):
                entries = parse_index(str(EXAMPLES / ex["dir"] / "NDTiff.index"))

                self.assertEqual(len(entries), ex["tiles"])
                self.assertEqual(
                    [min(e.column for e in entries), max(e.column for e in entries)],
                    ex["columns"],
                )
                self.assertEqual(
                    [min(e.row for e in entries), max(e.row for e in entries)],
                    ex["rows"],
                )
                self.assertEqual({e.z for e in entries}, {0})
                self.assertEqual(
                    [max(e.width for e in entries), max(e.height for e in entries)],
                    ex["tile_size"],
                )
                # pixelType 4 == 16-bit monochrome
                self.assertEqual({e.pixel_type for e in entries}, {4})

    def test_index_order_is_storage_order(self):
        """
        The whole filename mapping rests on this: records appear in acquisition
        order, so record N == slice N == image N of an exported sequence.
        Verified by pixel offsets increasing strictly within each data file,
        with the data files themselves never revisited.
        """
        for ex in load_manifest():
            with self.subTest(example=ex["dir"]):
                entries = parse_index(str(EXAMPLES / ex["dir"] / "NDTiff.index"))

                by_file = {}
                for e in entries:
                    by_file.setdefault(e.filename, []).append(e.pixel_offset)
                for name, offsets in by_file.items():
                    self.assertTrue(
                        all(a < b for a, b in zip(offsets, offsets[1:])),
                        f"{ex['dir']}/{name}: pixel offsets are not strictly increasing",
                    )

                # a data file is filled, closed, and never returned to
                seen, order = set(), [e.filename for e in entries]
                runs = [order[0]] + [b for a, b in zip(order, order[1:]) if a != b]
                for name in runs:
                    self.assertNotIn(name, seen, f"{ex['dir']}: {name} was revisited")
                    seen.add(name)

    def test_scan_is_column_major_serpentine(self):
        """Rows advance monotonically within a column and reverse between columns."""
        entries = parse_index(str(EXAMPLES / "full-grid" / "NDTiff.index"))

        runs, current = [], [entries[0]]
        for e in entries[1:]:
            if e.column == current[-1].column:
                current.append(e)
            else:
                runs.append(current)
                current = [e]
        runs.append(current)

        self.assertEqual(len(runs), 38, "expected one contiguous run per column")
        for i, run in enumerate(runs):
            rows = [e.row for e in run]
            ascending = all(a < b for a, b in zip(rows, rows[1:]))
            descending = all(a > b for a, b in zip(rows, rows[1:]))
            self.assertTrue(ascending or descending, f"column {i} is not monotonic")
            self.assertEqual(ascending, i % 2 == 0, f"column {i} breaks the serpentine")


class TestExamplesReproduce(unittest.TestCase):
    """Regenerating an example reproduces the committed output exactly."""

    def test_committed_outputs_match_regeneration(self):
        for ex in load_manifest():
            with self.subTest(example=ex["dir"]):
                src = EXAMPLES / ex["dir"]
                with tempfile.TemporaryDirectory() as tmp:
                    out = Path(tmp) / "TileConfiguration.txt"
                    csv = Path(tmp) / "tiles.csv"
                    proc = subprocess.run(
                        [sys.executable, str(SCRIPT), str(src / "NDTiff.index"),
                         "-o", str(out), "--csv", str(csv), *ex["args"]],
                        capture_output=True, text=True,
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)

                    for name, produced in (("TileConfiguration.txt", out), ("tiles.csv", csv)):
                        committed = (src / name).read_text()
                        self.assertEqual(
                            produced.read_text(), committed,
                            f"{ex['dir']}/{name} is stale - regenerate it "
                            f"(see examples/README.md)",
                        )

    def test_line_count_and_mosaic_size(self):
        for ex in load_manifest():
            with self.subTest(example=ex["dir"]):
                text = (EXAMPLES / ex["dir"] / "TileConfiguration.txt").read_text()
                coord_lines = [
                    ln for ln in text.splitlines()
                    if ln.strip() and not ln.startswith("#") and not ln.startswith("dim")
                ]
                self.assertEqual(len(coord_lines), ex["tiles"])
                self.assertIn("dim = 2", text)

                xs, ys = [], []
                for ln in coord_lines:
                    x, y = ln.split("(")[1].rstrip(")").split(",")
                    xs.append(float(x))
                    ys.append(float(y))
                self.assertEqual(min(xs), 0.0)
                self.assertEqual(min(ys), 0.0)
                w, h = ex["tile_size"]
                self.assertEqual(round(max(xs) + w), ex["mosaic"][0])
                self.assertEqual(round(max(ys) + h), ex["mosaic"][1])


class TestOverlapModes(unittest.TestCase):
    """Percent and pixel overlap are two spellings of the same thing."""

    def _generate(self, extra):
        src = EXAMPLES / "sparse-roi" / "NDTiff.index"
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "tc.txt"
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), str(src), "-o", str(out), *extra],
                capture_output=True, text=True,
            )
            return proc, out.read_text() if out.exists() else ""

    def test_percent_and_pixels_agree(self):
        _, pct = self._generate(["--overlap", "10"])
        _, px = self._generate(["--overlap-px", "204.8"])
        self.assertEqual(pct, px)

    def test_overlap_larger_than_tile_is_rejected(self):
        proc, _ = self._generate(["--overlap-px", "3000"])
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Overlap >= tile size", proc.stderr + proc.stdout)

    def test_zero_overlap_gives_tile_sized_step(self):
        _, text = self._generate(["--overlap", "0"])
        xs = sorted({float(ln.split("(")[1].split(",")[0])
                     for ln in text.splitlines() if ln.startswith("0")})
        self.assertEqual(xs[1] - xs[0], 2048.0)


if __name__ == "__main__":
    unittest.main()
