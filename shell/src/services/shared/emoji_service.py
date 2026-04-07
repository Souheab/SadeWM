"""EmojiService — emoji search and clipboard copy."""

import os
import subprocess
import unicodedata

from PySide6.QtCore import QObject, Signal, Slot


def _build_emoji_list():
    """Build a list of emoji dicts with name, char, and keywords."""
    emojis = []
    # Iterate over Unicode codepoints in known emoji ranges
    # We use a curated set of ranges that contain the most common emojis
    ranges = [
        (0x1F600, 0x1F64F),  # Emoticons
        (0x1F300, 0x1F5FF),  # Misc symbols and pictographs
        (0x1F680, 0x1F6FF),  # Transport and map
        (0x1F700, 0x1F77F),  # Alchemical symbols
        (0x1F780, 0x1F7FF),  # Geometric shapes extended
        (0x1F800, 0x1F8FF),  # Supplemental arrows-C
        (0x1F900, 0x1F9FF),  # Supplemental symbols and pictographs
        (0x1FA00, 0x1FA6F),  # Chess symbols
        (0x1FA70, 0x1FAFF),  # Symbols and pictographs extended-A
        (0x2600, 0x26FF),    # Miscellaneous symbols
        (0x2700, 0x27BF),    # Dingbats
        (0x231A, 0x231B),    # Watch, hourglass
        (0x23E9, 0x23F3),    # Various clocks/arrows
        (0x23F8, 0x23FA),    # Pause, stop, record
        (0x25AA, 0x25AB),    # Small squares
        (0x25B6, 0x25B6),    # Play button
        (0x25C0, 0x25C0),    # Reverse button
        (0x25FB, 0x25FE),    # Squares
        (0x2614, 0x2615),    # Umbrella with rain, hot beverage
        (0x2648, 0x2653),    # Zodiac
        (0x267F, 0x267F),    # Wheelchair
        (0x2693, 0x2693),    # Anchor
        (0x26A1, 0x26A1),    # Lightning
        (0x26AA, 0x26AB),    # Circles
        (0x26BD, 0x26BE),    # Soccer, baseball
        (0x26C4, 0x26C5),    # Snowman, sun behind cloud
        (0x26CE, 0x26CE),    # Ophiuchus
        (0x26D4, 0x26D4),    # No entry
        (0x26EA, 0x26EA),    # Church
        (0x26F2, 0x26F3),    # Fountain, golf
        (0x26F5, 0x26F5),    # Sailboat
        (0x26FA, 0x26FA),    # Tent
        (0x26FD, 0x26FD),    # Fuel pump
        (0x2702, 0x2702),    # Scissors
        (0x2705, 0x2705),    # Check mark
        (0x2708, 0x2709),    # Airplane, envelope
        (0x270A, 0x270B),    # Fists
        (0x270C, 0x270D),    # Victory, writing hand
        (0x270F, 0x270F),    # Pencil
        (0x2712, 0x2712),    # Black nib
        (0x2714, 0x2714),    # Check mark
        (0x2716, 0x2716),    # X
        (0x271D, 0x271D),    # Latin cross
        (0x2721, 0x2721),    # Star of David
        (0x2728, 0x2728),    # Sparkles
        (0x2733, 0x2734),    # Eight-spoked asterisk
        (0x2744, 0x2744),    # Snowflake
        (0x2747, 0x2747),    # Sparkle
        (0x274C, 0x274C),    # Cross mark
        (0x274E, 0x274E),    # Cross mark button
        (0x2753, 0x2755),    # Question marks
        (0x2757, 0x2757),    # Exclamation mark
        (0x2763, 0x2764),    # Exclamation, heart
        (0x2795, 0x2797),    # Plus, minus, division
        (0x27A1, 0x27A1),    # Right arrow
        (0x27B0, 0x27B0),    # Curly loop
        (0x27BF, 0x27BF),    # Double curly loop
        (0x2934, 0x2935),    # Arrows
        (0x2B05, 0x2B07),    # Arrows
        (0x2B1B, 0x2B1C),    # Squares
        (0x2B50, 0x2B50),    # Star
        (0x2B55, 0x2B55),    # Circle
        (0x3030, 0x3030),    # Wavy dash
        (0x303D, 0x303D),    # Part alternation mark
        (0x3297, 0x3297),    # Circled ideograph congratulation
        (0x3299, 0x3299),    # Circled ideograph secret
        # Flags (regional indicator symbols)
        (0x1F1E0, 0x1F1FF),
        # Keycap number signs
        (0x24C2, 0x24C2),
    ]

    seen = set()
    for start, end in ranges:
        for cp in range(start, end + 1):
            char = chr(cp)
            try:
                name = unicodedata.name(char, "")
            except Exception:
                name = ""
            if not name:
                continue
            if char in seen:
                continue
            seen.add(char)
            # Build keywords from name words (lower-case, deduplicated)
            keywords = list(dict.fromkeys(name.lower().split()))
            emojis.append({
                "char": char,
                "name": name.title(),
                "keywords": " ".join(keywords),
            })

    return emojis


_EMOJI_LIST = None


def _get_emoji_list():
    global _EMOJI_LIST
    if _EMOJI_LIST is None:
        _EMOJI_LIST = _build_emoji_list()
    return _EMOJI_LIST


class EmojiService(QObject):
    """Service that provides emoji search and clipboard copy."""

    def __init__(self, parent=None):
        super().__init__(parent)

    @Slot(str, result="QVariantList")
    def search(self, query):
        q = query.strip().lower()
        emojis = _get_emoji_list()
        if not q:
            return emojis[:200]
        results = []
        # Exact char match first
        for e in emojis:
            if e["char"] == q:
                results.append(e)
        remaining = [e for e in emojis if e not in results]
        # Name starts with
        prefix = [e for e in remaining if e["name"].lower().startswith(q)]
        results.extend(prefix)
        remaining = [e for e in remaining if e not in prefix]
        # Name contains
        contains = [e for e in remaining if q in e["name"].lower()]
        results.extend(contains)
        remaining = [e for e in remaining if e not in contains]
        # Keywords contain
        kw = [e for e in remaining if q in e["keywords"]]
        results.extend(kw)
        return results[:200]

    @Slot(str)
    def copyToClipboard(self, char):
        """Copy the given character to the X11 clipboard and primary selection."""
        # Try xclip first, then xdotool type, then xsel
        try:
            p = subprocess.Popen(
                ["xclip", "-selection", "clipboard"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            p.communicate(input=char.encode("utf-8"))
        except FileNotFoundError:
            pass
        except Exception:
            pass
        # Also set primary selection
        try:
            p = subprocess.Popen(
                ["xclip", "-selection", "primary"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            p.communicate(input=char.encode("utf-8"))
        except FileNotFoundError:
            pass
        except Exception:
            pass
