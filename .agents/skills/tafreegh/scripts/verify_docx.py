from __future__ import annotations

import re
import sys
import warnings
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import docx
from docx.oxml.ns import qn

try:
    from export_docx import (
        DEFAULT_FONT_NAME,
        DEFAULT_FONT_SIZE,
        DIALECT_MARKERS,
        NOTEBOOKLM_HEADER_PATTERNS,
        read_matn_source_content,
    )
    from lecture_identity import (
        LectureIdentity,
        load_canonical_routing,
        normalize_arabic,
    )
    from matn_matcher import (
        COMPOUND_SHARH_SPLIT_RE,
        MatchMode,
        SequentialMatnMatcher,
        TASHKEEL_REGEX,
        normalize_arabic_search,
        strip_tashkeel,
        strip_tashkeel_preserving_citations,
    )
except ImportError:
    from .export_docx import (
        DEFAULT_FONT_NAME,
        DEFAULT_FONT_SIZE,
        DIALECT_MARKERS,
        NOTEBOOKLM_HEADER_PATTERNS,
        read_matn_source_content,
    )
    from .lecture_identity import (
        LectureIdentity,
        load_canonical_routing,
        normalize_arabic,
    )
    from .matn_matcher import (
        COMPOUND_SHARH_SPLIT_RE,
        MatchMode,
        SequentialMatnMatcher,
        TASHKEEL_REGEX,
        normalize_arabic_search,
        strip_tashkeel,
        strip_tashkeel_preserving_citations,
    )

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HEADER_LINE_COUNT = 3
DEFAULT_DIALECT_RULES_PATH = Path(__file__).resolve().parent.parent / "references" / "dialect-rules.md"

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


def _is_run_bold(r) -> tuple[bool, bool, bool]:
    """Returns (is_bold, has_b, has_bCs)."""
    rPr = r._r.find(qn("w:rPr"))
    has_b = False
    has_bCs = False
    if rPr is not None:
        b = rPr.find(qn("w:b"))
        if b is not None:
            val = b.get(qn("w:val"))
            if val not in ("0", "false", "False", "off"):
                has_b = True
        bCs = rPr.find(qn("w:bCs"))
        if bCs is not None:
            val = bCs.get(qn("w:val"))
            if val not in ("0", "false", "False", "off"):
                has_bCs = True
    return (has_b or has_bCs or bool(r.bold)), has_b or bool(r.bold), has_bCs


def _is_matn_paragraph(p_idx: int, p_text: str, any_bold: bool, all_bold: bool) -> bool:
    """A valid Matn paragraph is in body (p_idx >= HEADER_LINE_COUNT), enclosed in (...), and fully bold."""
    stripped = p_text.strip()
    if p_idx < HEADER_LINE_COUNT or not stripped:
        return False
    return any_bold and all_bold and stripped.startswith("(") and stripped.endswith(")")


