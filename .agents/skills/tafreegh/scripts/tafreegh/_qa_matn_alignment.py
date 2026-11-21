"""Pass 6: Sequential canonical Matn alignment and tashkeel fidelity audit."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from ._qa_models import ParagraphRecord, ValidationReport
from .arabic_normalizer import (
    CITATION_SPAN_RE,
    collapse_whitespace,
    has_tashkeel,
    mask_citations,
    normalize_arabic_search,
    normalize_nfc_collapsed,
    strip_tashkeel_preserving_citations,
)
from .matn_matcher import (
    COMPOUND_SHARH_SPLIT_RE,
    MatchMode,
    SequentialMatnMatcher,
)
from .word_gateway import read_matn_source_content

_ARABIC_LETTER_RE = re.compile(r"[\u0621-\u064A\u0671]")
_TANWEEN_FATHA_AT_END_RE = re.compile(
    r"(?<=[\u0621-\u064A])\u064B(?=[اةءى]?(?![\u0621-\u064A\u064B-\u065F\u0670\u0640]))"
)
_SEAM_PUNCT_RE = re.compile(r"[.،]+")


@dataclass(frozen=True)
class _SegmentToken:
    start: int
    end: int
    text: str
    is_citation: bool


def _strip_seam_punct(text: str) -> str:
    """Strip sentence/clause seam dots and Arabic commas while preserving letters and diacritics."""
    return collapse_whitespace(_SEAM_PUNCT_RE.sub("", text))


def _has_non_orthographic_tashkeel(text: str) -> bool:
    """Return True when text has diacritics other than standalone word-final tanween-fatha."""
    without_tanween = _TANWEEN_FATHA_AT_END_RE.sub("", text)
    return has_tashkeel(without_tanween)


def _append_ws_tokens(tokens: list[_SegmentToken], segment: str, offset: int) -> None:
    """Append non-citation whitespace tokens with original character offsets."""
    for wm in re.finditer(r"\S+", segment):
        tokens.append(
            _SegmentToken(
                start=offset + wm.start(),
                end=offset + wm.end(),
                text=wm.group(0),
                is_citation=False,
            )
        )


def _tokenize_with_citations(text: str) -> list[_SegmentToken]:
    """Split NFC-collapsed segment into whitespace tokens while keeping citation spans atomic."""
    tokens: list[_SegmentToken] = []
    pos = 0
    for m in CITATION_SPAN_RE.finditer(text):
        if m.start() > pos:
            _append_ws_tokens(tokens, text[pos : m.start()], pos)
        tokens.append(
            _SegmentToken(
                start=m.start(),
                end=m.end(),
                text=m.group(0),
                is_citation=True,
            )
        )
        pos = m.end()
    if pos < len(text):
        _append_ws_tokens(tokens, text[pos:], pos)
    return tokens


class MatnAlignmentValidator:
    """Non-destructive Matn alignment verifier delegating to SequentialMatnMatcher public queries."""

    def __init__(self, matn_source: str | SequentialMatnMatcher) -> None:
        """Initialize a fresh SequentialMatnMatcher cursor over matn_source text."""
        source_text = matn_source.source if isinstance(matn_source, SequentialMatnMatcher) else matn_source
        self.source = unicodedata.normalize("NFC", source_text)
        self._matcher = SequentialMatnMatcher(self.source)

    @property
    def cursor(self) -> int:
        """Read-only high-water character offset forwarded from the inner matcher."""
        return self._matcher.cursor

    @property
    def cursor_norm(self) -> int:
        """Read-only high-water normalized character offset forwarded from the inner matcher."""
        return self._matcher.cursor_norm

    def _tail_matches_anchored_span(self, start_pos: int, end_pos: int, tail: str) -> bool:
        """Return True when tail appears verbatim in the NFC-normalized source slice around [start_pos, end_pos)."""
        around = normalize_nfc_collapsed(
            self.source[max(0, start_pos - 4) : min(len(self.source), end_pos + 4)]
        )
        return bool(tail and tail in around)

    def _matches_primary_span(self, span: str) -> bool:
        """Verify a multi-word vowelized sub-span against canonical source via cursor or seam-tolerant match."""
        for candidate in dict.fromkeys((span, span.rstrip("،.:؛!؟"))):
            if not candidate:
                continue
            if (
                self._matcher.advance_to_canonical_occurrence(candidate)
                or self._matcher.contains_verbatim(candidate)
            ):
                return True
            m_res = self._matcher.match_segment(candidate)
            if m_res.mode != MatchMode.PRIMARY and self._matcher.contains_normalized(candidate):
                wide = SequentialMatnMatcher(self.source, forward_lookahead=len(self.source) + 1)
                m_res = wide.match_segment(candidate)
            if m_res.mode == MatchMode.PRIMARY and (
                _strip_seam_punct(candidate) == _strip_seam_punct(normalize_nfc_collapsed(m_res.text))
            ):
                return True
        return False

    def _verify_mixed_or_long_jump(self, inner_collapsed: str) -> bool:
        """Verify vowelized sub-spans against <matn_source> while keeping Fallback spans unvowelized."""
        tokens = _tokenize_with_citations(inner_collapsed)
        if not tokens:
            return True

        n = len(tokens)
        is_cit_in_src = [
            tok.is_citation and self._matcher.contains_verbatim(tok.text) for tok in tokens
        ]
        is_vowelized = [
            (not tok.is_citation)
            and bool(_ARABIC_LETTER_RE.search(tok.text))
            and _has_non_orthographic_tashkeel(tok.text)
            for tok in tokens
        ]
        is_punct = [
            (not tok.is_citation) and not bool(_ARABIC_LETTER_RE.search(tok.text))
            for tok in tokens
        ]

        if n == 1 and is_vowelized[0]:
            return (
                self._matcher.advance_to_canonical_occurrence(inner_collapsed)
                or self._matcher.contains_verbatim(inner_collapsed)
            )

        idx = 0
        while idx < n:
            if not is_vowelized[idx]:
                idx += 1
                continue

            run_start_idx = idx
            if idx > 0 and is_cit_in_src[idx - 1]:
                run_start_idx = idx - 1

            run_end_idx = idx
            j = idx + 1
            while j < n:
                if is_vowelized[j] or is_cit_in_src[j]:
                    run_end_idx = j
                    j += 1
                    continue
                if is_punct[j]:
                    j += 1
                    continue
                # Bridge a single unvowelized word only when flanked by vowelized tokens inside source
                if (
                    not tokens[j].is_citation
                    and j + 1 < n
                    and is_vowelized[j + 1]
                    and self._matcher.contains_verbatim(
                        inner_collapsed[tokens[run_start_idx].start : tokens[j + 1].end]
                    )
                ):
                    run_end_idx = j + 1
                    j += 2
                    continue
                break

            span = inner_collapsed[tokens[run_start_idx].start : tokens[run_end_idx].end]
            word_count = len(normalize_arabic_search(span).split())
            if word_count >= 2:
                if not self._matches_primary_span(span):
                    if run_start_idx != idx:
                        trimmed = inner_collapsed[tokens[idx].start : tokens[run_end_idx].end]
                        if (
                            len(normalize_arabic_search(trimmed).split()) < 2
                            or not self._matches_primary_span(trimmed)
                        ):
                            return False
                    else:
                        return False
            else:
                # Single-word vowelized tail only passes when anchored as a local Compound Sharh-Matn
                if run_start_idx == 0:
                    return False
                prefix_plus_tail = inner_collapsed[: tokens[run_end_idx].end]
                if not COMPOUND_SHARH_SPLIT_RE.match(strip_tashkeel_preserving_citations(prefix_plus_tail)):
                    return False
                comp_res = self._matcher.match_segment(prefix_plus_tail)
                if not comp_res.is_source_anchored or not self._tail_matches_anchored_span(
                    comp_res.start_pos, comp_res.end_pos, tokens[run_end_idx].text
                ):
                    return False

            idx = run_end_idx + 1

        return True

    def verify_exported_segment(self, exported_text: str) -> bool:
        """Verify an exported Matn paragraph against canonical Matn source without violating cursor semantics."""
        inner_collapsed = normalize_nfc_collapsed(exported_text)
        if not inner_collapsed:
            return True

        res = self._matcher.match_segment(inner_collapsed)
        res_collapsed = normalize_nfc_collapsed(res.text)

        outer_text = mask_citations(inner_collapsed)
        has_outer_tashkeel = _has_non_orthographic_tashkeel(outer_text)

        if res.mode == MatchMode.PRIMARY:
            if inner_collapsed == res_collapsed or self._matcher.contains_verbatim(inner_collapsed):
                return True
            return (
                not has_outer_tashkeel
                and len(normalize_arabic_search(inner_collapsed).split()) < 4
            )

        if res.is_source_anchored:
            if inner_collapsed == res_collapsed:
                return True
            comp_m = COMPOUND_SHARH_SPLIT_RE.match(inner_collapsed)
            if not comp_m:
                return False
            orig_prefix, orig_tail = comp_m.group(1), comp_m.group(2).strip()
            if _has_non_orthographic_tashkeel(mask_citations(orig_prefix)):
                return False
            return self._tail_matches_anchored_span(res.start_pos, res.end_pos, orig_tail)

        if has_outer_tashkeel:
            if not COMPOUND_SHARH_SPLIT_RE.match(strip_tashkeel_preserving_citations(inner_collapsed)):
                if (
                    self._matcher.advance_to_canonical_occurrence(inner_collapsed)
                    or self._matcher.contains_verbatim(inner_collapsed)
                ):
                    return True
            return self._verify_mixed_or_long_jump(inner_collapsed)

        if (
            len(normalize_arabic_search(inner_collapsed).split()) >= 4
            and self._matcher.contains_normalized(inner_collapsed)
        ):
            return self._matcher.contains_verbatim(inner_collapsed)

        return True


def check_matn_alignment(
    para_records: list[ParagraphRecord],
    matn_path: Path,
    report: ValidationReport,
) -> None:
    """Verify Primary Mode and Compound Sharh-Matn blocks against canonical Matn source."""
    if not matn_path.exists():
        return
    matn_source = read_matn_source_content(matn_path)
    validator = MatnAlignmentValidator(matn_source)

    for rec in para_records:
        if not rec.is_matn:
            continue
        inner = rec.inner_text
        if not validator.verify_exported_segment(inner):
            inner_collapsed = collapse_whitespace(inner)
            report.flag(
                "MATN_SOURCE_MISMATCH",
                rec.index,
                (
                    f"Matn paragraph P{rec.index} does not match canonical <matn_source> verbatim "
                    "(or contains unverified tashkeel in Fallback Mode)."
                ),
                inner_collapsed[:100],
            )
