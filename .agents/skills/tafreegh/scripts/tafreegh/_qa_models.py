"""Shared domain models and issue-recording helper for DOCX QA audit passes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

HEADER_LINE_COUNT = 3

CANONICAL_DUA_TEXT = (
    "والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى آله وصحبه أجمعين، "
    "سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك."
)
CANONICAL_DUA_PATTERN = re.compile(
    r"والحمد لله رب العالمين وصل اللهم على نبينا محمد وعلى (?:آله|اله) وصحبه أجمعين، "
    r"سبحانك اللهم وبحمدك نشهد أن لا إله إلا أنت نستغفرك ونتوب إليك\.$"
)

_PAREN_CITATION_RE = re.compile(r"\([^)]*\)")


class Severity(str, Enum):
    """Validation issue severity level."""

    ERROR = "ERROR"


@dataclass(frozen=True)
class ParagraphRecord:
    """Normalized paragraph summary produced by OOXML styling inspection."""

    index: int
    text: str
    is_matn: bool


@dataclass
class ValidationIssue:
    """Single rule violation detected by a DOCX QA audit pass."""

    code: str
    severity: Severity
    paragraph_index: int | None
    message: str
    snippet: str = ""


@dataclass
class ValidationReport:
    """Aggregated QA validation report for a single exported .docx file."""

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
        """Serialize the report to a JSON-compatible dictionary."""
        return {
            "docx_path": self.docx_path,
            "passed": self.passed,
            "error_count": self.error_count,
            "total_paragraphs": self.total_paragraphs,
            "matn_paragraphs": self.matn_paragraphs,
            "student_paragraphs": self.student_paragraphs,
            "issues": [
                {
                    "code": issue.code,
                    "severity": issue.severity.value,
                    "paragraph_index": issue.paragraph_index,
                    "message": issue.message,
                    "snippet": issue.snippet,
                }
                for issue in self.issues
            ],
        }


def strip_parenthesized_citations(text: str) -> str:
    """Remove parenthesized citations (...) from text before lexical scanning."""
    return _PAREN_CITATION_RE.sub(" ", text)


def _flag(
    report: ValidationReport,
    code: str,
    paragraph_index: int | None,
    message: str,
    snippet: str = "",
) -> None:
    """Append an ERROR issue to report."""
    report.issues.append(
        ValidationIssue(
            code=code,
            severity=Severity.ERROR,
            paragraph_index=paragraph_index,
            message=message,
            snippet=snippet,
        )
    )
