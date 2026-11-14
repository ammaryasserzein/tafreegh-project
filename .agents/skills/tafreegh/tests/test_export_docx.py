import unittest
from pathlib import Path
import sys
import tempfile
import warnings
import docx
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from tafreegh.export_docx import (
    PublicationOrchestrator,
    archive_processed_inputs,
    export_documents,
    interleave_matn_segments,
    main as export_main,
    verify_isolated_segment,
)
from tafreegh.word_gateway import DocxArchiveError, create_docx, extract_text, inspect_docx
from tafreegh.lecture_identity import (
    NOTEBOOKLM_HEADER_PATTERNS,
    LectureIdentity,
    is_header_line,
    normalize_stem,
    resolve_document_identity,
    standardize_transcript_header,
)
from tafreegh.matn_matcher import SequentialMatnMatcher
from tafreegh.workspace_catalog import RuleCatalog, WorkspaceConfig

class TestResolveOneDriveFolder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = RuleCatalog.load()

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self._tmp_dir.name)
        for folder_name in (
            "1. الاسماء الحسنى",
            "1. رياض الصالحين",
            "1. سيرة (الرحيق المختوم)",
            "1. معاملات",
            "2. التوحيد",
            "2. لب الاصول",
            "ديوان الشافعي",
            "زاد المعاد",
            "شرح مختصر الروضة",
            "صيد الخاطر",
            "المنطق",
            "فقه البيوع (سعد الخثلان)",
        ):
            (self.base_path / folder_name).mkdir()

    def tearDown(self):
        self._tmp_dir.cleanup()

    def test_known_keywords_mapping(self):
        test_cases = [
            ("اسماء", "1. الاسماء الحسنى"),
            ("أسماء", "1. الاسماء الحسنى"),
            ("رياض", "1. رياض الصالحين"),
            ("سيرة", "1. سيرة (الرحيق المختوم)"),
            ("رحيق", "1. سيرة (الرحيق المختوم)"),
            ("الرحيق", "1. سيرة (الرحيق المختوم)"),
            ("معاملات", "1. معاملات"),
            ("دليل", "1. معاملات"),
            ("دليل الطالب (كتاب البيع)", "1. معاملات"),
            ("توحيد", "2. التوحيد"),
            ("فتح", "2. التوحيد"),
            ("فتح الباري (كتاب التوحيد)", "2. التوحيد"),
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
            ("سلم", "المنطق"),
            ("السلم", "المنطق"),
            ("بيوع", "فقه البيوع (سعد الخثلان)"),
            ("البيوع", "فقه البيوع (سعد الخثلان)"),
            ("فقه البيوع", "فقه البيوع (سعد الخثلان)"),
            ("فقه_البيوع", "فقه البيوع (سعد الخثلان)"),
            ("خثلان", "فقه البيوع (سعد الخثلان)"),
        ]
        for keyword, expected_folder in test_cases:
            with self.subTest(keyword=keyword):
                result = self.catalog.resolve_onedrive_folder(keyword, self.base_path)
                self.assertEqual(result, self.base_path / expected_folder)

    def test_fallback_creates_new_folder(self):
        keyword = "تفسير"
        result = self.catalog.resolve_onedrive_folder(keyword, self.base_path)
        self.assertEqual(result, self.base_path / "تفسير")


class TestParseMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routing_map = RuleCatalog.load().routing_map

    def test_extract_metadata_from_standard_header(self):
        sample = """بسم الله الرحمن الرحيم
اسم المادة: سيرة (الرحيق المختوم)
2026-09-10

والحمد لله، والصلاة والسلام على رسول الله..."""
        meta = LectureIdentity.from_text(sample, routing_map=self.routing_map)
        self.assertEqual(meta.date, "2026-09-10")
        self.assertEqual(meta.keyword, "سيرة")
        self.assertEqual(meta.subject_name, "سيرة (الرحيق المختوم)")

    def test_extract_metadata_from_alt_header(self):
        sample = """بسم الله الرحمن الرحيم
المادة: زاد المعاد (فصل في حجة أبي بكر الصديق رضي الله عنه)
2026-09-18

بسم الله والحمد لله والصلاة والسلام على رسول الله..."""
        meta = LectureIdentity.from_text(sample, routing_map=self.routing_map)
        self.assertEqual(meta.date, "2026-09-18")
        self.assertEqual(meta.keyword, "زاد")
        self.assertEqual(meta.subject_name, "زاد المعاد")

    def test_extract_metadata_from_filename_token(self):
        sample = "2026-09-12 معاملات.mp3 دليل المصدر والحمد لله والصلاة والسلام..."
        meta = LectureIdentity.from_text(sample, routing_map=self.routing_map)
        self.assertEqual(meta.date, "2026-09-12")
        self.assertEqual(meta.keyword, "معاملات")

    def test_canonical_subject_name_for_tawheed(self):
        sample = """بسم الله الرحمن الرحيم
المادة: توحيد
2026-09-18
"""
        meta = LectureIdentity.from_text(sample, routing_map=self.routing_map)
        self.assertEqual(meta.subject_name, "فتح الباري (كتاب التوحيد)")

    def test_notebooklm_arabic_source_guide_mantiq(self):
        sample = """2026-09-26 منطق.mp3
دليل المصدر
بسم الله الرحمن الرحيم الحمد لله رب العالمين..."""
        meta = LectureIdentity.from_text(sample, routing_map=self.routing_map)
        self.assertEqual(meta.date, "2026-09-26")
        self.assertEqual(meta.keyword, "منطق")
        self.assertEqual(meta.subject_name, "المنطق (السلم المنورق)")
        self.assertEqual(meta.audio_file, "2026-09-26 منطق.mp3")

    def test_notebooklm_english_source_guide_seerah(self):
        sample = """2026-10-01 سيرة.mp3

Source guide

الحمد لله رب العالمين..."""
        meta = LectureIdentity.from_text(sample, routing_map=self.routing_map)
        self.assertEqual(meta.date, "2026-10-01")
        self.assertEqual(meta.keyword, "سيرة")
        self.assertEqual(meta.subject_name, "سيرة (الرحيق المختوم)")
        self.assertEqual(meta.audio_file, "2026-10-01 سيرة.mp3")

    def test_notebooklm_sources_tag(self):
        sample = """المصادر
2026-10-03 معاملات.mp3
دليل المصدر
الحمد لله..."""
        meta = LectureIdentity.from_text(sample, routing_map=self.routing_map)
        self.assertEqual(meta.date, "2026-10-03")
        self.assertEqual(meta.keyword, "معاملات")
        self.assertEqual(meta.subject_name, "دليل الطالب (كتاب البيع)")
        self.assertEqual(meta.audio_file, "2026-10-03 معاملات.mp3")

    def test_numbered_stem_metadata(self):
        sample = "17-فقه_البيوع_17.mp3\nSource guide\nالحمد لله..."
        meta = LectureIdentity.from_text(sample, routing_map=self.routing_map)
        self.assertIsNone(meta.date)
        self.assertEqual(meta.lecture_number, "17")
        self.assertIn(meta.keyword, ("فقه_البيوع", "فقه البيوع"))
        self.assertEqual(meta.subject_name, "فقه البيوع (سعد الخثلان)")
        self.assertEqual(meta.audio_file, "17-فقه_البيوع_17.mp3")

    def test_numbered_stem_with_explicit_headers(self):
        sample = """بسم الله الرحمن الرحيم
المادة: فقه البيوع (سعد الخثلان)
المحاضرة: 17

الحمد لله رب العالمين..."""
        meta = LectureIdentity.from_text(sample, routing_map=self.routing_map)
        self.assertIsNone(meta.date)
        self.assertEqual(meta.lecture_number, "17")
        self.assertEqual(meta.subject_name, "فقه البيوع (سعد الخثلان)")

    def test_date_followed_by_newline_body_does_not_steal_body_word_as_keyword(self):
        sample = "بسم الله الرحمن الرحيم\n2026-10-09\n\nالحمد لله رب العالمين"
        meta = LectureIdentity.from_text(sample, routing_map=self.routing_map)
        self.assertEqual(meta.date, "2026-10-09")
        self.assertIsNone(meta.keyword)
        self.assertIsNone(meta.subject_name)

    def test_from_filename_extracts_underscore_separated_date_and_subject(self):
        ident = LectureIdentity.from_filename("2026-09-24__رياض.md", routing_map=self.routing_map)
        self.assertEqual(ident.date, "2026-09-24")
        self.assertEqual(ident.keyword, "رياض")
        self.assertEqual(ident.subject_name, "رياض الصالحين")
        self.assertEqual(ident.stem, "2026-09-24__رياض")

    def test_from_text_step6_ignores_trailing_prose_after_filename_token(self):
        meta1 = LectureIdentity.from_text(
            "2026-09-12 معاملات.mp3 شرح زاد المعاد\nالحمد لله",
            routing_map=self.routing_map,
        )
        self.assertEqual(meta1.keyword, "معاملات")
        self.assertEqual(meta1.subject_name, "دليل الطالب (كتاب البيع)")

        meta2 = LectureIdentity.from_text(
            "2026-09-12 مجهول.mp3 ثم قال صلى الله عليه وسلم\nالحمد لله",
            routing_map=self.routing_map,
        )
        self.assertEqual(meta2.keyword, "مجهول")
        self.assertEqual(meta2.subject_name, "مجهول")


