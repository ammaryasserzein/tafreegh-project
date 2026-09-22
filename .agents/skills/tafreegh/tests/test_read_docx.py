import unittest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# Add scripts to path so we can import read_docx
scripts_dir = Path(__file__).resolve().parent.parent / 'scripts'
sys.path.insert(0, str(scripts_dir))
import read_docx

class TestReadDocx(unittest.TestCase):
    def setUp(self):
        self.mock_zip = patch('read_docx.zipfile.ZipFile').start()
        self.mock_z = MagicMock()
        self.mock_zip.return_value.__enter__.return_value = self.mock_z

    def tearDown(self):
        patch.stopall()

    def test_extracts_arabic_bold_bcs_correctly(self):
        # Even if w:b is explicitly off, w:bCs being on should trigger bolding for Arabic
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:body>
                <w:p>
                    <w:r>
                        <w:rPr>
                            <w:b w:val="0"/>
                            <w:bCs/>
                        </w:rPr>
                        <w:t>عربي</w:t>
                    </w:r>
                </w:p>
            </w:body>
        </w:document>
        """.encode('utf-8')
        self.mock_z.read.return_value = xml
        result = read_docx.extract_text("dummy.docx")
        self.assertEqual(result, "**عربي**")

    def test_merges_consecutive_bold_runs_including_spaces(self):
        # Consecutive bold runs should be merged into a single bold block
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:body>
                <w:p>
                    <w:r>
                        <w:rPr><w:b/></w:rPr>
                        <w:t>word</w:t>
                    </w:r>
                    <w:r>
                        <w:rPr><w:b/></w:rPr>
                        <w:t xml:space="preserve"> </w:t>
                    </w:r>
                    <w:r>
                        <w:rPr><w:b/></w:rPr>
                        <w:t>next</w:t>
                    </w:r>
                </w:p>
            </w:body>
        </w:document>
        """.encode('utf-8')
        self.mock_z.read.return_value = xml
        result = read_docx.extract_text("dummy.docx")
        self.assertEqual(result, "**word next**")

    def test_does_not_create_invalid_markdown_for_bold_spaces(self):
        # A standalone bold space between non-bold words should just be a space, not ** **
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
            <w:body>
                <w:p>
                    <w:r>
                        <w:t>word</w:t>
                    </w:r>
                    <w:r>
                        <w:rPr><w:b/></w:rPr>
                        <w:t xml:space="preserve"> </w:t>
                    </w:r>
                    <w:r>
                        <w:t>next</w:t>
                    </w:r>
                </w:p>
            </w:body>
        </w:document>
        """.encode('utf-8')
        self.mock_z.read.return_value = xml
        result = read_docx.extract_text("dummy.docx")
        self.assertEqual(result, "word next")

if __name__ == '__main__':
    unittest.main()
