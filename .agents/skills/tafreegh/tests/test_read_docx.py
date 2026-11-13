import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from tafreegh import read_docx
from tafreegh.word_gateway import DocxArchiveError, create_docx, extract_text

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)

_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    "</Relationships>"
)


def _build_docx_bytes(body_xml: str) -> io.BytesIO:
    document_xml = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{_W_NS}">'
        f"<w:body>{body_xml}</w:body>"
        f"</w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
        zf.writestr("_rels/.rels", _RELS_XML)
        zf.writestr("word/document.xml", document_xml.encode("utf-8"))
    buf.seek(0)
    return buf


class TestWordGatewayExtractText(unittest.TestCase):
    def test_extracts_arabic_bold_bcs_only_correctly(self):
        # Even if w:b is explicitly off, w:bCs being on triggers bolding for Arabic
        archive = _build_docx_bytes(
            "<w:p><w:r><w:rPr><w:b w:val=\"0\"/><w:bCs/></w:rPr>"
            "<w:t>عربي</w:t></w:r></w:p>"
        )
        self.assertEqual(extract_text(archive), "**عربي**")

    def test_merges_consecutive_bold_runs_including_spaces(self):
        archive = _build_docx_bytes(
            "<w:p>"
            "<w:r><w:rPr><w:b/></w:rPr><w:t>word</w:t></w:r>"
            '<w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve"> </w:t></w:r>'
            "<w:r><w:rPr><w:b/></w:rPr><w:t>next</w:t></w:r>"
            "</w:p>"
        )
        self.assertEqual(extract_text(archive), "**word next**")

    def test_does_not_create_invalid_markdown_for_bold_spaces(self):
        archive = _build_docx_bytes(
            "<w:p>"
            "<w:r><w:t>word</w:t></w:r>"
            '<w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve"> </w:t></w:r>'
            "<w:r><w:t>next</w:t></w:r>"
            "</w:p>"
        )
        self.assertEqual(extract_text(archive), "word next")

    def test_consecutive_bold_paragraphs_remain_separate(self):
        archive = _build_docx_bytes(
            "<w:p><w:r><w:rPr><w:bCs/></w:rPr><w:t>(المتن الأول)</w:t></w:r></w:p>"
            "<w:p><w:r><w:rPr><w:bCs/></w:rPr><w:t>(المتن الثاني)</w:t></w:r></w:p>"
        )
        self.assertEqual(extract_text(archive), "**(المتن الأول)**\n\n**(المتن الثاني)**")

    def test_raises_docx_archive_error_for_missing_and_corrupt_archives(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            missing = tmp / "does_not_exist.docx"
            with self.assertRaises(DocxArchiveError):
                extract_text(missing)

            not_a_zip = tmp / "not_a_zip.docx"
            not_a_zip.write_text("plain text, not a zip archive", encoding="utf-8")
            with self.assertRaises(DocxArchiveError):
                extract_text(not_a_zip)

            empty_zip = tmp / "missing_document_xml.docx"
            with zipfile.ZipFile(empty_zip, "w") as zf:
                zf.writestr("[Content_Types].xml", _CONTENT_TYPES_XML)
            with self.assertRaises(DocxArchiveError):
                extract_text(empty_zip)

            malformed_xml = tmp / "malformed_xml.docx"
            with zipfile.ZipFile(malformed_xml, "w") as zf:
                zf.writestr("word/document.xml", b"<w:document><w:body><broken")
            with self.assertRaises(DocxArchiveError):
                extract_text(malformed_xml)

    def test_export_to_extract_round_trip_fidelity(self):
        source_md = """بسم الله الرحمن الرحيم
المادة: رياض الصالحين
2026-10-22

الحمد لله، قال تعالى `(عَمَّ يَتَسَاءَلُونَ)` في السورة.

<!-- fallback -->
**(وَعَنْ أَبِي هُرَيْرَةَ رَضِيَ اللَّهُ عَنْهُ)**

طالب: صوت غير مسموع.

### تقرير المتن الهجين (Dynamic Fallback Interleaving Summary)
- إجمالي مقاطع المتن: 1
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "round_trip.docx"
            create_docx(source_md, docx_path)
            extracted = extract_text(docx_path)

        self.assertEqual(
            extracted,
            "بسم الله الرحمن الرحيم\n\n"
            "المادة: رياض الصالحين\n\n"
            "2026-10-22\n\n"
            "الحمد لله، قال تعالى (عَمَّ يَتَسَاءَلُونَ) في السورة.\n\n"
            "**(وَعَنْ أَبِي هُرَيْرَةَ رَضِيَ اللَّهُ عَنْهُ)**\n\n"
            "طالب: صوت غير مسموع.",
        )


class TestReadDocxCLI(unittest.TestCase):
    def test_cli_extracts_valid_docx_and_exits_zero(self):
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "read_docx.py"
        with tempfile.TemporaryDirectory() as tmpdir:
            docx_path = Path(tmpdir) / "sample.docx"
            create_docx(
                "بسم الله الرحمن الرحيم\nالمادة: رياض الصالحين\n2026-10-22\n\n**(عَنْ أَبِي هُرَيْرَةَ)**",
                docx_path,
            )

            stdout_buf = io.StringIO()
            with contextlib.redirect_stdout(stdout_buf):
                rc = read_docx.main([str(docx_path)])
            self.assertEqual(rc, 0)
            self.assertIn("**(عَنْ أَبِي هُرَيْرَةَ)**", stdout_buf.getvalue())

            proc = subprocess.run(
                [sys.executable, str(script_path), str(docx_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 0)
            self.assertIn("**(عَنْ أَبِي هُرَيْرَةَ)**", proc.stdout)

    def test_cli_exits_one_and_reports_error_on_missing_or_corrupt_docx(self):
        script_path = Path(__file__).resolve().parent.parent / "scripts" / "read_docx.py"
        with tempfile.TemporaryDirectory() as tmpdir:
            corrupt_docx = Path(tmpdir) / "corrupt.docx"
            corrupt_docx.write_text("not a zip", encoding="utf-8")

            stdout_buf = io.StringIO()
            stderr_buf = io.StringIO()
            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                rc = read_docx.main([str(corrupt_docx)])
            self.assertEqual(rc, 1)
            self.assertEqual(stdout_buf.getvalue(), "")
            self.assertNotIn("Error reading docx:", stdout_buf.getvalue())
            self.assertTrue(stderr_buf.getvalue().strip())

            proc = subprocess.run(
                [sys.executable, str(script_path), str(Path(tmpdir) / "missing.docx")],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(proc.stdout, "")
            self.assertTrue(proc.stderr.strip())


if __name__ == "__main__":
    unittest.main()
