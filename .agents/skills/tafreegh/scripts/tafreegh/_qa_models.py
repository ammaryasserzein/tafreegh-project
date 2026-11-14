"""Shared domain models, constants, and issue reporting for DOCX QA audit passes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TypedDict

HEADER_LINE_COUNT = 3
STUDENT_PREFIX = "طالب:"
INAUDIBLE_TOKEN = "صوت غير مسموع"

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


class ValidationIssueDict(TypedDict):
    """Serialized representation of a single ValidationIssue."""

    code: str
    severity: str
    paragraph_index: int | None
    message: str
    snippet: str


class ValidationReportDict(TypedDict):
    """Serialized JSON structure returned by ValidationReport.to_dict()."""

    docx_path: str
    passed: bool
    error_count: int
    total_paragraphs: int
    matn_paragraphs: int
    student_paragraphs: int
    issues: list[ValidationIssueDict]


@dataclass(frozen=True)
class ParagraphRecord:
    """Normalized paragraph summary produced by OOXML styling inspection."""

    index: int
    text: str
    is_matn: bool

    @property
    def inner_text(self) -> str:
        """Return stripped paragraph text with enclosing Matn parentheses removed when applicable."""
        stripped = self.text.strip()
        if self.is_matn and stripped.startswith("(") and stripped.endswith(")"):
            return stripped[1:-1].strip()
        return stripped


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
        """Return total number of recorded validation errors."""
        return len(self.issues)

    @property
    def passed(self) -> bool:
        """Return True when zero validation errors were recorded."""
        return self.error_count == 0

    def flag(
        self,
        code: str,
        paragraph_index: int | None,
        message: str,
        snippet: str = "",
    ) -> None:
        """Record an ERROR ValidationIssue against the report."""
        self.issues.append(
            ValidationIssue(
                code=code,
                severity=Severity.ERROR,
                paragraph_index=paragraph_index,
                message=message,
                snippet=snippet,
            )
        )

    def to_dict(self) -> ValidationReportDict:
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
