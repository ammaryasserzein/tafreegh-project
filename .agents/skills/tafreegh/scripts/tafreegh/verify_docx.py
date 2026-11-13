from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .arabic_normalizer import (
    has_tashkeel,
    normalize_arabic,
    normalize_arabic_search,
    strip_tashkeel,
    strip_tashkeel_preserving_citations,
)
from .lecture_identity import NOTEBOOKLM_HEADER_PATTERNS, LectureIdentity
from .matn_matcher import (
    COMPOUND_SHARH_SPLIT_RE,
    MatchMode,
    SequentialMatnMatcher,
)
from .word_gateway import (
    DEFAULT_BIDI_LANG,
    DEFAULT_FONT_NAME,
    DEFAULT_FONT_SIZE,
    DEFAULT_MARGIN_INCHES,
    MARGIN_TOLERANCE_INCHES,
    DocxArchiveError,
    InspectedDocument,
    inspect_docx,
    read_matn_source_content,
)
from .workspace_catalog import RuleCatalog, WorkspaceConfig, resolve_runtime_context

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HEADER_LINE_COUNT = 3

CANONICAL_DUA_TEXT = (
    "والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، "
    "سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك."
)
CANONICAL_DUA_PATTERN = re.compile(
    r"والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى (?:آله|اله) وصحبه أجمعين، "
    r"سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك\.$"
)


class Severity(str, Enum):
    ERROR = "ERROR"


@dataclass(frozen=True)
class ParagraphRecord:
    index: int
    text: str
    is_matn: bool


@dataclass
class ValidationIssue:
    code: str
    severity: Severity
    paragraph_index: int | None
    message: str
    snippet: str = ""


@dataclass
class ValidationReport:
    docx_path: str
    issues: list[ValidationIssue] = field(default_factory=list)
    total_paragraphs: int = 0
    matn_paragraphs: int = 0
    student_paragraphs: int = 0

    @property
    def error_count(self) -> int:
        return len(self.issues)

    @property
    def passed(self) -> bool:
        return self.error_count == 0

    def to_dict(self) -> dict:
        return {
            "docx_path": self.docx_path,
            "passed": self.passed,
            "error_count": self.error_count,
            "total_paragraphs": self.total_paragraphs,
            "matn_paragraphs": self.matn_paragraphs,
            "student_paragraphs": self.student_paragraphs,
            "issues": [
                {
                    "code": i.code,
                    "severity": i.severity.value,
                    "paragraph_index": i.paragraph_index,
                    "message": i.message,
                    "snippet": i.snippet,
                }
                for i in self.issues
            ],
        }


def _flag(
    report: ValidationReport,
    code: str,
    paragraph_index: int | None,
    message: str,
    snippet: str = "",
) -> None:
    report.issues.append(
        ValidationIssue(
            code=code,
            severity=Severity.ERROR,
            paragraph_index=paragraph_index,
            message=message,
            snippet=snippet,
        )
    )


def _is_matn_paragraph(p_idx: int, p_text: str, any_bold: bool, all_bold: bool) -> bool:
    """A valid Matn paragraph is in body (p_idx >= HEADER_LINE_COUNT), enclosed in (...), and fully bold."""
    stripped = p_text.strip()
    if p_idx < HEADER_LINE_COUNT or not stripped:
        return False
    return any_bold and all_bold and stripped.startswith("(") and stripped.endswith(")")


