"""Tests for the unified Arabic Normalizer module."""

import pytest

from tafreegh.arabic_normalizer import (
    IndexedArabicText,
    build_search_index,
    has_tashkeel,
    normalize_arabic,
    normalize_arabic_search,
    normalize_arabic_token,
    strip_tashkeel,
    strip_tashkeel_preserving_citations,
)


def test_strip_tashkeel_removes_diacritics_and_tatweel():
    vowelized = "إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ اللّـٰهُ"
    assert strip_tashkeel(vowelized) == "إن مبادئ كل علم عشره الله"
    assert has_tashkeel(vowelized) is True
    assert has_tashkeel("إن مبادئ كل علم") is False
    assert has_tashkeel("اللـه") is True


def test_strip_tashkeel_preserving_citations_keeps_inner_parens_intact():
    text = (
        "مَا لَهُ أَدْرَاجٌ، قَالَ تَعَالَى: (أَوْ سُلَّمًا فِي السَّمَاءِ) "
        "وَقَالَ: (وَلَا تَقُولَنَّ * إِلَّا أَنْ يَشَاءَ اللَّهُ)"
    )
    assert strip_tashkeel_preserving_citations(text) == (
        "ما له أدراج، قال تعالى: (أَوْ سُلَّمًا فِي السَّمَاءِ) "
        "وقال: (وَلَا تَقُولَنَّ * إِلَّا أَنْ يَشَاءَ اللَّهُ)"
    )


def test_normalize_arabic_folds_hamza_and_whitespace_preserving_ta_marbuta_maqsura_and_punct():
    assert normalize_arabic("  أَبُو  إِبْرَاهِيمَ  آل  ٱلْمَدِينَة  ") == "اَبُو اِبْرَاهِيمَ ال الْمَدِينَة"
    assert normalize_arabic("  سيرة (الرحيق المختوم)  ") == "سيرة (الرحيق المختوم)"
    assert normalize_arabic("  شوية   يبقى   أهو  ") == "شوية يبقى اهو"
    assert normalize_arabic("") == ""


def test_normalize_arabic_token_folds_hamza_ta_marbuta_maqsura_and_underscores():
    assert normalize_arabic_token("  فقه_البيوع  ") == "فقه البيوع"
    assert normalize_arabic_token("سيرة_الأسماء_الحسنى") == "سيره الاسماء الحسني"
    assert normalize_arabic_token("") == ""


def test_normalize_arabic_search_canonicalizes_letters_diacritics_and_punctuation():
    raw = "  «أَلْـحَدُّ»، وَالْمَوْضُوعُ! ثُمَّ الثَّمَرَةُ...  "
    assert normalize_arabic_search(raw) == "الحد والموضوع ثم الثمره"
    assert normalize_arabic_search("  سُورَةُ الضُّحَىٰ  ") == "سوره الضحي"
    assert normalize_arabic_search("... ، ؟ !") == ""


def test_build_search_index_aligns_positions_and_extracts_vowelized_spans():
    source = "   \n«الحَدُّ»، وَالمَوْضُوعُ! ثُمَّ الثَّمَرَةُ"
    indexed = build_search_index(source)

    assert isinstance(indexed, IndexedArabicText)
    assert indexed.normalized == "الحد والموضوع ثم الثمره"
    assert len(indexed.pos_map) == len(indexed.normalized)

    # Second clause: "والموضوع" sits between punctuation and exclamation mark
    target = "والموضوع"
    norm_start = indexed.normalized.index(target)
    norm_end = norm_start + len(target)
    orig_start, orig_end, extracted = indexed.extract_span(norm_start, norm_end)

    assert extracted == "وَالمَوْضُوعُ"
    assert source[orig_start:orig_end] == extracted
    assert source[orig_end] == "!"

    # Empty / punctuation-only sources produce empty index cleanly
    empty_idx = build_search_index("... ، \t ")
    assert empty_idx.normalized == ""
    assert empty_idx.pos_map == ()

    with pytest.raises(ValueError):
        indexed.extract_span(-1, 2)
    with pytest.raises(ValueError):
        indexed.extract_span(3, 3)
    with pytest.raises(ValueError):
        indexed.extract_span(0, len(indexed.normalized) + 1)
