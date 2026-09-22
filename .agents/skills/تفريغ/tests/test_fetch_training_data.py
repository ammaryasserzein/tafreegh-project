import unittest
from unittest.mock import patch
import sys
import os
from pathlib import Path
import tempfile

scripts_dir = Path(__file__).resolve().parent.parent / 'scripts'
sys.path.insert(0, str(scripts_dir))
import fetch_training_data
import read_docx

class TestFetchTrainingData(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        
        # Override paths in the module
        fetch_training_data.ONEDRIVE_BASE = str(self.base_dir / "OneDrive" / "1. دوري")
        fetch_training_data.TRAINING_DATA_DIR = self.base_dir / "04_Training_Data"
        
        # Create directories
        os.makedirs(fetch_training_data.ONEDRIVE_BASE)
        os.makedirs(fetch_training_data.TRAINING_DATA_DIR)
        
        self.mock_extract = patch('read_docx.extract_text').start()
        self.mock_extract.return_value = "**dummy text**"
        
    def tearDown(self):
        self.temp_dir.cleanup()
        patch.stopall()

    def test_end_to_end_extraction_and_skip(self):
        # 1. Setup mock OneDrive structure
        subject_dir = Path(fetch_training_data.ONEDRIVE_BASE) / "1. الاسماء الحسنى" / "(تم التسليم)"
        os.makedirs(subject_dir)
        
        docx_path = subject_dir / "2026-09-18.docx"
        with open(docx_path, 'w') as f:
            f.write("dummy docx content")
            
        # 2. Run script for the first time
        fetch_training_data.main()
        
        # Assert the markdown file was created with the correct name
        expected_md_path = fetch_training_data.TRAINING_DATA_DIR / "2026-09-18_الاسماء الحسنى.md"
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
        
        fetch_training_data.main()
        
        self.mock_extract.assert_not_called()
        
if __name__ == '__main__':
    unittest.main()