def _check_ooxml_styling(doc_info: InspectedDocument, report: ValidationReport) -> list[ParagraphRecord]:
    """Checks section margins, paragraph RTL, run fonts/sizes/colors/bold/breaks via Word OOXML Gateway."""
    for section in doc_info.sections:
        for side_name, margin_val in (
            ("top", section.top_inches),
            ("bottom", section.bottom_inches),
            ("left", section.left_inches),
            ("right", section.right_inches),
        ):
            if margin_val is None or abs(margin_val - DEFAULT_MARGIN_INCHES) > MARGIN_TOLERANCE_INCHES:
                actual = f"{margin_val:.2f}" if margin_val is not None else "None"
                _flag(
                    report,
                    "MARGIN_INVALID",
                    None,
                    (
                        f"Section {section.section_index} {side_name} margin is {actual}in "
                        f"(expected {DEFAULT_MARGIN_INCHES:.2f}in)."
                    ),
                )

    para_records: list[ParagraphRecord] = []
    report.total_paragraphs = len(doc_info.paragraphs)

    for p in doc_info.paragraphs:
        p_idx = p.index
        p_text = p.text
        stripped = p_text.strip()

        if p.manual_line_break_count:
            _flag(
                report,
                "MANUAL_LINE_BREAK",
                p_idx,
                (
                    f"Paragraph P{p_idx} contains {p.manual_line_break_count} manual line break(s) "
                    "(<w:br/>); use native paragraphs."
                ),
                stripped[:80],
            )

        if not stripped:
            para_records.append(ParagraphRecord(p_idx, p_text, False))
            continue

        if not p.has_bidi:
            _flag(
                report,
                "PARAGRAPH_RTL_MISSING",
                p_idx,
                f"Paragraph P{p_idx} is missing w:bidi RTL property.",
                stripped[:80],
            )

        non_empty_runs = [r for r in p.runs if r.text and r.text.strip()]
        for r in non_empty_runs:
            if r.font_name != DEFAULT_FONT_NAME:
                _flag(
                    report,
                    "FONT_NAME_INVALID",
                    p_idx,
                    f"Paragraph P{p_idx} run has font '{r.font_name}' (expected '{DEFAULT_FONT_NAME}').",
                    r.text[:60],
                )

            if r.font_size_pt is None or abs(r.font_size_pt - float(DEFAULT_FONT_SIZE)) > 0.1:
                _flag(
                    report,
                    "FONT_SIZE_INVALID",
                    p_idx,
                    (
                        f"Paragraph P{p_idx} run has font size {r.font_size_pt}pt "
                        f"(expected {float(DEFAULT_FONT_SIZE):.1f}pt)."
                    ),
                    r.text[:60],
                )

            if r.has_rpr:
                if r.color_val is not None:
                    if r.color_val and r.color_val.lower() not in ("auto", "000000"):
                        _flag(
                            report,
                            "FONT_COLOR_FORBIDDEN",
                            p_idx,
                            f"Paragraph P{p_idx} run has inline color '{r.color_val}' (must inherit default black).",
                            r.text[:60],
                        )
                    else:
                        _flag(
                            report,
                            "FONT_COLOR_FORBIDDEN",
                            p_idx,
                            f"Paragraph P{p_idx} run injects inline <w:color/> tag.",
                            r.text[:60],
                        )

                if not r.has_rtl:
                    _flag(
                        report,
                        "RUN_RTL_MISSING",
                        p_idx,
                        f"Paragraph P{p_idx} run is missing <w:rtl/>.",
                        r.text[:60],
                    )
                if r.bidi_lang != DEFAULT_BIDI_LANG:
                    _flag(
                        report,
                        "RUN_LANG_MISSING",
                        p_idx,
                        f"Paragraph P{p_idx} run is missing w:lang w:bidi='{DEFAULT_BIDI_LANG}'.",
                        r.text[:60],
                    )

        any_bold = any(r.is_bold for r in non_empty_runs)
        all_bold = bool(non_empty_runs) and all(r.is_bold for r in non_empty_runs)
        is_matn = _is_matn_paragraph(p_idx, p_text, any_bold, all_bold)

        if p_idx < HEADER_LINE_COUNT and any_bold:
            _flag(
                report,
                "HEADER_BOLD_FORBIDDEN",
                p_idx,
                f"Header paragraph P{p_idx} must not be bold.",
                stripped[:80],
            )
        elif p_idx >= HEADER_LINE_COUNT and any_bold:
            if not is_matn:
                _flag(
                    report,
                    "ILLEGAL_BOLD_RUN",
                    p_idx,
                    f"Paragraph P{p_idx} contains bold runs outside a standalone Matn '(...)' block.",
                    stripped[:80],
                )
            else:
                for r in non_empty_runs:
                    if r.is_bold and (not r.has_b or not r.has_b_cs):
                        _flag(
                            report,
                            "MATN_BOLD_CS_MISSING",
                            p_idx,
                            f"Matn paragraph P{p_idx} bold run must set both w:b and w:bCs.",
                            r.text[:60],
                        )

        if is_matn:
            report.matn_paragraphs += 1
        if stripped.startswith("طالب:"):
            report.student_paragraphs += 1

        para_records.append(ParagraphRecord(p_idx, p_text, is_matn))

    return para_records