def _check_ooxml_styling(doc: docx.Document, report: ValidationReport) -> list[ParagraphRecord]:
    """Checks section margins, paragraph RTL, run fonts/sizes/colors/bold/breaks."""
    for s_idx, section in enumerate(doc.sections):
        for side_name, margin_val in (
            ("top", section.top_margin),
            ("bottom", section.bottom_margin),
            ("left", section.left_margin),
            ("right", section.right_margin),
        ):
            if margin_val is None or abs(margin_val.inches - 0.5) > 0.02:
                actual = f"{margin_val.inches:.2f}" if margin_val is not None else "None"
                _flag(
                    report,
                    "MARGIN_INVALID",
                    None,
                    f"Section {s_idx} {side_name} margin is {actual}in (expected 0.50in).",
                )

    para_records: list[ParagraphRecord] = []
    report.total_paragraphs = len(doc.paragraphs)

    for p_idx, p in enumerate(doc.paragraphs):
        p_text = p.text
        stripped = p_text.strip()

        br_nodes = p._p.findall(".//" + qn("w:br"))
        if br_nodes:
            _flag(
                report,
                "MANUAL_LINE_BREAK",
                p_idx,
                f"Paragraph P{p_idx} contains {len(br_nodes)} manual line break(s) (<w:br/>); use native paragraphs.",
                stripped[:80],
            )

        if not stripped:
            para_records.append(ParagraphRecord(p_idx, p_text, False))
            continue

        pPr = p._p.find(qn("w:pPr"))
        has_bidi = pPr is not None and pPr.find(qn("w:bidi")) is not None
        if not has_bidi:
            _flag(
                report,
                "PARAGRAPH_RTL_MISSING",
                p_idx,
                f"Paragraph P{p_idx} is missing w:bidi RTL property.",
                stripped[:80],
            )

        non_empty_runs = [r for r in p.runs if r.text and r.text.strip()]
        run_bold_states = []

        for r in non_empty_runs:
            is_bold, has_b, has_bCs = _is_run_bold(r)
            run_bold_states.append((r, is_bold, has_b, has_bCs))

            rPr = r._r.find(qn("w:rPr"))
            font_name = r.font.name
            if rPr is not None and not font_name:
                rFonts = rPr.find(qn("w:rFonts"))
                if rFonts is not None:
                    font_name = rFonts.get(qn("w:cs")) or rFonts.get(qn("w:ascii"))
            if font_name != DEFAULT_FONT_NAME:
                _flag(
                    report,
                    "FONT_NAME_INVALID",
                    p_idx,
                    f"Paragraph P{p_idx} run has font '{font_name}' (expected '{DEFAULT_FONT_NAME}').",
                    r.text[:60],
                )

            size_pt = r.font.size.pt if r.font.size is not None else None
            if size_pt is None or abs(size_pt - float(DEFAULT_FONT_SIZE)) > 0.1:
                _flag(
                    report,
                    "FONT_SIZE_INVALID",
                    p_idx,
                    f"Paragraph P{p_idx} run has font size {size_pt}pt (expected {float(DEFAULT_FONT_SIZE):.1f}pt).",
                    r.text[:60],
                )

            if rPr is not None:
                color_el = rPr.find(qn("w:color"))
                if color_el is not None:
                    val = color_el.get(qn("w:val"))
                    if val and val.lower() not in ("auto", "000000"):
                        _flag(
                            report,
                            "FONT_COLOR_FORBIDDEN",
                            p_idx,
                            f"Paragraph P{p_idx} run has inline color '{val}' (must inherit default black).",
                            r.text[:60],
                        )
                    elif val is not None:
                        _flag(
                            report,
                            "FONT_COLOR_FORBIDDEN",
                            p_idx,
                            f"Paragraph P{p_idx} run injects inline <w:color/> tag.",
                            r.text[:60],
                        )

                if rPr.find(qn("w:rtl")) is None:
                    _flag(
                        report,
                        "RUN_RTL_MISSING",
                        p_idx,
                        f"Paragraph P{p_idx} run is missing <w:rtl/>.",
                        r.text[:60],
                    )
                lang_el = rPr.find(qn("w:lang"))
                if lang_el is None or lang_el.get(qn("w:bidi")) != "ar-SA":
                    _flag(
                        report,
                        "RUN_LANG_MISSING",
                        p_idx,
                        f"Paragraph P{p_idx} run is missing w:lang w:bidi='ar-SA'.",
                        r.text[:60],
                    )

        any_bold = any(b[1] for b in run_bold_states)
        all_bold = bool(run_bold_states) and all(b[1] for b in run_bold_states)
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
                for r, is_b, has_b, has_bCs in run_bold_states:
                    if is_b and (not has_b or not has_bCs):
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


def _is_centered(p) -> bool:
    pPr = p._p.find(qn("w:pPr"))
    if pPr is not None:
        jc = pPr.find(qn("w:jc"))
        if jc is not None and jc.get(qn("w:val")) == "center":
            return True
    return False


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
            if not re.search(r"[\u0600-\u06FF]", clause) or not TASHKEEL_REGEX.search(clause):
                return True
    return False


