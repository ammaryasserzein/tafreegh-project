"""Modular DOCX QA Verification Gate orchestrating seven focused internal audit passes."""

from __future__ import annotations

import sys
from pathlib import Path

from ._qa_dialect_dialogue import check_dialect_and_dialogue
from ._qa_fallback_matn import check_unbolded_fallback_matn
from ._qa_headers_conclusion import check_headers_and_conclusion
from ._qa_matn_alignment import MatnAlignmentValidator, check_matn_alignment
from ._qa_models import (
    CANONICAL_DUA_PATTERN,
    CANONICAL_DUA_TEXT,
    HEADER_LINE_COUNT,
    ParagraphRecord,
    Severity,
    ValidationIssue,
    ValidationReport,
)
from ._qa_ooxml import check_ooxml_styling
from ._qa_punctuation import check_punctuation_and_orthography
from ._qa_raw_coverage import check_raw_coverage
from .word_gateway import DocxArchiveError, inspect_docx
from .workspace_catalog import RuleCatalog, WorkspaceConfig, resolve_runtime_context

__all__ = [
    "HEADER_LINE_COUNT",
    "CANONICAL_DUA_TEXT",
    "CANONICAL_DUA_PATTERN",
    "Severity",
    "ParagraphRecord",
    "ValidationIssue",
    "ValidationReport",
    "MatnAlignmentValidator",
    "verify_docx",
    "format_report_text",
    "main",
]


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
    """Run all seven QA verification passes against an exported OneDrive .docx document."""
    docx_path = Path(docx_path)
    report = ValidationReport(docx_path=str(docx_path))
    doc_info = inspect_docx(docx_path)

    _, active_catalog = resolve_runtime_context(
        workspace=workspace,
        catalog=catalog,
        context_path=context_path,
        dialect_rules_path=dialect_rules_path,
    )

    para_records = check_ooxml_styling(doc_info, report)
    check_headers_and_conclusion(doc_info, para_records, report, catalog=active_catalog)
    check_punctuation_and_orthography(para_records, report)
    check_dialect_and_dialogue(para_records, report, catalog=active_catalog)
    check_unbolded_fallback_matn(
        para_records,
        report,
        dialect_markers=active_catalog.dialect_markers,
    )
    if matn_path:
        check_matn_alignment(para_records, Path(matn_path), report)
    if raw_path:
        check_raw_coverage(para_records, Path(raw_path), report)
    return report


def format_report_text(report: ValidationReport) -> str:
    """Format a ValidationReport into a concise human-readable summary."""
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
    """CLI entrypoint for QA verification with JSON and human-readable exit codes (0, 1, 2)."""
    import argparse
    import json

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

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