LEAKED_METADATA_PATTERNS = [
    *NOTEBOOKLM_HEADER_PATTERNS,
    re.compile(r"button[\\_]*magic", re.IGNORECASE),
    re.compile(r"source\s*guide", re.IGNORECASE),
    re.compile(r"دليل\s*المصادر|دليل\s*المصدر"),
    re.compile(r"\.(?:mp3|m4a|wav|aac|ogg|opus)\b", re.IGNORECASE),
    re.compile(r"<!--.*?-->"),
    re.compile(r"تقرير المتن الهجين"),
]


def _has_illegal_asterisk(stripped: str, is_matn: bool) -> bool:
    """Returns True if stripped contains any '*' outside a spaced, vowelized parenthesized Quranic citation '(آية * آية)'."""
    if "*" not in stripped:
        return False
    if "**" in stripped:
        return True

    # In a Matn block, outer parentheses double as citation parentheses
    target = stripped

    outside = re.sub(r"\([^()]+\)", "", target)
    if "*" in outside:
        return True

    for m in re.finditer(r"\(([^()]+)\)", target):
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


def _check_headers_and_conclusion(
    doc_info: InspectedDocument,
    para_records: list[ParagraphRecord],
    report: ValidationReport,
    catalog: RuleCatalog,
) -> None:
    if len(doc_info.paragraphs) <= HEADER_LINE_COUNT:
        _flag(
            report,
            "DOCUMENT_TOO_SHORT",
            None,
            f"Document has fewer than {HEADER_LINE_COUNT + 1} paragraphs (missing {HEADER_LINE_COUNT}-line header or body).",
        )
        return

    for h_idx in range(HEADER_LINE_COUNT):
        if not doc_info.paragraphs[h_idx].is_centered:
            _flag(
                report,
                "HEADER_ALIGN_INVALID",
                h_idx,
                f"Header paragraph P{h_idx} must be center-aligned.",
                doc_info.paragraphs[h_idx].text.strip()[:60],
            )

    p0_text = doc_info.paragraphs[0].text.strip()
    if p0_text != "بسم الله الرحمن الرحيم":
        _flag(
            report,
            "HEADER_P0_INVALID",
            0,
            f"Header P0 is '{p0_text}' (expected 'بسم الله الرحمن الرحيم').",
            p0_text[:60],
        )

    p1_text = doc_info.paragraphs[1].text.strip()
    canonical_subjects = catalog.canonical_subjects
    if not p1_text.startswith("المادة: "):
        _flag(
            report,
            "HEADER_P1_SUBJECT_INVALID",
            1,
            f"Header P1 '{p1_text}' must start with 'المادة: '.",
            p1_text[:60],
        )
    else:
        subj_val = p1_text[len("المادة: ") :].strip()
        if canonical_subjects and subj_val not in canonical_subjects:
            _flag(
                report,
                "HEADER_P1_SUBJECT_INVALID",
                1,
                f"Header P1 subject '{subj_val}' is not a canonical subject from CONTEXT.md.",
                p1_text[:60],
            )

    p2_text = doc_info.paragraphs[2].text.strip()
    p2_ident = LectureIdentity.from_text(p2_text, routing_map=catalog.routing_map)
    normalized_p2 = re.sub(r"\s+", " ", p2_text)
    if not ((p2_ident.date or p2_ident.lecture_number) and p2_ident.header_line_3 == normalized_p2):
        _flag(
            report,
            "HEADER_P2_INVALID",
            2,
            f"Header P2 '{p2_text}' must be YYYY-MM-DD or 'المحاضرة: N'.",
            p2_text[:60],
        )

    non_empty_body: list[ParagraphRecord] = []
    for rec in para_records:
        stripped = rec.text.strip()
        if not stripped:
            continue
        if rec.index >= HEADER_LINE_COUNT:
            non_empty_body.append(rec)

        for pat in LEAKED_METADATA_PATTERNS:
            if pat.search(stripped):
                _flag(
                    report,
                    "LEAKED_METADATA",
                    rec.index,
                    f"Paragraph P{rec.index} contains leaked metadata or raw tag matching '{pat.pattern}'.",
                    stripped[:80],
                )

        if _has_illegal_asterisk(stripped, rec.is_matn):
            _flag(
                report,
                "FORBIDDEN_CHAR_ASTERISK",
                rec.index,
                f"Paragraph P{rec.index} contains literal '*' outside a spaced vowelized Quranic citation '(آية * آية)'.",
                stripped[:80],
            )

        if "`" in stripped:
            _flag(
                report,
                "LEAKED_METADATA",
                rec.index,
                f"Paragraph P{rec.index} contains leaked backtick '`'.",
                stripped[:80],
            )

    if non_empty_body:
        last_rec = non_empty_body[-1]
        last_text = last_rec.text.strip()
        if not CANONICAL_DUA_PATTERN.search(last_text):
            _flag(
                report,
                "CONCLUSION_DUA_INVALID",
                last_rec.index,
                f"Final paragraph does not end with the exact canonical council expiation du'a: '{CANONICAL_DUA_TEXT}'",
                last_text[-140:],
            )


