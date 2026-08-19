"""
Static checks on ndtiff_index_to_tileconfig.ijm.

There is no ImageJ in CI, so the macro cannot be executed here. These are the
next best thing: structural checks for the specific ways an ImageJ macro breaks
silently. They will not catch logic errors, but they catch the footguns that
produce a macro which loads fine and then misbehaves at runtime.

Run:  python -m unittest discover -s tests -v
"""

import re
import unittest
from pathlib import Path

MACRO = Path(__file__).resolve().parent.parent / "ndtiff_index_to_tileconfig.ijm"


def strip_noise(src: str) -> str:
    """Remove block comments, line comments, and string literals."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    src = re.sub(r"//[^\n]*", "", src)
    # string literals, honouring backslash escapes
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    return src


class TestMacroStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = MACRO.read_text()
        cls.code = strip_noise(cls.raw)

    def test_macro_exists_and_is_not_empty(self):
        self.assertTrue(MACRO.is_file(), f"{MACRO} is missing")
        self.assertGreater(len(self.raw), 1000)

    def test_brackets_balanced(self):
        pairs = {")": "(", "]": "[", "}": "{"}
        stack, line = [], 1
        for ch in self.code:
            if ch == "\n":
                line += 1
            elif ch in "([{":
                stack.append((ch, line))
            elif ch in pairs:
                self.assertTrue(stack, f"unmatched '{ch}' on line {line}")
                opened, opened_line = stack.pop()
                self.assertEqual(
                    opened, pairs[ch],
                    f"'{opened}' from line {opened_line} closed by '{ch}' on line {line}",
                )
        self.assertFalse(stack, f"unclosed {[s[0] for s in stack]} opened at {[s[1] for s in stack]}")

    def test_dialog_getters_match_adders(self):
        """
        The classic ImageJ macro bug. Dialog.getX() reads from a per-type queue
        in the order the fields were added -- there is no name lookup. If the
        number of adds and gets diverges for any type, every value after the
        divergence is silently wrong or the macro errors at runtime.

        Conditional fields (the z-step, added only when nZ > 1) must be read
        under the same condition, which keeps these counts equal too.
        """
        for kind in ("Number", "String", "Choice", "Checkbox"):
            adds = len(re.findall(rf"\bDialog\.add{kind}\s*\(", self.code))
            gets = len(re.findall(rf"\bDialog\.get{kind}\s*\(", self.code))
            self.assertEqual(
                adds, gets,
                f"Dialog.add{kind} appears {adds}x but Dialog.get{kind} {gets}x - "
                f"the {kind.lower()} queue is misaligned",
            )

    def test_no_continue_statement(self):
        """
        `continue` is not dependably supported by the ImageJ macro language.
        Loops here use if/else or an explicit flag instead.
        """
        hits = [
            i for i, ln in enumerate(self.code.splitlines(), 1)
            if re.search(r"\bcontinue\b", ln)
        ]
        self.assertFalse(hits, f"`continue` used on line(s) {hits}")

    def test_every_called_function_is_defined(self):
        defined = set(re.findall(r"\bfunction\s+(\w+)\s*\(", self.code))
        self.assertTrue(defined, "no function definitions found")

        # ImageJ built-ins the macro relies on; anything else must be local.
        builtin = {
            "if", "for", "while", "return", "print", "exit", "newArray", "lengthOf",
            "substring", "indexOf", "parseInt", "parseFloat", "isNaN", "d2s", "round",
            "floor", "toString", "fromCharCode", "call", "getBoolean", "showMessage",
            "getProfile", "getImageID", "selectImage", "close", "makeRectangle",
            "setBatchMode", "run", "open", "eval",
        }
        called = set(re.findall(r"(?<![.\w])(\w+)\s*\(", self.code)) - {"function"}
        unknown = called - defined - builtin
        self.assertFalse(unknown, f"called but never defined: {sorted(unknown)}")

    def test_no_duplicate_function_definitions(self):
        names = re.findall(r"\bfunction\s+(\w+)\s*\(", self.code)
        dupes = {n for n in names if names.count(n) > 1}
        self.assertFalse(dupes, f"defined more than once: {sorted(dupes)}")

    def test_globals_used_by_helpers_are_declared(self):
        """
        Variables shared between top-level code and functions must be declared
        with `var` at the top, or the function gets its own empty local.
        """
        for name in ("B", "pos"):
            self.assertTrue(
                re.search(rf"^\s*var\s+{name}\b", self.code, re.MULTILINE),
                f"`{name}` is used inside a function but not declared with `var`",
            )

    def test_pad_arguments_are_integers(self):
        """
        IJ.pad() expects an int; a value straight from Dialog.getNumber() is a
        double and can render as e.g. '0.0'. Digit/index reads are rounded.
        """
        self.assertRegex(self.code, r"digits\s*=\s*round\s*\(\s*Dialog\.getNumber")
        self.assertRegex(self.code, r"first\s*=\s*round\s*\(\s*Dialog\.getNumber")

    def test_raw_import_is_used_for_binary_read(self):
        """
        File.openAsRawString() corrupts bytes > 127. The macro must read the
        index through an 8-bit raw import instead.
        """
        self.assertNotIn("openAsRawString", self.code)
        self.assertRegex(self.code, r'run\s*\(\s*""\s*,\s*""')  # run("Raw...", "open=...")
        self.assertIn("getProfile()", self.raw)

    def test_output_files_are_closed(self):
        opens = len(re.findall(r"=\s*File\.open\s*\(", self.code))
        closes = len(re.findall(r"\bFile\.close\s*\(", self.code))
        self.assertEqual(opens, closes, "every File.open() needs a matching File.close()")


if __name__ == "__main__":
    unittest.main()
