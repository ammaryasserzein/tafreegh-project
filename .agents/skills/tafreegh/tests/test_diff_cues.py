"""Tests for diff_cues module — detecting new student cue candidates from Diff Loop."""

import pytest

from tafreegh.diff_cues import CueResult, detect_new_student_cues


class TestDetectNewStudentCues:
    """Seam: detect_new_student_cues(ai_text, corrected_text) -> CueResult"""

    def test_cue_result_exposes_domain_collections_without_list_emulation(self):
        result = CueResult()
        assert result.inserted == []
        assert result.removed == []
        assert result != []
        for magic in ("__len__", "__getitem__", "__iter__"):
            assert not hasattr(CueResult, magic)
        with pytest.raises(TypeError):
            len(result)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            _ = result[0]  # type: ignore[index]
        with pytest.raises(TypeError):
            iter(result)  # type: ignore[arg-type]

    def test_no_differences_returns_empty(self):
        text = "الحمد لله رب العالمين.\n\nطيب نبدأ الدرس."
        result = detect_new_student_cues(text, text)
        assert result.inserted == []
        assert result.removed == []

    def test_detects_new_inaudible_student_line(self):
        ai_text = "هل عندك سؤال يا فلان؟ نعم؟ طيب نكمل الدرس."
        corrected_text = (
            "هل عندك سؤال يا فلان؟ نعم؟\n\n"
            "طالب: صوت غير مسموع.\n\n"
            "طيب نكمل الدرس."
        )
        result = detect_new_student_cues(ai_text, corrected_text)
        assert len(result.inserted) == 1
        assert "نعم؟" in result.inserted[0]["cue_sentence"]

    def test_ignores_student_lines_present_in_both(self):
        shared = (
            "الشيخ يتكلم، نعم؟\n\n"
            "طالب: صوت غير مسموع.\n\n"
            "طيب نكمل."
        )
        result = detect_new_student_cues(shared, shared)
        assert result.inserted == []
        assert result.removed == []

    def test_detects_multiple_new_cues(self):
        ai_text = "أول نقطة، نعم؟ ثاني نقطة، بتقول حاجة؟ ثالث نقطة."
        corrected_text = (
            "أول نقطة، نعم؟\n\n"
            "طالب: صوت غير مسموع.\n\n"
            "ثاني نقطة، بتقول حاجة؟\n\n"
            "طالب: صوت غير مسموع.\n\n"
            "ثالث نقطة."
        )
        result = detect_new_student_cues(ai_text, corrected_text)
        assert len(result.inserted) == 2

    def test_extracts_preceding_sentence_as_cue(self):
        ai_text = "هذه المسألة مهمة جداً، واضح كدا؟ نمشي للنقطة التالية."
        corrected_text = (
            "هذه المسألة مهمة جداً، واضح كدا؟\n\n"
            "طالب: صوت غير مسموع.\n\n"
            "نمشي للنقطة التالية."
        )
        result = detect_new_student_cues(ai_text, corrected_text)
        assert len(result.inserted) == 1
        assert "واضح كدا؟" in result.inserted[0]["cue_sentence"]

    def test_ignores_audible_student_lines(self):
        """Only 'صوت غير مسموع' triggers cue detection, not regular student speech."""
        ai_text = "الشيخ يتكلم عن المسألة."
        corrected_text = (
            "الشيخ يتكلم عن المسألة.\n\n"
            "طالب: جزاك الله خيراً.\n\n"
        )
        result = detect_new_student_cues(ai_text, corrected_text)
        assert result.inserted == []
        assert result.removed == []

    def test_returns_line_number_in_corrected_text(self):
        corrected_text = (
            "سطر أول.\n\n"
            "سطر ثاني، نعم؟\n\n"
            "طالب: صوت غير مسموع.\n\n"
            "سطر رابع."
        )
        ai_text = "سطر أول.\n\nسطر ثاني، نعم؟ سطر رابع."
        result = detect_new_student_cues(ai_text, corrected_text)
        assert len(result.inserted) == 1
        assert "line_number" in result.inserted[0]
        assert result.inserted[0]["line_number"] > 0

    def test_handles_partial_inaudible_not_as_cue(self):
        """Partial inaudible (with parentheses) should NOT trigger cue detection —
        those are partial transcriptions, not missing student turns."""
        ai_text = "الشيخ يتكلم."
        corrected_text = (
            "الشيخ يتكلم.\n\n"
            "طالب: كلمة (صوت غير مسموع).\n\n"
        )
        result = detect_new_student_cues(ai_text, corrected_text)
        assert result.inserted == []
        assert result.removed == []

    def test_suppresses_rhetorical_ha_suffix(self):
        """Cue sentences ending in 'ها؟' are rhetorical — suppressed by suffix filter."""
        ai_text = "الشيخ يتكلم عن المسألة."
        corrected_text = (
            "الشيخ يتكلم عن المسألة، ها؟\n\n"
            "طالب: صوت غير مسموع.\n\n"
            "نكمل الدرس."
        )
        result = detect_new_student_cues(ai_text, corrected_text)
        assert result.inserted == []

    def test_suppresses_rhetorical_eih_suffix(self):
        """Cue sentences ending in 'إيه؟' are rhetorical — suppressed by suffix filter."""
        ai_text = "الشيخ يتكلم عن المسألة."
        corrected_text = (
            "طب دي إيه يعني؟ تدل على إيه؟\n\n"
            "طالب: صوت غير مسموع.\n\n"
            "نكمل الدرس."
        )
        result = detect_new_student_cues(ai_text, corrected_text)
        assert result.inserted == []