def _is_standalone_poetry_line(stripped: str, is_matn: bool) -> bool:
    """Checks if a paragraph is a standalone poetry verse:
    either bolded Matn poetry '(الشطر الأول ... الشطر الثاني)' or unbolded shahid poetry 'الشطر الأول ... الشطر الثاني'.
    Must have a single ' ... ' separating two balanced hemistichs (2-7 words each) without prose colons ':'.
    """
    inner = stripped[1:-1].strip() if (is_matn and stripped.startswith("(") and stripped.endswith(")")) else stripped
    if ":" in inner:
        return False
    if not is_matn and ("(" in inner or ")" in inner):
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


def _check_punctuation_and_orthography(
    para_records: list[ParagraphRecord],
    report: ValidationReport,
) -> None:
    for rec in para_records:
        if rec.index < HEADER_LINE_COUNT:
            continue
        stripped = rec.text.strip()
        if not stripped:
            continue

        if re.search(r"\(\s+|\s+\)", stripped):
            _flag(
                report,
                "BRACKET_INTERNAL_SPACE",
                rec.index,
                f"Paragraph P{rec.index} has internal whitespace inside parentheses '( ... )'.",
                stripped[:80],
            )

        q_space_match = re.search(r'(?:^|[\s،.:؟!(])"\s+|\s+"(?=$|[\s،.:؟!)])', stripped)
        if q_space_match:
            start = max(0, q_space_match.start() - 20)
            end = min(len(stripped), q_space_match.end() + 20)
            _flag(
                report,
                "QUOTE_INTERNAL_SPACE",
                rec.index,
                f"Paragraph P{rec.index} has internal whitespace inside quotes '\" ... \"'.",
                stripped[start:end],
            )

        if ".." in stripped and not _is_standalone_poetry_line(stripped, rec.is_matn):
            _flag(
                report,
                "ELLIPSIS_FORBIDDEN",
                rec.index,
                f"Paragraph P{rec.index} contains ellipsis ('...' or '..') outside a standalone poetry line.",
                stripped[:80],
            )

        if not rec.is_matn:
            text_no_ellipsis = re.sub(r"\.{2,}", "", stripped)
            body_before_end = text_no_ellipsis[:-1] if text_no_ellipsis.endswith(".") else text_no_ellipsis
            if re.search(r"(?<!\d)\.(?!\d)", body_before_end):
                _flag(
                    report,
                    "MID_PARAGRAPH_PERIOD",
                    rec.index,
                    f"Non-Matn paragraph P{rec.index} contains a mid-paragraph period ('.'); replace with '،' or split paragraph.",
                    stripped[:90],
                )

        forbidden_punc = re.findall(r"[,?;[\]{}]", stripped)
        if forbidden_punc:
            _flag(
                report,
                "FORBIDDEN_PUNCTUATION",
                rec.index,
                f"Paragraph P{rec.index} contains forbidden punctuation/brackets {set(forbidden_punc)}.",
                stripped[:80],
            )

        if not rec.is_matn and re.search(r"(?<!\w)إذن(?!\w)", stripped):
            _flag(
                report,
                "ORTHOGRAPHY_IZHAN_NUN",
                rec.index,
                f"Paragraph P{rec.index} writes 'إذن' with nun; standardize to 'إذًا'.",
                stripped[:80],
            )


def _strip_parenthesized_citations(text: str) -> str:
    """Removes parenthesized citations (...) from text."""
    return re.sub(r"\([^)]*\)", " ", text)


