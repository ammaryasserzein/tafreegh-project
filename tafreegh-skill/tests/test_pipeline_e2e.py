import sys
import unittest
import tempfile
import shutil
from pathlib import Path
import docx
from docx.oxml.ns import qn

# Ensure UTF-8 output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from export_docx import (
    export_documents,
    find_matching_matn_source,
    interleave_matn_segments,
    verify_isolated_segment,
)


class TestPipelineE2E(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_root = Path(self.temp_dir.name) / "project"
        self.onedrive_root = Path(self.temp_dir.name) / "onedrive"

        self.matn_dir = self.project_root / "01_Matn_Sources"
        self.raw_dir = self.project_root / "02_Raw_Inputs"
        self.ai_output_dir = self.project_root / "03_AI_Outputs"

        self.matn_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.ai_output_dir.mkdir(parents=True, exist_ok=True)
        self.onedrive_root.mkdir(parents=True, exist_ok=True)

        # Mock OneDrive category folder
        self.riyadh_folder = self.onedrive_root / "1. رياض الصالحين"
        self.riyadh_folder.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_pipeline_e2e_hybrid_matn_and_atomic_archiving(self):
        date = "2026-09-24"
        keyword = "رياض"

        # 1. Canonical Matn source with full tashkeel (missing intermediate segment)
        matn_content = (
            "عَنْ عَبْدِ اللَّهِ بْنِ عَمْرِو بْنِ الْعَاصِ رَضِيَ اللَّهُ عَنْهُمَا: "
            "أَنَّ النَّبِيَّ صَلَّى اللَّهُ عَلَيْهِ وَسَلَّمَ تَلا قَوْلَ اللَّهِ عَزَّ وَجَلَّ فِي إِبْرَاهِيمَ ... "
            "فَرَفَعَ يَدَيْهِ وَقَالَ: «اللَّهُمَّ أُمَّتِي أُمَّتِي»، وَبَكَى صَلَّى اللَّهُ عَلَيْهِ وَسَلَّمَ."
        )
        matn_file = self.matn_dir / f"{date}__{keyword}.md"
        matn_file.write_text(matn_content, encoding="utf-8")

        # 2. Raw transcript with 3 candidate matn segments:
        # - Segment 1: Primary match
        # - Segment 2: Fallback (missing from source, sandwiched between 1 and 3)
        # - Segment 3: Primary match
        transcript_markdown = f"""بسم الله الرحمن الرحيم
المادة: رياض الصالحين
{date}

الحمد لله والصلاة والسلام على رسول الله.

**(عن عبد الله بن عمرو بن العاص رضي الله عنهما)**

سيدنا عمرو بن العاص وابنه من العبادلة العلماء.

**(ان تعذبهم فانهم عبادك وان تغفر لهم فانك انت العزيز الحكيم)**

كلام في غاية الخضوع والرجاء.

**(فرفع يديه وقال اللهم امتي امتي وبكى)**

اللهم ارحم هذه الأمة المباركة.
"""
        raw_file = self.raw_dir / f"{date}__{keyword}.md"
        raw_file.write_text(transcript_markdown, encoding="utf-8")

        # Reproducible chunk dir to verify deletion
        chunk_dir = self.raw_dir / f"{date}__{keyword}.md_مقاطع"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        (chunk_dir / "chunk_01.txt").write_text("dummy chunk content", encoding="utf-8")

        # 3. Execute export_documents
        result = export_documents(
            markdown_text=transcript_markdown,
            original_md_path=raw_file,
            keyword=keyword,
            date=date,
            base_onedrive=self.onedrive_root,
            project_root=self.project_root,
        )

        onedrive_file = result["onedrive_file"]
        project_file = result["project_file"]
        archived = result["archived"]

        # --- ASSERTION 1: Word .docx Deliverable ---
        self.assertTrue(onedrive_file.exists(), "OneDrive .docx file must exist")
        self.assertEqual(onedrive_file.parent, self.riyadh_folder)

        doc = docx.Document(str(onedrive_file))
        # Check RTL on paragraphs
        has_rtl = False
        has_bold_cs = False
        full_docx_text = []

        for p in doc.paragraphs:
            full_docx_text.append(p.text)
            pPr = p._p.get_or_add_pPr()
            if pPr.find(qn("w:bidi")) is not None:
                has_rtl = True
            p_rPr = pPr.find(qn("w:rPr"))
            if p_rPr is not None and p_rPr.find(qn("w:rtl")) is not None:
                has_rtl = True
            for r in p.runs:
                rPr = r._r.get_or_add_rPr()
                if rPr.find(qn("w:bCs")) is not None:
                    has_bold_cs = True

        self.assertTrue(has_rtl, "Paragraphs must have RTL property")
        self.assertTrue(has_bold_cs, "Matn runs must have w:bCs bold property")
        doc_text_joined = "\n".join(full_docx_text)
        self.assertNotIn("<!-- fallback -->", doc_text_joined, "Word document must NOT contain fallback comment tags")

        # --- ASSERTION 2: AI Baseline Markdown & Fallback Summary ---
        self.assertTrue(project_file.exists(), "03_AI_Outputs markdown must exist")
        ai_md = project_file.read_text(encoding="utf-8")

        # Primary matches must have vowelized canonical text
        self.assertIn("عَنْ عَبْدِ اللَّهِ بْنِ عَمْرِو بْنِ الْعَاصِ رَضِيَ اللَّهُ عَنْهُمَا", ai_md)
        self.assertIn("فَرَفَعَ يَدَيْهِ وَقَالَ: «اللَّهُمَّ أُمَّتِي أُمَّتِي»، وَبَكَى", ai_md)

        # Fallback segment must be tagged with <!-- fallback --> and unvowelized bold matn
        self.assertIn("<!-- fallback -->", ai_md)
        self.assertIn("**(ان تعذبهم فانهم عبادك وان تغفر لهم فانك انت العزيز الحكيم)**", ai_md)

        # Summary report must be appended
        self.assertIn("### تقرير المتن الهجين (Dynamic Fallback Interleaving Summary)", ai_md)
        self.assertIn("إجمالي مقاطع المتن: 3", ai_md)
        self.assertIn("مطابقة أصلية (Primary Mode): 2", ai_md)
        self.assertIn("مقاطع Fallback (بدون تشكيل): 1", ai_md)
        self.assertIn("محصور بين متنين (مخفف الشك)", ai_md)

        # --- ASSERTION 3: Atomic Archiving ---
        self.assertIsNotNone(archived)
        matn_processed = self.matn_dir / "processed" / f"{date}__{keyword}.md"
        raw_processed = self.raw_dir / "processed" / f"{date}__{keyword}.md"

        self.assertFalse(matn_file.exists(), "Original matn source must be moved out of root")
        self.assertTrue(matn_processed.exists(), "Matn source must be in processed/")
        self.assertFalse(raw_file.exists(), "Original raw transcript must be moved out of root")
        self.assertTrue(raw_processed.exists(), "Raw transcript must be in processed/")

        # --- ASSERTION 4: Deletion of Reproducible Chunks ---
        self.assertFalse(chunk_dir.exists(), "Chunk directories (_مقاطع) must be deleted")

    def test_conservative_doubt_filters_isolated_dialect_commentary(self):
        # Sandwiched segment passes relaxed doubt even without cues
        self.assertTrue(verify_isolated_segment("ان تعذبهم فانهم عبادك"))

        # Isolated segment with Egyptian colloquial dialect is rejected by strict doubt
        self.assertFalse(verify_isolated_segment("ده الكلام على المستحب مش كدا؟"))
        self.assertFalse(verify_isolated_segment("بقى كده مفيش مشكلة خالص"))


if __name__ == "__main__":
    unittest.main()
