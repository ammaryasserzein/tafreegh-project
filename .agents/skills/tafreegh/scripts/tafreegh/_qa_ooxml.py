"""Pass 1: OOXML margin, RTL, font, color, break, and Matn bold formatting audit."""

from __future__ import annotations

from ._qa_models import HEADER_LINE_COUNT, STUDENT_PREFIX, ParagraphRecord, ValidationReport
from .word_gateway import (
    DEFAULT_BIDI_LANG,
    DEFAULT_FONT_NAME,
    DEFAULT_FONT_SIZE,
    DEFAULT_MARGIN_INCHES,
    MARGIN_TOLERANCE_INCHES,
    InspectedDocument,
    InspectedParagraph,
    InspectedRun,
)


def _is_matn_paragraph(p_idx: int, p_text: str, any_bold: bool, all_bold: bool) -> bool:
    """Return True when a body paragraph is enclosed in (...) and fully bold."""
    stripped = p_text.strip()
    if p_idx < HEADER_LINE_COUNT or not stripped:
        return False
    return any_bold and all_bold and stripped.startswith("(") and stripped.endswith(")")


def _check_section_margins(doc_info: InspectedDocument, report: ValidationReport) -> None:
    """Validate that every document section uses canonical page margins."""
    for section in doc_info.sections:
        for side_name, margin_val in (
            ("top", section.top_inches),
            ("bottom", section.bottom_inches),
            ("left", section.left_inches),
            ("right", section.right_inches),
        ):
            if margin_val is None or abs(margin_val - DEFAULT_MARGIN_INCHES) > MARGIN_TOLERANCE_INCHES:
                actual = f"{margin_val:.2f}" if margin_val is not None else "None"
                report.flag(
                    "MARGIN_INVALID",
                    None,
                    (
                        f"Section {section.section_index} {side_name} margin is {actual}in "
                        f"(expected {DEFAULT_MARGIN_INCHES:.2f}in)."
                    ),
                )


def _check_run_typography(p_idx: int, run: InspectedRun, report: ValidationReport) -> None:
    """Validate font family, size, color inheritance, RTL direction, and bidi language on a run."""
    if run.font_name != DEFAULT_FONT_NAME:
        report.flag(
            "FONT_NAME_INVALID",
            p_idx,
            f"Paragraph P{p_idx} run has font '{run.font_name}' (expected '{DEFAULT_FONT_NAME}').",
            run.text[:60],
        )

    if run.font_size_pt is None or abs(run.font_size_pt - float(DEFAULT_FONT_SIZE)) > 0.1:
        report.flag(
            "FONT_SIZE_INVALID",
            p_idx,
            (
                f"Paragraph P{p_idx} run has font size {run.font_size_pt}pt "
                f"(expected {float(DEFAULT_FONT_SIZE):.1f}pt)."
            ),
            run.text[:60],
        )

    if not run.has_rpr:
        return

    if run.color_val is not None:
        if run.color_val and run.color_val.lower() not in ("auto", "000000"):
            report.flag(
                "FONT_COLOR_FORBIDDEN",
                p_idx,
                f"Paragraph P{p_idx} run has inline color '{run.color_val}' (must inherit default black).",
                run.text[:60],
            )
        else:
            report.flag(
                "FONT_COLOR_FORBIDDEN",
                p_idx,
                f"Paragraph P{p_idx} run injects inline <w:color/> tag.",
                run.text[:60],
            )

    if not run.has_rtl:
        report.flag(
            "RUN_RTL_MISSING",
            p_idx,
            f"Paragraph P{p_idx} run is missing <w:rtl/>.",
            run.text[:60],
        )
    if run.bidi_lang != DEFAULT_BIDI_LANG:
        report.flag(
            "RUN_LANG_MISSING",
            p_idx,
            f"Paragraph P{p_idx} run is missing w:lang w:bidi='{DEFAULT_BIDI_LANG}'.",
            run.text[:60],
        )


def _resolve_paragraph_bolding(
    p_idx: int,
    p_text: str,
    stripped: str,
    non_empty_runs: list[InspectedRun],
    report: ValidationReport,
) -> bool:
    """Validate bold/bCs usage against Matn paragraph rules and return True for valid Matn blocks."""
    any_bold = any(r.is_bold for r in non_empty_runs)
    all_bold = bool(non_empty_runs) and all(r.is_bold for r in non_empty_runs)
    is_matn = _is_matn_paragraph(p_idx, p_text, any_bold, all_bold)

    if p_idx < HEADER_LINE_COUNT and any_bold:
        report.flag(
            "HEADER_BOLD_FORBIDDEN",
            p_idx,
            f"Header paragraph P{p_idx} must not be bold.",
            stripped[:80],
        )
        return is_matn

    if p_idx >= HEADER_LINE_COUNT and any_bold:
        if not is_matn:
            report.flag(
                "ILLEGAL_BOLD_RUN",
                p_idx,
                f"Paragraph P{p_idx} contains bold runs outside a standalone Matn '(...)' block.",
                stripped[:80],
            )
        else:
            for r in non_empty_runs:
                if r.is_bold and (not r.has_b or not r.has_b_cs):
                    report.flag(
                        "MATN_BOLD_CS_MISSING",
                        p_idx,
                        f"Matn paragraph P{p_idx} bold run must set both w:b and w:bCs.",
                        r.text[:60],
                    )
    return is_matn


def _check_paragraph_styling(p: InspectedParagraph, report: ValidationReport) -> ParagraphRecord:
    """Validate breaks, RTL, run typography, and bold rules for a single paragraph."""
    p_idx = p.index
    p_text = p.text
    stripped = p_text.strip()

    if p.manual_line_break_count:
        report.flag(
            "MANUAL_LINE_BREAK",
            p_idx,
            (
                f"Paragraph P{p_idx} contains {p.manual_line_break_count} manual line break(s) "
                "(<w:br/>); use native paragraphs."
            ),
            stripped[:80],
        )

    if not stripped:
        return ParagraphRecord(p_idx, p_text, False)

    if not p.has_bidi:
        report.flag(
            "PARAGRAPH_RTL_MISSING",
            p_idx,
            f"Paragraph P{p_idx} is missing w:bidi RTL property.",
            stripped[:80],
        )

    non_empty_runs = [r for r in p.runs if r.text and r.text.strip()]
    for r in non_empty_runs:
        _check_run_typography(p_idx, r, report)

    is_matn = _resolve_paragraph_bolding(p_idx, p_text, stripped, non_empty_runs, report)
    if is_matn:
        report.matn_paragraphs += 1
    if stripped.startswith(STUDENT_PREFIX):
        report.student_paragraphs += 1
    return ParagraphRecord(p_idx, p_text, is_matn)


def check_ooxml_styling(doc_info: InspectedDocument, report: ValidationReport) -> list[ParagraphRecord]:
    """Audit section margins, paragraph RTL, run typography/color/boldness, and line breaks."""
    _check_section_margins(doc_info, report)
    report.total_paragraphs = len(doc_info.paragraphs)
    return [_check_paragraph_styling(p, report) for p in doc_info.paragraphs]
