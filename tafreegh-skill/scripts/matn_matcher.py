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


TASHKEEL_REGEX = re.compile(r'[\u064B-\u065F\u0670\u0640]')


def strip_tashkeel(text: str) -> str:
    """Removes Arabic diacritics and tatweel."""
    return TASHKEEL_REGEX.sub('', text)


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

    def _extract_original_slice(self, norm_start: int, norm_end: int) -> tuple[int, int, str]:
        """Calculates exact coordinates and extracts original slice preserving tashkeel and punctuation."""
        orig_start = self.pos_map[norm_start]
        last_char_idx = self.pos_map[norm_end - 1]
        orig_end = last_char_idx + 1
        while orig_end < len(self.source) and TASHKEEL_REGEX.match(self.source[orig_end]):
            orig_end += 1
        return orig_start, orig_end, self.source[orig_start:orig_end]

    def _create_fallback_result(self, spoken_segment: str) -> MatnMatchResult:
        res = MatnMatchResult(
            mode=MatchMode.FALLBACK,
            text=strip_tashkeel(spoken_segment).strip(),
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
        3. Double-miss -> Fallback mode
        """
        search_query = normalize_arabic_search(spoken_segment)
        if not search_query or len(search_query) < 3:
            return self._create_fallback_result(spoken_segment)

        # 1. Forward search
        window_end = min(len(self.norm_source), self.cursor_norm + self.forward_lookahead)
        forward_slice = self.norm_source[self.cursor_norm:window_end]
        
        idx_forward = forward_slice.find(search_query)
        if idx_forward != -1:
            norm_start = self.cursor_norm + idx_forward
            norm_end = norm_start + len(search_query)
            orig_start, orig_end, canon_text = self._extract_original_slice(norm_start, norm_end)
            
            # Advance cursor
            self.cursor_norm = norm_end
            self.cursor = orig_end

            res = MatnMatchResult(
                mode=MatchMode.PRIMARY,
                text=canon_text,
                start_pos=orig_start,
                end_pos=orig_end,
                is_fallback=False,
                is_re_read=False
            )
            self.history.append(res)
            return res

        # 2. Look-behind search (0 -> cursor_norm)
        lookbehind_slice = self.norm_source[:self.cursor_norm]
        idx_behind = lookbehind_slice.find(search_query)
        if idx_behind != -1:
            norm_start = idx_behind
            norm_end = norm_start + len(search_query)
            orig_start, orig_end, canon_text = self._extract_original_slice(norm_start, norm_end)

            # Preserve forward cursor (do not rewind)
            res = MatnMatchResult(
                mode=MatchMode.PRIMARY,
                text=canon_text,
                start_pos=orig_start,
                end_pos=orig_end,
                is_fallback=False,
                is_re_read=True
            )
            self.history.append(res)
            return res

        # 3. Double-miss: Fallback Mode
        return self._create_fallback_result(spoken_segment)

    def resolve_sandwiched_fallbacks(self, window_size: int = 1) -> None:
        """Identifies fallback segments immediately bounded by verified primary matches within a localized window."""
        for i, item in enumerate(self.history):
            if item.mode == MatchMode.FALLBACK:
                prev_dists = [i - j for j in range(i - 1, -1, -1) if self.history[j].mode == MatchMode.PRIMARY]
                prev_dist = prev_dists[0] if prev_dists else None

                next_dists = [j - i for j in range(i + 1, len(self.history)) if self.history[j].mode == MatchMode.PRIMARY]
                next_dist = next_dists[0] if next_dists else None

                if prev_dist is not None and next_dist is not None:
                    item.is_sandwiched = (prev_dist <= window_size and next_dist <= window_size)
                else:
                    item.is_sandwiched = False


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