def _check_headers_and_conclusion(
    doc: docx.Document,
    para_records: list[ParagraphRecord],
    report: ValidationReport,
    context_path: Path | str | None = None,
) -> None:
    if len(doc.paragraphs) <= HEADER_LINE_COUNT:
        _flag(
            report,
            "DOCUMENT_TOO_SHORT",
            None,
            f"Document has fewer than {HEADER_LINE_COUNT + 1} paragraphs (missing {HEADER_LINE_COUNT}-line header or body).",
        )
        return

    for h_idx in range(HEADER_LINE_COUNT):
        if not _is_centered(doc.paragraphs[h_idx]):
            _flag(
                report,
                "HEADER_ALIGN_INVALID",
                h_idx,
                f"Header paragraph P{h_idx} must be center-aligned.",
                doc.paragraphs[h_idx].text.strip()[:60],
            )

    p0_text = doc.paragraphs[0].text.strip()
    if p0_text != "بسم الله الرحمن الرحيم":
        _flag(
            report,
            "HEADER_P0_INVALID",
            0,
            f"Header P0 is '{p0_text}' (expected 'بسم الله الرحمن الرحيم').",
            p0_text[:60],
        )

    p1_text = doc.paragraphs[1].text.strip()
    routing_map = load_canonical_routing(Path(context_path) if context_path else None)
    canonical_subjects = set(routing_map.values())
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

    p2_text = doc.paragraphs[2].text.strip()
    p2_ident = LectureIdentity.from_text(p2_text)
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


def load_dialect_replacements(
    rules_path: Path | str | None = None,
) -> list[tuple[re.Pattern, str]]:
    """Dynamically parses Egyptian colloquial normalization rules from references/dialect-rules.md."""
    path = Path(rules_path) if rules_path else DEFAULT_DIALECT_RULES_PATH
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8")
    replacements: list[tuple[re.Pattern, str]] = []
    fused_particles: set[str] = set()

    for line in text.splitlines():
        stripped = line.strip()

        # 1. Parse Markdown table rows: | raw_variants | **target** | notes |
        if stripped.startswith("|") and "**" in stripped:
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) >= 2:
                raw_col, target_col = cells[0], cells[1]
                target_m = re.search(r"\*\*(.+?)\*\*", target_col)
                if not target_m:
                    continue
                target = target_m.group(1).strip()
                raw_without_placeholders = re.sub(r"\[[^\]]*\]", "", raw_col).strip()
                if not raw_without_placeholders:
                    continue
                variants = []
                for v in raw_without_placeholders.split("/"):
                    v_clean = v.strip()
                    # Skip placeholder patterns with brackets or parenthetical context notes
                    if not v_clean or any(ch in v_clean for ch in "[]()") or v_clean == target:
                        continue
                    variants.append(re.sub(r"\s+", r"\\s+", re.escape(v_clean)))
                if variants:
                    joined = "|".join(variants) if len(variants) > 1 else variants[0]
                    pat = re.compile(rf"(?<!\w)(?:{joined})(?!\w)")
                    replacements.append((pat, target))

        # 2. Parse Fused Negation Particles: **مفيهوش**، **مالهاش**، **ملوش**، **مفيش**، **مكانوش**، **ميقفوش**
        elif "Fused Negation Particles" in stripped:
            tokens = [m[0] or m[1] for m in re.findall(r"\*\*([^*]+)\*\*|`([^`]+)`", stripped)]
            for tok in tokens:
                tok_clean = tok.strip()
                if not re.search(r"[\u0600-\u06FF]", tok_clean):
                    continue
                fused_particles.add(tok_clean)
                if tok_clean.startswith("م") and not tok_clean.startswith("ما"):
                    unfused = "ما" + tok_clean[1:]
                    fused_particles.add(unfused)
                    replacements.append((re.compile(rf"(?<!\w){re.escape(unfused)}(?!\w)"), tok_clean))

        # 3. Parse Compound Verb Negation: Write ما + فعل + ش as separate particles: **ما جتش**، ...
        elif "Compound Verb Negation" in stripped:
            tokens = [m[0] or m[1] for m in re.findall(r"\*\*([^*]+)\*\*|`([^`]+)`", stripped)]
            for tok in tokens:
                tok_clean = tok.strip()
                if tok_clean.startswith("ما ") and tok_clean.endswith("ش") and "[" not in tok_clean and "+" not in tok_clean:
                    joined_form = tok_clean.replace(" ", "")
                    replacements.append((re.compile(rf"(?<!\w){re.escape(joined_form)}(?!\w)"), tok_clean))

            # General compound verb negation rule for any other attached ما+[verb]+ش not in fused_particles
            if fused_particles:
                excl = "|".join(re.escape(fp) for fp in sorted(fused_particles))
                comp_pat = re.compile(rf"(?<!\w)(?!(?:{excl})(?!\w))ما([\u0600-\u06FF]{{2,}})ش(?!\w)")
            else:
                comp_pat = re.compile(r"(?<!\w)ما([\u0600-\u06FF]{2,})ش(?!\w)")
            replacements.append((comp_pat, r"ما \1ش"))

    return replacements


