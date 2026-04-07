"""Tests for EmojiService and related launcher fixes.

Run with:
  nix-shell -p python3Packages.emoji --run 'python3 -m pytest shell/src/tests/ -v'
or, if emoji is in the environment:
  python3 -m pytest shell/src/tests/ -v
"""

import sys
import os
import types
import unittest

# ---------------------------------------------------------------------------
# Provide a minimal PySide6 stub so tests can run without Qt installed
# ---------------------------------------------------------------------------
if "PySide6" not in sys.modules:
    pyside6 = types.ModuleType("PySide6")
    qtcore = types.ModuleType("PySide6.QtCore")

    class _QObject:
        def __init__(self, parent=None):
            pass

    def _Slot(*args, **kwargs):
        """Stub decorator — returns the function unchanged."""
        def decorator(fn):
            return fn
        # When used as bare @Slot the single arg is the decorated function.
        # Guard against type objects like str, which are also callable.
        if len(args) == 1 and callable(args[0]) and not isinstance(args[0], type):
            return args[0]
        return decorator

    qtcore.QObject = _QObject
    qtcore.Slot = _Slot

    pyside6.QtCore = qtcore
    sys.modules["PySide6"] = pyside6
    sys.modules["PySide6.QtCore"] = qtcore


# ---------------------------------------------------------------------------
# Now we can import the service (emoji lib must already be in sys.path)
# ---------------------------------------------------------------------------
# Add the shell/src tree so the import works without pip install
_src = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, os.path.abspath(_src))

from services.shared.emoji_service import (  # noqa: E402
    _build_emoji_list,
    _get_emoji_list,
    EmojiService,
    _HAS_EMOJI_LIB,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEmojiLibAvailable(unittest.TestCase):
    def test_emoji_library_imported(self):
        self.assertTrue(
            _HAS_EMOJI_LIB,
            "emoji library not available — install it: pip install emoji",
        )


@unittest.skipUnless(_HAS_EMOJI_LIB, "emoji library not installed")
class TestBuildEmojiList(unittest.TestCase):
    def setUp(self):
        self.emojis = _build_emoji_list()

    def test_returns_list(self):
        self.assertIsInstance(self.emojis, list)

    def test_non_empty(self):
        self.assertGreater(len(self.emojis), 100)

    def test_entry_structure(self):
        for e in self.emojis[:20]:
            self.assertIn("char", e)
            self.assertIn("name", e)
            self.assertIn("keywords", e)
            self.assertIsInstance(e["char"], str)
            self.assertIsInstance(e["name"], str)
            self.assertIsInstance(e["keywords"], str)

    def test_only_fully_qualified(self):
        """All entries should come from EMOJI_DATA with status == 2."""
        try:
            import emoji as _el
        except ImportError:
            self.skipTest("emoji lib not available")
        for e in self.emojis:
            data = _el.EMOJI_DATA.get(e["char"])
            self.assertIsNotNone(data, f"char {e['char']!r} not in EMOJI_DATA")
            self.assertEqual(data.get("status"), 2,
                             f"{e['char']!r} is not fully qualified")

    def test_sorted_alphabetically(self):
        names = [e["name"].lower() for e in self.emojis]
        self.assertEqual(names, sorted(names))

    def test_no_colons_in_name(self):
        for e in self.emojis:
            self.assertNotIn(":", e["name"],
                             f"Name still has colons: {e['name']!r}")

    def test_no_underscores_in_name(self):
        for e in self.emojis:
            self.assertNotIn("_", e["name"],
                             f"Name still has underscores: {e['name']!r}")

    def test_well_known_emoji_present(self):
        chars = {e["char"] for e in self.emojis}
        for expected in ("😀", "❤️", "🚀", "🐍"):
            self.assertIn(expected, chars, f"Expected emoji {expected!r} missing")

    def test_no_duplicates(self):
        chars = [e["char"] for e in self.emojis]
        self.assertEqual(len(chars), len(set(chars)), "Duplicate emoji chars found")


@unittest.skipUnless(_HAS_EMOJI_LIB, "emoji library not installed")
class TestEmojiServiceSearch(unittest.TestCase):
    def setUp(self):
        self.svc = EmojiService()

    def test_empty_query_returns_up_to_200(self):
        results = self.svc.search("")
        self.assertIsInstance(results, list)
        self.assertLessEqual(len(results), 200)
        self.assertGreater(len(results), 0)

    def test_search_face(self):
        results = self.svc.search("face")
        self.assertGreater(len(results), 0)
        for e in results:
            self.assertIn("face", e["name"].lower() + " " + e["keywords"])

    def test_search_heart(self):
        results = self.svc.search("heart")
        self.assertGreater(len(results), 0)
        names = [e["name"].lower() for e in results]
        self.assertTrue(any("heart" in n for n in names))

    def test_name_prefix_ranked_before_contains(self):
        """Entries whose name starts with the query come before ones that merely contain it."""
        results = self.svc.search("sun")
        if len(results) < 2:
            return
        prefix_indices = [i for i, e in enumerate(results)
                          if e["name"].lower().startswith("sun")]
        contains_indices = [i for i, e in enumerate(results)
                            if not e["name"].lower().startswith("sun")
                            and "sun" in e["name"].lower()]
        if prefix_indices and contains_indices:
            self.assertLess(max(prefix_indices), min(contains_indices),
                            "Prefix matches should precede contains matches")

    def test_results_capped_at_200(self):
        results = self.svc.search("a")
        self.assertLessEqual(len(results), 200)

    def test_no_results_for_nonsense(self):
        results = self.svc.search("zzzznotanemoji9999")
        self.assertEqual(results, [])

    def test_whitespace_query_same_as_empty(self):
        r1 = self.svc.search("")
        r2 = self.svc.search("   ")
        self.assertEqual(r1, r2)

    def test_case_insensitive(self):
        r_lower = self.svc.search("heart")
        r_upper = self.svc.search("HEART")
        self.assertEqual(r_lower, r_upper)

    def test_alias_search(self):
        """Search by alias term should find results (e.g. 'grinning' → 😀)."""
        results = self.svc.search("grinning")
        chars = [e["char"] for e in results]
        self.assertIn("😀", chars)

    def test_result_entries_have_required_keys(self):
        results = self.svc.search("smile")
        for e in results:
            self.assertIn("char", e)
            self.assertIn("name", e)
            self.assertIn("keywords", e)

    def test_no_duplicate_results(self):
        results = self.svc.search("face")
        chars = [e["char"] for e in results]
        self.assertEqual(len(chars), len(set(chars)), "Duplicate results returned")


@unittest.skipUnless(_HAS_EMOJI_LIB, "emoji library not installed")
class TestGetEmojiListCaching(unittest.TestCase):
    def test_same_list_returned_twice(self):
        """_get_emoji_list() should return the same list object on repeated calls."""
        a = _get_emoji_list()
        b = _get_emoji_list()
        self.assertIs(a, b, "_get_emoji_list should cache and return the same list")


if __name__ == "__main__":
    unittest.main(verbosity=2)
