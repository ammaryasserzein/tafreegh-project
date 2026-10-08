import unittest
from pathlib import Path
import sys
import tempfile
import docx
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Add scripts directory to sys.path
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from export_docx import (
    get_onedrive_folder,
    parse_metadata,
    is_header_line,
    standardize_transcript_header,
    create_docx,
    export_documents,
    export_dual_copies,
    archive_processed_inputs,
    is_matching_stem,
    normalize_stem,
)

class TestGetOneDriveFolder(unittest.TestCase):
    def setUp(self):
        self.base_path = Path("C:/Users/L/OneDrive/1. دوري")

    def test_known_keywords_mapping(self):
        test_cases = [
            ("اسماء", "1. الاسماء الحسنى"),
            ("أسماء", "1. الاسماء الحسنى"),
            ("رياض", "1. رياض الصالحين"),
            ("سيرة", "1. سيرة (الرحيق المختوم)"),
            ("معاملات", "1. معاملات"),
            ("دليل", "1. معاملات"),
            ("توحيد", "2. التوحيد"),
            ("لب", "2. لب الاصول"),
            ("لب الاصول", "2. لب الاصول"),
            ("أصول", "2. لب الاصول"),
            ("اصول", "2. لب الاصول"),
            ("الاصول", "2. لب الاصول"),
            ("الأصول", "2. لب الاصول"),
            ("ديوان", "ديوان الشافعي"),
            ("زاد", "زاد المعاد"),
            ("روضة", "شرح مختصر الروضة"),
            ("مختصر الروضة", "شرح مختصر الروضة"),
            ("صيد", "صيد الخاطر"),
            ("منطق", "المنطق"),
            ("المنطق", "المنطق"),
        ]
        for keyword, expected_folder in test_cases:
            with self.subTest(keyword=keyword):
                result = get_onedrive_folder(keyword, self.base_path)
                self.assertEqual(result, self.base_path / expected_folder)

    def test_fallback_creates_new_folder(self):
        keyword = "تفسير"
        result = get_onedrive_folder(keyword, self.base_path)
        self.assertEqual(result, self.base_path / "تفسير")


class TestParseMetadata(unittest.TestCase):
    def test_extract_metadata_from_standard_header(self):
        sample = """بسم الله الرحمن الرحيم
اسم المادة: سيرة (الرحيق المختوم)
2026-09-10

والحمد لله، والصلاة والسلام على رسول الله..."""
        meta = parse_metadata(sample)
        self.assertEqual(meta["date"], "2026-09-10")
        self.assertEqual(meta["keyword"], "سيرة")
        self.assertEqual(meta["subject_name"], "سيرة (الرحيق المختوم)")

    def test_extract_metadata_from_alt_header(self):
        sample = """بسم الله الرحمن الرحيم
المادة: زاد المعاد (فصل في حجة أبي بكر الصديق رضي الله عنه)
2026-09-18

بسم الله والحمد لله والصلاة والسلام على رسول الله..."""
        meta = parse_metadata(sample)
        self.assertEqual(meta["date"], "2026-09-18")
        self.assertEqual(meta["keyword"], "زاد")
        self.assertEqual(meta["subject_name"], "زاد المعاد")

    def test_extract_metadata_from_filename_token(self):
        sample = "2026-09-12 معاملات.mp3 دليل المصدر والحمد لله والصلاة والسلام..."
        meta = parse_metadata(sample)
        self.assertEqual(meta["date"], "2026-09-12")
        self.assertEqual(meta["keyword"], "معاملات")

    def test_canonical_subject_name_for_tawheed(self):
        sample = """بسم الله الرحمن الرحيم
المادة: توحيد
2026-09-18
"""
        meta = parse_metadata(sample)
        self.assertEqual(meta["subject_name"], "فتح الباري (كتاب التوحيد)")

    def test_notebooklm_arabic_source_guide_mantiq(self):
        sample = """2026-09-26 منطق.mp3
دليل المصدر
بسم الله الرحمن الرحيم الحمد لله رب العالمين..."""
        meta = parse_metadata(sample)
        self.assertEqual(meta["date"], "2026-09-26")
        self.assertEqual(meta["keyword"], "منطق")
        self.assertEqual(meta["subject_name"], "المنطق (السلم المنورق)")
        self.assertEqual(meta["audio_file"], "2026-09-26 منطق.mp3")

    def test_notebooklm_english_source_guide_seerah(self):
        sample = """2026-10-01 سيرة.mp3

Source guide

الحمد لله رب العالمين..."""
        meta = parse_metadata(sample)
        self.assertEqual(meta["date"], "2026-10-01")
        self.assertEqual(meta["keyword"], "سيرة")
        self.assertEqual(meta["subject_name"], "سيرة (الرحيق المختوم)")
        self.assertEqual(meta["audio_file"], "2026-10-01 سيرة.mp3")

    def test_notebooklm_sources_tag(self):
        sample = """المصادر
2026-10-03 معاملات.mp3
دليل المصدر
الحمد لله..."""
        meta = parse_metadata(sample)
        self.assertEqual(meta["date"], "2026-10-03")
        self.assertEqual(meta["keyword"], "معاملات")
        self.assertEqual(meta["subject_name"], "دليل الطالب (كتاب البيع)")
        self.assertEqual(meta["audio_file"], "2026-10-03 معاملات.mp3")


