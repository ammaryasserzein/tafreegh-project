"""Unified Arabic text normalization for identity, alignment, export, QA, and diffing."""

from __future__ import annotations

import re
from dataclasses import dataclass

_TASHKEEL_RE = re.compile(r"[\u064B-\u065F\u0670\u0640]")
_CITATION_SPLIT_RE = re.compile(r"(\([^)]+\))")
_WHITESPACE_RE = re.compile(r"\s+")
_TOKEN_SEP_RE = re.compile(r"[_\s]+")
_NON_WORD_RE = re.compile(r"[^\w\s]")

_HAMZA_MAP = {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا"}
_LETTER_FOLD_MAP = {**_HAMZA_MAP, "ة": "ه", "ى": "ي"}

_HAMZA_TABLE = str.maketrans(_HAMZA_MAP)
_LETTER_FOLD_TABLE = str.maketrans(_LETTER_FOLD_MAP)
_CLOSING_DELIMITERS: dict[str, str] = {")": "(", "}": "{", "]": "[", "»": "«"}


@dataclass(frozen=True)
class IndexedArabicText:
    """Normalized Arabic text paired with a character-to-source position index map."""

    source: str
    normalized: str
    pos_map: tuple[int, ...]

    def extract_span(self, norm_start: int, norm_end: int) -> tuple[int, int, str]:
        """Map a normalized [norm_start, norm_end) span back to source indices including trailing diacritics and matching closing delimiters."""
        if norm_start < 0 or norm_end <= norm_start or norm_end > len(self.normalized):
            raise ValueError(
                f"Invalid normalized span [{norm_start}, {norm_end}) for length {len(self.normalized)}"
            )
        orig_start = self.pos_map[norm_start]
        orig_end = self.pos_map[norm_end - 1] + 1
        while orig_end < len(self.source) and has_tashkeel(self.source[orig_end]):
            orig_end += 1

        while orig_end < len(self.source):
            next_ch = self.source[orig_end]
            canon_slice = self.source[orig_start:orig_end]
            opener = _CLOSING_DELIMITERS.get(next_ch)
            if opener is not None and canon_slice.count(opener) > canon_slice.count(next_ch):
                orig_end += 1
                continue
            if next_ch == '"' and canon_slice.count('"') % 2 != 0:
                orig_end += 1
                continue
            break

        return orig_start, orig_end, self.source[orig_start:orig_end]


def strip_tashkeel(text: str) -> str:
    """Remove Arabic diacritics and tatweel from text."""
    return _TASHKEEL_RE.sub("", text)


def has_tashkeel(text: str) -> bool:
    """Return True when text contains any Arabic diacritic or tatweel."""
    return bool(_TASHKEEL_RE.search(text))


def strip_tashkeel_preserving_citations(text: str) -> str:
    """Strip diacritics from fallback prose while keeping parenthesized citations verbatim."""
    parts = _CITATION_SPLIT_RE.split(text)
    return "".join(
        part if (part.startswith("(") and part.endswith(")")) else strip_tashkeel(part)
        for part in parts
    )


def collapse_whitespace(text: str) -> str:
    """Collapse consecutive whitespace into single spaces and trim both ends."""
    if not text:
        return ""
    return _WHITESPACE_RE.sub(" ", text).strip()


def normalize_arabic(text: str) -> str:
    """Fold hamzas/alif-wasl and collapse whitespace while preserving diacritics, ta-marbuta, alif-maqsura, and punctuation."""
    if not text:
        return ""
    return collapse_whitespace(text.translate(_HAMZA_TABLE))


def normalize_arabic_token(text: str) -> str:
    """Canonicalize an identifier/routing token by folding hamza/ta-marbuta/alif-maqsura and underscores."""
    if not text:
        return ""
    folded = text.translate(_LETTER_FOLD_TABLE)
    return _TOKEN_SEP_RE.sub(" ", folded).strip()


def normalize_arabic_search(text: str) -> str:
    """Canonicalize Arabic text for tolerant substring matching across diacritics, letters, and punctuation."""
    if not text:
        return ""
    folded = strip_tashkeel(text).translate(_LETTER_FOLD_TABLE)
    cleaned = _NON_WORD_RE.sub(" ", folded)
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def build_search_index(source: str) -> IndexedArabicText:
    """Normalize source for search while recording each normalized character's source index."""
    norm_chars: list[str] = []
    pos_map: list[int] = []
    prev_was_space = False

    for idx, ch in enumerate(source):
        if _TASHKEEL_RE.match(ch):
            continue

        norm_c = _LETTER_FOLD_MAP.get(ch, ch)
        if norm_c.isspace() or _NON_WORD_RE.match(norm_c):
            norm_c = " "

        if norm_c == " ":
            if not prev_was_space and norm_chars:
                norm_chars.append(" ")
                pos_map.append(idx)
                prev_was_space = True
        else:
            norm_chars.append(norm_c)
            pos_map.append(idx)
            prev_was_space = False

    if norm_chars and norm_chars[-1] == " ":
        norm_chars.pop()
        pos_map.pop()

    return IndexedArabicText(
        source=source,
        normalized="".join(norm_chars),
        pos_map=tuple(pos_map),
    )
