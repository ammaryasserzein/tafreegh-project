"""Pass 3: Punctuation, poetry spacing, mid-paragraph period, and orthography audit."""

from __future__ import annotations

import re

from ._qa_models import HEADER_LINE_COUNT, ParagraphRecord, ValidationReport

_BRACKET_SPACE_RE = re.compile(r"\(\s+|\s+\)")
_QUOTE_SPACE_RE = re.compile(r'(?:^|[\s،.:؟!(])"\s+|\s+"(?=$|[\s،.:؟!)])')
_MULTI_DOT_RE = re.compile(r"\.{2,}")
_MID_PERIOD_RE = re.compile(r"(?<!\d)\.(?!\d)")
_FORBIDDEN_PUNC_RE = re.compile(r"[,?;[\]{}]")
_IZHAN_NUN_RE = re.compile(r"(?<!\w)إذن(?!\w)")


def _is_standalone_poetry_line(rec: ParagraphRecord) -> bool:
    """Return True when a paragraph is a balanced two-hemistich poetry verse separated by ' ... '."""
    inner = rec.inner_text
    if ":" in inner:
        return False
    if not rec.is_matn and ("(" in inner or ")" in inner):
        return False
    parts = inner.split(" ... ")
    if len(parts) != 2:
        return False
    h1_words = parts[0].strip().split()
    h2_words = parts[1].strip().split()
    return (
        2 <= len(h1_words) <= 7
        and 2 <= len(h2_words) <= 7
        and abs(len(h1_words) - len(h2_words)) <= 3
    )


def check_punctuation_and_orthography(
    para_records: list[ParagraphRecord],
    report: ValidationReport,
) -> None:
    """Verify Arabic punctuation spacing, poetry ellipses, mid-paragraph periods, and 'إذًا' orthography."""
    for rec in para_records:
        if rec.index < HEADER_LINE_COUNT:
            continue
        stripped = rec.text.strip()
        if not stripped:
            continue

        if _BRACKET_SPACE_RE.search(stripped):
            report.flag(
                "BRACKET_INTERNAL_SPACE",
                rec.index,
                f"Paragraph P{rec.index} has internal whitespace inside parentheses '( ... )'.",
                stripped[:80],
            )

        q_space_match = _QUOTE_SPACE_RE.search(stripped)
        if q_space_match:
            start = max(0, q_space_match.start() - 20)
            end = min(len(stripped), q_space_match.end() + 20)
            report.flag(
                "QUOTE_INTERNAL_SPACE",
                rec.index,
                f"Paragraph P{rec.index} has internal whitespace inside quotes '\" ... \"'.",
                stripped[start:end],
            )

        if ".." in stripped and not _is_standalone_poetry_line(rec):
            report.flag(
                "ELLIPSIS_FORBIDDEN",
                rec.index,
                f"Paragraph P{rec.index} contains ellipsis ('...' or '..') outside a standalone poetry line.",
                stripped[:80],
            )

        if not rec.is_matn:
            text_no_ellipsis = _MULTI_DOT_RE.sub("", stripped)
            body_before_end = (
                text_no_ellipsis[:-1] if text_no_ellipsis.endswith(".") else text_no_ellipsis
            )
            if _MID_PERIOD_RE.search(body_before_end):
                report.flag(
                    "MID_PARAGRAPH_PERIOD",
                    rec.index,
                    f"Non-Matn paragraph P{rec.index} contains a mid-paragraph period ('.'); replace with '،' or split paragraph.",
                    stripped[:90],
                )

        forbidden_punc = _FORBIDDEN_PUNC_RE.findall(stripped)
        if forbidden_punc:
            report.flag(
                "FORBIDDEN_PUNCTUATION",
                rec.index,
                f"Paragraph P{rec.index} contains forbidden punctuation/brackets {set(forbidden_punc)}.",
                stripped[:80],
            )

        if not rec.is_matn and _IZHAN_NUN_RE.search(stripped):
            report.flag(
                "ORTHOGRAPHY_IZHAN_NUN",
                rec.index,
                f"Paragraph P{rec.index} writes 'إذن' with nun; standardize to 'إذًا'.",
                stripped[:80],
            )
