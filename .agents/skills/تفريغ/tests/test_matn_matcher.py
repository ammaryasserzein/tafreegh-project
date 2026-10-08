import unittest
import sys
from pathlib import Path

scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from matn_matcher import (
    SequentialMatnMatcher,
    MatchMode,
    strip_tashkeel,
    normalize_arabic_search,
    format_matn_segment,
    generate_fallback_summary,
)


class TestMatnMatcher(unittest.TestCase):
    def setUp(self):
        self.sample_source = (
            "إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ ... "
            "الحَدُّ وَالمَوْضُوعُ ثُمَّ الثَّمَرَهْ ... "
            "وَنِسْبَةٌ وَفَضْلُهُ وَالوَاضِعْ ... "
            "وَالِاسْمُ الِاسْتِمْدَادُ حُكْمُ الشَّارِعْ ... "
            "مَسَائِلُ وَالبَعْضُ بِالبَعْضِ اكْتَفَى ... "
            "وَمَنْ دَرَى الجَمِيعَ حَازَ الشَّرَفَا"
        )
        self.matcher = SequentialMatnMatcher(self.sample_source, forward_lookahead=500)

    def test_strip_tashkeel(self):
        vowelized = "إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ"
        plain = strip_tashkeel(vowelized)
        self.assertEqual(plain, "إن مبادئ كل علم عشره")

    def test_forward_search_advances_cursor(self):
        res1 = self.matcher.match_segment("ان مبادئ كل علم عشره")
        self.assertEqual(res1.mode, MatchMode.PRIMARY)
        self.assertFalse(res1.is_fallback)
        self.assertFalse(res1.is_re_read)
        self.assertIn("مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ", res1.text)
        self.assertGreater(self.matcher.cursor, 0)

        prev_cursor = self.matcher.cursor
        res2 = self.matcher.match_segment("الحد والموضوع ثم الثمره")
        self.assertEqual(res2.mode, MatchMode.PRIMARY)
        self.assertIn("الحَدُّ وَالمَوْضُوعُ ثُمَّ الثَّمَرَهْ", res2.text)
        self.assertGreater(self.matcher.cursor, prev_cursor)

    def test_lookbehind_matches_re_read_preserving_cursor(self):
        # Match segment 1 and 2
        self.matcher.match_segment("مبادئ كل علم عشره")
        self.matcher.match_segment("الحد والموضوع ثم الثمره")
        cursor_after_second = self.matcher.cursor

        # Sheikh re-reads segment 1 sentence by sentence
        res_reread = self.matcher.match_segment("مبادئ كل علم عشره")
        self.assertEqual(res_reread.mode, MatchMode.PRIMARY)
        self.assertTrue(res_reread.is_re_read)
        self.assertFalse(res_reread.is_fallback)
        self.assertEqual(self.matcher.cursor, cursor_after_second)

        # Continues forward to segment 3
        res3 = self.matcher.match_segment("ونسبه وفضله والواضع")
        self.assertEqual(res3.mode, MatchMode.PRIMARY)
        self.assertFalse(res3.is_re_read)
        self.assertGreater(self.matcher.cursor, cursor_after_second)

    def test_fallback_mode_on_unmatched_segment(self):
        # Match segment 1
        self.matcher.match_segment("مبادئ كل علم عشره")

        # Unmatched segment not in matn source
        res_fallback = self.matcher.match_segment("قال الشاعر كلاما خارج المنظومة تماما")
        self.assertEqual(res_fallback.mode, MatchMode.FALLBACK)
        self.assertTrue(res_fallback.is_fallback)
        self.assertEqual(res_fallback.start_pos, -1)

    def test_sandwiched_fallback_context(self):
        # Primary -> Fallback -> Primary
        self.matcher.match_segment("مبادئ كل علم عشره")
        self.matcher.match_segment("كلام سقط من النسخة المطبوعة")
        self.matcher.match_segment("ونسبه وفضله والواضع")

        self.matcher.resolve_sandwiched_fallbacks()
        self.assertTrue(self.matcher.history[1].is_sandwiched)

    def test_format_matn_segment_visual_distinction(self):
        res_primary = self.matcher.match_segment("مبادئ كل علم عشره")
        formatted_primary = format_matn_segment(res_primary)
        self.assertNotIn("<!-- fallback -->", formatted_primary)
        self.assertTrue(formatted_primary.startswith("**("))

        res_fallback = self.matcher.match_segment("مقطع مفقود من ملف المتن")
        formatted_fallback = format_matn_segment(res_fallback)
        self.assertIn("<!-- fallback -->", formatted_fallback)
        self.assertIn("**(مقطع مفقود من ملف المتن)**", formatted_fallback)

    def test_generate_fallback_summary(self):
        self.matcher.match_segment("مبادئ كل علم عشره")
        self.matcher.match_segment("مقطع سقط من المتن")
        self.matcher.match_segment("ونسبه وفضله والواضع")
        self.matcher.resolve_sandwiched_fallbacks()

        summary = generate_fallback_summary(self.matcher)
        self.assertIn("تقرير المتن الهجين", summary)
        self.assertIn("مقاطع Fallback", summary)
        self.assertIn("1", summary)

    def test_punctuated_matn_source_forward_match(self):
        source = (
            "إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ ... "
            "الحَدُّ، وَالمَوْضُوعُ، ثُمَّ الثَّمَرَهْ!"
        )
        matcher = SequentialMatnMatcher(source, forward_lookahead=500)
        # Spoken segment has no punctuation, but source has commas, ellipsis, exclamation
        res = matcher.match_segment("الحد والموضوع ثم الثمره")
        self.assertEqual(res.mode, MatchMode.PRIMARY)
        self.assertFalse(res.is_fallback)
        self.assertEqual(res.text, "الحَدُّ، وَالمَوْضُوعُ، ثُمَّ الثَّمَرَهْ")
        self.assertEqual(source[res.start_pos:res.end_pos], res.text)
        self.assertGreater(res.start_pos, 0)
        self.assertEqual(res.end_pos, matcher.cursor)

    def test_spoken_query_with_punctuation_matches_unpunctuated_source(self):
        source = "الحَدُّ وَالمَوْضُوعُ ثُمَّ الثَّمَرَهْ"
        matcher = SequentialMatnMatcher(source, forward_lookahead=500)
        # Spoken segment contains ASR punctuation
        res = matcher.match_segment("الحد، والموضوع! ثم الثمره.")
        self.assertEqual(res.mode, MatchMode.PRIMARY)
        self.assertEqual(res.text, "الحَدُّ وَالمَوْضُوعُ ثُمَّ الثَّمَرَهْ")
        self.assertEqual(source[res.start_pos:res.end_pos], res.text)

    def test_coordinate_accuracy_with_whitespace_and_tashkeel(self):
        source = "   \n\tالحَدُّ وَالمَوْضُوعُ... \n   "
        matcher = SequentialMatnMatcher(source, forward_lookahead=500)
        res = matcher.match_segment("الحد والموضوع")
        self.assertEqual(res.mode, MatchMode.PRIMARY)
        self.assertEqual(res.text, "الحَدُّ وَالمَوْضُوعُ")
        self.assertEqual(source[res.start_pos:res.end_pos], res.text)

    def test_sandwiched_fallback_requires_localized_window(self):
        # Primary, Fallback, Fallback, Fallback, Primary
        # Under localized window (default=1), consecutive fallbacks (>1 distance) are NOT sandwiched
        self.matcher.match_segment("مبادئ كل علم عشره")
        self.matcher.match_segment("سقط أول")
        self.matcher.match_segment("سقط ثان")
        self.matcher.match_segment("سقط ثالث")
        self.matcher.match_segment("ونسبه وفضله والواضع")

        self.matcher.resolve_sandwiched_fallbacks()
        self.assertFalse(self.matcher.history[1].is_sandwiched)
        self.assertFalse(self.matcher.history[2].is_sandwiched)
        self.assertFalse(self.matcher.history[3].is_sandwiched)

    def test_sandwiched_fallback_configurable_window(self):
        # Primary, Fallback, Fallback, Primary
        # With window_size=2, fallbacks within distance 2 are sandwiched
        self.matcher.match_segment("مبادئ كل علم عشره")
        self.matcher.match_segment("سقط أول")
        self.matcher.match_segment("سقط ثان")
        self.matcher.match_segment("ونسبه وفضله والواضع")

        self.matcher.resolve_sandwiched_fallbacks(window_size=2)
        self.assertTrue(self.matcher.history[1].is_sandwiched)
        self.assertTrue(self.matcher.history[2].is_sandwiched)


if __name__ == "__main__":
    unittest.main()