class TestHeaderFiltering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routing_map = RuleCatalog.load().routing_map

    def test_is_header_line_notebooklm_tags(self):
        self.assertIsInstance(NOTEBOOKLM_HEADER_PATTERNS, tuple)
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
        clean = standardize_transcript_header(raw, routing_map=self.routing_map)
        self.assertNotIn("Source guide", clean)
        self.assertNotIn(".mp3", clean)
        self.assertTrue(clean.startswith("بسم الله الرحمن الرحيم\nالمادة: سيرة (الرحيق المختوم)\n2026-10-01"))
        self.assertIn("الحمد لله رب العالمين", clean)

    def test_is_header_line_numbered_headers(self):
        self.assertTrue(is_header_line("المحاضرة: 17"))
        self.assertTrue(is_header_line("المحاضرة: 5"))
        self.assertTrue(is_header_line("17-فقه_البيوع_17.mp3"))
        self.assertTrue(is_header_line("17-فقه_البيوع_17"))

    def test_standardize_transcript_header_numbered_lecture(self):
        raw = """17-فقه_البيوع_17.mp3

Source guide

المادة: فقه البيوع (سعد الخثلان)
المحاضرة: 17

الحمد لله رب العالمين، والصلاة والسلام على رسول الله."""
        clean = standardize_transcript_header(raw, routing_map=self.routing_map)
        self.assertNotIn("Source guide", clean)
        self.assertNotIn(".mp3", clean)
        self.assertTrue(clean.startswith("بسم الله الرحمن الرحيم\nالمادة: فقه البيوع (سعد الخثلان)\nالمحاضرة: 17"))
        self.assertIn("الحمد لله رب العالمين", clean)

    def test_standardize_transcript_header_override_precedence(self):
        # Caller's explicit identity override must take precedence over markdown header
        raw = """بسم الله الرحمن الرحيم
المادة: قديم
2026-01-01

الحمد لله رب العالمين."""
        override = LectureIdentity(lecture_number="5", subject_name="فقه جديد")
        clean = standardize_transcript_header(raw, identity=override, routing_map=self.routing_map)
        self.assertTrue(clean.startswith("بسم الله الرحمن الرحيم\nالمادة: فقه جديد\nالمحاضرة: 5"))
        self.assertNotIn("قديم", clean)


