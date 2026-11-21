import unittest

from tafreegh.diff_inline_matn import (
    MatnDiffCategory,
    classify_matn_diffs,
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
**(ففي مسند احمد)**

**(إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ)**"""
        user_text = """**(فَفِي مُسْنَدِ أَحْمَدَ)**

**(كَلِمَتَانِ خَفِيفَتَانِ)**

**(إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَةٌ)**

**(إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ)**"""
        diffs = classify_matn_diffs(
            ai_text,
            user_text,
            matn_source="إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ",
        )
        report = format_matn_diff_report(diffs)
        self.assertIn("تصحيحات Fallback (1)", report)
        self.assertIn("متون شفهية عارضة / نقولات مستقلة (1)", report)
        self.assertIn("أخطاء نسخ المتن الأصلي (1)", report)
        self.assertIn("استعادة مرساة المتن بعد تباعد الشرح (Anchor Expiry) (1)", report)
        self.assertEqual(report.count("الأصل المعالج:"), 2)

    def test_full_hadith_plus_subclauses_and_anchor_expiry_reread_avoids_false_copy_errors(self):
        self.assertEqual(MatnDiffCategory.ANCHOR_EXPIRY_REREAD.value, "anchor_expiry_reread")
        self.assertFalse(hasattr(MatnDiffCategory, "DISTANT_REREAD_REBOLD"))

        full_hadith = (
            "عَنْ ابْنِ مَسْعُودٍ رَضِيَ اللَّهُ عَنْهُ قَالَ: فَقَالَ: "
            "«أَتَرْضَوْنَ أَنْ تَكُونُوا رُبُعَ أَهْلِ الْجَنَّةِ؟» قُلْنَا: نَعَمْ"
        )
        ai_text = f"""**({full_hadith})**

شرح أول.

**(أَتَرْضَوْنَ أَنْ تَكُونُوا رُبُعَ أَهْلِ الْجَنَّةِ)**

**(قُلْنَا: نَعَمْ)**
"""
        user_text = f"""**({full_hadith})**

شرح أول.

**(أَتَرْضَوْنَ أَنْ تَكُونُوا رُبُعَ أَهْلِ الْجَنَّةِ)**

**(قُلْنَا: نَعَمْ)**

شرح طويل جدا استمر أكثر من صفحة كاملة.

**(أَتَرْضَوْنَ أَنْ تَكُونُوا رُبُعَ أَهْلِ الْجَنَّةِ)**
"""
        diffs = classify_matn_diffs(ai_text, user_text, matn_source=full_hadith)
        copy_errors = [d for d in diffs if d.category == MatnDiffCategory.MATN_COPY_ERROR]
        self.assertEqual(copy_errors, [])
        expiry_diffs = [d for d in diffs if d.category == MatnDiffCategory.ANCHOR_EXPIRY_REREAD]
        self.assertEqual(len(expiry_diffs), 1)
        self.assertEqual(expiry_diffs[0].user_text, "أَتَرْضَوْنَ أَنْ تَكُونُوا رُبُعَ أَهْلِ الْجَنَّةِ")
        report = format_matn_diff_report(diffs)
        self.assertIn("Anchor Expiry", report)

    def test_anchor_expiry_reread_with_edited_tashkeel_captures_both_diffs(self):
        ai_text = """**(إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ)**

شرح أول مستفيض للمبادئ العشرة."""
        user_text = """**(إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ)**

شرح أول مستفيض للمبادئ العشرة يستمر لصفحات.

**(إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَةٌ)**"""
        matn_source = "إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ"

        diffs = classify_matn_diffs(ai_text, user_text, matn_source=matn_source)
        copy_errors = [d for d in diffs if d.category == MatnDiffCategory.MATN_COPY_ERROR]
        expiry_diffs = [d for d in diffs if d.category == MatnDiffCategory.ANCHOR_EXPIRY_REREAD]

        self.assertEqual(len(copy_errors), 1)
        self.assertEqual(copy_errors[0].user_text, "إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَةٌ")
        self.assertEqual(copy_errors[0].ai_text, "إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ")
        self.assertEqual(len(expiry_diffs), 1)
        self.assertEqual(expiry_diffs[0].user_text, "إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَةٌ")

    def test_immediate_adjacent_duplicate_not_labeled_anchor_expiry(self):
        ai_text = """**(إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ)**"""
        user_text = """**(إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ)**
**(إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ)**"""
        matn_source = "إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ"

        diffs = classify_matn_diffs(ai_text, user_text, matn_source=matn_source)
        expiry_diffs = [d for d in diffs if d.category == MatnDiffCategory.ANCHOR_EXPIRY_REREAD]
        self.assertEqual(len(expiry_diffs), 0)

    def test_anchor_expiry_reread_in_fallback_mode_captures_fallback_correction(self):
        ai_text = """<!-- fallback -->
**(ففي مسند احمد)**

شرح مطول جدا."""
        user_text = """<!-- fallback -->
**(ففي مسند احمد)**

شرح مطول جدا يستمر طويلا.

**(فَفِي مُسْنَدِ أَحْمَدَ)**"""
        diffs = classify_matn_diffs(ai_text, user_text)
        fb_diffs = [d for d in diffs if d.category == MatnDiffCategory.FALLBACK_CORRECTION]
        expiry_diffs = [d for d in diffs if d.category == MatnDiffCategory.ANCHOR_EXPIRY_REREAD]
        self.assertEqual(len(fb_diffs), 1)
        self.assertEqual(len(expiry_diffs), 1)

    def test_compound_fallback_prefix_wrapping_primary_matn_is_fallback_correction(self):
        ai_text = "ثم قال الشاعر: **(أَأَنْثُرُ دُرًّا)**"
        user_text = "**(حدثنا أبو علي قال: أَأَنْثُرُ دُرًّا)**"
        matn_source = "أَأَنْثُرُ دُرًّا بَيْنَ سَارِحَةِ الْبَهْمِ"

        diffs = classify_matn_diffs(ai_text, user_text, matn_source=matn_source)
        fb_diffs = [d for d in diffs if d.category == MatnDiffCategory.FALLBACK_CORRECTION]
        copy_errors = [d for d in diffs if d.category == MatnDiffCategory.MATN_COPY_ERROR]

        self.assertEqual(copy_errors, [])
        self.assertEqual(len(fb_diffs), 1)
        self.assertEqual(fb_diffs[0].ai_text, "أَأَنْثُرُ دُرًّا")
        self.assertEqual(fb_diffs[0].user_text, "حدثنا أبو علي قال: أَأَنْثُرُ دُرًّا")

    def test_compound_fallback_suffix_absent_from_source_is_fallback_correction(self):
        ai_text = "**(أَأَنْثُرُ دُرًّا)**"
        user_text = "**(أَأَنْثُرُ دُرًّا أي هذا مثل مشهور)**"
        matn_source = "أَأَنْثُرُ دُرًّا بَيْنَ سَارِحَةِ الْبَهْمِ"

        diffs = classify_matn_diffs(ai_text, user_text, matn_source=matn_source)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].category, MatnDiffCategory.FALLBACK_CORRECTION)
        self.assertEqual(diffs[0].ai_text, "أَأَنْثُرُ دُرًّا")

    def test_single_word_variant_links_to_ai_text_as_matn_copy_error(self):
        ai_text = "**(وَقَدْ بَسَطَتْ لَنَا الدُّنْيَا ذِرَاعَيْهَا)**"
        user_text = "**(وَقَدْ انْبَسَطَتْ لَنَا الدُّنْيَا ذِرَاعَيْهَا)**"
        matn_source = "وَقَدْ بَسَطَتْ لَنَا الدُّنْيَا ذِرَاعَيْهَا"

        diffs = classify_matn_diffs(ai_text, user_text, matn_source=matn_source)
        oral_diffs = [d for d in diffs if d.category == MatnDiffCategory.ORAL_CITATION]
        copy_errors = [d for d in diffs if d.category == MatnDiffCategory.MATN_COPY_ERROR]

        self.assertEqual(oral_diffs, [])
        self.assertEqual(len(copy_errors), 1)
        self.assertEqual(copy_errors[0].ai_text, "وَقَدْ بَسَطَتْ لَنَا الدُّنْيَا ذِرَاعَيْهَا")
        self.assertEqual(copy_errors[0].user_text, "وَقَدْ انْبَسَطَتْ لَنَا الدُّنْيَا ذِرَاعَيْهَا")

    def test_short_single_word_variant_links_to_ai_text_as_matn_copy_error(self):
        ai_text = "**(وَلَمَّا بَسَطَتْ يَدَهَا)**"
        user_text = "**(وَلَمَّا انْبَسَطَتْ يَدَهَا)**"
        matn_source = "وَلَمَّا بَسَطَتْ يَدَهَا"

        diffs = classify_matn_diffs(ai_text, user_text, matn_source=matn_source)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].category, MatnDiffCategory.MATN_COPY_ERROR)
        self.assertEqual(diffs[0].ai_text, "وَلَمَّا بَسَطَتْ يَدَهَا")

    def test_unrelated_oral_citation_with_incidental_common_words_stays_oral_citation(self):
        ai_text = "**(في الله)**"
        user_text = "**(مَنْ كَانَ فِي حَاجَةِ أَخِيهِ كَانَ اللَّهُ فِي حَاجَتِهِ)**"
        matn_source = "متن مختلف تماما"

        diffs = classify_matn_diffs(ai_text, user_text, matn_source=matn_source)
        oral_diffs = [d for d in diffs if d.category == MatnDiffCategory.ORAL_CITATION]
        self.assertEqual(len(oral_diffs), 1)
        self.assertIsNone(oral_diffs[0].ai_text)


if __name__ == "__main__":
    unittest.main()