def _strip_parenthesized_citations(text: str) -> str:
    """Removes parenthesized citations (...) from text."""
    return re.sub(r"\([^)]*\)", " ", text)


KINSHIP_GRAMMATICAL_STOPWORDS = frozenset({
    "ده", "في", "هنا", "هناك", "بيسأل", "يسأل", "قال", "بيقول", "يقول",
    "بتاع", "عايز", "عاوز", "طلب", "بعث", "بعت", "كاتب", "كتب", "اللي",
    "المسلم", "المؤمن", "الصعيدي", "الصييت", "الطالب", "الحاضر", "السائل",
    "المصري", "التاني", "بقى", "على", "يعني", "أحد", "يبقى", "وجاي", "واعتذر",
    "بيتساءل", "بتقول", "بيضرب", "عمال",
})

VOCATIVE_GRAMMATICAL_STOPWORDS = frozenset({
    "سيدي", "سيدنا", "ابني", "بني", "أخي", "أخانا", "أخونا", "أخويا", "اخويا",
    "جماعة", "إخواننا", "إخواني", "شباب", "ولاد", "أولاد", "أستاذ", "أستاذنا", "مولانا",
    "شيخنا", "عم", "رب", "ربنا", "ربي", "الله", "رسول", "نبي", "بشر",
    "ناس", "طالب", "طلاب", "حبيبي", "حبيبنا", "بشمهندس", "مهندس",
    "جميل", "عسل", "عساسيل", "عسايل", "حلويات", "إما", "اما", "إيه", "ايه", "ولا",
    "قول", "سؤال", "سلام", "نهار", "ابن", "واد", "كمن", "اللي", "ليتني", "ذا", "روح",
})


BASE_KINSHIP_NOUNS: frozenset[str] = frozenset({
    "أخوكم", "اخوكم", "أخونا", "اخونا", "الأخ", "الاخ", "الأخت", "الاخت",
})

BASE_KUNYA_PREFIXES: frozenset[str] = frozenset({
    "أبو", "ابو", "أبا", "ابا",
})

BASE_TITLE_PREFIXES: frozenset[str] = frozenset({
    "شيخ", "الشيخ", "دكتور", "الدكتور",
})

BASE_EXEMPT_NAMES: frozenset[str] = frozenset({
    "زيد", "عمرو", "بكر", "هند", "جحا", "إبراهيم",
})


def _is_vocative_grammatical_non_name(
    token: str,
    stopwords: frozenset[str] = VOCATIVE_GRAMMATICAL_STOPWORDS,
) -> bool:
    if token in stopwords:
        return True
    if token.endswith(("وك", "ها", "هم", "كم")):
        return True
    return bool(re.match(r"^ت[\u0621-\u064A]{3,}ه$", token))


