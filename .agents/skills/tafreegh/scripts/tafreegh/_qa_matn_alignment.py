"""Pass 6: Sequential canonical Matn alignment and tashkeel fidelity audit."""

from __future__ import annotations

import re
from pathlib import Path

from ._qa_models import ParagraphRecord, ValidationReport, _flag
from .arabic_normalizer import strip_tashkeel_preserving_citations
from .matn_matcher import (
    COMPOUND_SHARH_SPLIT_RE,
    MatchMode,
    SequentialMatnMatcher,
)
from .word_gateway import read_matn_source_content


class MatnAlignmentValidator:
    """Non-destructive Matn alignment verifier delegating to SequentialMatnMatcher public queries."""

    def __init__(self, matn_source: str | SequentialMatnMatcher) -> None:
        source_text = matn_source.source if isinstance(matn_source, SequentialMatnMatcher) else matn_source
        self.source = source_text
        self._matcher = SequentialMatnMatcher(source_text)

    @property
    def cursor(self) -> int:
        """Read-only high-water character offset forwarded from the inner matcher."""
        return self._matcher.cursor

    @property
    def cursor_norm(self) -> int:
        """Read-only high-water normalized character offset forwarded from the inner matcher."""
        return self._matcher.cursor_norm

    def verify_exported_segment(self, exported_text: str) -> bool:
        """Verify an exported Matn paragraph against canonical Matn source without violating cursor semantics."""
        inner_collapsed = re.sub(r"\s+", " ", exported_text).strip()
        if not inner_collapsed:
            return True

        res = self._matcher.match_segment(inner_collapsed)
        res_collapsed = re.sub(r"\s+", " ", res.text).strip()

        if res.mode == MatchMode.PRIMARY:
            return inner_collapsed == res_collapsed or self._matcher.contains_verbatim(inner_collapsed)

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

        has_outer_tashkeel = strip_tashkeel_preserving_citations(inner_collapsed) != inner_collapsed
        if has_outer_tashkeel:
            if not COMPOUND_SHARH_SPLIT_RE.match(strip_tashkeel_preserving_citations(inner_collapsed)):
                return (
                    self._matcher.advance_to_canonical_occurrence(inner_collapsed)
                    or self._matcher.contains_verbatim(inner_collapsed)
                )
            return False

        if self._matcher.contains_normalized(inner_collapsed):
            return self._matcher.contains_verbatim(inner_collapsed)

        return True

    def verify_segment(self, exported_text: str) -> bool:
        """Alias for verify_exported_segment."""
        return self.verify_exported_segment(exported_text)


def check_matn_alignment(
    para_records: list[ParagraphRecord],
    matn_path: Path,
    report: ValidationReport,
) -> None:
    """Verify Primary Mode and compound Sharh-Matn blocks against canonical Matn source."""
    if not matn_path.exists():
        return
    matn_source = read_matn_source_content(matn_path)
    validator = MatnAlignmentValidator(matn_source)

    for rec in para_records:
        if not rec.is_matn:
            continue
        stripped = rec.text.strip()
        inner = stripped[1:-1].strip() if (stripped.startswith("(") and stripped.endswith(")")) else stripped
        if not validator.verify_exported_segment(inner):
            inner_collapsed = re.sub(r"\s+", " ", inner).strip()
            _flag(
                report,
                "MATN_SOURCE_MISMATCH",
                rec.index,
                (
                    f"Matn paragraph P{rec.index} does not match canonical <matn_source> verbatim "
                    "(or contains unverified tashkeel in Fallback Mode)."
                ),
                inner_collapsed[:100],
            )
