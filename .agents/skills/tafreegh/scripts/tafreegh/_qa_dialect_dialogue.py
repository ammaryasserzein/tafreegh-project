"""Pass 4: Dialogue formatting, Attendee Anonymization, Salawat, and dialect normalization audit."""

from __future__ import annotations

import re

from ._qa_models import (
    HEADER_LINE_COUNT,
    ParagraphRecord,
    ValidationReport,
    _flag,
    strip_parenthesized_citations,
)
from .arabic_normalizer import strip_tashkeel
from .workspace_catalog import RuleCatalog

_SHEIKH_PREFIX_RE = re.compile(r"^(?:الشيخ|شيخ)\s*:")
_STUDENT_NUMBERED_RE = re.compile(r"^طالب\s*\d+\s*:")
_INAUDIBLE_PARENS_RE = re.compile(r"^\(\s*صوت غير مسموع\s*\)\.?$")
_QUOTED_SPAN_RE = re.compile(r'"[^"]*"')


def check_dialect_and_dialogue(
    para_records: list[ParagraphRecord],
    report: ValidationReport,
    catalog: RuleCatalog,
) -> None:
    """Audit speaker attribution, Attendee Anonymization, Salawat, and dialect replacements."""
    rules = catalog.dialect_replacements
    attendee_rules = catalog.attendee_rules

    for rec in para_records:
        if rec.index < HEADER_LINE_COUNT:
            continue
        stripped = rec.text.strip()
        if not stripped or rec.is_matn:
            continue

        if _SHEIKH_PREFIX_RE.match(stripped):
            _flag(
                report,
                "SHEIKH_PREFIX_FORBIDDEN",
                rec.index,
                f"Paragraph P{rec.index} prefixes speech with 'الشيخ:'; default speaker must have no prefix.",
                stripped[:80],
            )

        if _STUDENT_NUMBERED_RE.match(stripped):
            _flag(
                report,
                "STUDENT_NUMBERING_FORBIDDEN",
                rec.index,
                f"Paragraph P{rec.index} uses numbered student label; always use 'طالب: '.",
                stripped[:80],
            )

        if stripped.startswith("طالب:"):
            if not rec.text.startswith("طالب: "):
                _flag(
                    report,
                    "STUDENT_PREFIX_SPACE_MISSING",
                    rec.index,
                    f"Student paragraph P{rec.index} must start with 'طالب: ' (single space after colon).",
                    stripped[:80],
                )
            if not stripped.endswith((".", "؟", "!")):
                _flag(
                    report,
                    "STUDENT_TERMINAL_PUNCTUATION_MISSING",
                    rec.index,
                    f"Student paragraph P{rec.index} must end with '.', '؟', or '!'.",
                    stripped[:80],
                )

            student_body = stripped[len("طالب:") :].strip()
            if "صوت غير مسموع" in student_body:
                if _INAUDIBLE_PARENS_RE.match(student_body):
                    _flag(
                        report,
                        "INAUDIBLE_COMPLETE_PARENS_FORBIDDEN",
                        rec.index,
                        (
                            f"Student paragraph P{rec.index} has complete silence wrapped in parentheses; "
                            "must be 'طالب: صوت غير مسموع.' without parentheses."
                        ),
                        stripped[:80],
                    )
                elif student_body != "صوت غير مسموع." and "(صوت غير مسموع)" not in student_body:
                    _flag(
                        report,
                        "INAUDIBLE_PARTIAL_PARENS_MISSING",
                        rec.index,
                        (
                            f"Student paragraph P{rec.index} has partial speech with 'صوت غير مسموع' not enclosed in parentheses; "
                            "must be 'طالب: <كلمات> (صوت غير مسموع).'"
                        ),
                        stripped[:80],
                    )

        scan_text = strip_parenthesized_citations(stripped)
        scan_no_quotes = strip_tashkeel(_QUOTED_SPAN_RE.sub(" ", scan_text))
        for leak_kind, matched_phrase in attendee_rules.find_leaks(scan_no_quotes):
            _flag(
                report,
                "ATTENDEE_NAME_UNANONYMIZED",
                rec.index,
                f"Paragraph P{rec.index} contains unanonymized attendee {leak_kind} '{matched_phrase}'; replace personal name with '{attendee_rules.placeholder}'.",
                stripped[:80],
            )

        if "عليه الصلاة والسلام" in scan_text:
            _flag(
                report,
                "SALAWAT_UNNORMALIZED",
                rec.index,
                f"Paragraph P{rec.index} contains 'عليه الصلاة والسلام'; standardize to 'صلى الله عليه وسلم'.",
                stripped[:80],
            )

        for pat, target_form in rules:
            m = pat.search(scan_text)
            if m:
                suggested = m.expand(target_form) if "\\" in target_form else target_form
                _flag(
                    report,
                    "DIALECT_UNNORMALIZED",
                    rec.index,
                    (
                        f"Paragraph P{rec.index} contains unnormalized dialect form '{m.group(0)}'; "
                        f"standardize to '{suggested}'."
                    ),
                    stripped[:80],
                )