@dataclass(frozen=True)
class AttendeeAnonymizationRules:
    placeholder: str
    kinship_nouns: frozenset[str]
    kunya_prefixes: frozenset[str]
    title_prefixes: frozenset[str]
    exempt_names: frozenset[str]
    kinship_stopwords: frozenset[str] = field(
        default_factory=lambda: KINSHIP_GRAMMATICAL_STOPWORDS
    )
    vocative_stopwords: frozenset[str] = field(
        default_factory=lambda: VOCATIVE_GRAMMATICAL_STOPWORDS
    )

    def is_vocative_non_name(self, token: str) -> bool:
        return _is_vocative_grammatical_non_name(token, self.vocative_stopwords)

    def find_leaks(self, text: str) -> list[tuple[str, str]]:
        """Scans stripped prose for unanonymized kinship and classroom vocative attendee references."""
        all_prefixes = sorted(self.kunya_prefixes | self.title_prefixes, key=len, reverse=True)
        prefix_alt = "|".join(re.escape(p) for p in all_prefixes)
        kinship_alt = "|".join(
            re.escape(k) for k in sorted(self.kinship_nouns, key=len, reverse=True)
        )
        prefix_group = rf"(?:(?:{prefix_alt})\s+)*" if prefix_alt else ""
        voc_prefix_group = rf"(?:(?P<prefix>{prefix_alt})\s+)?" if prefix_alt else ""

        leaks: list[tuple[str, str]] = []
        if kinship_alt:
            kinship_re = re.compile(
                rf"(?<!\w)[وف]?(?:{kinship_alt})\s+(?P<prefixes>{prefix_group})(?P<cand>[\u0621-\u064A]{{3,}})(?!\w)"
            )
            for m_kin in kinship_re.finditer(text):
                cand = m_kin.group("cand")
                prefix_tokens = m_kin.group("prefixes").split()
                has_kunya = any(p in self.kunya_prefixes for p in prefix_tokens)
                if cand == self.placeholder:
                    continue
                if not has_kunya and (cand in self.exempt_names or cand in self.kinship_stopwords):
                    continue
                leaks.append(("reference", m_kin.group(0)))

        vocative_re = re.compile(
            rf"(?<!\w)[وف]?(?P<trig>ولا\s+(?:إيه|ايه)|إيه|ايه|ها|قول|اتفضل|تفضل|نعم|ماشي|صح|فاهم)\s+يا\s+"
            rf"{voc_prefix_group}(?P<cand>[\u0621-\u064A]{{3,}})(?!\w)"
        )
        for m_voc in vocative_re.finditer(text):
            cand = m_voc.group("cand")
            prefix = m_voc.groupdict().get("prefix")
            trig = m_voc.group("trig").strip()
            if cand == self.placeholder:
                continue
            if prefix and prefix in self.kunya_prefixes:
                # Exempt Egyptian rhetorical topical echo: '<word> إيه يا أبو <word>'
                pre_window = text[max(0, m_voc.start() - 35) : m_voc.start()]
                if trig in ("إيه", "ايه") and re.search(
                    rf"(?<!\w)(?:[وفبكل]?ال|[وفبكل])?{re.escape(cand)}(?!\w)", pre_window
                ):
                    continue
                leaks.append(("vocative", m_voc.group(0)))
                continue
            if cand in self.exempt_names or cand in self.title_prefixes or self.is_vocative_non_name(cand):
                continue
            leaks.append(("vocative", m_voc.group(0)))

        return leaks


def load_attendee_anonymization_rules(
    rules_path: Path | str | None = None,
) -> AttendeeAnonymizationRules:
    """Dynamically parses Attendee Anonymization SSOT (exempt names, titles, kunyas) from references/dialect-rules.md."""
    path = Path(rules_path) if rules_path else DEFAULT_DIALECT_RULES_PATH
    placeholder = "فلان"
    kinship_nouns: set[str] = set()
    kunya_prefixes: set[str] = set()
    title_prefixes: set[str] = set()
    exempt_names: set[str] = set()

    if not path.exists():
        warnings.warn(
            f"Dialect rules file not found at {path}; using baseline attendee anonymization rules.",
            UserWarning,
            stacklevel=2,
        )
        return AttendeeAnonymizationRules(
            placeholder=placeholder,
            kinship_nouns=BASE_KINSHIP_NOUNS,
            kunya_prefixes=BASE_KUNYA_PREFIXES,
            title_prefixes=BASE_TITLE_PREFIXES,
            exempt_names=BASE_EXEMPT_NAMES,
            kinship_stopwords=KINSHIP_GRAMMATICAL_STOPWORDS,
            vocative_stopwords=VOCATIVE_GRAMMATICAL_STOPWORDS,
        )

    text = path.read_text(encoding="utf-8")
    header_m = re.search(r"^##\s+Attendee Anonymization\s*\(([\u0621-\u064A]+)\)", text, re.MULTILINE)
    if header_m:
        placeholder = header_m.group(1)

    for line in text.splitlines():
        stripped = line.strip()
        if "Preserved Titles & Kunyas" in stripped:
            clean_line = stripped.replace("**", "")
            for tok in re.findall(rf"([\u0621-\u064A]+)\s+{re.escape(placeholder)}(?!\w)", clean_line):
                if tok == "يا":
                    continue
                dehamza = re.sub(r"[أإآ]", "ا", tok)
                if dehamza.startswith("اخو"):
                    kinship_nouns.update({"أخوكم", "اخوكم", "أخونا", "اخونا", tok, dehamza})
                elif dehamza in ("الاخ", "الاخت"):
                    kinship_nouns.update({tok, dehamza})
                elif dehamza in ("ابو", "ابا"):
                    hamza_form = f"أ{dehamza[1:]}"
                    kunya_prefixes.update({tok, dehamza, hamza_form})
                else:
                    base = tok[2:] if tok.startswith("ال") and len(tok) >= 5 else tok
                    definite = tok if tok.startswith("ال") else f"ال{tok}"
                    title_prefixes.update({
                        base,
                        definite,
                        re.sub(r"[أإآ]", "ا", base),
                        re.sub(r"[أإآ]", "ا", definite),
                    })
        elif "Preserved Non-Attendee Names" in stripped:
            for grp in re.findall(r"\(([^)]+)\)", stripped):
                exempt_names.update(re.findall(r"[\u0621-\u064A]+", grp))

    if not kinship_nouns or not kunya_prefixes or not title_prefixes or not exempt_names:
        warnings.warn(
            f"Attendee anonymization rules parsed from {path} produced empty rule set(s); falling back to baseline rules.",
            UserWarning,
            stacklevel=2,
        )
        if not kinship_nouns:
            kinship_nouns.update(BASE_KINSHIP_NOUNS)
        if not kunya_prefixes:
            kunya_prefixes.update(BASE_KUNYA_PREFIXES)
        if not title_prefixes:
            title_prefixes.update(BASE_TITLE_PREFIXES)
        if not exempt_names:
            exempt_names.update(BASE_EXEMPT_NAMES)

    return AttendeeAnonymizationRules(
        placeholder=placeholder,
        kinship_nouns=frozenset(kinship_nouns),
        kunya_prefixes=frozenset(kunya_prefixes),
        title_prefixes=frozenset(title_prefixes),
        exempt_names=frozenset(exempt_names),
        kinship_stopwords=KINSHIP_GRAMMATICAL_STOPWORDS,
        vocative_stopwords=VOCATIVE_GRAMMATICAL_STOPWORDS,
    )