class TestHeaderFiltering(unittest.TestCase):
    def test_is_header_line_notebooklm_tags(self):
        self.assertTrue(is_header_line("المصادر"))
        self.assertTrue(is_header_line("مصادر"))
        self.assertTrue(is_header_line("دليل المصدر"))
        self.assertTrue(is_header_line("دليل مصادر"))
        self.assertTrue(is_header_line("Source guide"))
        self.assertTrue(is_header_line("Source Guide"))
        self.assertTrue(is_header_line("Sources"))
        self.assertTrue(is_header_line("2026-10-01 سيرة.mp3"))
        self.assertTrue(is_header_line("2026-09-26 منطق.mp3"))
        self.assertTrue(is_header_line("2026-10-03 معاملات.m4a"))
        self.assertFalse(is_header_line("الحمد لله رب العالمين"))
        self.assertFalse(is_header_line("طالب: صوت غير مسموع."))

    def test_standardize_transcript_header_excludes_notebooklm_tags(self):
        raw = """2026-10-01 سيرة.mp3

Source guide

الحمد لله رب العالمين، والصلاة والسلام على رسول الله."""
        clean = standardize_transcript_header(raw)
        self.assertNotIn("Source guide", clean)
        self.assertNotIn(".mp3", clean)
        self.assertTrue(clean.startswith("بسم الله الرحمن الرحيم\nالمادة: سيرة (الرحيق المختوم)\n2026-10-01"))
        self.assertIn("الحمد لله رب العالمين", clean)


class TestCreateDocx(unittest.TestCase):
    def test_create_docx_produces_valid_formatted_file(self):
        sample_md = """بسم الله الرحمن الرحيم
المادة: زاد المعاد (فصل في حجة أبي بكر الصديق رضي الله عنه)
2026-09-10

الحمد لله، والصلاة والسلام على رسول الله.

**(فَفِي مُسْنَدِ أَحْمَدَ وَالشَّافِعِيِّ رَضِيَ اللَّهُ عَنْهُمَا أَنَّهُمْ)**

الكفار.

طالب: في الحجة سيدنا.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "test_out.docx"
            create_docx(sample_md, out_file)
            
            self.assertTrue(out_file.exists())
            self.assertGreater(out_file.stat().st_size, 1000)
            
            doc = docx.Document(str(out_file))
            self.assertGreaterEqual(len(doc.paragraphs), 5)
            
            # Margins
            section = doc.sections[0]
            self.assertAlmostEqual(section.top_margin.inches, 0.5, places=2)
            self.assertAlmostEqual(section.bottom_margin.inches, 0.5, places=2)
            self.assertAlmostEqual(section.left_margin.inches, 0.5, places=2)
            self.assertAlmostEqual(section.right_margin.inches, 0.5, places=2)
            
            # Header
            self.assertEqual(doc.paragraphs[0].text.strip(), "بسم الله الرحمن الرحيم")
            self.assertEqual(doc.paragraphs[0].alignment, WD_ALIGN_PARAGRAPH.CENTER)
            self.assertEqual(doc.paragraphs[1].text.strip(), "المادة: زاد المعاد")
            self.assertEqual(doc.paragraphs[1].alignment, WD_ALIGN_PARAGRAPH.CENTER)
            self.assertEqual(doc.paragraphs[2].text.strip(), "2026-09-10")
            self.assertEqual(doc.paragraphs[2].alignment, WD_ALIGN_PARAGRAPH.CENTER)
            
            # Bold matn
            matn_found = False
            for p in doc.paragraphs:
                for r in p.runs:
                    self.assertIsNone(r.font.color.rgb)
                    if "فَفِي مُسْنَدِ أَحْمَدَ" in r.text:
                        matn_found = True
                        self.assertTrue(r.bold)
                        rPr = r._r.get_or_add_rPr()
                        self.assertIsNotNone(rPr.find(qn('w:bCs')), "w:bCs missing on Arabic bold run")
            self.assertTrue(matn_found, "Matn text was not found with bold formatting")

    def test_student_label_is_never_bold(self):
        sample_md = """بسم الله الرحمن الرحيم
