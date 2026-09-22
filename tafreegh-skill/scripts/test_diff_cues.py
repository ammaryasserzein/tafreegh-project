"""Tests for diff_cues module — detecting new student cue candidates from Diff Loop."""

from diff_cues import detect_new_student_cues


class TestDetectNewStudentCues:
    """Seam: detect_new_student_cues(ai_text, corrected_text) -> list[CueCandidate]"""

    def test_no_differences_returns_empty(self):
        text = "الحمد لله رب العالمين.\n\nطيب نبدأ الدرس."
        assert detect_new_student_cues(text, text) == []

    def test_detects_new_inaudible_student_line(self):
        ai_text = "هل عندك سؤال يا فلان؟ نعم؟ طيب نكمل الدرس."
        corrected_text = (
            "هل عندك سؤال يا فلان؟ نعم؟\n\n"
            "طالب: صوت غير مسموع.\n\n"
            "طيب نكمل الدرس."
        )
        result = detect_new_student_cues(ai_text, corrected_text)
        assert len(result) == 1
        assert "نعم؟" in result[0]["cue_sentence"]

    def test_ignores_student_lines_present_in_both(self):
        shared = (
            "الشيخ يتكلم، نعم؟\n\n"
            "طالب: صوت غير مسموع.\n\n"
            "طيب نكمل."
        )
        assert detect_new_student_cues(shared, shared) == []

    def test_detects_multiple_new_cues(self):
        ai_text = "أول نقطة، نعم؟ ثاني نقطة، بتقول إيه؟ ثالث نقطة."
        corrected_text = (
            "أول نقطة، نعم؟\n\n"
            "طالب: صوت غير مسموع.\n\n"
            "ثاني نقطة، بتقول إيه؟\n\n"
            "طالب: صوت غير مسموع.\n\n"
            "ثالث نقطة."
        )
        result = detect_new_student_cues(ai_text, corrected_text)
        assert len(result) == 2

    def test_extracts_preceding_sentence_as_cue(self):
        ai_text = "هذه المسألة مهمة جداً، واضح كدا؟ نمشي للنقطة التالية."
        corrected_text = (
            "هذه المسألة مهمة جداً، واضح كدا؟\n\n"
            "طالب: صوت غير مسموع.\n\n"
            "نمشي للنقطة التالية."
        )
        result = detect_new_student_cues(ai_text, corrected_text)
        assert len(result) == 1
        assert "واضح كدا؟" in result[0]["cue_sentence"]

    def test_ignores_audible_student_lines(self):
        """Only 'صوت غير مسموع' triggers cue detection, not regular student speech."""
        ai_text = "الشيخ يتكلم عن المسألة."
        corrected_text = (
            "الشيخ يتكلم عن المسألة.\n\n"
            "طالب: جزاك الله خيراً.\n\n"
        )
        assert detect_new_student_cues(ai_text, corrected_text) == []

    def test_returns_line_number_in_corrected_text(self):
        corrected_text = (
            "سطر أول.\n\n"
            "سطر ثاني، نعم؟\n\n"
            "طالب: صوت غير مسموع.\n\n"
            "سطر رابع."
        )
        ai_text = "سطر أول.\n\nسطر ثاني، نعم؟ سطر رابع."
        result = detect_new_student_cues(ai_text, corrected_text)
        assert len(result) == 1
        assert "line_number" in result[0]
        assert result[0]["line_number"] > 0

    def test_handles_partial_inaudible_not_as_cue(self):
        """Partial inaudible (with parentheses) should NOT trigger cue detection —
        those are partial transcriptions, not missing student turns."""
        ai_text = "الشيخ يتكلم."
        corrected_text = (
            "الشيخ يتكلم.\n\n"
            "طالب: كلمة (صوت غير مسموع).\n\n"
        )
        assert detect_new_student_cues(ai_text, corrected_text) == []
