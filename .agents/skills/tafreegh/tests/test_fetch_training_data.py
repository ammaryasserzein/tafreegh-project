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
            "سؤال بلاغي، ها؟\n",
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

        # Genuine cue captured; rhetorical 'ها؟' suppressed
        self.assertEqual(len(result.consolidated_cues.inserted), 1)
        self.assertIn("نعم؟", result.consolidated_cues.inserted[0]["cue_sentence"])

        report = result.format_report()
        self.assertIn("تقرير تصنيف فروقات المتن", report)
        self.assertIn("مرشحات تنبيهات محادثة جديدة", report)
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


if __name__ == "__main__":
    unittest.main()