def _check_dialect_and_dialogue(
    para_records: list[ParagraphRecord],
    report: ValidationReport,
    dialect_rules: list[tuple[re.Pattern, str]] | None = None,
    dialect_rules_path: Path | str | None = None,
) -> None:
    rules = dialect_rules if dialect_rules is not None else load_dialect_replacements(dialect_rules_path)
    attendee_rules = load_attendee_anonymization_rules(dialect_rules_path)

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


def _has_colloquial_marker(text: str) -> bool:
    plain = strip_tashkeel(text)
    if re.search(r"(?<!\w)هو\s+[\u0600-\u06FF\s]+\s+ولا\s+", plain):
        return True
    words = re.findall(r"[\u0600-\u06FF]+", plain)
    for w in words:
        w_norm = normalize_arabic(w)
        if w in DIALECT_MARKERS or w_norm in DIALECT_MARKERS:
            return True
        if w.startswith(("هت", "هي", "بي", "بت", "ما")) and w.endswith("ش") and len(w) >= 4:
            return True
    return False


def _extract_leading_classical_clause(candidate: str) -> str:
    """Extracts consecutive leading Classical Arabic sub-clauses before any colloquial shift."""
    # Split on parenthetical colloquial glosses or commas
    sub_clauses = re.split(r"https?://|\s*-\s*يعني\s+|[،]", candidate)
    classical_parts: list[str] = []
    for sub in sub_clauses:
        sub_clean = sub.strip(" .؟!:-")
        if not sub_clean:
            continue
        if _has_colloquial_marker(sub_clean):
            break
        classical_parts.append(sub_clean)
    return "، ".join(classical_parts)


def _check_unbolded_fallback_matn(
    para_records: list[ParagraphRecord],
    report: ValidationReport,
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
                core_clause = _extract_leading_classical_clause(cand)
                words = re.findall(r"[\u0600-\u06FF]+", core_clause)
                if len(words) >= 4 and not _has_colloquial_marker(core_clause):
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
) -> ValidationReport:
    docx_path = Path(docx_path)
    report = ValidationReport(docx_path=str(docx_path))
    doc = docx.Document(str(docx_path))

    para_records = _check_ooxml_styling(doc, report)
    _check_headers_and_conclusion(doc, para_records, report, context_path=context_path)
    _check_punctuation_and_orthography(para_records, report)
    _check_dialect_and_dialogue(para_records, report, dialect_rules_path=dialect_rules_path)
    _check_unbolded_fallback_matn(para_records, report)
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

    report = verify_docx(
        docx_path=args.docx_path,
        raw_path=args.raw,
        matn_path=args.matn,
        context_path=args.context,
    )

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_report_text(report))

    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