class TestCreateDocx(unittest.TestCase):
    def test_create_docx_uses_workspace_context_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            context_path = root / "CONTEXT.md"
            context_path.write_text(
                "## 3. توجيه المتون (Routing Map)\n\n"
                "| الكلمة الدلالية | المادة المعتمدة | المتن ومصدره |\n"
                "| --- | --- | --- |\n"
                "| `(مخصص)` | **مادة مخصصة للاختبار** | متن |\n",
                encoding="utf-8",
            )
            ws = WorkspaceConfig.resolve(project_root=root, context_path=context_path, env={})
            out_file = root / "out.docx"
            create_docx("2026-11-01 مخصص.mp3\n\nالحمد لله رب العالمين.", out_file, workspace=ws)
            doc = docx.Document(str(out_file))
            self.assertEqual(doc.paragraphs[1].text, "المادة: مادة مخصصة للاختبار")

    def test_create_docx_override_precedence(self):
        sample_md = """بسم الله الرحمن الرحيم
المادة: قديم
2026-01-01

الحمد لله رب العالمين."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "output.docx"
            override = LectureIdentity(lecture_number="5", subject_name="فقه جديد")
            create_docx(sample_md, out_file, identity=override)
            doc = docx.Document(str(out_file))
            p_texts = [p.text for p in doc.paragraphs]
            self.assertIn("المادة: فقه جديد", p_texts)
            self.assertIn("المحاضرة: 5", p_texts)
            self.assertNotIn("المادة: قديم", p_texts)

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

            res = archive_processed_inputs(LectureIdentity(date="2026-10-01", keyword="سيرة"), project_root=root)

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

    def test_export_documents_overwrite_flag_replaces_in_place_without_ai_suffix(self):
        sample_md_v1 = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

الحمد لله، النسخة الأولى.
"""
        sample_md_v2 = """بسم الله الرحمن الرحيم
المادة: المنطق (السلم المنورق)
2026-10-17

الحمد لله، النسخة الثانية المصححة.
"""
        with tempfile.TemporaryDirectory() as tmp_onedrive, tempfile.TemporaryDirectory() as tmp_project:
            (Path(tmp_onedrive) / "المنطق").mkdir()
            res1 = export_documents(
                markdown_text=sample_md_v1,
                base_onedrive=Path(tmp_onedrive),
                project_root=Path(tmp_project),
            )
            self.assertEqual(res1["onedrive_file"].name, "2026-10-17.docx")

            # Re-export with overwrite=True must keep 2026-10-17.docx instead of 2026-10-17 #AI.docx
            res2 = export_documents(
                markdown_text=sample_md_v2,
                base_onedrive=Path(tmp_onedrive),
                project_root=Path(tmp_project),
                overwrite=True,
            )
            self.assertEqual(res2["onedrive_file"].name, "2026-10-17.docx")
            self.assertFalse((Path(tmp_onedrive) / "المنطق" / "2026-10-17 #AI.docx").exists())
            doc = docx.Document(str(res2["onedrive_file"]))
            texts = [p.text for p in doc.paragraphs]
            self.assertIn("الحمد لله، النسخة الثانية المصححة.", texts)



