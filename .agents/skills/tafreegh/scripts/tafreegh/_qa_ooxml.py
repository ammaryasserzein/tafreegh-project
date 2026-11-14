"""Pass 1: OOXML margin, RTL, font, color, break, and Matn bold formatting audit."""

from __future__ import annotations

from ._qa_models import HEADER_LINE_COUNT, ParagraphRecord, ValidationReport, _flag
from .word_gateway import (
    DEFAULT_BIDI_LANG,
    DEFAULT_FONT_NAME,
    DEFAULT_FONT_SIZE,
    DEFAULT_MARGIN_INCHES,
    MARGIN_TOLERANCE_INCHES,
    InspectedDocument,
)


def _is_matn_paragraph(p_idx: int, p_text: str, any_bold: bool, all_bold: bool) -> bool:
    """Return True when a body paragraph is enclosed in (...) and fully bold."""
    stripped = p_text.strip()
    if p_idx < HEADER_LINE_COUNT or not stripped:
        return False
    return any_bold and all_bold and stripped.startswith("(") and stripped.endswith(")")


def check_ooxml_styling(doc_info: InspectedDocument, report: ValidationReport) -> list[ParagraphRecord]:
    """Audit section margins, paragraph RTL, run typography/color/boldness, and line breaks."""
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
