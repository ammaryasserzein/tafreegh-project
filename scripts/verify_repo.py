#!/usr/bin/env python3
"""
Repository Verification Guardrail
Validates:
1. Root-level scratch containment (.scratch/ or $env:TEMP)
2. Standard directory structure integrity
3. Context and standards path integrity and table syntax
4. Elimination of negative phrasing in steering documentation
5. Coding standards existence and structural completeness
"""
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

STANDARD_DIRS = [
    "01_Matn_Sources",
    "02_Raw_Inputs",
    "03_AI_Outputs",
    "04_Training_Data",
]

FORBIDDEN_ROOT_PATTERNS = [
    re.compile(r"^diff_.*\.txt$", re.IGNORECASE),
    re.compile(r"^git_.*\.txt$", re.IGNORECASE),
    re.compile(r"^.*_context\.md$", re.IGNORECASE),
    re.compile(r"^context_log\.txt$", re.IGNORECASE),
]

STEERING_DOCS = [
    "CONTEXT.md",
    "CODING_STANDARDS.md",
]

NEGATIVE_PHRASING_PATTERNS = [
    re.compile(r"\bلا تفعل\b"),
    re.compile(r"\bتجنب\b"),
    re.compile(r"\bignore\b", re.IGNORECASE),
    re.compile(r"\bdon't\b", re.IGNORECASE),
]

REQUIRED_STANDARDS_SECTIONS = [
    "Scope & Blast Radius",
    "Verifiable Completion Criteria",
]

@dataclass
class Finding:
    category: str
    message: str
    file_path: str = ""
    line_number: int = 0

    def __str__(self) -> str:
        location = f"{self.file_path}:{self.line_number} " if self.file_path else ""
        return f"[{self.category}] {location}{self.message}"

def check_directories(findings: list[Finding]) -> None:
    for dir_name in STANDARD_DIRS:
        target_path = REPO_ROOT / dir_name
        if not target_path.is_dir():
            findings.append(Finding(category="DIR", message=f"Missing standard directory: {dir_name}"))

def check_scratch_cleanliness(findings: list[Finding]) -> None:
    for candidate_file in REPO_ROOT.iterdir():
        if candidate_file.is_file():
            for pattern in FORBIDDEN_ROOT_PATTERNS:
                if pattern.match(candidate_file.name):
                    findings.append(Finding(
                        category="SCRATCH",
                        message=f"Root-level scratch file found: {candidate_file.name}. Move to .scratch/ or $env:TEMP",
                        file_path=candidate_file.name
                    ))

def check_steering_docs_phrasing(findings: list[Finding]) -> None:
    for doc_name in STEERING_DOCS:
        target_doc = REPO_ROOT / doc_name
        if not target_doc.is_file():
            continue
        lines = target_doc.read_text(encoding="utf-8").splitlines()
        for line_number, line_content in enumerate(lines, 1):
            for pattern in NEGATIVE_PHRASING_PATTERNS:
                if pattern.search(line_content):
                    findings.append(Finding(
                        category="PHRASING",
                        message=f"Negative phrasing matched '{pattern.pattern}': {line_content.strip()[:60]}",
                        file_path=doc_name,
                        line_number=line_number
                    ))

def check_context_integrity(findings: list[Finding]) -> None:
    context_file = REPO_ROOT / "CONTEXT.md"
    if not context_file.is_file():
        findings.append(Finding(category="CONTEXT", message="Missing CONTEXT.md in repository root."))
        return

    content = context_file.read_text(encoding="utf-8")

    # Match directory references with or without backticks or trailing slashes
    for match in re.finditer(r"\b([0-9]{2}_[A-Za-z_]+)\b", content):
        dir_reference = match.group(1)
        if dir_reference not in STANDARD_DIRS:
            findings.append(Finding(
                category="CONTEXT",
                message=f"Invalid folder reference in CONTEXT.md: `{dir_reference}`",
                file_path="CONTEXT.md"
            ))

    # Validate table syntax with escaped pipe support
    lines = content.splitlines()
    in_table = False
    expected_column_count = 0
    for line_number, line_content in enumerate(lines, 1):
        stripped_line = line_content.strip()
        if stripped_line.startswith("|") and stripped_line.endswith("|"):
            # Split strictly on unescaped pipe characters
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", stripped_line)[1:-1]]
            if not in_table:
                in_table = True
                expected_column_count = len(cells)
            else:
                if len(cells) != expected_column_count:
                    findings.append(Finding(
                        category="TABLE",
                        message=f"Table column count mismatch: expected {expected_column_count}, got {len(cells)}",
                        file_path="CONTEXT.md",
                        line_number=line_number
                    ))
        else:
            in_table = False

def check_coding_standards(findings: list[Finding]) -> None:
    standards_file = REPO_ROOT / "CODING_STANDARDS.md"
    if not standards_file.is_file():
        findings.append(Finding(category="STANDARDS", message="Missing CODING_STANDARDS.md in repository root."))
        return

    text_content = standards_file.read_text(encoding="utf-8")
    for section_heading in REQUIRED_STANDARDS_SECTIONS:
        if section_heading not in text_content:
            findings.append(Finding(
                category="STANDARDS",
                message=f"CODING_STANDARDS.md missing required section: '{section_heading}'",
                file_path="CODING_STANDARDS.md"
            ))

def main() -> None:
    findings: list[Finding] = []
    check_directories(findings)
    check_scratch_cleanliness(findings)
    check_steering_docs_phrasing(findings)
    check_context_integrity(findings)
    check_coding_standards(findings)

    if findings:
        print(f"FAILED: {len(findings)} repository verification finding(s) detected:")
        for item in findings:
            print(f"  - {item}")
        sys.exit(1)
    else:
        print("PASSED: Repository integrity, table formatting, and coding standards verified cleanly.")
        sys.exit(0)

if __name__ == "__main__":
    main()