class TestLectureIdentityMatching(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routing_map = RuleCatalog.load().routing_map

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

    def test_matches_standard_date_stem(self):
        self.assertTrue(
            LectureIdentity(date="2026-10-01", keyword="سيرة").matches(
                "2026-10-01_سيرة.md", routing_map=self.routing_map
            )
        )

    def test_matches_double_extension(self):
        self.assertTrue(
            LectureIdentity(date="2026-10-01", keyword="سيرة").matches(
                "2026-10-01_سيرة.md.md", routing_map=self.routing_map
            )
        )

    def test_matches_suffixes_ai_full_and_processed(self):
        self.assertTrue(
            LectureIdentity(date="2026-09-19", keyword="منطق").matches(
                "2026-09-19_منطق_(السلم_المنورق)_AI_full.md", routing_map=self.routing_map
            )
        )
        self.assertTrue(
            LectureIdentity(date="2026-10-01", keyword="سيرة").matches(
                "2026-10-01_سيرة_processed.docx", routing_map=self.routing_map
            )
        )
        self.assertTrue(
            LectureIdentity(date="2026-08-29", keyword="لب").matches(
                "2026-08-29_لب_الأصول_AI.md", routing_map=self.routing_map
            )
        )

    def test_matches_chunk_folder_suffix(self):
        self.assertTrue(
            LectureIdentity(date="2026-10-01", keyword="سيرة").matches(
                "2026-10-01  سيرة.md_مقاطع", routing_map=self.routing_map
            )
        )

    def test_matches_delimiter_variations(self):
        self.assertTrue(
            LectureIdentity(date="2026-09-24", keyword="رياض").matches(
                "2026-09-24__رياض.md", routing_map=self.routing_map
            )
        )
        self.assertTrue(
            LectureIdentity(date="2026-09-24", keyword="رياض").matches(
                "2026-09-24  رياض.md", routing_map=self.routing_map
            )
        )

    def test_matches_different_keyword_rejects(self):
        self.assertFalse(
            LectureIdentity(date="2026-09-19", keyword="سيرة").matches(
                "2026-09-19_منطق_AI.md", routing_map=self.routing_map
            )
        )

    def test_matches_different_date_rejects(self):
        self.assertFalse(
            LectureIdentity(date="2026-09-19", keyword="سيرة").matches(
                "2026-09-20_سيرة.md", routing_map=self.routing_map
            )
        )

    def test_matches_date_with_keyword_rejects_empty_keyword_candidate(self):
        self.assertFalse(
            LectureIdentity(date="2026-09-24", keyword="رياض").matches(
                "2026-09-24.md", routing_map=self.routing_map
            )
        )

    def test_matches_numbered_stem_and_aliases(self):
        self.assertTrue(
            LectureIdentity(keyword="بيوع", stem="17-فقه_البيوع_17").matches(
                "17-فقه_البيوع_17.md", routing_map=self.routing_map
            )
        )
        self.assertTrue(
            LectureIdentity(keyword="بيوع", lecture_number="17").matches(
                "17-فقه_البيوع_17.md", routing_map=self.routing_map
            )
        )
        self.assertTrue(
            LectureIdentity(date="17", keyword="بيوع").matches(
                "17-فقه_البيوع_17.md", routing_map=self.routing_map
            )
        )
        self.assertTrue(
            LectureIdentity(keyword="فقه_البيوع", lecture_number="17").matches(
                "17-فقه_البيوع_17_AI.md", routing_map=self.routing_map
            )
        )
        self.assertFalse(
            LectureIdentity(keyword="بيوع", lecture_number="18").matches(
                "17-فقه_البيوع_17.md", routing_map=self.routing_map
            )
        )
        self.assertFalse(
            LectureIdentity(keyword="رياض", lecture_number="17").matches(
                "17-فقه_البيوع_17.md", routing_map=self.routing_map
            )
        )

    def test_matches_numbered_stem_requires_target_num(self):
        # A numbered candidate must NOT match when no target_num or stem is provided
        self.assertFalse(
            LectureIdentity(keyword="بيوع").matches("17-فقه_البيوع_17.md", routing_map=self.routing_map)
        )
        self.assertFalse(
            LectureIdentity(keyword="فقه البيوع").matches("17-فقه_البيوع_17.md", routing_map=self.routing_map)
        )

    def test_matches_ignores_empty_or_whitespace_keyword(self):
        self.assertFalse(
            LectureIdentity(lecture_number="17", keyword="   ").matches(
                "17-رياض-17.md", routing_map=self.routing_map
            )
        )
        self.assertFalse(
            LectureIdentity(lecture_number="17", keyword="_").matches(
                "17_رياض.docx", routing_map=self.routing_map
            )
        )


class TestExportNumberedDocuments(unittest.TestCase):
    def test_export_numbered_lecture_documents_e2e(self):
        with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_onedrive:
            root_path = Path(tmp_root)
            onedrive_base = Path(tmp_onedrive)
            
            raw_dir = root_path / "02_Raw_Inputs"
            matn_dir = root_path / "01_Matn_Sources"
            raw_dir.mkdir(parents=True)
            matn_dir.mkdir(parents=True)
            
            raw_file = raw_dir / "17-فقه_البيوع_17.md"
            matn_file = matn_dir / "17-فقه_البيوع_17.md"
            
            matn_text = "وَيَحْرُمُ رِبَا النَّسِيئَةِ، فِي بَيْعِ كُلِّ جِنْسَيْنِ اتَّفَقَا فِي عِلَّةِ رِبَا الْفَضْلِ."
            matn_file.write_text(matn_text, encoding="utf-8")
            
            transcript = """17-فقه_البيوع_17.mp3
Source guide
المادة: فقه البيوع (سعد الخثلان)
المحاضرة: 17

الحمد لله والصلاة والسلام على رسول الله.
**(ويحرم ربا النسيئة في بيع كل جنسين اتفقا في علة ربا الفضل)**
طالب: صوت غير مسموع.
نعم، هذا ضابط ربا النسيئة."""
            raw_file.write_text(transcript, encoding="utf-8")
            
            results = export_documents(
                transcript,
                original_md_path=raw_file,
                base_onedrive=onedrive_base,
                project_root=root_path,
            )
            
            # 1. Output files exist
            onedrive_file = results["onedrive_file"]
            project_file = results["project_file"]
            self.assertTrue(onedrive_file.exists())
            self.assertTrue(project_file.exists())
            
            # 2. Correct naming
            self.assertEqual(onedrive_file.name, "17-فقه_البيوع_17.docx")
            self.assertEqual(project_file.name, "17-فقه_البيوع_17_AI.md")
            
            # 3. Check docx content and headers
            doc = docx.Document(str(onedrive_file))
            headers = [p.text.strip() for p in doc.paragraphs[:3]]
            self.assertEqual(headers[0], "بسم الله الرحمن الرحيم")
            self.assertEqual(headers[1], "المادة: فقه البيوع (سعد الخثلان)")
            self.assertEqual(headers[2], "المحاضرة: 17")
            
            # 4. Check archiving into processed/
            self.assertFalse(raw_file.exists())
            self.assertFalse(matn_file.exists())
            self.assertTrue((raw_dir / "processed" / "17-فقه_البيوع_17.md").exists())
            self.assertTrue((matn_dir / "processed" / "17-فقه_البيوع_17.md").exists())

    def test_export_documents_metadata_from_path_sets_header_lines(self):
        with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_onedrive:
            root_path = Path(tmp_root)
            onedrive_base = Path(tmp_onedrive)
            
            raw_dir = root_path / "02_Raw_Inputs"
            raw_dir.mkdir(parents=True)
            raw_file = raw_dir / "17-فقه_البيوع_17.md"
            
            # Markdown text body has NO header block
            transcript = "الحمد لله، نبدأ في شرح ربا النسيئة."
            raw_file.write_text(transcript, encoding="utf-8")
            
            results = export_documents(
                transcript,
                original_md_path=raw_file,
                base_onedrive=onedrive_base,
                project_root=root_path,
            )
            
            onedrive_file = results["onedrive_file"]
            doc = docx.Document(str(onedrive_file))
            headers = [p.text.strip() for p in doc.paragraphs[:3]]
            self.assertEqual(headers[0], "بسم الله الرحمن الرحيم")
            self.assertEqual(headers[1], "المادة: فقه البيوع (سعد الخثلان)")
            self.assertEqual(headers[2], "المحاضرة: 17")

    def test_export_documents_dynamic_stem_fallback_uses_course_subject(self):
        with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_onedrive:
            root_path = Path(tmp_root)
            onedrive_base = Path(tmp_onedrive)
            
            # Transcript for Diwan al-Shafi'i lecture 5 without mirrored stem in body
            transcript = "المادة: ديوان الشافعي\nالمحاضرة: 5\nقال الإمام الشافعي رحمه الله."
            results = export_documents(
                transcript,
                base_onedrive=onedrive_base,
                project_root=root_path,
            )
            project_file = results["project_file"]
            self.assertIn("5-ديوان_الشافعي_5_AI.md", project_file.name)

    def test_export_documents_numbered_override_supersedes_parsed_date_in_filenames(self):
        with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_onedrive:
            root_path = Path(tmp_root)
            onedrive_base = Path(tmp_onedrive)
            raw_dir = root_path / "02_Raw_Inputs"
            raw_dir.mkdir(parents=True)
            raw_file = raw_dir / "2026-01-01_قديم.md"
            transcript = "بسم الله الرحمن الرحيم\nالمادة: قديم\n2026-01-01\n\nالحمد لله رب العالمين."
            raw_file.write_text(transcript, encoding="utf-8")
            override = LectureIdentity(lecture_number="5", subject_name="فقه جديد")

            results = export_documents(
                transcript,
                original_md_path=raw_file,
                identity=override,
                base_onedrive=onedrive_base,
                project_root=root_path,
            )
            self.assertEqual(results["onedrive_file"].name, "5-فقه_جديد_5.docx")
            self.assertEqual(results["project_file"].name, "5-فقه_جديد_5_AI.md")


class TestPublicationOrchestratorAndInterleaving(unittest.TestCase):
    def _build_temp_workspace(
        self,
        tmp_dir: str,
        *,
        folder_name: str = "1. رياض الصالحين",
        dialect_rules_text: str | None = None,
    ) -> tuple[Path, Path, Path, Path, WorkspaceConfig]:
        root = Path(tmp_dir) / "repo"
        onedrive = Path(tmp_dir) / "onedrive"
        matn_dir = root / "01_Matn_Sources"
        raw_dir = root / "02_Raw_Inputs"
        matn_dir.mkdir(parents=True)
        raw_dir.mkdir(parents=True)
        (onedrive / folder_name).mkdir(parents=True)
        dialect_path: Path | None = None
        if dialect_rules_text is not None:
            dialect_path = root / "dialect-rules.md"
            dialect_path.write_text(dialect_rules_text, encoding="utf-8")
        ws = WorkspaceConfig.resolve(
            project_root=root,
            onedrive_base=onedrive,
            dialect_rules_path=dialect_path,
            env={},
        )
        return root, onedrive, matn_dir, raw_dir, ws

    def test_interleave_matn_segments_handles_primary_sandwiched_and_isolated_dialect(self):
        matn_source = (
            "إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ ... "
            "وَنِسْبَةٌ وَفَضْلُهُ وَالوَاضِعْ"
        )
        matcher = SequentialMatnMatcher(matn_source)
        catalog = RuleCatalog.load()
        markdown = (
            "<!-- fallback -->\n"
            "**(ده كلام عامي خالص مش كدا؟)**\n\n"
            "**((ان مبادئ كل علم عشره))**\n\n"
            "**(سقط من المطبوعة لكنه فصيح)**\n\n"
            "شرح بين الأبيات فيه **((ونسبه وفضله والواضع))** وفيه **(ده كلام عامي جوه السطر مش كدا؟)**."
        )

        interleaved = interleave_matn_segments(markdown, matcher, catalog=catalog)
        # Isolated colloquial fallback fails Conservative Doubt -> unbolded
        self.assertIn("(ده كلام عامي خالص مش كدا؟)", interleaved)
        self.assertNotIn("**(ده كلام عامي خالص مش كدا؟)**", interleaved)
        # Primary matches receive full canonical tashkeel and strip outer extra parens
        self.assertIn("**(إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ)**", interleaved)
        self.assertIn("**(وَنِسْبَةٌ وَفَضْلُهُ وَالوَاضِعْ)**", interleaved)
        # Sandwiched classical fallback between two primary matches stays bolded with fallback comment
        self.assertIn("<!-- fallback -->\n**(سقط من المطبوعة لكنه فصيح)**", interleaved)
        # Inline colloquial fallback after last primary is unbolded
        self.assertIn("(ده كلام عامي جوه السطر مش كدا؟)", interleaved)
        self.assertNotIn("**(ده كلام عامي جوه السطر مش كدا؟)**", interleaved)

    def test_verify_isolated_segment_strips_tashkeel_and_preserves_source_anchored_compound(self):
        catalog = RuleCatalog.load()
        self.assertFalse(verify_isolated_segment("دَهْ كَلَام مِشْ كِدَا", catalog=catalog))

        # Compound Sharh-Matn anchored in source remains bolded even with colloquial Sharh prefix
        matn_source = "بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ"
        matcher = SequentialMatnMatcher(matn_source)
        interleaved = interleave_matn_segments(
            "**الشرح ده في قوله: بسم الله الرحمن الرحيم**",
            matcher,
            catalog=catalog,
        )
        self.assertIn("**(الشرح ده في قوله: بِسْمِ اللَّهِ الرَّحْمَنِ الرَّحِيمِ)**", interleaved)

    def test_orchestrator_separates_prepare_emit_and_explicit_archive_phases(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            _, _, matn_dir, raw_dir, ws = self._build_temp_workspace(tmpdir)

            matn_file = matn_dir / "2026-10-22__رياض.md"
            matn_file.write_text("بَابُ الْإِخْلَاصِ", encoding="utf-8")
            raw_file = raw_dir / "2026-10-22__رياض.md"
            raw_text = (
                "2026-10-22 رياض.mp3\nSource guide\n\n"
                "**`(باب الإخلاص)`**\n\n"
                "**(سقط من المطبوعة)**\n\n"
                "المبلغ 5000 جنيه ولفظ `مقحم`، والحمد لله."
            )
            raw_file.write_text(raw_text, encoding="utf-8")
            chunk_dir = raw_dir / "2026-10-22__رياض.md_مقاطع"
            chunk_dir.mkdir()
            (chunk_dir / "part1.txt").write_text("chunk", encoding="utf-8")

            orchestrator = PublicationOrchestrator(workspace=ws)

            prepared = orchestrator.prepare_transcript(raw_text, original_md_path=raw_file)
            self.assertNotIn("Source guide", prepared.clean_markdown)
            self.assertNotIn("`", prepared.clean_markdown)
            self.assertTrue(
                prepared.clean_markdown.startswith("بسم الله الرحمن الرحيم\nالمادة: رياض الصالحين\n2026-10-22")
            )
            self.assertIn("بَابُ الْإِخْلَاصِ", prepared.clean_markdown)
            self.assertIn("5 آلاف", prepared.clean_markdown)
            self.assertTrue(matn_file.exists())
            self.assertTrue(raw_file.exists())

            rendered = orchestrator.emit_deliverables(prepared)
            self.assertTrue(rendered.onedrive_file.exists())
            self.assertTrue(rendered.project_file.exists())
            ai_text = rendered.project_file.read_text(encoding="utf-8")
            self.assertIn("<!-- fallback -->", ai_text)
            self.assertIn("### تقرير المتن الهجين (Dynamic Fallback Interleaving Summary)", ai_text)
            self.assertNotIn("`", ai_text)

            docx_text = extract_text(rendered.onedrive_file)
            self.assertNotIn("<!-- fallback -->", docx_text)
            self.assertNotIn("### تقرير المتن الهجين", docx_text)
            inspected = inspect_docx(rendered.onedrive_file)
            self.assertEqual(inspected.paragraphs[0].text, "بسم الله الرحمن الرحيم")
            self.assertEqual(inspected.paragraphs[1].text, "المادة: رياض الصالحين")

            # Emission alone must NOT move or delete input files
            self.assertTrue(matn_file.exists())
            self.assertTrue(raw_file.exists())
            self.assertTrue(chunk_dir.exists())

            # Collision-safe #AI and #AI (1) naming vs in-place overwrite
            second = orchestrator.emit_deliverables(prepared, overwrite=False)
            self.assertEqual(second.onedrive_file.name, "2026-10-22 #AI.docx")
            third = orchestrator.emit_deliverables(prepared, overwrite=False)
            self.assertEqual(third.onedrive_file.name, "2026-10-22 #AI (1).docx")
            replaced = orchestrator.emit_deliverables(prepared, overwrite=True)
            self.assertEqual(replaced.onedrive_file.name, "2026-10-22.docx")

            # Explicit archive step moves inputs to processed/ and deletes chunks
            archived = orchestrator.archive_inputs(prepared.identity)
            self.assertEqual(len(archived["matn_files"]), 1)
            self.assertEqual(len(archived["raw_files"]), 1)
            self.assertFalse(matn_file.exists())
            self.assertFalse(raw_file.exists())
            self.assertFalse(chunk_dir.exists())
            self.assertTrue((matn_dir / "processed" / "2026-10-22__رياض.md").exists())
            self.assertTrue((raw_dir / "processed" / "2026-10-22__رياض.md").exists())

    def test_orchestrator_publish_supports_deferred_archiving_explicit_inputs_and_error_safety(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, onedrive, matn_dir, raw_dir, ws = self._build_temp_workspace(
                tmpdir,
                folder_name="المنطق",
            )
            raw_file = raw_dir / "2026-10-17__منطق.md"
            raw_text = "بسم الله الرحمن الرحيم\nالمادة: المنطق (السلم المنورق)\n2026-10-17\n\nالحمد لله."
            raw_file.write_text(raw_text, encoding="utf-8")

            custom_matn = Path(tmpdir) / "external_matn.md"
            custom_matn.write_text("إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ", encoding="utf-8")

            orchestrator = PublicationOrchestrator(workspace=ws)
            res = orchestrator.publish(
                "2026-10-17 منطق.mp3\n\n**(ان مبادئ كل علم عشره)**",
                original_md_path=raw_file,
                matn_source_path=custom_matn,
                identity=LectureIdentity(date="2026-10-18", keyword="منطق"),
                archive=False,
            )
            self.assertIsNone(res["archived"])
            self.assertTrue(raw_file.exists())
            self.assertEqual(res["onedrive_file"].name, "2026-10-18.docx")
            self.assertIn("إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ", res["project_file"].read_text(encoding="utf-8"))

            # Corrupt template aborts before archiving inputs
            corrupt_template = root / "corrupt_template.docx"
            corrupt_template.write_text("not a zip", encoding="utf-8")
            broken_ws = WorkspaceConfig.resolve(
                project_root=root,
                onedrive_base=onedrive,
                word_base_template=corrupt_template,
                env={},
            )
            broken_orchestrator = PublicationOrchestrator(workspace=broken_ws)
            with self.assertRaises(DocxArchiveError):
                broken_orchestrator.publish(raw_text, original_md_path=raw_file, archive=True)
            self.assertTrue(raw_file.exists())
            self.assertFalse((matn_dir / "processed").exists())

    def test_export_documents_and_cli_support_numeric_lecture_date_and_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, onedrive, _, raw_dir, _ = self._build_temp_workspace(
                tmpdir,
                folder_name="2. فقه البيوع",
            )
            raw_file = raw_dir / "sample.md"
            raw_file.write_text("الحمد لله رب العالمين.", encoding="utf-8")

            res = export_documents(
                "الحمد لله رب العالمين.",
                original_md_path=raw_file,
                keyword="بيوع",
                date="17",
                base_onedrive=onedrive,
                project_root=root,
            )
            self.assertEqual(res["onedrive_file"].name, "17-فقه_البيوع_سعد_الخثلان_17.docx")
            self.assertEqual(inspect_docx(res["onedrive_file"]).paragraphs[2].text, "المحاضرة: 17")

            missing_rc = export_main([str(Path(tmpdir) / "does_not_exist.md")])
            self.assertEqual(missing_rc, 1)

            cli_md = Path(tmpdir) / "2026-10-25__بيوع.md"
            cli_md.write_text("بسم الله الرحمن الرحيم\nالمادة: فقه البيوع (سعد الخثلان)\n2026-10-25\n\nالحمد لله.", encoding="utf-8")
            ws_env = WorkspaceConfig.resolve(project_root=root, onedrive_base=onedrive, env={})
            first_out = PublicationOrchestrator(workspace=ws_env).publish(
                cli_md.read_text(encoding="utf-8"),
                original_md_path=cli_md,
                archive=False,
            )
            self.assertEqual(first_out["onedrive_file"].name, "2026-10-25.docx")
            self.assertTrue(first_out["onedrive_file"].exists())
            reexport_same = PublicationOrchestrator(workspace=ws_env).publish(
                "بسم الله الرحمن الرحيم\nالمادة: فقه البيوع (سعد الخثلان)\n2026-10-25\n\nمعدل.",
                overwrite=True,
                archive=False,
            )
            self.assertEqual(reexport_same["onedrive_file"].name, "2026-10-25.docx")
            self.assertIn("معدل", extract_text(reexport_same["onedrive_file"]))


class TestLectureIdentity(unittest.TestCase):
    def test_lecture_identity_is_frozen_and_drops_dict_emulation(self):
        from collections.abc import Mapping
        from dataclasses import FrozenInstanceError

        ident = LectureIdentity(
            date="2026-10-09",
            lecture_number="17",
            keyword="بيوع",
            subject_name="فقه البيوع (سعد الخثلان)",
            audio_file="17-فقه_البيوع_17.mp3",
            stem="17-فقه_البيوع_17",
        )
        # Attribute access
        self.assertEqual(ident.date, "2026-10-09")
        self.assertEqual(ident.lecture_number, "17")
        self.assertEqual(ident.keyword, "بيوع")
        self.assertEqual(ident.subject_name, "فقه البيوع (سعد الخثلان)")
        self.assertEqual(ident.audio_file, "17-فقه_البيوع_17.mp3")
        self.assertEqual(ident.stem, "17-فقه_البيوع_17")

        # Strict immutability forbids in-place attribute mutation
        with self.assertRaises(FrozenInstanceError):
            ident.date = "2026-10-10"  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            ident.keyword = "فقه_البيوع"  # type: ignore[misc]

        # Dictionary-emulation methods and protocol are completely absent
        self.assertNotIsInstance(ident, Mapping)
        for attr in ("__getitem__", "__setitem__", "__contains__", "get", "items", "keys", "values"):
            self.assertFalse(hasattr(ident, attr), f"Dict shim {attr} must be removed")
        with self.assertRaises(TypeError):
            _ = ident["date"]  # type: ignore[index]

    def test_lecture_identity_header_line_3(self):
        # 1. Date precedence
        ident_date = LectureIdentity(date="2026-09-18", lecture_number="5")
        self.assertEqual(ident_date.header_line_3, "2026-09-18")

        # 2. Numbered lecture without date
        ident_num = LectureIdentity(lecture_number="17")
        self.assertEqual(ident_num.header_line_3, "المحاضرة: 17")

        # 3. Fallback when neither is present
        ident_none = LectureIdentity()
        self.assertEqual(ident_none.header_line_3, "تاريخ_غير_محدد")

    def test_lecture_identity_header_lines_renders_canonical_triple(self):
        ident = LectureIdentity(lecture_number="17", subject_name="فقه البيوع (سعد الخثلان)")
        self.assertEqual(
            ident.header_lines,
            (
                "بسم الله الرحمن الرحيم",
                "المادة: فقه البيوع (سعد الخثلان)",
                "المحاضرة: 17",
            ),
        )

    def test_lecture_identity_resolved_stem(self):
        # 1. Explicit stem
        ident1 = LectureIdentity(stem="custom-stem_01")
        self.assertEqual(ident1.resolved_stem, "custom-stem_01")

        # 2. Numbered lecture stem derivation
        ident2 = LectureIdentity(lecture_number="17", subject_name="فقه البيوع (سعد الخثلان)")
        self.assertEqual(ident2.resolved_stem, "17-فقه_البيوع_سعد_الخثلان_17")

        # 3. Date fallback
        ident3 = LectureIdentity(date="2026-10-01")
        self.assertEqual(ident3.resolved_stem, "2026-10-01")

    def test_lecture_identity_merge(self):
        base = LectureIdentity(date="2026-10-09")
        other = LectureIdentity(keyword="بيوع", subject_name="فقه البيوع (سعد الخثلان)")
        merged = base.merge(other)
        self.assertEqual(merged.date, "2026-10-09")
        self.assertEqual(merged.keyword, "بيوع")
        self.assertEqual(merged.subject_name, "فقه البيوع (سعد الخثلان)")

    def test_lecture_identity_merge_override_precedence(self):
        # Explicit override in 'other' must supersede non-empty value in 'base'
        base = LectureIdentity(lecture_number="1", subject_name="سيرة قديمة")
        override = LectureIdentity(lecture_number="2", subject_name="سيرة (الرحيق المختوم)")
        merged = base.merge(override)
        self.assertEqual(merged.lecture_number, "2")  # overridden
        self.assertEqual(merged.subject_name, "سيرة (الرحيق المختوم)")  # overridden

        # Non-destructive merge preserves unspecified fields from base
        base_date = LectureIdentity(date="2026-10-09", subject_name="سيرة قديمة")
        merged_num = base_date.merge(override)
        self.assertEqual(merged_num.lecture_number, "2")
        self.assertEqual(merged_num.date, "2026-10-09")

        # Document resolution prioritizes explicit numbered lecture override over parsed date
        # without mutating base_date or override
        routing_map = RuleCatalog.load().routing_map
        path_num = LectureIdentity.from_filename("17-فقه_البيوع_17.md", routing_map=routing_map)
        resolved_from_path = resolve_document_identity(
            "بسم الله الرحمن الرحيم\n2026-10-09",
            path_identity=path_num,
            routing_map=routing_map,
        )
        self.assertEqual(resolved_from_path.lecture_number, "17")
        self.assertIsNone(resolved_from_path.date)
        self.assertEqual(resolved_from_path.subject_name, "فقه البيوع (سعد الخثلان)")

        resolved = resolve_document_identity(
            "بسم الله الرحمن الرحيم\n2026-10-09",
            override,
            path_identity=path_num,
            routing_map=routing_map,
        )
        self.assertEqual(resolved.lecture_number, "2")
        self.assertIsNone(resolved.date)
        self.assertIsNone(resolved.stem)
        self.assertEqual(resolved.resolved_stem, "2-سيرة_الرحيق_المختوم_2")
        self.assertEqual(resolved.subject_name, "سيرة (الرحيق المختوم)")
        self.assertEqual(base_date.date, "2026-10-09")
        self.assertIsNone(override.date)

        # Higher-precedence override must clear stale stem parsed from path_identity too
        path_date_stem = LectureIdentity.from_filename("2026-01-01_قديم.md", routing_map=routing_map)
        override_num = LectureIdentity(lecture_number="5", subject_name="فقه جديد")
        resolved_num = resolve_document_identity(
            "بسم الله الرحمن الرحيم\nالمادة: قديم\n2026-01-01",
            override_num,
            path_identity=path_date_stem,
            routing_map=routing_map,
        )
        self.assertIsNone(resolved_num.date)
        self.assertIsNone(resolved_num.stem)
        self.assertEqual(resolved_num.resolved_stem, "5-فقه_جديد_5")

    def test_lecture_identity_matching_date_and_numbered(self):
        # Date match
        ident_date = LectureIdentity(date="2026-09-24", keyword="رياض")
        self.assertTrue(ident_date.matches("2026-09-24__رياض.md"))
        self.assertFalse(ident_date.matches("2026-09-25__رياض.md"))

        # Mirrored numbered match with keyword
        ident_num = LectureIdentity(lecture_number="17", keyword="بيوع")
        self.assertTrue(ident_num.matches("17-فقه_البيوع_17.md"))
        self.assertTrue(ident_num.matches("17-بيوع-17.docx"))
        self.assertFalse(ident_num.matches("18-فقه_البيوع_18.md"))

    def test_lecture_identity_matching_with_subject_name_only(self):
        # Identity instantiated with only subject_name derives direct tokens; catalog routing_map enables aliases
        routing_map = RuleCatalog.load().routing_map
        ident_subj = LectureIdentity(lecture_number="17", subject_name="فقه البيوع (سعد الخثلان)")
        self.assertTrue(ident_subj.matches("17-فقه_البيوع_17.md"))
        self.assertTrue(ident_subj.matches("17-بيوع-17.docx", routing_map=routing_map))
        self.assertFalse(ident_subj.matches("18-فقه_البيوع_18.md"))
        self.assertFalse(ident_subj.matches("17-رياض-17.md"))



class TestCanonicalRoutingSSOT(unittest.TestCase):
    def test_canonical_routing_loads_from_context_md(self):
        catalog = RuleCatalog.load()
        self.assertGreater(len(catalog.routing_map), 30)
        # Verify core subjects are mapped dynamically from CONTEXT.md
        self.assertEqual(catalog.routing_map.get("بيوع"), "فقه البيوع (سعد الخثلان)")
        self.assertEqual(catalog.routing_map.get("خثلان"), "فقه البيوع (سعد الخثلان)")
        self.assertEqual(catalog.routing_map.get("فقه_البيوع"), "فقه البيوع (سعد الخثلان)")
        self.assertEqual(catalog.routing_map.get("سيرة"), "سيرة (الرحيق المختوم)")
        self.assertEqual(catalog.routing_map.get("رحيق"), "سيرة (الرحيق المختوم)")
        self.assertEqual(catalog.routing_map.get("منطق"), "المنطق (السلم المنورق)")
        self.assertEqual(catalog.routing_map.get("سلم"), "المنطق (السلم المنورق)")
        self.assertEqual(catalog.routing_map.get("زاد"), "زاد المعاد")

    def test_load_canonical_routing_from_custom_table(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_context = Path(tmp_dir) / "CONTEXT.md"
            custom_context.write_text(
                "## 3. توجيه المتون (Routing Map)\n\n"
                "| الكلمة الدلالية | المادة المعتمدة | المتن ومصدره |\n"
                "| --- | --- | --- |\n"
                "| `(عقيدة)` / `(واسطية)` | **العقيدة الواسطية** | الواسطية لشيخ الإسلام |\n",
                encoding="utf-8"
            )
            catalog = RuleCatalog.load(context_path=custom_context)
            self.assertEqual(catalog.routing_map.get("عقيدة"), "العقيدة الواسطية")
            self.assertEqual(catalog.routing_map.get("واسطية"), "العقيدة الواسطية")
            self.assertEqual(catalog.routing_map.get("العقيدة"), "العقيدة الواسطية")
            self.assertEqual(catalog.routing_map.get("الواسطية"), "العقيدة الواسطية")

    def test_load_canonical_routing_with_swapped_columns(self):
        # Table where subject column comes first, keywords second
        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_context = Path(tmp_dir) / "CONTEXT.md"
            custom_context.write_text(
                "## 3. توجيه المتون (Routing Map)\n\n"
                "| المادة المعتمدة | الكلمة الدلالية |\n"
                "| --- | --- |\n"
                "| **أصول الفقه** | `(أصول)` / `(ورقات)` |\n",
                encoding="utf-8"
            )
            catalog = RuleCatalog.load(context_path=custom_context)
            self.assertEqual(catalog.routing_map.get("أصول"), "أصول الفقه")
            self.assertEqual(catalog.routing_map.get("ورقات"), "أصول الفقه")
            self.assertEqual(catalog.routing_map.get("أصول الفقه"), "أصول الفقه")

    def test_export_documents_uses_injected_workspace_and_custom_catalog(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "repo"
            onedrive = Path(tmp_dir) / "onedrive"
            root.mkdir()
            (onedrive / "العقيدة الواسطية").mkdir(parents=True)
            (root / "01_Matn_Sources").mkdir(parents=True)
            (root / "01_Matn_Sources" / "2026-11-01__واسطية.md").write_text(
                "الْحَمْدُ لِلَّهِ الَّذِي أَرْسَلَ رَسُولَهُ",
                encoding="utf-8",
            )
            custom_context = root / "CONTEXT.md"
            custom_context.write_text(
                "## 3. توجيه المتون (Routing Map)\n\n"
                "| الكلمة الدلالية | المادة المعتمدة | المتن ومصدره |\n"
                "| --- | --- | --- |\n"
                "| `(عقيدة)` / `(واسطية)` | **العقيدة الواسطية** | الواسطية |\n",
                encoding="utf-8",
            )
            custom_dialect = root / "dialect-rules.md"
            custom_dialect.write_text(
                "## Attendee Anonymization (فلان)\n"
                "- **Preserved Titles & Kunyas**: أخوكم فلان، أبو فلان، الشيخ فلان.\n"
                "- **Preserved Non-Attendee Names**: (زيد).\n"
                "## Colloquial Lexicon & Verbal Markers\n- **عامية_مخصصة**\n",
                encoding="utf-8",
            )
            ws = WorkspaceConfig.resolve(
                project_root=root,
                onedrive_base=onedrive,
                context_path=custom_context,
                dialect_rules_path=custom_dialect,
                env={},
            )
            res = export_documents(
                "2026-11-01 واسطية.mp3\n\nالحمد لله رب العالمين.\n\n**(كلام فيه عامية_مخصصة جدا)**",
                workspace=ws,
            )
            self.assertEqual(res["onedrive_file"].parent, onedrive / "العقيدة الواسطية")
            doc = docx.Document(str(res["onedrive_file"]))
            self.assertEqual(doc.paragraphs[1].text.strip(), "المادة: العقيدة الواسطية")
            ai_out = res["project_file"].read_text(encoding="utf-8")
            self.assertIn("(كلام فيه عامية_مخصصة جدا)", ai_out)
            self.assertNotIn("**(كلام فيه عامية_مخصصة جدا)**", ai_out)
            self.assertNotIn("<!-- fallback -->", extract_text(res["onedrive_file"]))


class TestLoadDialectMarkers(unittest.TestCase):
    def test_load_from_default_dialect_rules_ssot(self):
        """Verify RuleCatalog loads the 7 colloquial markers from dialect-rules.md SSOT."""
        catalog = RuleCatalog.load()
        seven_markers = {"بتوع", "الفلوس", "اتسرق", "اتسرقت", "اتكسر", "اتعمل", "هشتري"}
        for marker in seven_markers:
            self.assertIn(marker, catalog.dialect_markers)
        self.assertIn("ملوش", catalog.dialect_markers)

    def test_load_dialect_markers_custom_path(self):
        """Verify custom markdown dialect rules can be loaded dynamically."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_rules = Path(tmp_dir) / "dialect-rules.md"
            custom_rules.write_text(
                "## Attendee Anonymization (فلان)\n"
                "- **Preserved Titles & Kunyas**: أخوكم فلان، أبو فلان، الشيخ فلان.\n"
                "- **Preserved Non-Attendee Names**: (زيد).\n"
                "## Colloquial Lexicon & Verbal Markers\n\n"
                "- **علامة_جديدة**، **لفظ_عامي**\n",
                encoding="utf-8",
            )
            catalog = RuleCatalog.load(dialect_rules_path=custom_rules)
            self.assertIn("علامة_جديدة", catalog.dialect_markers)
            self.assertIn("لفظ_عامي", catalog.dialect_markers)

    def test_load_dialect_markers_fallback_missing_file(self):
        """Verify fallback to base markers and D6 warning when rules file does not exist."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_rules = Path(tmp_dir) / "non_existent_dialect_rules.md"
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                catalog = RuleCatalog.load(dialect_rules_path=missing_rules)
            self.assertTrue(any(issubclass(w.category, UserWarning) for w in caught))
            self.assertIn("كدا", catalog.dialect_markers)
            self.assertIn("مش", catalog.dialect_markers)
            self.assertIsInstance(catalog.dialect_markers, frozenset)



if __name__ == "__main__":
    unittest.main()