def _check_dialect_and_dialogue(
    para_records: list[ParagraphRecord],
    report: ValidationReport,
    catalog: RuleCatalog,
) -> None:
    rules = catalog.dialect_replacements
    attendee_rules = catalog.attendee_rules

    for rec in para_records:
        if rec.index < HEADER_LINE_COUNT:
            continue
        stripped = rec.text.strip()
        if not stripped or rec.is_matn:
            continue

        if re.match(r"^(?:الشيخ|شيخ)\s*:", stripped):
            _flag(
                report,
                "SHEIKH_PREFIX_FORBIDDEN",
                rec.index,
                f"Paragraph P{rec.index} prefixes speech with 'الشيخ:'; default speaker must have no prefix.",
                stripped[:80],
            )

        if re.match(r"^طالب\s*\d+\s*:", stripped):
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
                if re.match(r"^\(\s*صوت غير مسموع\s*\)\.?$", student_body):
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

        scan_text = _strip_parenthesized_citations(stripped)
        scan_no_quotes = strip_tashkeel(re.sub(r'"[^"]*"', " ", scan_text))
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


FALLBACK_MATN_TRIGGERS: list[tuple[str, re.Pattern]] = [
    ("قالوا", re.compile(r"(?:^|[،.؟!:)»\"\s])(قالوا\s*:?\s*[^.؟!\n]+)")),
    ("فإن قلت", re.compile(r"(?:^|[،.؟!:)»\"\s])(فإن\s+قلت\s*:?\s*[^.؟!\n]+)")),
    ("قلت", re.compile(r"(?:^|[،.؟!:)»\"\s])(قلت(?:\s+في)?\s*:?\s*[^.؟!\n]+)")),
    ("وأيضا", re.compile(r"(?:^|[،.؟!:)»\"\s])(وأيضا\s*:?\s*[^.؟!\n]+)")),
    ("فصل في", re.compile(r"(?:^|[،.؟!:)»\"\s])(فصل\s+في\s+[\u0600-\u06FF\s]{4,40}?)(?=[،.؟!]|$)")),
    ("قال الشاعر", re.compile(r"(?:^|[،.؟!:)»\"])\s*([^،.؟!\n]+[،:]\s*قال\s+الشاعر\s*:?)")),
    ("قال", re.compile(r"(?:^|[،.؟!:)»\"\s])(قال(?!\s+(?:تعالى|الله|النبي|رسول))\s*:\s*[^.؟!\n]+)")),
]


def _has_colloquial_marker(
    text: str,
    dialect_markers: frozenset[str] | set[str],
) -> bool:
    plain = strip_tashkeel(text)
    if re.search(r"(?<!\w)هو\s+[\u0600-\u06FF\s]+\s+ولا\s+", plain):
        return True
    words = re.findall(r"[\u0600-\u06FF]+", plain)
    for w in words:
        w_norm = normalize_arabic(w)
        if w in dialect_markers or w_norm in dialect_markers:
            return True
        if w.startswith(("هت", "هي", "بي", "بت", "ما")) and w.endswith("ش") and len(w) >= 4:
            return True
    return False


def _extract_leading_classical_clause(
    candidate: str,
    dialect_markers: frozenset[str] | set[str],
) -> str:
    """Extracts consecutive leading Classical Arabic sub-clauses before any colloquial shift."""
    # Split on parenthetical colloquial glosses or commas
    sub_clauses = re.split(r"https?://|\s*-\s*يعني\s+|[،]", candidate)
    classical_parts: list[str] = []
    for sub in sub_clauses:
        sub_clean = sub.strip(" .؟!:-")
        if not sub_clean:
            continue
        if _has_colloquial_marker(sub_clean, dialect_markers):
            break
        classical_parts.append(sub_clean)
    return "، ".join(classical_parts)


def _check_unbolded_fallback_matn(
    para_records: list[ParagraphRecord],
    report: ValidationReport,
    dialect_markers: frozenset[str] | set[str],
) -> None:
    """Detects candidate unbolded Classical Arabic Sharh/Matn clauses inside explanation paragraphs."""
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
                words = re.findall(r"[\u0600-\u06FF]+", core_clause)
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