المادة: زاد المعاد
2026-09-18

الحمد لله.

طالب: صوت غير مسموع.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "test_student.docx"
            create_docx(sample_md, out_file)
            doc = docx.Document(str(out_file))
            
            student_p = [p for p in doc.paragraphs if "طالب:" in p.text]
            self.assertTrue(len(student_p) > 0)
            for r in student_p[0].runs:
                self.assertFalse(r.bold, f"Student run '{r.text}' should NOT be bold")

    def test_header_with_blank_lines_does_not_leak_into_body(self):
        sample_md = """بسم الله الرحمن الرحيم

المادة: فتح الباري (كتاب التوحيد)

2026-09-18

الحمد لله، والصلاة والسلام على رسول الله.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "test_header.docx"
            create_docx(sample_md, out_file)
            doc = docx.Document(str(out_file))
            
            self.assertEqual(len(doc.paragraphs), 4)
            self.assertEqual(doc.paragraphs[0].text.strip(), "بسم الله الرحمن الرحيم")
            self.assertEqual(doc.paragraphs[1].text.strip(), "المادة: فتح الباري (كتاب التوحيد)")
            self.assertEqual(doc.paragraphs[2].text.strip(), "2026-09-18")
            self.assertEqual(doc.paragraphs[3].text.strip(), "الحمد لله، والصلاة والسلام على رسول الله.")

    def test_create_docx_strips_notebooklm_header_lines_from_body(self):
        sample = """2026-10-01 سيرة.mp3

Source guide

الحمد لله رب العالمين، والصلاة والسلام على رسول الله.
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "test_nb.docx"
            create_docx(sample, out_file)
            doc = docx.Document(str(out_file))
            body_texts = [p.text.strip() for p in doc.paragraphs]
            self.assertEqual(body_texts[0], "بسم الله الرحمن الرحيم")
            self.assertEqual(body_texts[1], "المادة: سيرة (الرحيق المختوم)")
            self.assertEqual(body_texts[2], "2026-10-01")
            self.assertNotIn("Source guide", body_texts)
            self.assertNotIn("2026-10-01 سيرة.mp3", body_texts)
            self.assertEqual(body_texts[3], "الحمد لله رب العالمين، والصلاة والسلام على رسول الله.")


class TestArchiveProcessedInputs(unittest.TestCase):
    def test_archive_moves_matching_raw_and_matn_and_deletes_chunks(self):
        with tempfile.TemporaryDirectory() as tmp_root:
            root = Path(tmp_root)
            matn_dir = root / "01_Matn_Sources"
            raw_dir = root / "02_Raw_Inputs"
            matn_dir.mkdir()
            raw_dir.mkdir()

            # Matching files
            (matn_dir / "2026-10-01__سيرة.md").write_text("matn content", encoding="utf-8")
            (raw_dir / "2026-10-01 سيرة.md").write_text("raw content", encoding="utf-8")
            chunks_dir = raw_dir / "2026-10-01  سيرة.md_مقاطع"
            chunks_dir.mkdir()
            (chunks_dir / "part1.txt").write_text("part 1", encoding="utf-8")

            # Other files
            (matn_dir / "2026-10-03__معاملات.md").write_text("other matn", encoding="utf-8")
            (raw_dir / "2026-10-03 معاملات.md").write_text("other raw", encoding="utf-8")

            res = archive_processed_inputs(date="2026-10-01", keyword="سيرة", project_root=root)

            # Assert moved files exist in processed/
            self.assertTrue((matn_dir / "processed" / "2026-10-01__سيرة.md").exists())
            self.assertFalse((matn_dir / "2026-10-01__سيرة.md").exists())
            self.assertTrue((raw_dir / "processed" / "2026-10-01 سيرة.md").exists())
            self.assertFalse((raw_dir / "2026-10-01 سيرة.md").exists())

            # Assert chunk folder deleted
            self.assertFalse(chunks_dir.exists())

            # Assert other files untouched
            self.assertTrue((matn_dir / "2026-10-03__معاملات.md").exists())
            self.assertTrue((raw_dir / "2026-10-03 معاملات.md").exists())


