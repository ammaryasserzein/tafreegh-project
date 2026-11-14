import unittest

from tafreegh.matn_matcher import (
    MatchMode,
    MatnCursorSnapshot,
    SequentialMatnMatcher,
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

    def test_fallback_mode_preserves_tashkeel_inside_inner_parenthesized_citations(self):
        seg = "مَا لَهُ أَدْرَاجٌ لِيُتَوَصَّلَ بِهِ إِلَى سَطْحٍ وَشِبْهِهِ، قَالَ تَعَالَى: (أَوْ سُلَّمًا فِي السَّمَاءِ)"
        res_fallback = self.matcher.match_segment(seg)
        self.assertEqual(res_fallback.mode, MatchMode.FALLBACK)
        self.assertEqual(
            res_fallback.text,
            "ما له أدراج ليتوصل به إلى سطح وشبهه، قال تعالى: (أَوْ سُلَّمًا فِي السَّمَاءِ)",
        )

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

    def test_sandwiched_fallback_supports_consecutive_fallbacks_gap(self):
        # Primary, Fallback, Fallback, Fallback, Primary
        # Consecutive fallbacks bounded before and after by verified primary matches are sandwiched
        self.matcher.match_segment("مبادئ كل علم عشره")
        self.matcher.match_segment("سقط أول")
        self.matcher.match_segment("سقط ثان")
        self.matcher.match_segment("سقط ثالث")
        self.matcher.match_segment("ونسبه وفضله والواضع")

        self.matcher.resolve_sandwiched_fallbacks()
        self.assertTrue(self.matcher.history[1].is_sandwiched)
        self.assertTrue(self.matcher.history[2].is_sandwiched)
        self.assertTrue(self.matcher.history[3].is_sandwiched)

    def test_isolated_fallbacks_outside_primary_bounds(self):
        # Fallback (start) -> Primary -> Fallback -> Primary -> Fallback (end)
        self.matcher.match_segment("سقط قبل البداية")
        self.matcher.match_segment("مبادئ كل علم عشره")
        self.matcher.match_segment("سقط بينهما")
        self.matcher.match_segment("ونسبه وفضله والواضع")
        self.matcher.match_segment("سقط بعد النهاية")

        self.matcher.resolve_sandwiched_fallbacks()
        self.assertFalse(self.matcher.history[0].is_sandwiched)
        self.assertTrue(self.matcher.history[2].is_sandwiched)
        self.assertFalse(self.matcher.history[4].is_sandwiched)

    def test_lookbehind_matches_most_recent_occurrence_with_rfind(self):
        source = (
            "قَالَ الْمُصَنِّفُ رَحِمَهُ اللَّهُ: "
            "إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ ... "
            "ثُمَّ قَالَ الْمُصَنِّفُ رَحِمَهُ اللَّهُ: "
            "الحَدُّ وَالمَوْضُوعُ ثُمَّ الثَّمَرَهْ"
        )
        matcher = SequentialMatnMatcher(source, forward_lookahead=1000)
        # Advance through first quote
        matcher.match_segment("قال المصنف رحمه الله")
        # Advance through first verse
        matcher.match_segment("ان مبادئ كل علم عشره")
        # Advance through second quote
        matcher.match_segment("ثم قال المصنف رحمه الله")
        # Advance through second verse
        matcher.match_segment("الحد والموضوع ثم الثمره")

        # Now re-read: "قال المصنف رحمه الله"
        res_reread = matcher.match_segment("قال المصنف رحمه الله")
        self.assertEqual(res_reread.mode, MatchMode.PRIMARY)
        self.assertTrue(res_reread.is_re_read)
        first_idx = source.find("قَالَ الْمُصَنِّفُ")
        second_idx = source.rfind("قَالَ الْمُصَنِّفُ")
        self.assertNotEqual(first_idx, second_idx)
        self.assertEqual(res_reread.start_pos, second_idx)


    def test_overlap_reread_advances_cursor(self):
        source = "النَّظَرُ فِي مُبْدَعَاتِهِ، وَمُدَاوَمَةُ التَّفَكُّرِ فِي مَصْنُوعَاتِهِ"
        matcher = SequentialMatnMatcher(source, forward_lookahead=500)
        # Advance through first part
        r1 = matcher.match_segment("النظر في مبدعاته")
        self.assertEqual(r1.mode, MatchMode.PRIMARY)
        self.assertFalse(r1.is_re_read)
        cursor1 = matcher.cursor

        # Re-read leading part while extending into new text
        r2 = matcher.match_segment("النظر في مبدعاته ومداومة التفكر في مصنوعاته")
        self.assertEqual(r2.mode, MatchMode.PRIMARY)
        self.assertFalse(r2.is_re_read)
        self.assertGreater(matcher.cursor, cursor1)
        self.assertIn("وَمُدَاوَمَةُ التَّفَكُّرِ فِي مَصْنُوعَاتِهِ", r2.text)

    def test_compound_sharh_prefix_with_primary_matn_tail_aligns_tail_and_advances_cursor(self):
        source = (
            "فَقُلْنَا: اللَّهُ أَكْبَرُ! "
            "وَذَلِكَ أَنَّكُمْ فِي أَهْلِ الشِّرْكِ كَالشَّعْرَةِ الْبَيْضَاءِ"
        )
        matcher = SequentialMatnMatcher(source, forward_lookahead=500)
        matcher.match_segment("فقلنا الله اكبر")
        cursor_before = matcher.cursor

        res = matcher.match_segment("ثُمَّ بَيَّنَ وَجْهَ ذَلِكَ بِقَوْلِهِ، وذلك")
        self.assertEqual(res.mode, MatchMode.FALLBACK)
        self.assertTrue(res.is_fallback)
        self.assertEqual(res.text, "ثم بين وجه ذلك بقوله، وَذَلِكَ")
        self.assertGreater(matcher.cursor, cursor_before)

    def test_compound_sharh_single_word_tail_ignores_distant_occurrence_beyond_cursor_window(self):
        filler = " ".join(["كَلِمَةٌ"] * 35)
        source = f"بِدَايَةُ الْمَتْنِ {filler} وَذَلِكَ نِهَايَةُ الْمَتْنِ"
        matcher = SequentialMatnMatcher(source, forward_lookahead=1000)
        matcher.match_segment("بداية المتن")
        cursor_before = matcher.cursor

        res = matcher.match_segment("ثم أشار الشارح بقوله، وذلك")
        self.assertEqual(res.mode, MatchMode.FALLBACK)
        self.assertEqual(res.text, "ثم أشار الشارح بقوله، وذلك")
        self.assertEqual(matcher.cursor, cursor_before)

    def test_compound_sharh_matn_acts_as_source_anchored_bound_for_sandwiched_fallbacks(self):
        source = (
            "فَقُلْنَا: اللَّهُ أَكْبَرُ! "
            "وَذَلِكَ أَنَّكُمْ فِي أَهْلِ الشِّرْكِ كَالشَّعْرَةِ الْبَيْضَاءِ"
        )
        matcher = SequentialMatnMatcher(source, forward_lookahead=500)
        comp = matcher.match_segment("ثم بين وجه ذلك بقوله، وذلك")
        pure_fb = matcher.match_segment("عبارة شرح غير موجودة في المتن")
        prim = matcher.match_segment("انكم في اهل الشرك كالشعره البيضاء")

        matcher.resolve_sandwiched_fallbacks()
        self.assertTrue(comp.is_source_anchored)
        self.assertFalse(comp.is_sandwiched)
        self.assertTrue(pure_fb.is_sandwiched)
        self.assertFalse(prim.is_sandwiched)

    def test_compound_sharh_single_word_tail_matches_at_active_reread_position_after_full_hadith_read(self):
        source = (
            "عَنْ ابْنِ مَسْعُودٍ قَالَ: إِنِّي لَأَرْجُو أَنْ تَكُونُوا نِصْفَ أَهْلِ الْجَنَّةِ، "
            "وَذَلِكَ أَنَّ الْجَنَّةَ لَا يَدْخُلُهَا إِلَّا نَفْسٌ مُسْلِمَةٌ"
        )
        matcher = SequentialMatnMatcher(source, forward_lookahead=500)
        # 1. Sheikh reads the entire Hadith upfront (cursor reaches end of source)
        full = matcher.match_segment(
            "عن ابن مسعود قال اني لارجو ان تكونوا نصف اهل الجنه وذلك ان الجنه لا يدخلها الا نفس مسلمه"
        )
        self.assertEqual(full.mode, MatchMode.PRIMARY)
        self.assertEqual(matcher.cursor, len(source))

        # 2. Sheikh re-reads clause before 'وَذَلِكَ' during commentary
        reread = matcher.match_segment("اني لارجو ان تكونوا نصف اهل الجنه")
        self.assertTrue(reread.is_re_read)

        # 3. Commentary introduces next single-word lemma 'وَذَلِكَ' right after active re-read clause
        comp = matcher.match_segment("ثم بين وجه ذلك بقوله، وذلك")
        self.assertTrue(comp.is_source_anchored)
        self.assertEqual(comp.text, "ثم بين وجه ذلك بقوله، وَذَلِكَ")


    def test_sequential_matn_matcher_does_not_expose_verify_exported_segment(self):
        """SequentialMatnMatcher is a generation pipeline engine; validation heuristics belong in verify_docx (CODING_STANDARDS § 6)."""
        self.assertFalse(hasattr(self.matcher, "verify_exported_segment"))
        self.assertFalse(hasattr(SequentialMatnMatcher, "verify_exported_segment"))

    def test_encapsulates_internal_buffers_and_exposes_read_only_cursor_and_snapshot(self):
        self.assertFalse(hasattr(self.matcher, "norm_source"))
        self.assertFalse(hasattr(self.matcher, "pos_map"))

        snap_init = self.matcher.snapshot()
        self.assertEqual(snap_init, MatnCursorSnapshot(cursor=0, cursor_norm=0, history_length=0))

        with self.assertRaises(AttributeError):
            self.matcher.cursor = 10  # type: ignore[misc]
        with self.assertRaises(AttributeError):
            self.matcher.cursor_norm = 10  # type: ignore[misc]

        res = self.matcher.match_segment("ان مبادئ كل علم عشره")
        snap_after = self.matcher.snapshot()
        self.assertEqual(snap_after.cursor, self.matcher.cursor)
        self.assertEqual(snap_after.cursor_norm, self.matcher.cursor_norm)
        self.assertEqual(snap_after.history_length, 1)
        self.assertEqual(
            self.matcher.source_window(res.start_pos, res.end_pos),
            self.sample_source[max(0, res.start_pos - 4) : min(len(self.sample_source), res.end_pos + 4)],
        )

    def test_contains_and_advance_to_canonical_occurrence_domain_methods(self):
        filler = " ".join(["كَلِمَةٌ"] * 250)
        long_source = f"إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ {filler} وَمَنْ دَرَى الجَمِيعَ حَازَ الشَّرَفَا"
        matcher = SequentialMatnMatcher(long_source, forward_lookahead=50)
        matcher.match_segment("ان مبادئ كل علم عشره")
        cursor_before = matcher.cursor

        self.assertTrue(matcher.contains_verbatim("وَمَنْ دَرَى الجَمِيعَ حَازَ الشَّرَفَا"))
        self.assertFalse(matcher.contains_verbatim("ومن درى الجميع حاز الشرفا"))
        self.assertTrue(matcher.contains_normalized("ومن درى الجميع حاز الشرفا"))
        self.assertFalse(matcher.contains_normalized("نص غير موجود اطلاقا"))

        self.assertFalse(matcher.advance_to_canonical_occurrence("ومن درى الجميع حاز الشرفا"))
        self.assertEqual(matcher.cursor, cursor_before)

        self.assertTrue(matcher.advance_to_canonical_occurrence("وَمَنْ دَرَى الجَمِيعَ حَازَ الشَّرَفَا"))
        self.assertGreater(matcher.cursor, cursor_before)
        self.assertEqual(matcher.cursor, len(long_source))


if __name__ == "__main__":
    unittest.main()
