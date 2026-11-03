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
from dataclasses import dataclass
from enum import Enum


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


TASHKEEL_REGEX = re.compile(r'[\u064B-\u065F\u0670\u0640]')
COMPOUND_SHARH_SPLIT_RE = re.compile(
    r"^(.+?(?:بقوله|في قوله|قوله)\s*[،:]\s*)(.+)$"
)


def strip_tashkeel(text: str) -> str:
    """Removes Arabic diacritics and tatweel."""
    return TASHKEEL_REGEX.sub('', text)


def strip_tashkeel_preserving_citations(text: str) -> str:
    """Removes Arabic diacritics from fallback text while preserving vowelized parenthesized citations (...) inside it."""
    parts = re.split(r'(\([^)]+\))', text)
    return "".join(
        part if (part.startswith('(') and part.endswith(')')) else strip_tashkeel(part)
        for part in parts
    )


def normalize_arabic_search(text: str) -> str:
    """Normalizes Arabic text for tolerant substring matching."""
    t = strip_tashkeel(text)
    t = re.sub(r'[أإآٱ]', 'ا', t)
    t = re.sub(r'ة', 'ه', t)
    t = re.sub(r'ى', 'ي', t)
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


class SequentialMatnMatcher:
    def __init__(self, matn_source: str, forward_lookahead: int = 2000):
        self.source = matn_source
        self.forward_lookahead = forward_lookahead
        self.cursor = 0
        self.cursor_norm = 0
        self._active_norm_pos = 0
        self.history: list[MatnMatchResult] = []

        # Build position mapping from normalized characters back to source indices
        self.norm_chars: list[str] = []
        self.pos_map: list[int] = []
        prev_was_space = False

        for idx, ch in enumerate(self.source):
            if TASHKEEL_REGEX.match(ch):
                continue

            norm_c = ch
            if norm_c in 'أإآٱ':
                norm_c = 'ا'
            elif norm_c == 'ة':
                norm_c = 'ه'
            elif norm_c == 'ى':
                norm_c = 'ي'
            elif re.match(r'[^\w\s]', norm_c) or norm_c.isspace():
                norm_c = ' '

            if norm_c == ' ':
                if not prev_was_space and self.norm_chars:
                    self.norm_chars.append(' ')
                    self.pos_map.append(idx)
                    prev_was_space = True
            else:
                self.norm_chars.append(norm_c)
                self.pos_map.append(idx)
                prev_was_space = False

        # Strip trailing space if any
        if self.norm_chars and self.norm_chars[-1] == ' ':
            self.norm_chars.pop()
            self.pos_map.pop()

        self.norm_source = "".join(self.norm_chars)
        self._collapsed_source = re.sub(r"\s+", " ", self.source).strip()

    def _extract_original_slice(self, norm_start: int, norm_end: int) -> tuple[int, int, str]:
        """Calculates exact coordinates and extracts original slice preserving tashkeel and punctuation."""
        orig_start = self.pos_map[norm_start]
        last_char_idx = self.pos_map[norm_end - 1]
        orig_end = last_char_idx + 1
        while orig_end < len(self.source) and TASHKEEL_REGEX.match(self.source[orig_end]):
            orig_end += 1
        return orig_start, orig_end, self.source[orig_start:orig_end]

    def _record_anchored_match(
        self,
        norm_start: int,
        norm_end: int,
        *,
        mode: MatchMode,
        is_fallback: bool,
        is_re_read: bool,
        prefix: str = "",
    ) -> MatnMatchResult:
        """Extracts canonical slice, advances cursor when forward, records history, and returns result."""
        orig_start, orig_end, canon_slice = self._extract_original_slice(norm_start, norm_end)
        self._active_norm_pos = norm_end
        if not is_re_read:
            self.cursor_norm = norm_end
            self.cursor = orig_end
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
        """Checks that [norm_start:norm_end] lies on token boundaries in self.norm_source."""
        left_ok = norm_start == 0 or self.norm_source[norm_start - 1] == " "
        right_ok = norm_end == len(self.norm_source) or self.norm_source[norm_end] == " "
        return left_ok and right_ok

    def _find_whole_word(self, start: int, end: int, query: str, reverse: bool = False) -> int:
        """Finds query on token boundaries within self.norm_source[start:end]. Returns absolute norm index or -1."""
        if not query or end <= start:
            return -1
        if not reverse:
            pos = start
            while pos <= end - len(query):
                idx = self.norm_source.find(query, pos, end)
                if idx == -1:
                    return -1
                if self._is_whole_word_span(idx, idx + len(query)):
                    return idx
                pos = idx + 1
            return -1
        pos = end
        while pos - start >= len(query):
            idx = self.norm_source.rfind(query, start, pos)
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

        is_single_word = " " not in tail_query
        if is_single_word:
            # Single-word tail must sit in a tight 120-char forward window at active reading position (or high-water cursor)
            norm_start = -1
            for base_pos in dict.fromkeys((self._active_norm_pos, self.cursor_norm)):
                win_end = min(len(self.norm_source), base_pos + 120)
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
                is_re_read=norm_end <= self.cursor_norm,
                prefix=sharh_prefix,
            )

        # Multi-word tail: standard forward window then look-behind
        overlap = 300
        search_start = max(0, self.cursor_norm - overlap)
        window_end = min(len(self.norm_source), self.cursor_norm + self.forward_lookahead)
        norm_start = self._find_whole_word(search_start, window_end, tail_query, reverse=False)
        if norm_start != -1 and (norm_start + len(tail_query)) > self.cursor_norm:
            return self._record_anchored_match(
                norm_start,
                norm_start + len(tail_query),
                mode=MatchMode.FALLBACK,
                is_fallback=True,
                is_re_read=False,
                prefix=sharh_prefix,
            )

        idx_behind = self._find_whole_word(0, self.cursor_norm, tail_query, reverse=True)
        if idx_behind != -1:
            return self._record_anchored_match(
                idx_behind,
                idx_behind + len(tail_query),
                mode=MatchMode.FALLBACK,
                is_fallback=True,
                is_re_read=True,
                prefix=sharh_prefix,
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

        # 1. Forward search (allowing overlap for re-read prefixes extending into new text)
        overlap = 300
        search_start = max(0, self.cursor_norm - overlap)
        window_end = min(len(self.norm_source), self.cursor_norm + self.forward_lookahead)
        forward_slice = self.norm_source[search_start:window_end]

        idx_forward = forward_slice.find(search_query)
        if idx_forward != -1:
            norm_start = search_start + idx_forward
            norm_end = norm_start + len(search_query)
            if norm_end > self.cursor_norm:
                return self._record_anchored_match(
                    norm_start,
                    norm_end,
                    mode=MatchMode.PRIMARY,
                    is_fallback=False,
                    is_re_read=False,
                )

        # 2. Look-behind search (0 -> cursor_norm)
        lookbehind_slice = self.norm_source[:self.cursor_norm]
        idx_behind = lookbehind_slice.rfind(search_query)
        if idx_behind != -1:
            return self._record_anchored_match(
                idx_behind,
                idx_behind + len(search_query),
                mode=MatchMode.PRIMARY,
                is_fallback=False,
                is_re_read=True,
            )

        # 3. Compound Sharh prefix + Primary Matn tail (e.g. 'ثم بين وجه ذلك بقوله، وَذَلِكَ')
        compound_res = self._match_compound_sharh_matn(spoken_segment)
        if compound_res is not None:
            return compound_res

        # 4. Double-miss: Fallback Mode
        return self._create_fallback_result(spoken_segment)

    def verify_exported_segment(self, exported_text: str) -> bool:
        """Verifies an exported Matn block against canonical source using sequential cursor semantics."""
        inner_collapsed = re.sub(r"\s+", " ", exported_text).strip()
        if not inner_collapsed:
            return True

        res = self.match_segment(inner_collapsed)
        res_collapsed = re.sub(r"\s+", " ", res.text).strip()

        if res.mode == MatchMode.PRIMARY:
            return inner_collapsed == res_collapsed or inner_collapsed in self._collapsed_source

        if res.is_source_anchored:
            if inner_collapsed == res_collapsed:
                return True
            comp_m = COMPOUND_SHARH_SPLIT_RE.match(inner_collapsed)
            if not comp_m:
                return False
            orig_prefix, orig_tail = comp_m.group(1), comp_m.group(2).strip()
            if strip_tashkeel_preserving_citations(orig_prefix) != orig_prefix:
                return False
            around = re.sub(
                r"\s+",
                " ",
                self.source[max(0, res.start_pos - 4) : min(len(self.source), res.end_pos + 4)],
            )
            return bool(orig_tail and orig_tail in around)

        # Unanchored Fallback
        has_outer_tashkeel = strip_tashkeel_preserving_citations(inner_collapsed) != inner_collapsed
        if has_outer_tashkeel:
            # Allow long-jump verbatim Primary Matn quotes beyond forward_lookahead (non-compound)
            if (
                not COMPOUND_SHARH_SPLIT_RE.match(strip_tashkeel_preserving_citations(inner_collapsed))
                and inner_collapsed in self._collapsed_source
            ):
                norm_q = normalize_arabic_search(inner_collapsed)
                jump_idx = self.norm_source.find(norm_q, self.cursor_norm)
                if jump_idx != -1:
                    self.cursor_norm = jump_idx + len(norm_q)
                    self.cursor = self.pos_map[self.cursor_norm - 1] + 1
                return True
            return False

        norm_query = normalize_arabic_search(inner_collapsed)
        if norm_query and norm_query in self.norm_source:
            return inner_collapsed in self._collapsed_source
        return True

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
    clean_text = result.text.strip()
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