class MatnAlignmentValidator:
    """Validator seam component verifying exported Matn blocks against canonical <matn_source> non-destructively."""

    def __init__(self, matn_source: str | SequentialMatnMatcher):
        if isinstance(matn_source, SequentialMatnMatcher):
            self.source = matn_source.source
        else:
            self.source = matn_source
        self._collapsed_source = re.sub(r"\s+", " ", self.source).strip()
        # Internal sequential matcher isolated to this validator instance;
        # will never mutate any external domain matcher passed in.
        self._matcher = SequentialMatnMatcher(self.source)

    @property
    def cursor(self) -> int:
        return self._matcher.cursor

    @property
    def cursor_norm(self) -> int:
        return self._matcher.cursor_norm

    def verify_exported_segment(self, exported_text: str) -> bool:
        """Verifies an exported Matn block against canonical source using sequential cursor semantics."""
        inner_collapsed = re.sub(r"\s+", " ", exported_text).strip()
        if not inner_collapsed:
            return True

        res = self._matcher.match_segment(inner_collapsed)
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
                jump_idx = self._matcher.norm_source.find(norm_q, self._matcher.cursor_norm)
                if jump_idx != -1:
                    self._matcher.cursor_norm = jump_idx + len(norm_q)
                    self._matcher.cursor = (
                        self._matcher.pos_map[self._matcher.cursor_norm - 1] + 1
                    )
                return True
            return False

        norm_query = normalize_arabic_search(inner_collapsed)
        if norm_query and norm_query in self._matcher.norm_source:
            return inner_collapsed in self._collapsed_source
        return True

    def verify_segment(self, exported_text: str) -> bool:
        """Alias for verify_exported_segment."""
        return self.verify_exported_segment(exported_text)


def _verify_exported_matn_segment(
    exported_text: str,
    matn_source: str | SequentialMatnMatcher | None = None,
    matcher: SequentialMatnMatcher | None = None,
) -> bool:
    """Functional validator seam helper verifying an exported segment without mutating external matcher state."""
    target = matcher if matcher is not None else matn_source
    if target is None:
        raise ValueError("Either matn_source or matcher must be provided")
    validator = MatnAlignmentValidator(target)
    return validator.verify_exported_segment(exported_text)


def _check_matn_alignment(
    para_records: list[ParagraphRecord],
    matn_path: Path,
    report: ValidationReport,
) -> None:
    """Verifies Primary Mode and compound Sharh-Matn blocks against canonical <matn_source>."""
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


def _clean_raw_for_coverage(raw_text: str) -> list[str]:
    """Cleans transcript words for coverage comparison."""
    lines = []
    for line in raw_text.splitlines():
        l = line.strip()
        if not l:
            continue
        if re.search(r"\.(?:mp3|m4a|wav|aac|ogg|opus)\b", l, re.IGNORECASE):
            continue
        if re.search(r"source\s*guide|button[\\_]*magic|دليل\s*المصدر|المصادر", l, re.IGNORECASE):
            continue
        lines.append(l)

    joined = " ".join(lines)
    norm = normalize_arabic_search(joined)
    words = norm.split()
    return [w for w in words if w not in ("ا", "اا", "ااا", "ام", "اه", "ها", "و")]


