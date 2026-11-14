"""Pass 2: Header triple, leaked metadata, forbidden asterisks, and canonical du'a conclusion audit."""

from __future__ import annotations

import re

from ._qa_models import (
    CANONICAL_DUA_PATTERN,
    CANONICAL_DUA_TEXT,
    HEADER_LINE_COUNT,
    ParagraphRecord,
    ValidationReport,
)
from .arabic_normalizer import collapse_whitespace, has_tashkeel
from .lecture_identity import (
    AUDIO_FILENAME_EXT_RE,
    NOTEBOOKLM_HEADER_PATTERNS,
    NOTEBOOKLM_TAG_RE,
    LectureIdentity,
)
from .word_gateway import HTML_COMMENT_RE, HYBRID_SUMMARY_TITLE, InspectedDocument
from .workspace_catalog import RuleCatalog

LEAKED_METADATA_PATTERNS: tuple[re.Pattern[str], ...] = (
    *NOTEBOOKLM_HEADER_PATTERNS,
    NOTEBOOKLM_TAG_RE,
    AUDIO_FILENAME_EXT_RE,
    HTML_COMMENT_RE,
    re.compile(re.escape(HYBRID_SUMMARY_TITLE)),
)


def _has_illegal_asterisk(stripped: str) -> bool:
    """Return True if stripped contains '*' outside a spaced, vowelized parenthesized Quranic citation '(آية * آية)'."""
    if "*" not in stripped:
        return False
    if "**" in stripped:
        return True

    outside = re.sub(r"\([^()]+\)", "", stripped)
    if "*" in outside:
        return True

    for m in re.finditer(r"\(([^()]+)\)", stripped):
        inner = m.group(1)
        if "*" not in inner:
            continue
        if re.search(r"(?<! )\*|\*(?! )", inner):
            return True
        clauses = inner.split(" * ")
        if len(clauses) < 2:
            return True
        for clause in clauses:
            if not re.search(r"[\u0600-\u06FF]", clause) or not has_tashkeel(clause):
                return True
    return False


def _check_header_triple(
    doc_info: InspectedDocument,
    report: ValidationReport,
    catalog: RuleCatalog,
) -> None:
    """Verify the 3-line centered header formatting, canonical subject, and date/lecture line."""
    for h_idx in range(HEADER_LINE_COUNT):
        if not doc_info.paragraphs[h_idx].is_centered:
            report.flag(
                "HEADER_ALIGN_INVALID",
                h_idx,
                f"Header paragraph P{h_idx} must be center-aligned.",
                doc_info.paragraphs[h_idx].text.strip()[:60],
            )

    p0_text = doc_info.paragraphs[0].text.strip()
    if p0_text != "بسم الله الرحمن الرحيم":
        report.flag(
            "HEADER_P0_INVALID",
            0,
            f"Header P0 is '{p0_text}' (expected 'بسم الله الرحمن الرحيم').",
            p0_text[:60],
        )

    p1_text = doc_info.paragraphs[1].text.strip()
    canonical_subjects = catalog.canonical_subjects
    if not p1_text.startswith("المادة: "):
        report.flag(
            "HEADER_P1_SUBJECT_INVALID",
            1,
            f"Header P1 '{p1_text}' must start with 'المادة: '.",
            p1_text[:60],
        )
    else:
        subj_val = p1_text[len("المادة: ") :].strip()
        if canonical_subjects and subj_val not in canonical_subjects:
            report.flag(
                "HEADER_P1_SUBJECT_INVALID",
                1,
                f"Header P1 subject '{subj_val}' is not a canonical subject from CONTEXT.md.",
                p1_text[:60],
            )

    p2_text = doc_info.paragraphs[2].text.strip()
    p2_ident = LectureIdentity.from_text(p2_text, routing_map=catalog.routing_map)
    normalized_p2 = collapse_whitespace(p2_text)
    if not ((p2_ident.date or p2_ident.lecture_number) and p2_ident.header_line_3 == normalized_p2):
        report.flag(
            "HEADER_P2_INVALID",
            2,
            f"Header P2 '{p2_text}' must be YYYY-MM-DD or 'المحاضرة: N'.",
            p2_text[:60],
        )


def _check_body_leaks_and_conclusion(
    para_records: list[ParagraphRecord],
    report: ValidationReport,
) -> None:
    """Audit all paragraphs for leaked tags/markdown and ensure final body ends with canonical du'a."""
    non_empty_body: list[ParagraphRecord] = []
    for rec in para_records:
        stripped = rec.text.strip()
        if not stripped:
            continue
        if rec.index >= HEADER_LINE_COUNT:
            non_empty_body.append(rec)

        for pat in LEAKED_METADATA_PATTERNS:
            if pat.search(stripped):
                report.flag(
                    "LEAKED_METADATA",
                    rec.index,
                    f"Paragraph P{rec.index} contains leaked metadata or raw tag matching '{pat.pattern}'.",
                    stripped[:80],
                )

        if _has_illegal_asterisk(stripped):
            report.flag(
                "FORBIDDEN_CHAR_ASTERISK",
                rec.index,
                f"Paragraph P{rec.index} contains literal '*' outside a spaced vowelized Quranic citation '(آية * آية)'.",
                stripped[:80],
            )

        if "`" in stripped:
            report.flag(
                "LEAKED_METADATA",
                rec.index,
                f"Paragraph P{rec.index} contains leaked backtick '`'.",
                stripped[:80],
            )

    if non_empty_body:
        last_rec = non_empty_body[-1]
        last_text = last_rec.text.strip()
        if not CANONICAL_DUA_PATTERN.search(last_text):
            report.flag(
                "CONCLUSION_DUA_INVALID",
                last_rec.index,
                f"Final paragraph does not end with the exact canonical council expiation du'a: '{CANONICAL_DUA_TEXT}'",
                last_text[-140:],
            )


def check_headers_and_conclusion(
    doc_info: InspectedDocument,
    para_records: list[ParagraphRecord],
    report: ValidationReport,
    catalog: RuleCatalog,
) -> None:
    """Verify the 3-line canonical header, absence of leaked tags/markdown, and conclusion du'a."""
    if len(doc_info.paragraphs) <= HEADER_LINE_COUNT:
        report.flag(
            "DOCUMENT_TOO_SHORT",
            None,
            f"Document has fewer than {HEADER_LINE_COUNT + 1} paragraphs (missing {HEADER_LINE_COUNT}-line header or body).",
        )
        return
    _check_header_triple(doc_info, report, catalog)
    _check_body_leaks_and_conclusion(para_records, report)
