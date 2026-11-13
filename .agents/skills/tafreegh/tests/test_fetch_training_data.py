import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tafreegh import fetch_training_data
from tafreegh.lecture_identity import LectureIdentity
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

        self.mock_extract = patch('tafreegh.read_docx.extract_text').start()
        self.mock_extract.return_value = "**dummy text**"

    def tearDown(self):
        self.temp_dir.cleanup()
        patch.stopall()

    def test_end_to_end_extraction_and_skip(self):
        # 1. Setup mock OneDrive structure
        subject_dir = self.workspace.onedrive_base / "1. الاسماء الحسنى" / "(تم التسليم)"
        os.makedirs(subject_dir)

        docx_path = subject_dir / "2026-09-18.docx"
        with open(docx_path, 'w') as f:
            f.write("dummy docx content")

        # 2. Run script for the first time
        fetch_training_data.main(workspace=self.workspace)

        # Assert the markdown file was created with the correct name
        expected_md_path = self.workspace.training_data_dir / "2026-09-18_الاسماء الحسنى.md"
        self.assertTrue(expected_md_path.exists(), "Markdown file was not created in 04_Training_Data")

        with open(expected_md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        self.assertEqual(content, "**dummy text**")

        # Assert the original file was NOT deleted
        self.assertTrue(docx_path.exists(), "Original docx should not be deleted")

        # 3. Run script again to test skipping
        # Change the mock return value to prove it doesn't get called again
        self.mock_extract.return_value = "should not be called"
        self.mock_extract.reset_mock()

        fetch_training_data.main(workspace=self.workspace)

        self.mock_extract.assert_not_called()

    def test_numbered_lecture_extraction_and_baseline_matching(self):
        # 1. Setup mock OneDrive structure for numbered lecture
        subject_dir = self.workspace.onedrive_base / "فقه البيوع (سعد الخثلان)" / "(تم التسليم)"
        os.makedirs(subject_dir, exist_ok=True)

        docx_path = subject_dir / "17-فقه_البيوع_17.docx"
        with open(docx_path, 'w', encoding='utf-8') as f:
            f.write("dummy docx content")

        # 2. Setup mock AI baseline in 03_AI_Outputs
        os.makedirs(self.workspace.ai_outputs_dir, exist_ok=True)
        ai_baseline_path = self.workspace.ai_outputs_dir / "17-فقه_البيوع_17_AI.md"
        ai_baseline_path.write_text("الحمد لله رب العالمين\nنعم؟\nطالب: صوت غير مسموع.", encoding="utf-8")

        # 3. Run script
        fetch_training_data.main(workspace=self.workspace)

        # 4. Assert training markdown was created using numbered stem
        expected_md_path = self.workspace.training_data_dir / "17-فقه_البيوع_17.md"
        self.assertTrue(expected_md_path.exists(), "Numbered lecture markdown should be created as 17-فقه_البيوع_17.md")

        # 5. Direct test of _find_ai_baseline with LectureIdentity
        ident = LectureIdentity(lecture_number="17", stem="17-فقه_البيوع_17", keyword="بيوع")
        found = fetch_training_data._find_ai_baseline(identity=ident, workspace=self.workspace)
        self.assertEqual(found, ai_baseline_path)


if __name__ == '__main__':
    unittest.main()