def _find_unmatched_windows(
    source_words: list[str],
    target_words_set: set[str],
    target_bigrams: set[str],
    window_size: int = 12,
) -> list[str]:
    """Finds 12-word windows in source_words with 0 bigram hits and <50% unigram hits in target."""
    unmatched: list[str] = []
    idx = 0
    while idx <= len(source_words) - window_size:
        chunk_words = source_words[idx : idx + window_size]
        bigram_hits = sum(
            1
            for j in range(window_size - 1)
            if f"{chunk_words[j]} {chunk_words[j + 1]}" in target_bigrams
        )
        word_hits = sum(1 for w in chunk_words if w in target_words_set)
        if bigram_hits == 0 and word_hits < (window_size // 2):
            unmatched.append(" ".join(chunk_words))
            idx += window_size
        else:
            idx += 1
    return unmatched


def _check_raw_coverage(
    para_records: list[ParagraphRecord],
    raw_path: Path,
    report: ValidationReport,
) -> None:
    if not raw_path.exists():
        return
    raw_text = raw_path.read_text(encoding="utf-8")
    raw_words = _clean_raw_for_coverage(raw_text)
    window_size = 12
    if len(raw_words) < window_size:
        return

    body_texts = [rec.text for rec in para_records if rec.index >= HEADER_LINE_COUNT and rec.text.strip()]
    docx_norm = normalize_arabic_search(" ".join(body_texts))
    docx_words_list = docx_norm.split()
    docx_words_set = set(docx_words_list)
    docx_bigrams = {
        f"{docx_words_list[i]} {docx_words_list[i + 1]}"
        for i in range(len(docx_words_list) - 1)
    }

    for dropped_phrase in _find_unmatched_windows(raw_words, docx_words_set, docx_bigrams, window_size):
        _flag(
            report,
            "RAW_COVERAGE_DROP",
            None,
            f"Raw transcript clause appears dropped from .docx: '{dropped_phrase}'.",
            dropped_phrase,
        )

    # Reverse check (docx -> raw): detect hallucinated explanation additions
    raw_words_set = set(raw_words)
    raw_bigrams = {
        f"{raw_words[i]} {raw_words[i + 1]}"
        for i in range(len(raw_words) - 1)
    }

    for rec in para_records:
        if rec.index < HEADER_LINE_COUNT or rec.is_matn:
            continue
        p_clean = CANONICAL_DUA_PATTERN.sub("", rec.text.strip())
        p_clean = re.sub(r"^طالب:\s*", "", p_clean)
        p_clean = p_clean.replace("صوت غير مسموع", "")
        p_clean = _strip_parenthesized_citations(p_clean)
        p_words = _clean_raw_for_coverage(p_clean)
        if len(p_words) < window_size:
            continue

        for added_phrase in _find_unmatched_windows(p_words, raw_words_set, raw_bigrams, window_size):
            _flag(
                report,
                "RAW_HALLUCINATION_ADDITION",
                rec.index,
                f"Paragraph P{rec.index} contains a clause not found in raw transcript: '{added_phrase}'.",
                added_phrase,
            )


def verify_docx(
    docx_path: Path | str,
    raw_path: Path | str | None = None,
    matn_path: Path | str | None = None,
    context_path: Path | str | None = None,
    dialect_rules_path: Path | str | None = None,
    *,
    workspace: WorkspaceConfig | None = None,
    catalog: RuleCatalog | None = None,
) -> ValidationReport:
    docx_path = Path(docx_path)
    report = ValidationReport(docx_path=str(docx_path))
    doc_info = inspect_docx(docx_path)

    _, active_catalog = resolve_runtime_context(
        workspace=workspace,
        catalog=catalog,
        context_path=context_path,
        dialect_rules_path=dialect_rules_path,
    )

    para_records = _check_ooxml_styling(doc_info, report)
    _check_headers_and_conclusion(doc_info, para_records, report, catalog=active_catalog)
    _check_punctuation_and_orthography(para_records, report)
    _check_dialect_and_dialogue(para_records, report, catalog=active_catalog)
    _check_unbolded_fallback_matn(
        para_records,
        report,
        dialect_markers=active_catalog.dialect_markers,
    )
    if matn_path:
        _check_matn_alignment(para_records, Path(matn_path), report)
    if raw_path:
        _check_raw_coverage(para_records, Path(raw_path), report)
    return report


def format_report_text(report: ValidationReport) -> str:
    status = "PASSED" if report.passed else "FAILED"
    lines = [
        f"=== Tafreegh DOCX Verification Report [{status}] ===",
        f"File: {report.docx_path}",
        f"Paragraphs: {report.total_paragraphs} (Matn: {report.matn_paragraphs}, Student: {report.student_paragraphs})",
        f"Errors: {report.error_count}",
    ]
    if report.issues:
        lines.append("\nIssues:")
        for idx, issue in enumerate(report.issues, 1):
            loc = f"P{issue.paragraph_index}" if issue.paragraph_index is not None else "DOC"
            lines.append(f"  {idx}. [{issue.severity.value}] [{issue.code}] ({loc}) {issue.message}")
            if issue.snippet:
                lines.append(f"     Snippet: {issue.snippet}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Verify exported Tafreegh .docx against all formatting, dialect, and alignment rules."
    )
    parser.add_argument("docx_path", type=Path, help="Path to the .docx file to verify.")
    parser.add_argument("--raw", type=Path, default=None, help="Optional path to raw transcript .md for coverage check.")
    parser.add_argument("--matn", type=Path, default=None, help="Optional path to canonical matn .md.")
    parser.add_argument("--context", type=Path, default=None, help="Optional path to CONTEXT.md.")
    parser.add_argument("--json", action="store_true", help="Output report as JSON.")

    args = parser.parse_args(argv)
    if not args.docx_path.exists():
        print(f"Error: File not found: {args.docx_path}", file=sys.stderr)
        return 2

    try:
        report = verify_docx(
            docx_path=args.docx_path,
            raw_path=args.raw,
            matn_path=args.matn,
            context_path=args.context,
        )
    except DocxArchiveError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_report_text(report))

    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
