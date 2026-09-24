import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import verify_repo

def test_verify_repo_passes_on_current_repo():
    findings = verify_repo.run_all_checks()
    assert len(findings) == 0, f"Expected 0 findings, got: {[str(item) for item in findings]}"

def test_finding_dataclass_formatting_with_line_number():
    finding = verify_repo.Finding(
        category=verify_repo.FindingCategory.DIR,
        message="Missing directory",
        file_path="sample.md",
        line_number=42
    )
    assert str(finding) == "[DIR] sample.md:42 Missing directory"

def test_finding_dataclass_formatting_without_line_number():
    finding = verify_repo.Finding(
        category=verify_repo.FindingCategory.CONTEXT,
        message="Invalid folder",
        file_path="CONTEXT.md",
        line_number=0
    )
    assert str(finding) == "[CONTEXT] CONTEXT.md Invalid folder"
    assert ":0" not in str(finding)

def test_escaped_pipe_table_parsing(tmp_path):
    table_content = (
        "# Test Table\n\n"
        "| Header 1 | Header 2 |\n"
        "| --- | --- |\n"
        "| Text with \\| escaped pipe | Second column |\n"
    )
    context_file = tmp_path / "CONTEXT.md"
    context_file.write_text(table_content, encoding="utf-8")

    findings = []
    verify_repo.check_context_integrity(findings, base_dir=tmp_path)
    table_findings = [item for item in findings if item.category == verify_repo.FindingCategory.TABLE]
    assert len(table_findings) == 0, f"Escaped pipe caused false-positive mismatch: {table_findings}"

def test_negative_phrasing_detection(tmp_path):
    bad_doc = tmp_path / "CONTEXT.md"
    bad_doc.write_text("هنا قاعدة: لا تفعل ذلك أبداً.", encoding="utf-8")

    findings = []
    verify_repo.check_steering_docs_phrasing(findings, base_dir=tmp_path)
    phrasing_findings = [item for item in findings if item.category == verify_repo.FindingCategory.PHRASING]
    assert len(phrasing_findings) == 1
    assert "لا تفعل" in phrasing_findings[0].message
