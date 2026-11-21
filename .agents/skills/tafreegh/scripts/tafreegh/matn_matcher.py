"""Dynamic Fallback Interleaving & Sequential Matn Cursor.

Implements ADR 0002:
- Tracks position in canonical Matn source via Sequential Cursor.
- Forward look-ahead search (~2000 chars) for standard flow.
- Look-behind search across entire previously read range (0 -> cursor) for sentence re-reads.
- Dynamic fallback switching on double-miss.
- Context-dependent Conservative Doubt rule (sandwiched fallback detection).
- Visual tagging with <!-- fallback --> in intermediate markdown.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from .arabic_normalizer import (
    build_search_index,
    collapse_whitespace,
    normalize_arabic_search,
    strip_tashkeel_preserving_citations,
)


class MatchMode(str, Enum):
    PRIMARY = "primary"
    FALLBACK = "fallback"


@dataclass
class MatnMatchResult:
    mode: MatchMode
    text: str
    start_pos: int
    end_pos: int
    is_fallback: bool
    is_re_read: bool = False
    is_sandwiched: bool = False

    @property
    def is_source_anchored(self) -> bool:
        """True when this segment (Primary or compound Sharh+Matn) anchored to canonical source coordinates."""
        return self.start_pos >= 0


@dataclass(frozen=True)
class MatnCursorSnapshot:
    """Read-only snapshot of SequentialMatnMatcher alignment cursor and history size."""

    cursor: int
    cursor_norm: int
    history_length: int


COMPOUND_SHARH_SPLIT_RE = re.compile(
    r"^((?:.*?\s)?(?:[وفك]?(?:بقوله|في قوله|قوله|لقوله(?:\s+[^:،\n]{1,35})?|(?:قال|يقول)\s+(?:الشيخ|الإمام|المصنف|ابن|أبو|القاضي|الحافظ)\s+[^:،\n]{1,35})|ثم\s+أنشد\s+قائل\u064B?ا\u064B?)\s*[،:]\s*)(.+)$"
)

_LINEBREAK_RUN_RE = re.compile(r"[ \t]*(?:\r?\n|\r)+[ \t]*")
_TRAILING_PUNCT_CHARS = frozenset("،.:!؟")
_collapse_whitespace = collapse_whitespace


def _normalize_nfc_collapsed(text: str) -> str:
    """Collapse whitespace and normalize Unicode combining mark order to NFC."""
    return unicodedata.normalize("NFC", _collapse_whitespace(text))


def collapse_linebreaks(text: str) -> str:
    """Collapse internal line breaks and surrounding horizontal whitespace into single spaces."""
    if "\n" not in text and "\r" not in text:
        return text
    return _LINEBREAK_RUN_RE.sub(" ", text).strip()


class SequentialMatnMatcher:
    def __init__(self, matn_source: str, forward_lookahead: int = 2000):
        self.source = matn_source
        self.forward_lookahead = forward_lookahead
        self._cursor = 0
        self._cursor_norm = 0
        self._active_norm_pos = 0
        self.history: list[MatnMatchResult] = []

        self._search_index = build_search_index(self.source)
        self._collapsed_source = _normalize_nfc_collapsed(self.source)

    @property
    def cursor(self) -> int:
        """Read-only source character offset of the high-water Sequential Cursor."""
        return self._cursor

    @property
    def cursor_norm(self) -> int:
        """Read-only normalized character offset of the high-water Sequential Cursor."""
        return self._cursor_norm

    def snapshot(self) -> MatnCursorSnapshot:
        """Returns an immutable snapshot of cursor offsets and recorded history count."""
        return MatnCursorSnapshot(
            cursor=self._cursor,
            cursor_norm=self._cursor_norm,
            history_length=len(self.history),
        )

    def _forward_window(self) -> tuple[int, int]:
        """Returns [search_start, window_end) in normalized source coordinates."""
        overlap = 300
        search_start = max(0, self._cursor_norm - overlap)
        window_end = min(
            len(self._search_index.normalized),
            self._cursor_norm + self.forward_lookahead,
        )
        return search_start, window_end

    def contains_verbatim(self, text: str) -> bool:
        """Returns True when whitespace-collapsed NFC text appears verbatim in canonical Matn source."""
        collapsed = _normalize_nfc_collapsed(text)
        return bool(collapsed and collapsed in self._collapsed_source)

    def contains_normalized(self, text: str) -> bool:
        """Returns True when normalized Arabic text matches anywhere in canonical Matn source."""
        norm_q = normalize_arabic_search(text)
        return bool(norm_q and norm_q in self._search_index.normalized)

    def advance_to_canonical_occurrence(self, text: str) -> bool:
        """Advances cursor to the next canonical verbatim occurrence ahead of cursor; returns True if moved."""
        collapsed = _normalize_nfc_collapsed(text)
        norm_q = normalize_arabic_search(text)
        if not collapsed or not norm_q:
            return False

        norm_source = self._search_index.normalized
        pos = self._cursor_norm
        while pos <= len(norm_source) - len(norm_q):
            idx = norm_source.find(norm_q, pos)
            if idx == -1:
                return False
            norm_end = idx + len(norm_q)
            orig_start, orig_end, canon_slice = self._search_index.extract_span(idx, norm_end)
            pad = max(4, len(collapsed) - len(canon_slice) + 4)
            lo = max(0, orig_start - pad)
            hi = min(len(self.source), orig_end + pad)
            if collapsed in _normalize_nfc_collapsed(self.source[lo:hi]):
                self._cursor_norm = norm_end
                self._active_norm_pos = norm_end
                self._cursor = orig_end
                return True
            pos = idx + 1
        return False

    def _record_anchored_match(
        self,
        norm_start: int,
        norm_end: int,
        *,
        mode: MatchMode,
        is_fallback: bool,
        is_re_read: bool,
        prefix: str = "",
        spoken_segment: str = "",
    ) -> MatnMatchResult:
        """Extracts canonical slice, advances cursor when forward, records history, and returns result."""
        orig_start, orig_end, canon_slice = self._search_index.extract_span(norm_start, norm_end)
        trailing = spoken_segment.rstrip()
        if trailing and trailing[-1] in _TRAILING_PUNCT_CHARS:
            if orig_end < len(self.source) and self.source[orig_end] == trailing[-1]:
                orig_end += 1
                canon_slice = self.source[orig_start:orig_end]
        self._active_norm_pos = norm_end
        if not is_re_read:
            self._cursor_norm = norm_end
            self._cursor = orig_end
        canon_slice = collapse_linebreaks(canon_slice)
        res = MatnMatchResult(
            mode=mode,
            text=f"{prefix}{canon_slice}",
            start_pos=orig_start,
            end_pos=orig_end,
            is_fallback=is_fallback,
            is_re_read=is_re_read,
        )
        self.history.append(res)
        return res

    def _is_whole_word_span(self, norm_start: int, norm_end: int) -> bool:
        """Checks that [norm_start:norm_end] lies on token boundaries in normalized source."""
        norm_source = self._search_index.normalized
        left_ok = norm_start == 0 or norm_source[norm_start - 1] == " "
        right_ok = norm_end == len(norm_source) or norm_source[norm_end] == " "
        return left_ok and right_ok

    def _find_whole_word(self, start: int, end: int, query: str, reverse: bool = False) -> int:
        """Finds query on token boundaries within normalized source[start:end]. Returns absolute norm index or -1."""
        if not query or end <= start:
            return -1
        norm_source = self._search_index.normalized
        if not reverse:
            pos = start
            while pos <= end - len(query):
                idx = norm_source.find(query, pos, end)
                if idx == -1:
                    return -1
                if self._is_whole_word_span(idx, idx + len(query)):
                    return idx
                pos = idx + 1
            return -1
        pos = end
        while pos - start >= len(query):
            idx = norm_source.rfind(query, start, pos)
            if idx == -1:
                return -1
            if self._is_whole_word_span(idx, idx + len(query)):
                return idx
            pos = idx
        return -1

    def _match_compound_sharh_matn(self, spoken_segment: str) -> MatnMatchResult | None:
        """Matches compound Fallback-Sharh prefix + Primary-Matn tail (e.g. 'ثم بين وجه ذلك بقوله، وَذَلِكَ')."""
        cleaned = strip_tashkeel_preserving_citations(spoken_segment).strip()
        m = COMPOUND_SHARH_SPLIT_RE.match(cleaned)
        if not m:
            return None

        sharh_prefix, raw_tail = m.group(1), m.group(2)
        tail_query = normalize_arabic_search(raw_tail)
        if not tail_query or len(tail_query) < 3:
            return None

        norm_source = self._search_index.normalized
        is_single_word = " " not in tail_query
        if is_single_word:
            # Single-word tail must sit in a tight 120-char forward window at active reading position (or high-water cursor)
            norm_start = -1
            for base_pos in dict.fromkeys((self._active_norm_pos, self._cursor_norm)):
                win_end = min(len(norm_source), base_pos + 120)
                norm_start = self._find_whole_word(base_pos, win_end, tail_query, reverse=False)
                if norm_start != -1:
                    break
            if norm_start == -1:
                return None
            norm_end = norm_start + len(tail_query)
            return self._record_anchored_match(
                norm_start,
                norm_end,
                mode=MatchMode.FALLBACK,
                is_fallback=True,
                is_re_read=norm_end <= self._cursor_norm,
                prefix=sharh_prefix,
                spoken_segment=spoken_segment,
            )

        # Multi-word tail: standard forward window then look-behind
        search_start, window_end = self._forward_window()
        norm_start = self._find_whole_word(search_start, window_end, tail_query, reverse=False)
        if norm_start != -1 and (norm_start + len(tail_query)) > self._cursor_norm:
            return self._record_anchored_match(
                norm_start,
                norm_start + len(tail_query),
                mode=MatchMode.FALLBACK,
                is_fallback=True,
                is_re_read=False,
                prefix=sharh_prefix,
                spoken_segment=spoken_segment,
            )

        idx_behind = self._find_whole_word(0, self._cursor_norm, tail_query, reverse=True)
        if idx_behind != -1:
            return self._record_anchored_match(
                idx_behind,
                idx_behind + len(tail_query),
                mode=MatchMode.FALLBACK,
                is_fallback=True,
                is_re_read=True,
                prefix=sharh_prefix,
                spoken_segment=spoken_segment,
            )

        return None

    def _create_fallback_result(self, spoken_segment: str) -> MatnMatchResult:
        res = MatnMatchResult(
            mode=MatchMode.FALLBACK,
            text=strip_tashkeel_preserving_citations(spoken_segment).strip(),
            start_pos=-1,
            end_pos=-1,
            is_fallback=True
        )
        self.history.append(res)
        return res

    def match_segment(self, spoken_segment: str) -> MatnMatchResult:
        """
        Attempts to match spoken segment using sequential cursor:
        1. Forward search in window [cursor_norm : cursor_norm + forward_lookahead]
        2. Look-behind search in range [0 : cursor_norm] for re-reads
        3. Compound Fallback-Sharh prefix + Primary-Matn tail
        4. Double-miss -> Fallback mode
        """
        search_query = normalize_arabic_search(spoken_segment)
        if not search_query or len(search_query) < 3:
            return self._create_fallback_result(spoken_segment)

        norm_source = self._search_index.normalized

        # 1. Forward search (allowing overlap for re-read prefixes extending into new text)
        search_start, window_end = self._forward_window()
        forward_slice = norm_source[search_start:window_end]

        idx_forward = forward_slice.find(search_query)
        if idx_forward != -1:
            norm_start = search_start + idx_forward
            norm_end = norm_start + len(search_query)
            if norm_end > self._cursor_norm:
                return self._record_anchored_match(
                    norm_start,
                    norm_end,
                    mode=MatchMode.PRIMARY,
                    is_fallback=False,
                    is_re_read=False,
                    spoken_segment=spoken_segment,
                )

        # 2. Look-behind search (0 -> cursor_norm)
        lookbehind_slice = norm_source[:self._cursor_norm]
        idx_behind = lookbehind_slice.rfind(search_query)
        if idx_behind != -1:
            return self._record_anchored_match(
                idx_behind,
                idx_behind + len(search_query),
                mode=MatchMode.PRIMARY,
                is_fallback=False,
                is_re_read=True,
                spoken_segment=spoken_segment,
            )

        # 3. Compound Sharh prefix + Primary Matn tail (e.g. 'ثم بين وجه ذلك بقوله، وَذَلِكَ')
        compound_res = self._match_compound_sharh_matn(spoken_segment)
        if compound_res is not None:
            return compound_res

        # 4. Double-miss: Fallback Mode
        return self._create_fallback_result(spoken_segment)

    def resolve_sandwiched_fallbacks(self) -> None:
        """Identifies unanchored fallback segments bounded before and after by source-anchored matches."""
        first_anchored = next((i for i, h in enumerate(self.history) if h.is_source_anchored), None)
        last_anchored = next(
            (i for i in range(len(self.history) - 1, -1, -1) if self.history[i].is_source_anchored),
            None,
        )

        for i, item in enumerate(self.history):
            if item.mode == MatchMode.FALLBACK and not item.is_source_anchored:
                item.is_sandwiched = (
                    first_anchored is not None
                    and last_anchored is not None
                    and first_anchored < i < last_anchored
                )


def format_matn_segment(result: MatnMatchResult) -> str:
    """Formats matn segment for intermediate markdown."""
    clean_text = collapse_linebreaks(result.text.strip())
    if result.is_fallback:
        return f"<!-- fallback -->\n**({clean_text})**"
    return f"**({clean_text})**"


def generate_fallback_summary(matcher: SequentialMatnMatcher) -> str:
    """Generates a summary block of dynamic fallback interleaving."""
    matcher.resolve_sandwiched_fallbacks()
    total = len(matcher.history)
    primary = sum(1 for h in matcher.history if h.mode == MatchMode.PRIMARY)
    reread = sum(1 for h in matcher.history if h.is_re_read)
    fallback = sum(1 for h in matcher.history if h.mode == MatchMode.FALLBACK)
    sandwiched = sum(1 for h in matcher.history if h.is_sandwiched)

    lines = [
        "### تقرير المتن الهجين (Dynamic Fallback Interleaving Summary)",
        f"- إجمالي مقاطع المتن: {total}",
        f"- مطابقة أصلية (Primary Mode): {primary} (منها {reread} إعادة قراءة / Re-read)",
        f"- مقاطع Fallback (بدون تشكيل): {fallback} (منها {sandwiched} بين مقطعين موثقين / Sandwiched)",
    ]

    if fallback > 0:
        lines.append("\n**تفصيل مقاطع Fallback:**")
        fb_idx = 1
        for i, h in enumerate(matcher.history):
            if h.mode == MatchMode.FALLBACK:
                context_label = "محصور بين متنين (مخفف الشك)" if h.is_sandwiched else "منفرد (صارم الشك)"
                snippet = h.text[:40] + ("..." if len(h.text) > 40 else "")
                lines.append(f"  {fb_idx}. المقطع #{i + 1}: \"{snippet}\" [{context_label}]")
                fb_idx += 1

    return "\n".join(lines)
