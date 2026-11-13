import contextlib
import datetime
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tafreegh import fetch_training_data
from tafreegh.lecture_identity import LectureIdentity
from tafreegh.word_gateway import create_docx
from tafreegh.workspace_catalog import WorkspaceConfig


class TestFetchTrainingData(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)

        self.workspace = WorkspaceConfig.resolve(
            project_root=self.base_dir,
            onedrive_base=self.base_dir / "OneDrive" / "1. دوري",
            env={},
        )
        os.makedirs(self.workspace.onedrive_base)
        os.makedirs(self.workspace.training_data_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_end_to_end_extraction_and_skip(self):
        # 1. Setup real OneDrive structure with a real .docx deliverable
        subject_dir = self.workspace.onedrive_base / "1. الاسماء الحسنى" / "(تم التسليم)"
        os.makedirs(subject_dir)

        docx_path = subject_dir / "2026-09-18.docx"
        create_docx(
            "بسم الله الرحمن الرحيم\nالمادة: الأسماء الحسنى\n2026-09-18\n\n**(نَصُّ الْمَتْنِ)**\n\nشرح مختصر.",
            docx_path,
            workspace=self.workspace,
        )

        # 2. Run script for the first time
        rc = fetch_training_data.main(workspace=self.workspace)
        self.assertEqual(rc, 0)

        # Assert the markdown file was created with the correct name and bold formatting
        expected_md_path = self.workspace.training_data_dir / "2026-09-18_الاسماء الحسنى.md"
        self.assertTrue(expected_md_path.exists(), "Markdown file was not created in 04_Training_Data")

        content = expected_md_path.read_text(encoding="utf-8")
        self.assertIn("**(نَصُّ الْمَتْنِ)**", content)
        self.assertIn("شرح مختصر.", content)

        # Assert the original file was NOT deleted
        self.assertTrue(docx_path.exists(), "Original docx should not be deleted")

        # 3. Run script again to verify skip-existing idempotence without mocks
        expected_md_path.write_text("existing curated training data", encoding="utf-8")
        fetch_training_data.main(workspace=self.workspace)
        self.assertEqual(expected_md_path.read_text(encoding="utf-8"), "existing curated training data")

    def test_numbered_lecture_extraction_and_baseline_matching(self):
        subject_dir = self.workspace.onedrive_base / "فقه البيوع (سعد الخثلان)" / "(تم التسليم)"
        os.makedirs(subject_dir, exist_ok=True)

        docx_path = subject_dir / "17-فقه_البيوع_17.docx"
        create_docx(
            "بسم الله الرحمن الرحيم\nالمادة: فقه البيوع (سعد الخثلان)\nالمحاضرة: 17\n\n"
            "الحمد لله رب العالمين\nطالب: صوت غير مسموع.",
            docx_path,
            workspace=self.workspace,
        )

        os.makedirs(self.workspace.ai_outputs_dir, exist_ok=True)
        ai_baseline_path = self.workspace.ai_outputs_dir / "17-فقه_البيوع_17_AI.md"
        ai_baseline_path.write_text("الحمد لله رب العالمين\nنعم؟", encoding="utf-8")

        fetch_training_data.main(workspace=self.workspace)

        expected_md_path = self.workspace.training_data_dir / "17-فقه_البيوع_17.md"
        self.assertTrue(expected_md_path.exists(), "Numbered lecture markdown should be created as 17-فقه_البيوع_17.md")
        self.assertIn("طالب: صوت غير مسموع.", expected_md_path.read_text(encoding="utf-8"))

        ident = LectureIdentity(lecture_number="17", stem="17-فقه_البيوع_17", keyword="بيوع")
        found = fetch_training_data._find_ai_baseline(identity=ident, workspace=self.workspace)
        self.assertEqual(found, ai_baseline_path)

    def test_undated_unnumbered_docx_uses_mtime_without_mutating_identity(self):
        subject_dir = self.workspace.onedrive_base / "1. رياض الصالحين" / "(تم التسليم)"
        os.makedirs(subject_dir, exist_ok=True)

        docx_path = subject_dir / "notes.docx"
        create_docx(
            "بسم الله الرحمن الرحيم\nالمادة: رياض الصالحين\n2026-10-09\n\n"
            "الحمد لله\nفصل جديد في العلم.\nطالب: صوت غير مسموع.",
            docx_path,
            workspace=self.workspace,
        )

        mtime = 1791504000  # fixed timestamp
        os.utime(docx_path, (mtime, mtime))
        expected_date = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

        os.makedirs(self.workspace.ai_outputs_dir, exist_ok=True)
        ai_baseline_path = self.workspace.ai_outputs_dir / f"{expected_date}_رياض_الصالحين_AI.md"
        ai_baseline_path.write_text("الحمد لله\nفصل جديد في العلم.", encoding="utf-8")

        stdout_buf = io.StringIO()
        with (
            patch.object(
                fetch_training_data,
                "_find_ai_baseline",
                wraps=fetch_training_data._find_ai_baseline,
            ) as spy_find_baseline,
            contextlib.redirect_stdout(stdout_buf),
        ):
            rc = fetch_training_data.main(workspace=self.workspace)

        self.assertEqual(rc, 0)
        spy_find_baseline.assert_called_once()
        passed_identity = spy_find_baseline.call_args.kwargs["identity"]
        self.assertEqual(passed_identity.date, expected_date)
        output = stdout_buf.getvalue()
        self.assertIn(f"from diff with {ai_baseline_path.name}", output)
        self.assertNotIn("No AI baseline", output)

        expected_md_path = self.workspace.training_data_dir / f"{expected_date}_رياض الصالحين_notes.md"
        self.assertTrue(expected_md_path.exists())
        extracted = expected_md_path.read_text(encoding="utf-8")
        self.assertIn("فصل جديد في العلم.", extracted)
        self.assertIn("طالب: صوت غير مسموع.", extracted)

    def test_skips_corrupt_docx_gracefully_without_writing_error_text(self):
        subject_dir = self.workspace.onedrive_base / "1. الاسماء الحسنى" / "(تم التسليم)"
        os.makedirs(subject_dir)

        corrupt_docx = subject_dir / "2026-09-18.docx"
        corrupt_docx.write_text("not a real docx zip archive", encoding="utf-8")

        valid_docx = subject_dir / "2026-09-25.docx"
        create_docx(
            "بسم الله الرحمن الرحيم\nالمادة: الأسماء الحسنى\n2026-09-25\n\nالحمد لله.",
            valid_docx,
            workspace=self.workspace,
        )

        stdout_buf = io.StringIO()
        with contextlib.redirect_stdout(stdout_buf):
            rc = fetch_training_data.main(workspace=self.workspace)

        self.assertEqual(rc, 0)
        corrupt_md = self.workspace.training_data_dir / "2026-09-18_الاسماء الحسنى.md"
        valid_md = self.workspace.training_data_dir / "2026-09-25_الاسماء الحسنى.md"
        self.assertFalse(corrupt_md.exists(), "Corrupt .docx must not write error text into 04_Training_Data")
        self.assertTrue(valid_md.exists(), "Valid .docx after corrupt file should still be processed")
        self.assertIn("Failed to read", stdout_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
