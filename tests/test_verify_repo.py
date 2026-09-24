import sys
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import verify_repo

def test_verify_repo_passes_on_current_repo():
    findings = []
    verify_repo.check_directories(findings)
    verify_repo.check_scratch_cleanliness(findings)
    verify_repo.check_steering_docs_phrasing(findings)
    verify_repo.check_context_integrity(findings)
    verify_repo.check_coding_standards(findings)
    assert len(findings) == 0, f"Expected 0 findings, got: {[str(f) for f in findings]}"

def test_finding_dataclass_formatting():
    f = verify_repo.Finding(category="TEST", message="A test message", file_path="test.md", line_number=10)
    assert str(f) == "[TEST] test.md:10 A test message"
