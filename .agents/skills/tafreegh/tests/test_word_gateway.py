"""Tests for the symmetric Word OOXML Gateway seam."""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

from tafreegh import export_docx
from tafreegh.word_gateway import (
    DEFAULT_BIDI_LANG,
    DEFAULT_FONT_NAME,
    DEFAULT_FONT_SIZE,
    DEFAULT_MARGIN_INCHES,
    DocxArchiveError,
    InspectedDocument,
    create_docx,
    extract_text,
    inspect_docx,
    read_matn_source_content,
    strip_hybrid_summary,
    strip_markdown_leakage,
)


class TestWordGatewaySanitizationAndMatnSource(unittest.TestCase):
    def test_strip_markdown_leakage_strips_arabic_backticks_preserving_english(self):
        raw = "قال تعالى `(عَمَّ يَتَسَاءَلُونَ)` وراجع `export_docx.py` في `2026-10-22`."
        self.assertEqual(
            strip_markdown_leakage(raw),
            "قال تعالى (عَمَّ يَتَسَاءَلُونَ) وراجع `export_docx.py` في `2026-10-22`.",
        )

    def test_strip_markdown_leakage_handles_multiline_arabic_and_empty_backticks(self):
        raw = "تمهيد `` وقوله `(السَّطْرُ الأَوَّلُ\nالسَّطْرُ الثَّانِي)` وراجع `file.py`."
        self.assertEqual(
            strip_markdown_leakage(raw),
            "تمهيد `` وقوله (السَّطْرُ الأَوَّلُ\nالسَّطْرُ الثَّانِي) وراجع `file.py`.",
        )

    def test_strip_hybrid_summary_removes_report_block(self):
        md = (
            "الحمد لله.\n\n"
            "### تقرير المتن الهجين (Dynamic Fallback Interleaving Summary)\n"
            "- إجمالي مقاطع المتن: 2\n"
        )
        self.assertEqual(strip_hybrid_summary(md), "الحمد لله.")
        self.assertEqual(strip_hybrid_summary("الحمد لله فقط."), "الحمد لله فقط.")

    def test_read_matn_source_content_supports_md_and_docx_and_raises_on_corrupt_docx(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            md_path = tmp / "matn.md"
            md_path.write_text("السطر الأول\nالسطر الثاني", encoding="utf-8")
            self.assertEqual(read_matn_source_content(md_path), "السطر الأول\nالسطر الثاني")

            docx_path = tmp / "matn.docx"
            create_docx(
                "بسم الله الرحمن الرحيم\nالمادة: رياض الصالحين\n2026-10-22\n\n"
                "عَنْ أَبِي هُرَيْرَةَ\n\nرَضِيَ اللَّهُ عَنْهُ",
                docx_path,
            )
            content = read_matn_source_content(docx_path)
            self.assertIn("عَنْ أَبِي هُرَيْرَةَ", content)
            self.assertIn("رَضِيَ اللَّهُ عَنْهُ", content)

            corrupt_docx = tmp / "corrupt.docx"
            corrupt_docx.write_text("not a zip archive", encoding="utf-8")
            with self.assertRaises(DocxArchiveError):
                read_matn_source_content(corrupt_docx)

            missing_docx = tmp / "missing.docx"
            with self.assertRaises(DocxArchiveError):
                read_matn_source_content(missing_docx)

    def test_read_matn_source_content_strips_markdown_wrappers_preserving_spaced_quran_asterisks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "matn.md"
            md_path.write_text(
                "> ## **التَّعَبُّدُ:**\n\n> *النَّظَرُ* في **(آية * آية)** و (سُورَةٌ * أُخْرَى)",
                encoding="utf-8",
            )
            cleaned = read_matn_source_content(md_path)
            self.assertEqual(
                cleaned,
                "التَّعَبُّدُ:\n\nالنَّظَرُ في (آية * آية) و (سُورَةٌ * أُخْرَى)",
            )

    def test_create_docx_never_writes_literal_double_asterisks_on_nested_bold(self):
        md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

**(مَتْنٌ أَوَّلُ)** وَكَلَامٌ **(مَتْنٌ ثَانٍ)**

**(نَصٌّ **دَاخِلِيٌّ**)**

**(نَصٌّ **مُفْرَدٌ)**
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "nested_bold.docx"
            create_docx(md, out_path)
            info = inspect_docx(out_path)
            for p in info.paragraphs:
                self.assertNotIn("**", p.text, f"Literal '**' leaked into paragraph: {p.text}")
                for r in p.runs:
                    self.assertNotIn("**", r.text, f"Literal '**' leaked into run: {r.text}")

    def test_create_docx_preserves_inline_bold_runs_with_bcs(self):
        md = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

نص فيه **(متن مضمن)** هنا.

طالب: قال **(متن)** هنا.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "inline_bold.docx"
            create_docx(md, out_path)
            info = inspect_docx(out_path)

            p_mixed = info.paragraphs[3]
            self.assertEqual(p_mixed.text, "نص فيه (متن مضمن) هنا.")
            bold_runs = [r for r in p_mixed.runs if r.is_bold]
            self.assertEqual([r.text for r in bold_runs], ["(متن مضمن)"])
            self.assertTrue(bold_runs[0].has_b)
            self.assertTrue(bold_runs[0].has_b_cs)

            p_student = info.paragraphs[4]
            self.assertEqual(p_student.text, "طالب: قال (متن) هنا.")
            student_bold_runs = [r for r in p_student.runs if r.is_bold]
            self.assertEqual([r.text for r in student_bold_runs], ["(متن)"])
            self.assertTrue(student_bold_runs[0].has_b_cs)

    def test_create_docx_raises_on_corrupt_template(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            corrupt_template = tmp / "bad_template.docx"
            corrupt_template.write_text("invalid zip", encoding="utf-8")
            with self.assertRaises(DocxArchiveError):
                create_docx(
                    "بسم الله الرحمن الرحيم\nالمادة: رياض الصالحين\n2026-10-22\n\nالحمد لله.",
                    tmp / "out.docx",
                    template_path=corrupt_template,
                )

    def test_canonical_ooxml_constants(self):
        self.assertEqual(DEFAULT_FONT_NAME, "Traditional Arabic")
        self.assertEqual(DEFAULT_FONT_SIZE, 18)
        self.assertAlmostEqual(DEFAULT_MARGIN_INCHES, 0.5)
        self.assertEqual(DEFAULT_BIDI_LANG, "ar-SA")


class TestWordGatewayInspectDocx(unittest.TestCase):
    def test_inspects_rendered_docx_margins_headers_rtl_and_bold_runs(self):
        md = """بسم الله الرحمن الرحيم
المادة: رياض الصالحين
2026-10-22

الحمد لله.

**(عَنْ أَبِي هُرَيْرَةَ)**
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "inspect.docx"
            create_docx(md, out_path)

            info = inspect_docx(out_path)
            self.assertIsInstance(info, InspectedDocument)
            self.assertEqual(len(info.sections), 1)
            sec = info.sections[0]
            self.assertAlmostEqual(sec.top_inches, 0.5, places=2)
            self.assertAlmostEqual(sec.bottom_inches, 0.5, places=2)
            self.assertAlmostEqual(sec.left_inches, 0.5, places=2)
            self.assertAlmostEqual(sec.right_inches, 0.5, places=2)

            self.assertEqual(len(info.paragraphs), 5)
            # Header paragraph P0
            p0 = info.paragraphs[0]
            self.assertTrue(p0.is_centered)
            self.assertTrue(p0.has_bidi)
            self.assertFalse(p0.runs[0].is_bold)
            self.assertEqual(p0.runs[0].font_name, "Traditional Arabic")
            self.assertAlmostEqual(p0.runs[0].font_size_pt, 18.0)
            self.assertTrue(p0.runs[0].has_rtl)
            self.assertEqual(p0.runs[0].bidi_lang, "ar-SA")
            self.assertIsNone(p0.runs[0].color_val)

            # Matn paragraph P4
            p4 = info.paragraphs[4]
            self.assertFalse(p4.is_centered)
            self.assertTrue(p4.has_bidi)
            self.assertTrue(p4.runs[0].is_bold)
            self.assertTrue(p4.runs[0].has_b)
            self.assertTrue(p4.runs[0].has_b_cs)

    def test_inspects_mutated_breaks_color_and_bcs_only_runs(self):
        doc = docx.Document()
        doc.sections[0].top_margin = Inches(1.0)
        p = doc.add_paragraph()
        r = p.add_run("نص")
        r.font.size = Pt(14)
        r_pr = r._r.get_or_add_rPr()
        r_pr.append(OxmlElement("w:bCs"))
        color_el = OxmlElement("w:color")
        color_el.set(qn("w:val"), "FF0000")
        r_pr.append(color_el)
        r._r.append(OxmlElement("w:br"))

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)

        info = inspect_docx(buf)
        self.assertAlmostEqual(info.sections[0].top_inches, 1.0, places=2)
        p0 = info.paragraphs[0]
        self.assertFalse(p0.has_bidi)
        self.assertEqual(p0.manual_line_break_count, 1)
        run0 = p0.runs[0]
        self.assertTrue(run0.is_bold)
        self.assertFalse(run0.has_b)
        self.assertTrue(run0.has_b_cs)
        self.assertEqual(run0.color_val, "FF0000")
        self.assertAlmostEqual(run0.font_size_pt, 14.0)

    def test_inspect_docx_raises_docx_archive_error_on_missing_or_corrupt_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            with self.assertRaises(DocxArchiveError):
                inspect_docx(tmp / "missing.docx")

            bad = tmp / "corrupt.docx"
            bad.write_text("not a zip", encoding="utf-8")
            with self.assertRaises(DocxArchiveError):
                inspect_docx(bad)

            valid = tmp / "valid.docx"
            create_docx("بسم الله الرحمن الرحيم\nالمادة: رياض الصالحين\n2026-10-22\n\nالحمد لله.", valid)
            with patch("zipfile.ZipFile.read", side_effect=RuntimeError("File is encrypted, password required")):
                with self.assertRaises(DocxArchiveError):
                    extract_text(valid)
            with patch("zipfile.ZipFile.read", side_effect=zlib.error("Error -3 while decompressing data")):
                with self.assertRaises(DocxArchiveError):
                    extract_text(valid)
            with patch("docx.Document", side_effect=RuntimeError("File is encrypted, password required")):
                with self.assertRaises(DocxArchiveError):
                    inspect_docx(valid)

    def test_bold_flag_symmetry_across_extract_and_inspect(self):
        doc = docx.Document()
        p = doc.add_paragraph()

        r_on = p.add_run("مثبت")
        r_on_pr = r_on._r.get_or_add_rPr()
        b_cs_on = OxmlElement("w:bCs")
        b_cs_on.set(qn("w:val"), "true")
        r_on_pr.append(b_cs_on)

        r_off = p.add_run(" غيرمثبت")
        r_off_pr = r_off._r.get_or_add_rPr()
        b_off = OxmlElement("w:b")
        b_off.set(qn("w:val"), "off")
        b_cs_off = OxmlElement("w:bCs")
        b_cs_off.set(qn("w:val"), "false")
        r_off_pr.append(b_off)
        r_off_pr.append(b_cs_off)

        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        inspected = inspect_docx(buf)
        buf.seek(0)
        extracted = extract_text(buf)

        self.assertTrue(inspected.paragraphs[0].runs[0].is_bold)
        self.assertFalse(inspected.paragraphs[0].runs[1].is_bold)
        self.assertEqual(extracted, "**مثبت** غيرمثبت")

    def test_verify_docx_has_zero_dependency_on_export_docx(self):
        scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
        proc = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                "import sys; import tafreegh.verify_docx; assert 'tafreegh.export_docx' not in sys.modules",
            ],
            cwd=str(scripts_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=f"stderr={proc.stderr}")

    def test_export_docx_cli_exits_one_on_corrupt_docx_matn_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            md_path = tmp / "2026-10-22_رياض.md"
            md_path.write_text("بسم الله الرحمن الرحيم\nالمادة: رياض الصالحين\n2026-10-22\n\nالحمد لله.", encoding="utf-8")
            corrupt_matn = tmp / "corrupt_matn.docx"
            corrupt_matn.write_text("not a zip", encoding="utf-8")

            stderr_buf = io.StringIO()
            with contextlib.redirect_stderr(stderr_buf):
                rc = export_docx.main([str(md_path), "رياض", "2026-10-22", str(corrupt_matn)])
            self.assertEqual(rc, 1)
            self.assertIn("Error:", stderr_buf.getvalue())


if __name__ == "__main__":
    unittest.main()
