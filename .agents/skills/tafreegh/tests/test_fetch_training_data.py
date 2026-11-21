import contextlib
import datetime
import io
import os
import tempfile
import unittest
from pathlib import Path

from tafreegh import fetch_training_data
from tafreegh.diff_inline_matn import MatnDiffCategory
from tafreegh.fetch_training_data import (
    DiffLoopAnalyzer,
    DiffLoopRunResult,
    LectureDiffAnalysis,
)
from tafreegh.lecture_identity import LectureIdentity
from tafreegh.word_gateway import create_docx
from tafreegh.workspace_catalog import WorkspaceConfig


class TestDiffLoopAnalyzer(unittest.TestCase):
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

    def test_end_to_end_extraction_and_skip_idempotence(self):
        subject_dir = self.workspace.onedrive_base / "1. الاسماء الحسنى" / "(تم التسليم)"
        os.makedirs(subject_dir)

        docx_path = subject_dir / "2026-09-18.docx"
        create_docx(
            "بسم الله الرحمن الرحيم\nالمادة: الأسماء الحسنى\n2026-09-18\n\n**(نَصُّ الْمَتْنِ)**\n\nشرح مختصر.",
            docx_path,
            workspace=self.workspace,
        )

        analyzer = DiffLoopAnalyzer(workspace=self.workspace)
        first_run = analyzer.run()

        self.assertIsInstance(first_run, DiffLoopRunResult)
        self.assertEqual(first_run.scanned_count, 1)
        self.assertEqual(len(first_run.extracted_paths), 1)
        self.assertEqual(first_run.skipped_paths, ())
        self.assertEqual(first_run.failed_paths, ())
        self.assertIsInstance(first_run.analyses[0], LectureDiffAnalysis)
        self.assertFalse(first_run.analyses[0].skipped_existing)

        expected_md_path = self.workspace.training_data_dir / "2026-09-18_الاسماء الحسنى.md"
        self.assertTrue(expected_md_path.exists(), "Markdown file was not created in 04_Training_Data")

        content = expected_md_path.read_text(encoding="utf-8")
        self.assertIn("**(نَصُّ الْمَتْنِ)**", content)
        self.assertIn("شرح مختصر.", content)
        self.assertTrue(docx_path.exists(), "Original docx should not be deleted")

        # Re-run to verify skip-existing idempotence without mocks
        expected_md_path.write_text("existing curated training data", encoding="utf-8")
        second_run = analyzer.run()
        self.assertEqual(second_run.extracted_paths, ())
        self.assertEqual(second_run.skipped_paths, (docx_path,))
        self.assertTrue(second_run.analyses[0].skipped_existing)
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

        analyzer = DiffLoopAnalyzer(workspace=self.workspace)
        result = analyzer.run()

        expected_md_path = self.workspace.training_data_dir / "17-فقه_البيوع_17.md"
        self.assertTrue(expected_md_path.exists())
        self.assertIn("طالب: صوت غير مسموع.", expected_md_path.read_text(encoding="utf-8"))

        analysis = result.analyses[0]
        self.assertEqual(analysis.ai_baseline_path, ai_baseline_path)
        ident = LectureIdentity(lecture_number="17", stem="17-فقه_البيوع_17", keyword="بيوع")
        self.assertEqual(analyzer.find_ai_baseline(ident), ai_baseline_path)

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

        analyzer = DiffLoopAnalyzer(workspace=self.workspace)
        result = analyzer.run()

        self.assertEqual(len(result.analyses), 1)
        analysis = result.analyses[0]
        self.assertEqual(analysis.identity.date, expected_date)
        self.assertEqual(analysis.ai_baseline_path, ai_baseline_path)
        self.assertEqual(len(result.consolidated_cues.inserted), 1)

        report = result.format_report()
        self.assertIn(f"from diff with {ai_baseline_path.name}", report)
        self.assertNotIn("No AI baseline", report)

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

        analyzer = DiffLoopAnalyzer(workspace=self.workspace)
        result = analyzer.run()

        corrupt_md = self.workspace.training_data_dir / "2026-09-18_الاسماء الحسنى.md"
        valid_md = self.workspace.training_data_dir / "2026-09-25_الاسماء الحسنى.md"
        self.assertFalse(corrupt_md.exists(), "Corrupt .docx must not write error text into 04_Training_Data")
        self.assertTrue(valid_md.exists(), "Valid .docx after corrupt file should still be processed")
        self.assertEqual(len(result.failed_paths), 1)
        self.assertEqual(result.failed_paths[0][0], corrupt_docx)
        self.assertIn("Failed to read", result.format_report())

    def test_unified_baseline_and_matn_source_pairing_runs_cues_and_matn_diffs(self):
        subject_dir = self.workspace.onedrive_base / "1. الأسماء الحسنى" / "(تم التسليم)"
        os.makedirs(subject_dir, exist_ok=True)
        os.makedirs(self.workspace.ai_outputs_dir, exist_ok=True)
        os.makedirs(self.workspace.matn_sources_dir, exist_ok=True)

        matn_source_path = self.workspace.matn_sources_dir / "2026-09-18_الأسماء_الحسنى.md"
        canonical_clause = "وَمَنْ يَتَّقِ اللَّهَ يَجْعَلْ لَهُ مَخْرَجًا"
        matn_source_path.write_text(
            f"الحمد لله رب العالمين.\n{canonical_clause}\nإِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ\n",
            encoding="utf-8",
        )

        ai_baseline_path = self.workspace.ai_outputs_dir / "2026-09-18_الأسماء_الحسنى_AI.md"
        ai_baseline_path.write_text(
            "بسم الله الرحمن الرحيم\n"
            "المادة: الأسماء الحسنى\n"
            "2026-09-18\n\n"
            "<!-- fallback -->\n"
            "**(ففي مسند احمد)**\n\n"
            f"**({canonical_clause})**\n\n"
            "شرح أول.\n\n"
            "سؤال عادي، نعم؟\n\n"
            "جملة زائدة، مش كدا؟\n"
            "طالب: صوت غير مسموع.\n\n"
            "فصل آخر طويل في نفس الباب.\n\n"
            "مسألة أصولية جديدة.\n\n"
            "سؤال بلاغي، ها؟\n\n"
            "### تقرير المتن الهجين (Hybrid Alignment Summary)\n\n"
            "- مقاطع بوضع Fallback: 1\n\n"
            "**تفصيل مقاطع Fallback:**\n\n"
            "- سطر 6: **(ففي مسند احمد)**\n",
            encoding="utf-8",
        )

        reviewed_docx = subject_dir / "2026-09-18.docx"
        create_docx(
            "بسم الله الرحمن الرحيم\n"
            "المادة: الأسماء الحسنى\n"
            "2026-09-18\n\n"
            "**(فَفِي مُسْنَدِ أَحْمَدَ)**\n\n"
            f"**({canonical_clause})**\n\n"
            "شرح أول.\n\n"
            "**(إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ)**\n\n"
            "**(كَلِمَتَانِ خَفِيفَتَانِ)**\n\n"
            f"**({canonical_clause})**\n\n"
            "سؤال عادي، نعم؟\n"
            "طالب: صوت غير مسموع.\n\n"
            "جملة زائدة، مش كدا؟\n\n"
            "فصل آخر طويل في نفس الباب.\n\n"
            "مسألة أصولية جديدة.\n\n"
            "سؤال بلاغي، ها؟\n"
            "طالب: صوت غير مسموع.\n",
            reviewed_docx,
            workspace=self.workspace,
        )

        analyzer = DiffLoopAnalyzer(workspace=self.workspace)
        ident = LectureIdentity(date="2026-09-18", subject_name="الأسماء الحسنى")
        self.assertEqual(analyzer.find_matn_source(ident), matn_source_path)

        result = analyzer.run()
        self.assertEqual(len(result.analyses), 1)
        analysis = result.analyses[0]
        self.assertEqual(analysis.ai_baseline_path, ai_baseline_path)
        self.assertEqual(analysis.matn_source_path, matn_source_path)

        categories = {d.category for d in analysis.matn_diffs}
        self.assertIn(MatnDiffCategory.FALLBACK_CORRECTION, categories)
        self.assertIn(MatnDiffCategory.MATN_COPY_ERROR, categories)
        self.assertIn(MatnDiffCategory.ORAL_CITATION, categories)
        self.assertIn(MatnDiffCategory.ANCHOR_EXPIRY_REREAD, categories)
        self.assertTrue(
            all("تفصيل مقاطع Fallback" not in (d.ai_text or "") for d in analysis.matn_diffs),
            "Hybrid summary footer must be stripped from AI baseline before Matn diffing",
        )

        # Genuine inserted/removed cues captured; rhetorical 'ها؟' suppressed
        self.assertEqual(len(result.consolidated_cues.inserted), 1)
        self.assertIn("نعم؟", result.consolidated_cues.inserted[0]["cue_sentence"])
        self.assertEqual(len(result.consolidated_cues.removed), 1)
        self.assertIn("مش كدا؟", result.consolidated_cues.removed[0]["cue_sentence"])

        report = result.format_report()
        self.assertIn("تقرير تصنيف فروقات المتن", report)
        self.assertIn("مرشحات تنبيهات محادثة جديدة", report)
        self.assertIn("تنبيهات محذوفة من قبل المستخدم", report)
        self.assertIn("تصحيحات Fallback", report)
        self.assertIn("أخطاء نسخ المتن الأصلي", report)

        # Thin CLI entrypoint emits the consolidated report and returns 0
        cli_docx_path = subject_dir / "2026-09-25.docx"
        create_docx(
            "بسم الله الرحمن الرحيم\nالمادة: الأسماء الحسنى\n2026-09-25\n\nالحمد لله.",
            cli_docx_path,
            workspace=self.workspace,
        )
        stdout_buf = io.StringIO()
        with contextlib.redirect_stdout(stdout_buf):
            rc = fetch_training_data.main(workspace=self.workspace)
        self.assertEqual(rc, 0)
        self.assertIn("Saved extracted text to", stdout_buf.getvalue())

    def test_pairs_docx_matn_source_and_handles_corrupt_matn_source_gracefully(self):
        subject_dir = self.workspace.onedrive_base / "1. الأسماء الحسنى" / "(تم التسليم)"
        os.makedirs(subject_dir, exist_ok=True)
        os.makedirs(self.workspace.ai_outputs_dir, exist_ok=True)
        os.makedirs(self.workspace.matn_sources_dir, exist_ok=True)

        # 1. Valid .docx canonical Matn source
        canonical_clause = "إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ"
        docx_matn = self.workspace.matn_sources_dir / "2026-09-18_الأسماء_الحسنى.docx"
        create_docx(canonical_clause, docx_matn, workspace=self.workspace)

        ai_1 = self.workspace.ai_outputs_dir / "2026-09-18_الأسماء_الحسنى_AI.md"
        ai_1.write_text("بسم الله الرحمن الرحيم\nالمادة: الأسماء الحسنى\n2026-09-18\n", encoding="utf-8")

        rev_1 = subject_dir / "2026-09-18.docx"
        create_docx(
            f"بسم الله الرحمن الرحيم\nالمادة: الأسماء الحسنى\n2026-09-18\n\n**({canonical_clause})**\n",
            rev_1,
            workspace=self.workspace,
        )

        # 2. Corrupt .docx canonical Matn source on another lecture
        corrupt_matn = self.workspace.matn_sources_dir / "2026-09-25_الأسماء_الحسنى.docx"
        corrupt_matn.write_text("not a valid zip archive", encoding="utf-8")

        ai_2 = self.workspace.ai_outputs_dir / "2026-09-25_الأسماء_الحسنى_AI.md"
        ai_2.write_text("بسم الله الرحمن الرحيم\nالمادة: الأسماء الحسنى\n2026-09-25\n\nنعم؟\n", encoding="utf-8")

        rev_2 = subject_dir / "2026-09-25.docx"
        create_docx(
            "بسم الله الرحمن الرحيم\nالمادة: الأسماء الحسنى\n2026-09-25\n\nنعم؟\nطالب: صوت غير مسموع.\n",
            rev_2,
            workspace=self.workspace,
        )

        analyzer = DiffLoopAnalyzer(workspace=self.workspace)
        result = analyzer.run()

        self.assertEqual(len(result.extracted_paths), 2)
        first, second = result.analyses
        self.assertIsNone(first.matn_source_error)
        self.assertIn(MatnDiffCategory.MATN_COPY_ERROR, {d.category for d in first.matn_diffs})

        self.assertEqual(second.matn_source_path, corrupt_matn)
        self.assertIsNotNone(second.matn_source_error)
        self.assertTrue((self.workspace.training_data_dir / "2026-09-25_الأسماء الحسنى.md").exists())
        self.assertEqual(len(result.consolidated_cues.inserted), 1)
        self.assertEqual(len(result.failed_paths), 1)
        self.assertEqual(result.failed_paths[0][0], corrupt_matn)
        self.assertIn("Warning: failed to read Matn source", result.format_report())

    def test_missing_undated_unnumbered_docx_records_read_error(self):
        subject_dir = self.workspace.onedrive_base / "1. رياض الصالحين" / "(تم التسليم)"
        os.makedirs(subject_dir, exist_ok=True)
        missing_docx = subject_dir / "notes.docx"

        analyzer = DiffLoopAnalyzer(workspace=self.workspace)
        analysis = analyzer.analyze_docx(missing_docx)

        self.assertIsNotNone(analysis.read_error)
        self.assertFalse(analysis.markdown_path.exists())


if __name__ == "__main__":
    unittest.main()
