"""Pass 3: Punctuation, poetry spacing, mid-paragraph period, and orthography audit."""

from __future__ import annotations

import re

from ._qa_models import HEADER_LINE_COUNT, ParagraphRecord, ValidationReport
from .arabic_normalizer import mask_citations, strip_tashkeel

_BRACKET_SPACE_RE = re.compile(r"\(\s+|\s+\)")
_PAIRED_QUOTE_RE = re.compile(r'"([^"]*)"')
_QUOTE_SPACE_ODD_RE = re.compile(r'(?:^|[\s(])"\s+|\s+"(?=$|[\s،.:؟!)])')
_MULTI_DOT_RE = re.compile(r"\.{2,}")
_MID_PERIOD_RE = re.compile(r"(?<!\d)\.(?!\d)")
_BASE_FORBIDDEN_PUNC_RE = re.compile(r"[,?;]")
_PROSE_BRACKETS_RE = re.compile(r"[\[\]{}]")
_GUILLEMET_RE = re.compile(r"[«»]")
_DASH_PUNC_RE = re.compile(r"(?<!\d)\s+-\s+(?!\d)|[—–]")
_IZHAN_NUN_RE = re.compile(r"(?<!\w)إذن(?!\w)")
_IZHAN_EXEMPT_PREFIX_RE = re.compile(
    r"(?:^|(?<!\w))(?:[وف]?(?:من\s+غير|بدون|دون|عن|بعد)|ب)\s+$"
)


def _is_standalone_poetry_line(rec: ParagraphRecord) -> bool:
    """Return True when a paragraph is a balanced two-hemistich poetry verse separated by ' ... '."""
    inner = rec.inner_text
    if not rec.is_matn and inner.startswith("(") and inner.endswith(")"):
        candidate = inner[1:-1].strip()
        if "(" not in candidate and ")" not in candidate:
            inner = candidate
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
        2 <= len(h1_words) <= 9
        and 2 <= len(h2_words) <= 9
        and abs(len(h1_words) - len(h2_words)) <= 5
    )


def _find_quote_internal_space(stripped: str) -> tuple[int, int] | None:
    """Return span of whitespace inside quotes using paired check on even parity and boundary regex on odd parity."""
    if stripped.count('"') % 2 == 0:
        for m in _PAIRED_QUOTE_RE.finditer(stripped):
            inner = m.group(1)
            if inner != inner.strip():
                return m.start(), m.end()
        return None
    m_odd = _QUOTE_SPACE_ODD_RE.search(stripped)
    return (m_odd.start(), m_odd.end()) if m_odd else None


def _collect_forbidden_punctuation(stripped: str, *, is_matn: bool) -> set[str]:
    """Collect forbidden punctuation symbols, keeping Matn source brackets and quotes exempt."""
    found = set(_BASE_FORBIDDEN_PUNC_RE.findall(stripped))
    if is_matn:
        return found
    found.update(_PROSE_BRACKETS_RE.findall(stripped))
    prose_outside_citations = mask_citations(
        stripped,
        lambda m: m.group(0) if m.group(0).startswith("«") else " ",
    )
    found.update(_GUILLEMET_RE.findall(prose_outside_citations))
    for dash_m in _DASH_PUNC_RE.finditer(stripped):
        found.add(dash_m.group(0).strip())
    return found


def _has_non_noun_izhan(stripped: str) -> bool:
    """Return True when 'إذن' appears outside prepositional permission phrases."""
    for m in _IZHAN_NUN_RE.finditer(stripped):
        pre_plain = strip_tashkeel(stripped[: m.start()])
        if not _IZHAN_EXEMPT_PREFIX_RE.search(pre_plain):
            return True
    return False


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

        q_space_span = _find_quote_internal_space(stripped)
        if q_space_span is not None:
            start = max(0, q_space_span[0] - 20)
            end = min(len(stripped), q_space_span[1] + 20)
            report.flag(
                "QUOTE_INTERNAL_SPACE",
                rec.index,
                f"Paragraph P{rec.index} has internal whitespace inside quotes '\" ... \"'.",
                stripped[start:end],
            )

        is_poetry = _is_standalone_poetry_line(rec)
        if ".." in stripped and not is_poetry:
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
            if not is_poetry and stripped.endswith("،"):
                report.flag(
                    "PROSE_TRAILING_COMMA",
                    rec.index,
                    f"Non-Matn paragraph P{rec.index} ends with an Arabic comma ('،'); terminate with '.', '؟', '!', or ':' before Matn.",
                    stripped[-80:],
                )

        forbidden_punc = _collect_forbidden_punctuation(stripped, is_matn=rec.is_matn)
        if forbidden_punc:
            report.flag(
                "FORBIDDEN_PUNCTUATION",
                rec.index,
                f"Paragraph P{rec.index} contains forbidden punctuation/brackets {sorted(forbidden_punc)}.",
                stripped[:80],
            )

        if not rec.is_matn and _has_non_noun_izhan(stripped):
            report.flag(
                "ORTHOGRAPHY_IZHAN_NUN",
                rec.index,
                f"Paragraph P{rec.index} writes 'إذن' with nun; standardize to 'إذًا'.",
                stripped[:80],
            )
