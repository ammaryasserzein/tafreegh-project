"""Pass 5: Unbolded Classical Arabic Sharh/Matn fallback trigger audit."""

from __future__ import annotations

import re

from ._qa_models import HEADER_LINE_COUNT, ParagraphRecord, ValidationReport, _flag
from .arabic_normalizer import normalize_arabic, strip_tashkeel

FALLBACK_MATN_TRIGGERS: list[tuple[str, re.Pattern[str]]] = [
    ("قالوا", re.compile(r"(?:^|[،.؟!:)»\"\s])(قالوا\s*:?\s*[^.؟!\n]+)")),
    ("فإن قلت", re.compile(r"(?:^|[،.؟!:)»\"\s])(فإن\s+قلت\s*:?\s*[^.؟!\n]+)")),
    ("قلت", re.compile(r"(?:^|[،.؟!:)»\"\s])(قلت(?:\s+في)?\s*:?\s*[^.؟!\n]+)")),
    ("وأيضا", re.compile(r"(?:^|[،.؟!:)»\"\s])(وأيضا\s*:?\s*[^.؟!\n]+)")),
    ("فصل في", re.compile(r"(?:^|[،.؟!:)»\"\s])(فصل\s+في\s+[\u0600-\u06FF\s]{4,40}?)(?=[،.؟!]|$)")),
    ("قال الشاعر", re.compile(r"(?:^|[،.؟!:)»\"])\s*([^،.؟!\n]+[،:]\s*قال\s+الشاعر\s*:?)")),
    ("قال", re.compile(r"(?:^|[،.؟!:)»\"\s])(قال(?!\s+(?:تعالى|الله|النبي|رسول))\s*:\s*[^.؟!\n]+)")),
]

_ARABIC_WORD_RE = re.compile(r"[\u0600-\u06FF]+")
_HO_WALA_RE = re.compile(r"(?<!\w)هو\s+[\u0600-\u06FF\s]+\s+ولا\s+")
_CLAUSE_SPLIT_RE = re.compile(r"https?://|\s*-\s*يعني\s+|[،]")


def _has_colloquial_marker(
    text: str,
    dialect_markers: frozenset[str] | set[str],
) -> bool:
    """Return True if text contains Egyptian colloquial words or verbal negation/future patterns."""
    plain = strip_tashkeel(text)
    if _HO_WALA_RE.search(plain):
        return True
    for word in _ARABIC_WORD_RE.findall(plain):
        word_norm = normalize_arabic(word)
        if word in dialect_markers or word_norm in dialect_markers:
            return True
        if word.startswith(("هت", "هي", "بي", "بت", "ما")) and word.endswith("ش") and len(word) >= 4:
            return True
    return False


def _extract_leading_classical_clause(
    candidate: str,
    dialect_markers: frozenset[str] | set[str],
) -> str:
    """Extract consecutive leading Classical Arabic sub-clauses before any colloquial shift."""
    classical_parts: list[str] = []
    for sub in _CLAUSE_SPLIT_RE.split(candidate):
        sub_clean = sub.strip(" .؟!:-")
        if not sub_clean:
            continue
        if _has_colloquial_marker(sub_clean, dialect_markers):
            break
        classical_parts.append(sub_clean)
    return "، ".join(classical_parts)


def check_unbolded_fallback_matn(
    para_records: list[ParagraphRecord],
    report: ValidationReport,
    dialect_markers: frozenset[str] | set[str],
) -> None:
    """Detect unbolded Classical Arabic Sharh/Matn clauses inside explanation paragraphs."""
    for rec in para_records:
        if rec.index < HEADER_LINE_COUNT or rec.is_matn:
            continue
        stripped = rec.text.strip()
        if not stripped or stripped.startswith("طالب:"):
            continue

        for label, pat in FALLBACK_MATN_TRIGGERS:
            for m in pat.finditer(stripped):
                cand = m.group(1).strip()
                core_clause = _extract_leading_classical_clause(cand, dialect_markers)
                words = _ARABIC_WORD_RE.findall(core_clause)
                if len(words) >= 4 and not _has_colloquial_marker(core_clause, dialect_markers):
                    _flag(
                        report,
                        "UNBOLDED_FALLBACK_MATN",
                        rec.index,
                        (
                            f"Paragraph P{rec.index} contains an unbolded Classical Arabic Sharh/Matn segment "
                            f"triggered by '{label}': isolate as '**(...)**'."
                        ),
                        core_clause[:100],
                    )
