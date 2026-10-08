import unittest
import sys
from pathlib import Path

scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from diff_inline_matn import (
    classify_matn_diffs,
    MatnDiffCategory,
    format_matn_diff_report,
)


class TestDiffInlineMatn(unittest.TestCase):
    def test_detects_fallback_correction(self):
        ai_text = """<!-- fallback -->
**(ففي مسند احمد والشافعي)**
الكفار."""
        user_text = """**(فَفِي مُسْنَدِ أَحْمَدَ وَالشَّافِعِيِّ رَضِيَ اللَّهُ عَنْهُمَا)**
الكفار."""
        matn_source = "نص مختلف تماما"

        diffs = classify_matn_diffs(ai_text, user_text, matn_source=matn_source)
        fb_diffs = [d for d in diffs if d.category == MatnDiffCategory.FALLBACK_CORRECTION]
        self.assertEqual(len(fb_diffs), 1)
        self.assertIn("أَحْمَدَ", fb_diffs[0].user_text)

    def test_detects_oral_citation_not_in_matn_source(self):
        ai_text = "وهنا قال النبي صلى الله عليه وسلم كلمتان خفيفتان على اللسان حبيبتان إلى الرحمن."
        user_text = "وهنا قال النبي صلى الله عليه وسلم **(كَلِمَتَانِ خَفِيفَتَانِ عَلَى اللِّسَانِ حَبِيبَتَانِ إِلَى الرَّحْمَنِ)**."
        matn_source = "إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ ... الحَدُّ وَالمَوْضُوعُ ثُمَّ الثَّمَرَهْ"

        diffs = classify_matn_diffs(ai_text, user_text, matn_source=matn_source)
        oral_diffs = [d for d in diffs if d.category == MatnDiffCategory.ORAL_CITATION]
        self.assertEqual(len(oral_diffs), 1)
        self.assertIn("كَلِمَتَانِ", oral_diffs[0].user_text)

    def test_detects_matn_copy_error_when_in_matn_source(self):
        ai_text = "وقرأ الشيخ: **(إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ)**"
        user_text = "وقرأ الشيخ: **(إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ ... الحَدُّ وَالمَوْضُوعُ ثُمَّ الثَّمَرَهْ)**"
        matn_source = "إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ ... الحَدُّ وَالمَوْضُوعُ ثُمَّ الثَّمَرَهْ"

        diffs = classify_matn_diffs(ai_text, user_text, matn_source=matn_source)
        copy_errors = [d for d in diffs if d.category == MatnDiffCategory.MATN_COPY_ERROR]
        self.assertEqual(len(copy_errors), 1)

    def test_format_matn_diff_report(self):
        ai_text = """<!-- fallback -->
**(ففي مسند احمد)**"""
        user_text = """**(فَفِي مُسْنَدِ أَحْمَدَ)**"""
        diffs = classify_matn_diffs(ai_text, user_text)
        report = format_matn_diff_report(diffs)
        self.assertIn("تصحيحات Fallback", report)


if __name__ == "__main__":
    unittest.main()
