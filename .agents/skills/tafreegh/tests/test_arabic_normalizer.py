"""Tests for the unified Arabic Normalizer module."""

import pytest

from tafreegh.arabic_normalizer import (
    CITATION_SPAN_RE,
    IndexedArabicText,
    build_search_index,
    has_tashkeel,
    mask_citations,
    normalize_arabic,
    normalize_arabic_search,
    normalize_arabic_token,
    normalize_dialect_markers,
    normalize_nfc_collapsed,
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


@pytest.mark.parametrize(
    "sample",
    [
        "",
        "   \t\n  ",
        "... ، ؟ ! « » —",
        "إِنَّ مَبَادِئَ كُلِّ عِلْمٍ عَشَرَهْ ... الحَدُّ وَالمَوْضُوعُ ثُمَّ الثَّمَرَهْ!",
        "سُورَةُ الضُّحَىٰ — ٱلْحَمْدُ لِلَّـهِ (1): فَقِهْ_الْبُيُوعِ!",
        "  أَبُو\u200f إِبْرَاهِيمَ  \t آل\n عِمْرَانَ  ",
        "قَالَ {بَدِيعُ} [البقرة: 117] وَقَالَ: [1] خُلِقَ [الملك: ٣ - ٤] تَفَاوُتٍ [الْعَمَلُ ثَمَرَةٌ]",
        "أَمْرٌ[1]نَافِعٌ [2] نَافِعٌ[3]",
        "[1] [2]",
    ],
)
def test_build_search_index_matches_normalize_arabic_search_parity(sample: str):
    assert build_search_index(sample).normalized == normalize_arabic_search(sample)


def test_strip_tashkeel_preserving_citations_handles_tatweel_empty_and_unmatched_parens():
    assert strip_tashkeel_preserving_citations("مَـتْـنٌ () وَمَا (لَـم) يَـنْـتَـهِ (بِـلَا") == (
        "متن () وما (لَـم) ينته (بلا"
    )


def test_strip_tashkeel_preserving_citations_preserves_ornate_and_quoted_citations():
    text = (
        'قَالَ تَعَالَى: ﴿وَإِذْ زَاغَتِ الأَبْصَارُ﴾ وَقَالَ النَّبِيُّ: "أُتِيَ النَّبِيُّ" '
        'وَفَارِغٌ ﴿﴾ "" وَغَيْرُ مُغْلَقٍ ﴿آيَةٌ "حَدِيثٌ'
    )
    assert strip_tashkeel_preserving_citations(text) == (
        'قال تعالى: ﴿وَإِذْ زَاغَتِ الأَبْصَارُ﴾ وقال النبي: "أُتِيَ النَّبِيُّ" '
        'وفارغ ﴿﴾ "" وغير مغلق ﴿آية "حديث'
    )


def test_build_search_index_skips_editorial_digit_brackets_while_retaining_flanked_source():
    source = "قَالَ {بَدِيعُ} [البقرة: 117] وَقَالَ: [1] خُلِقَ [الملك: ٣ - ٤] تَفَاوُتٍ [الْعَمَلُ ثَمَرَةٌ]"
    assert normalize_arabic_search(source) == "قال بديع وقال خلق تفاوت العمل ثمره"

    indexed = build_search_index(source)
    assert indexed.normalized == normalize_arabic_search(source)

    query = "قال بديع وقال"
    norm_start = indexed.normalized.index(query)
    norm_end = norm_start + len(query)
    orig_start, orig_end, extracted = indexed.extract_span(norm_start, norm_end)
    assert extracted == "قَالَ {بَدِيعُ} [البقرة: 117] وَقَالَ"
    assert source[orig_start:orig_end] == extracted

    compact = "أَمْرٌ[1]نَافِعٌ"
    compact_idx = build_search_index(compact)
    assert compact_idx.normalized == "امر نافع"
    _, _, compact_extracted = compact_idx.extract_span(0, len(compact_idx.normalized))
    assert compact_extracted == "أَمْرٌ[1]نَافِعٌ"


@pytest.mark.parametrize(
    ("source", "query", "expected"),
    [
        (
            "قَالَ تَعَالَى: (قُلْ هُوَ اللَّهُ أَحَدٌ) وَبَعْدَهُ",
            "قال تعالي قل هو الله احد",
            "قَالَ تَعَالَى: (قُلْ هُوَ اللَّهُ أَحَدٌ)",
        ),
        (
            'قَالَ النَّبِيُّ: "إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ" فَيُعْلَمُ',
            "قال النبي انما الاعمال بالنيات",
            'قَالَ النَّبِيُّ: "إِنَّمَا الْأَعْمَالُ بِالنِّيَّاتِ"',
        ),
        (
            "وَقَالَ: «الْحَقُّ أَحَقُّ أَنْ يُتَّبَعَ» ثُمَّ",
            "وقال الحق احق ان يتبع",
            "وَقَالَ: «الْحَقُّ أَحَقُّ أَنْ يُتَّبَعَ»",
        ),
        (
            "بَابُ {الْعِلْمُ نُورٌ} وَ [الْعَمَلُ ثَمَرَةٌ] انتهى",
            "باب العلم نور و العمل ثمره",
            "بَابُ {الْعِلْمُ نُورٌ} وَ [الْعَمَلُ ثَمَرَةٌ]",
        ),
        (
            'فَائِدَةٌ: ("صَدَقَ اللَّهُ") ثُمَّ',
            "فائده صدق الله",
            'فَائِدَةٌ: ("صَدَقَ اللَّهُ")',
        ),
        (
            "قَالَ تَعَالَى: (قُلْ هُوَ اللَّهُ أَحَدٌ) وَبَعْدَهُ",
            "قل هو الله احد",
            "قُلْ هُوَ اللَّهُ أَحَدٌ",
        ),
    ],
)
def test_extract_span_preserves_unbalanced_closing_delimiters_without_overextending(
    source: str, query: str, expected: str
):
    indexed = build_search_index(source)
    norm_start = indexed.normalized.index(query)
    norm_end = norm_start + len(query)
    orig_start, orig_end, extracted = indexed.extract_span(norm_start, norm_end)

    assert extracted == expected
    assert source[orig_start:orig_end] == expected


def test_normalize_nfc_collapsed_normalizes_combining_order_and_whitespace():
    shadda_first = "  قَالَ\t\n \u0627\u0644\u0644\u0651\u064e\u0647\u064f   تَعَالَى  "
    fatha_first_nfc = "قَالَ \u0627\u0644\u0644\u064e\u0651\u0647\u064f تَعَالَى"
    assert normalize_nfc_collapsed(shadda_first) == fatha_first_nfc
    assert normalize_nfc_collapsed(f"  {fatha_first_nfc}  ") == fatha_first_nfc
    assert normalize_nfc_collapsed("") == ""


def test_citation_span_re_and_mask_citations_handle_all_delimiters_and_callbacks():
    sample = 'قال: (آيَةٌ) و﴿سُورَةٌ﴾ و"حَدِيثٌ" و«أَثَرٌ» ثم انتهى.'
    assert CITATION_SPAN_RE.findall(sample) == ["(آيَةٌ)", "﴿سُورَةٌ﴾", '"حَدِيثٌ"', "«أَثَرٌ»"]
    assert mask_citations(sample) == "قال:   و  و  و  ثم انتهى."
    assert mask_citations(sample, lambda m: f"{m.group(0)[0]}{m.group(0)[-1]}") == (
        'قال: () و﴿﴾ و"" و«» ثم انتهى.'
    )
    assert strip_tashkeel_preserving_citations('قَالَ: «حَدِيثٌ» وَقَالَ') == "قال: «حَدِيثٌ» وقال"


def test_normalize_dialect_markers_expands_hamza_and_tashkeel_forms_for_generators():
    gen = (m for m in ["أهو", "إِنَّما", "كدا"])
    expanded = normalize_dialect_markers(gen)
    assert expanded == frozenset({"أهو", "اهو", "إِنَّما", "انما", "كدا"})


def test_query_containing_editorial_citation_matches_source_and_preserves_word_brackets():
    from tafreegh.matn_matcher import MatchMode, SequentialMatnMatcher

    source = "قَالَ {بَدِيعُ} [البقرة: 117] وَقَالَ: [1] خُلِقَ [الملك: ٣ - ٤] تَفَاوُتٍ [الْعَمَلُ ثَمَرَةٌ] انتهى"
    query = "قال بديع [البقرة: 117] وقال [1] خلق تفاوت [العمل ثمرة]"

    indexed = build_search_index(source)
    norm_query = normalize_arabic_search(query)
    assert norm_query == "قال بديع وقال خلق تفاوت العمل ثمره"

    norm_start = indexed.normalized.index(norm_query)
    norm_end = norm_start + len(norm_query)
    _, _, extracted = indexed.extract_span(norm_start, norm_end)
    assert extracted == "قَالَ {بَدِيعُ} [البقرة: 117] وَقَالَ: [1] خُلِقَ [الملك: ٣ - ٤] تَفَاوُتٍ [الْعَمَلُ ثَمَرَةٌ]"

    matcher = SequentialMatnMatcher(source, forward_lookahead=500)
    res = matcher.match_segment(query)
    assert res.mode == MatchMode.PRIMARY
    assert res.text == extracted
    assert "[البقرة: 117]" in res.text
    assert "[الْعَمَلُ ثَمَرَةٌ]" in res.text