class TestExportDocuments(unittest.TestCase):
    def test_export_documents_creates_both_files(self):
        sample_md = """بسم الله الرحمن الرحيم
اسم المادة: سيرة (الرحيق المختوم)
2026-09-10

الحمد لله، والصلاة والسلام على رسول الله.
"""
        with tempfile.TemporaryDirectory() as tmp_onedrive, tempfile.TemporaryDirectory() as tmp_project:
            (Path(tmp_onedrive) / "1. سيرة (الرحيق المختوم)").mkdir()
            res = export_documents(
                markdown_text=sample_md,
                base_onedrive=Path(tmp_onedrive),
                project_root=Path(tmp_project)
            )
            
            onedrive_file = res["onedrive_file"]
            project_file = res["project_file"]
            
            expected_od_folder = Path(tmp_onedrive) / "1. سيرة (الرحيق المختوم)"
            self.assertEqual(onedrive_file.parent, expected_od_folder)
            self.assertEqual(onedrive_file.name, "2026-09-10.docx")
            self.assertTrue(onedrive_file.exists())
            
            expected_proj_folder = Path(tmp_project) / "03_AI_Outputs"
            self.assertEqual(project_file.parent, expected_proj_folder)
            self.assertTrue(project_file.name.startswith("2026-09-10_سيرة"))
            self.assertTrue(project_file.exists())


class TestIsMatchingStem(unittest.TestCase):
    def test_normalize_stem_strips_extensions_and_suffixes(self):
        self.assertEqual(
            normalize_stem("2026-09-19_منطق_(السلم_المنورق)_AI_full.md.md"),
            "2026-09-19_منطق_(السلم_المنورق)"
        )
        self.assertEqual(
            normalize_stem("2026-10-01_سيرة_processed.docx"),
            "2026-10-01_سيرة"
        )
        self.assertEqual(
            normalize_stem("2026-10-01  سيرة.md_مقاطع"),
            "2026-10-01  سيرة"
        )
        self.assertEqual(
            normalize_stem("2026-08-29_لب_الأصول_AI.md"),
            "2026-08-29_لب_الأصول"
        )

    def test_is_matching_stem_standard_match(self):
        self.assertTrue(is_matching_stem("2026-10-01_سيرة.md", "2026-10-01", "سيرة"))

    def test_is_matching_stem_double_extension(self):
        self.assertTrue(is_matching_stem("2026-10-01_سيرة.md.md", "2026-10-01", "سيرة"))

    def test_is_matching_stem_suffixes_ai_full_and_processed(self):
        self.assertTrue(is_matching_stem("2026-09-19_منطق_(السلم_المنورق)_AI_full.md", "2026-09-19", "منطق"))
        self.assertTrue(is_matching_stem("2026-10-01_سيرة_processed.docx", "2026-10-01", "سيرة"))
        self.assertTrue(is_matching_stem("2026-08-29_لب_الأصول_AI.md", "2026-08-29", "لب"))

    def test_is_matching_stem_chunk_folder_suffix(self):
        self.assertTrue(is_matching_stem("2026-10-01  سيرة.md_مقاطع", "2026-10-01", "سيرة"))

    def test_is_matching_stem_delimiter_variations(self):
        self.assertTrue(is_matching_stem("2026-09-24__رياض.md", "2026-09-24", "رياض"))
        self.assertTrue(is_matching_stem("2026-09-24  رياض.md", "2026-09-24", "رياض"))

    def test_is_matching_stem_different_keyword_rejects(self):
        self.assertFalse(is_matching_stem("2026-09-19_منطق_AI.md", "2026-09-19", "سيرة"))

    def test_is_matching_stem_different_date_rejects(self):
        self.assertFalse(is_matching_stem("2026-09-20_سيرة.md", "2026-09-19", "سيرة"))


if __name__ == "__main__":
    unittest.main()
