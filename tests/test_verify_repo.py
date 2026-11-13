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


def test_negative_phrasing_in_skill_and_references(tmp_path):
    ref_dir = tmp_path / ".agents" / "skills" / "tafreegh" / "references"
    ref_dir.mkdir(parents=True)
    bad_ref = ref_dir / "formatting-rules.md"
    bad_ref.write_text("- Prohibited: spacing inside parens\n- Never output brackets.", encoding="utf-8")

    findings = []
    verify_repo.check_steering_docs_phrasing(findings, base_dir=tmp_path)
    phrasing_findings = [item for item in findings if item.category == verify_repo.FindingCategory.PHRASING]
    assert len(phrasing_findings) == 2
    assert all(f.file_path == ".agents/skills/tafreegh/references/formatting-rules.md" for f in phrasing_findings)


def test_check_no_arabic_in_backticks(tmp_path):
    ref_dir = tmp_path / ".agents" / "skills" / "tafreegh" / "references"
    ref_dir.mkdir(parents=True)
    doc = ref_dir / "dialect-rules.md"
    doc.write_text(
        "Valid English backtick: `export_docx.py` and `YYYY-MM-DD`.\n"
        "Invalid Arabic backtick: `مفيهوش` and `**(نص المتن)**`.\n",
        encoding="utf-8",
    )

    findings = []
    verify_repo.check_no_arabic_in_backticks(findings, base_dir=tmp_path)
    assert len(findings) == 2
    assert all(f.line_number == 2 for f in findings)
    assert any("مفيهوش" in f.message for f in findings)


def test_check_directories_allows_processed_subdirectories(tmp_path):
    for d in verify_repo.STANDARD_DIRS:
        (tmp_path / d).mkdir()
    (tmp_path / "01_Matn_Sources" / "processed").mkdir()
    (tmp_path / "02_Raw_Inputs" / "processed").mkdir()
    (tmp_path / "02_Raw_Inputs" / "2026-09-19 منطق.md_مقاطع").mkdir()

    findings = []
    verify_repo.check_directories(findings, base_dir=tmp_path)
    assert len(findings) == 0, f"Expected 0 findings, got: {findings}"

def test_check_directories_flags_unauthorized_subdirectory(tmp_path):
    for d in verify_repo.STANDARD_DIRS:
        (tmp_path / d).mkdir()
    (tmp_path / "01_Matn_Sources" / "random_folder").mkdir()

    findings = []
    verify_repo.check_directories(findings, base_dir=tmp_path)
    dir_findings = [f for f in findings if f.category == verify_repo.FindingCategory.DIR]
    assert len(dir_findings) == 1
    assert "Unauthorized subdirectory" in dir_findings[0].message

def _scratch_findings(base_dir: Path) -> list[verify_repo.Finding]:
    findings = []
    verify_repo.check_no_root_scratch(findings, base_dir=base_dir)
    return [f for f in findings if f.category == verify_repo.FindingCategory.SCRATCH]


def test_check_no_root_scratch_allows_standard_files(tmp_path):
    for filename in (
        "CODING_STANDARDS.md",
        "CONTEXT.md",
        "GLOSSARY.md",
        "Word base.docx",
        ".gitignore",
        ".lintstagedrc",
        ".prettierignore",
        ".prettierrc",
        "package.json",
        "package-lock.json",
        "pytest.ini",
    ):
        (tmp_path / filename).write_text("Test", encoding="utf-8")

    assert _scratch_findings(tmp_path) == []


def test_check_no_root_scratch_flags_unauthorized_scratch(tmp_path):
    (tmp_path / "CODING_STANDARDS.md").write_text("Test", encoding="utf-8")
    (tmp_path / "detailed_diff.py").write_text("Test", encoding="utf-8")
    (tmp_path / "temp.md").write_text("Test", encoding="utf-8")

    scratch_findings = _scratch_findings(tmp_path)
    assert len(scratch_findings) == 2
    assert {f.file_path for f in scratch_findings} == {"detailed_diff.py", "temp.md"}


def test_check_no_root_scratch_rejects_retired_root_files(tmp_path):
    (tmp_path / "README.md").write_text("Retired", encoding="utf-8")
    (tmp_path / "handoff.md").write_text("Retired", encoding="utf-8")

    scratch_findings = _scratch_findings(tmp_path)
    assert {f.file_path for f in scratch_findings} == {"README.md", "handoff.md"}


def test_check_no_root_scratch_allows_git_worktree_pointer_file(tmp_path):
    (tmp_path / ".git").write_text(
        "gitdir: C:/Users/example/repo/.git/worktrees/Staging\n",
        encoding="utf-8",
    )

    assert _scratch_findings(tmp_path) == []


def test_check_no_root_scratch_rejects_invalid_git_file(tmp_path):
    (tmp_path / ".git").write_text("not a valid pointer\n", encoding="utf-8")

    scratch_findings = _scratch_findings(tmp_path)
    assert len(scratch_findings) == 1
    assert scratch_findings[0].file_path == ".git"


def test_check_no_root_scratch_allows_standard_and_tooling_directories(tmp_path):
    for dirname in (
        "01_Matn_Sources",
        "02_Raw_Inputs",
        "03_AI_Outputs",
        "04_Training_Data",
        "scripts",
        "tests",
        "docs",
        "tafreegh-skill",
        "node_modules",
        ".git",
        ".agents",
        ".scratch",
        ".husky",
        ".pytest_cache",
        ".obsidian",
        ".vscode",
    ):
        (tmp_path / dirname).mkdir()

    assert _scratch_findings(tmp_path) == []


def test_check_no_root_scratch_flags_unauthorized_root_directories(tmp_path):
    (tmp_path / ".scratch").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scratch").mkdir()
    (tmp_path / "tmp_notes").mkdir()
    (tmp_path / ".scratch_extra").mkdir()

    scratch_findings = _scratch_findings(tmp_path)
    assert {f.file_path for f in scratch_findings} == {"scratch", "tmp_notes", ".scratch_extra"}


def test_single_canonical_chunker_location():
    assert (REPO_ROOT / ".agents" / "skills" / "tafreegh" / "scripts" / "chunk_transcript.py").is_file()
    assert not (REPO_ROOT / "scripts" / "chunk_transcript.py").exists()


def test_count_open_deferred_reviews(tmp_path):
    assert verify_repo.count_open_deferred_reviews(base_dir=tmp_path) == 0

    deferred_dir = tmp_path / "docs" / "agents"
    deferred_dir.mkdir(parents=True)
    deferred_file = deferred_dir / "deferred-reviews.md"
    content = (
        "# Backlog\n\n"
        "| ID | Status |\n"
        "| --- | --- |\n"
        "| D1 | - [ ] open |\n"
        "| D2 | - [x] done |\n"
        "| D3 | - [ ] open |\n"
    )
    deferred_file.write_text(content, encoding="utf-8")
    assert verify_repo.count_open_deferred_reviews(base_dir=tmp_path) == 2


def test_glossary_domain_language_purity():
    glossary_path = REPO_ROOT / "GLOSSARY.md"
    assert glossary_path.is_file(), "GLOSSARY.md must exist in repo root"
    content = glossary_path.read_text(encoding="utf-8")
    assert "<matn_source>" not in content, "GLOSSARY.md must not contain implementation detail '<matn_source>'"
    assert "seam splitting" not in content, "GLOSSARY.md must not contain implementation detail 'seam splitting'"


