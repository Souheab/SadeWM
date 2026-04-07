"""EmojiService — emoji search and clipboard copy."""

import subprocess

try:
    import emoji as _emoji_lib
    _HAS_EMOJI_LIB = True
except ImportError:
    _HAS_EMOJI_LIB = False

from PySide6.QtCore import QObject, Slot

# Fully-qualified emoji only (status == 2); gives ~3900 canonical entries.
_FULLY_QUALIFIED = 2


def _build_emoji_list():
    """Build a sorted list of emoji dicts from the emoji library."""
    if not _HAS_EMOJI_LIB:
        return []

    result = []
    for char, data in _emoji_lib.EMOJI_DATA.items():
        if data.get("status") != _FULLY_QUALIFIED:
            continue

        # Name: strip surrounding colons and replace underscores with spaces
        raw_name = data.get("en", "").strip(":")
        name = raw_name.replace("_", " ")

        # Aliases: additional search terms from the alias list
        aliases = [a.strip(":").replace("_", " ")
                   for a in data.get("alias", [])]

        # keywords = name words + alias words (deduplicated, lower-case)
        kw_set: dict[str, None] = {}
        for word in name.lower().split():
            kw_set[word] = None
        for alias in aliases:
            for word in alias.lower().split():
                kw_set[word] = None
        keywords = " ".join(kw_set.keys())

        result.append({
            "char": char,
            "name": name.title(),
            "keywords": keywords,
        })

    result.sort(key=lambda e: e["name"].lower())
    return result


_EMOJI_LIST: list | None = None


def _get_emoji_list() -> list:
    global _EMOJI_LIST
    if _EMOJI_LIST is None:
        _EMOJI_LIST = _build_emoji_list()
    return _EMOJI_LIST


class EmojiService(QObject):
    """Service that provides emoji search and clipboard copy."""

    def __init__(self, parent=None):
        super().__init__(parent)

    @Slot(str, result="QVariantList")
    def search(self, query: str) -> list:
        q = query.strip().lower()
        emojis = _get_emoji_list()
        if not q:
            return emojis[:200]

        # Tier 1: exact char match
        tier1 = [e for e in emojis if e["char"] == q]
        matched = set(id(e) for e in tier1)
        # Tier 2: name starts with query
        tier2 = [e for e in emojis if id(e) not in matched
                 and e["name"].lower().startswith(q)]
        matched.update(id(e) for e in tier2)
        # Tier 3: name contains query
        tier3 = [e for e in emojis if id(e) not in matched
                 and q in e["name"].lower()]
        matched.update(id(e) for e in tier3)
        # Tier 4: keyword match
        tier4 = [e for e in emojis if id(e) not in matched
                 and q in e["keywords"]]

        return (tier1 + tier2 + tier3 + tier4)[:200]

    @Slot(str)
    def copyToClipboard(self, char: str) -> None:
        """Copy the given character to the X11 clipboard and primary selection."""
        encoded = char.encode("utf-8")
        for sel in ("clipboard", "primary"):
            try:
                p = subprocess.Popen(
                    ["xclip", "-selection", sel],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                p.communicate(input=encoded)
            except FileNotFoundError:
                # xclip not available; try xsel as fallback
                try:
                    flag = "--clipboard" if sel == "clipboard" else "--primary"
                    p = subprocess.Popen(
                        ["xsel", flag, "--input"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    p.communicate(input=encoded)
                except FileNotFoundError:
                    pass
            except Exception:
                pass
