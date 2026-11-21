"""Pass 7: Bidirectional raw transcript coverage and hallucination audit."""

from __future__ import annotations

import re
from pathlib import Path

from ._qa_models import (
    CANONICAL_DUA_PATTERN,
    HEADER_LINE_COUNT,
    INAUDIBLE_TOKEN,
    STUDENT_PREFIX,
    ParagraphRecord,
    ValidationReport,
    strip_parenthesized_citations,
)
from .arabic_normalizer import normalize_arabic_search
from .lecture_identity import (
    AUDIO_FILENAME_EXT_RE,
    NOTEBOOKLM_HEADER_PATTERNS,
    NOTEBOOKLM_TAG_RE,
)

_STUDENT_PREFIX_RE = re.compile(rf"^{re.escape(STUDENT_PREFIX)}\s*")
_LEADING_STEM_LINE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ _]+[^\n]+$")
_FILLER_TOKENS = frozenset({"ا", "اا", "ااا", "ام", "اه", "ها", "و"})


def _tokenize_cleaned_prose(text: str) -> list[str]:
    """Strip NotebookLM tags/audio filenames and leading extensionless stem lines for coverage checks."""
    lines: list[str] = []
    non_empty_idx = 0
    for line in text.splitlines():
        stripped = line.strip().lstrip("\ufeff").strip()
        if not stripped:
            continue
        is_leading = non_empty_idx < 3
        non_empty_idx += 1
        if (
            (is_leading and _LEADING_STEM_LINE_RE.match(stripped))
            or any(pat.match(stripped) for pat in NOTEBOOKLM_HEADER_PATTERNS)
            or AUDIO_FILENAME_EXT_RE.search(stripped)
            or NOTEBOOKLM_TAG_RE.search(stripped)
        ):
            continue
        lines.append(stripped)

    norm = normalize_arabic_search(" ".join(lines))
    return [w for w in norm.split() if w not in _FILLER_TOKENS]


def _build_word_index(words: list[str]) -> tuple[set[str], set[str]]:
    """Build unigram and adjacent bigram lookup sets from normalized words."""
    return (
        set(words),
        {f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)},
    )


def _find_unmatched_windows(
    source_words: list[str],
    target_words_set: set[str],
    target_bigrams: set[str],
    window_size: int = 12,
) -> list[str]:
    """Return 12-word windows with 0 bigram hits and <50% unigram hits in target."""
    unmatched: list[str] = []
    idx = 0
    while idx <= len(source_words) - window_size:
        chunk_words = source_words[idx : idx + window_size]
        bigram_hits = sum(
            1
            for j in range(window_size - 1)
            if f"{chunk_words[j]} {chunk_words[j + 1]}" in target_bigrams
        )
        word_hits = sum(1 for w in chunk_words if w in target_words_set)
        if bigram_hits == 0 and word_hits < (window_size // 2):
            unmatched.append(" ".join(chunk_words))
            idx += window_size
        else:
            idx += 1
    return unmatched


def check_raw_coverage(
    para_records: list[ParagraphRecord],
    raw_path: Path,
    report: ValidationReport,
) -> None:
    """Detect dropped raw clauses and ungrounded non-Matn paragraph additions."""
    if not raw_path.exists():
        return
    raw_text = raw_path.read_text(encoding="utf-8")
    raw_words = _tokenize_cleaned_prose(raw_text)
    window_size = 12
    if len(raw_words) < window_size:
        return

    body_texts = [
        rec.text for rec in para_records if rec.index >= HEADER_LINE_COUNT and rec.text.strip()
    ]
    docx_words_list = normalize_arabic_search(" ".join(body_texts)).split()
    docx_words_set, docx_bigrams = _build_word_index(docx_words_list)

    for dropped_phrase in _find_unmatched_windows(raw_words, docx_words_set, docx_bigrams, window_size):
        report.flag(
            "RAW_COVERAGE_DROP",
            None,
            f"Raw transcript clause appears dropped from .docx: '{dropped_phrase}'.",
            dropped_phrase,
        )

    raw_words_set, raw_bigrams = _build_word_index(raw_words)

    for rec in para_records:
        if rec.index < HEADER_LINE_COUNT or rec.is_matn:
            continue
        p_clean = CANONICAL_DUA_PATTERN.sub("", rec.text.strip())
        p_clean = _STUDENT_PREFIX_RE.sub("", p_clean)
        p_clean = p_clean.replace(INAUDIBLE_TOKEN, "")
        p_clean = strip_parenthesized_citations(p_clean)
        p_words = _tokenize_cleaned_prose(p_clean)
        if len(p_words) < window_size:
            continue

        for added_phrase in _find_unmatched_windows(p_words, raw_words_set, raw_bigrams, window_size):
            report.flag(
                "RAW_HALLUCINATION_ADDITION",
                rec.index,
                f"Paragraph P{rec.index} contains a clause not found in raw transcript: '{added_phrase}'.",
                added_phrase,
            )
