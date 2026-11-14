"""Pass 4: Dialogue formatting, Attendee Anonymization, Salawat, and dialect normalization audit."""

from __future__ import annotations

import re

from ._qa_models import (
    HEADER_LINE_COUNT,
    INAUDIBLE_TOKEN,
    STUDENT_PREFIX,
    ParagraphRecord,
    ValidationReport,
    strip_parenthesized_citations,
)
from .arabic_normalizer import strip_tashkeel
from .workspace_catalog import AttendeeAnonymizationRules, RuleCatalog

_SHEIKH_PREFIX_RE = re.compile(r"^(?:الشيخ|شيخ)\s*:")
_STUDENT_NUMBERED_RE = re.compile(r"^طالب\s*\d+\s*:")
_INAUDIBLE_PARENS_RE = re.compile(rf"^\(\s*{re.escape(INAUDIBLE_TOKEN)}\s*\)\.?$")
_QUOTED_SPAN_RE = re.compile(r'"[^"]*"')


def _check_dialogue_turns(rec: ParagraphRecord, stripped: str, report: ValidationReport) -> None:
    """Validate speaker attribution labels, spacing, terminal punctuation, and inaudible notation."""
    if _SHEIKH_PREFIX_RE.match(stripped):
        report.flag(
            "SHEIKH_PREFIX_FORBIDDEN",
            rec.index,
            f"Paragraph P{rec.index} prefixes speech with 'الشيخ:'; default speaker must have no prefix.",
            stripped[:80],
        )

    if _STUDENT_NUMBERED_RE.match(stripped):
        report.flag(
            "STUDENT_NUMBERING_FORBIDDEN",
            rec.index,
            f"Paragraph P{rec.index} uses numbered student label; always use '{STUDENT_PREFIX} '.",
            stripped[:80],
        )

    if not stripped.startswith(STUDENT_PREFIX):
        return

    if not rec.text.startswith(f"{STUDENT_PREFIX} "):
        report.flag(
            "STUDENT_PREFIX_SPACE_MISSING",
            rec.index,
            f"Student paragraph P{rec.index} must start with '{STUDENT_PREFIX} ' (single space after colon).",
            stripped[:80],
        )
    if not stripped.endswith((".", "؟", "!")):
        report.flag(
            "STUDENT_TERMINAL_PUNCTUATION_MISSING",
            rec.index,
            f"Student paragraph P{rec.index} must end with '.', '؟', or '!'.",
            stripped[:80],
        )

    student_body = stripped[len(STUDENT_PREFIX) :].strip()
    if INAUDIBLE_TOKEN not in student_body:
        return

    if _INAUDIBLE_PARENS_RE.match(student_body):
        report.flag(
            "INAUDIBLE_COMPLETE_PARENS_FORBIDDEN",
            rec.index,
            (
                f"Student paragraph P{rec.index} has complete silence wrapped in parentheses; "
                f"must be '{STUDENT_PREFIX} {INAUDIBLE_TOKEN}.' without parentheses."
            ),
            stripped[:80],
        )
    elif student_body != f"{INAUDIBLE_TOKEN}." and f"({INAUDIBLE_TOKEN})" not in student_body:
        report.flag(
            "INAUDIBLE_PARTIAL_PARENS_MISSING",
            rec.index,
            (
                f"Student paragraph P{rec.index} has partial speech with '{INAUDIBLE_TOKEN}' not enclosed in parentheses; "
                f"must be '{STUDENT_PREFIX} <كلمات> ({INAUDIBLE_TOKEN}).'"
            ),
            stripped[:80],
        )


def _check_lexical_rules(
    rec: ParagraphRecord,
    stripped: str,
    report: ValidationReport,
    rules: tuple[tuple[re.Pattern[str], str], ...],
    attendee_rules: AttendeeAnonymizationRules,
) -> None:
    """Validate Attendee Anonymization, canonical Salawat, and dialect replacements on a paragraph."""
    scan_text = strip_parenthesized_citations(stripped)
    scan_no_quotes = strip_tashkeel(_QUOTED_SPAN_RE.sub(" ", scan_text))
    for leak_kind, matched_phrase in attendee_rules.find_leaks(scan_no_quotes):
        report.flag(
            "ATTENDEE_NAME_UNANONYMIZED",
            rec.index,
            f"Paragraph P{rec.index} contains unanonymized attendee {leak_kind} '{matched_phrase}'; replace personal name with '{attendee_rules.placeholder}'.",
            stripped[:80],
        )

    if "عليه الصلاة والسلام" in scan_text:
        report.flag(
            "SALAWAT_UNNORMALIZED",
            rec.index,
            f"Paragraph P{rec.index} contains 'عليه الصلاة والسلام'; standardize to 'صلى الله عليه وسلم'.",
            stripped[:80],
        )

    for pat, target_form in rules:
        m = pat.search(scan_text)
        if m:
            suggested = m.expand(target_form) if "\\" in target_form else target_form
            report.flag(
                "DIALECT_UNNORMALIZED",
                rec.index,
                (
                    f"Paragraph P{rec.index} contains unnormalized dialect form '{m.group(0)}'; "
                    f"standardize to '{suggested}'."
                ),
                stripped[:80],
            )


def check_dialect_and_dialogue(
    para_records: list[ParagraphRecord],
    report: ValidationReport,
    catalog: RuleCatalog,
) -> None:
    """Audit speaker attribution, Attendee Anonymization, Salawat, and dialect replacements."""
    rules = tuple(catalog.dialect_replacements)
    attendee_rules = catalog.attendee_rules

    for rec in para_records:
        if rec.index < HEADER_LINE_COUNT:
            continue
        stripped = rec.text.strip()
        if not stripped or rec.is_matn:
            continue
        _check_dialogue_turns(rec, stripped, report)
        _check_lexical_rules(rec, stripped, report, rules, attendee_rules)
