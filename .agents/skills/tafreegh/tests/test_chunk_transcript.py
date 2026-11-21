"""Tests for the canonical transcript chunker inside the tafreegh skill toolkit."""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
CANONICAL_SCRIPT = SCRIPTS_DIR / "chunk_transcript.py"

from tafreegh import chunk_transcript


def test_smart_chunk_text_empty_or_whitespace_returns_empty():
    assert chunk_transcript.smart_chunk_text("") == []
    assert chunk_transcript.smart_chunk_text("   \n\t  ") == []


def test_smart_chunk_text_within_max_words_returns_single_chunk():
    text = "  بسم الله الرحمن الرحيم. الحمد لله رب العالمين.  "
    chunks = chunk_transcript.smart_chunk_text(text, target_words=10, min_words=5, max_words=15)
    assert chunks == ["بسم الله الرحمن الرحيم. الحمد لله رب العالمين."]


def test_smart_chunk_text_splits_at_sentence_boundaries_preserving_all_words():
    sentences = [
        f"هذه جملة علمية رقم {i} فيها شرح واضح ومفصل للمسألة الفقهية."
        for i in range(1, 13)
    ]
    text = " ".join(sentences)

    chunks = chunk_transcript.smart_chunk_text(text, target_words=36, min_words=24, max_words=48)

    assert len(chunks) >= 3
    for chunk in chunks[:-1]:
        assert chunk.endswith(".")
        word_count = len(chunk.split())
        assert 24 <= word_count <= 48
    assert " ".join(chunks).split() == text.split()


def test_smart_chunk_text_splits_at_arabic_question_mark_boundaries():
    questions = [
        f"هل هذه المسألة الفقهية رقم {i} متفق عليها بين أئمة المذاهب الأربعة؟"
        for i in range(1, 7)
    ]
    text = " ".join(questions)

    chunks = chunk_transcript.smart_chunk_text(text, target_words=24, min_words=18, max_words=30)

    assert len(chunks) >= 2
    for chunk in chunks[:-1]:
        assert chunk.endswith("؟")
        assert 18 <= len(chunk.split()) <= 30
    assert " ".join(chunks).split() == text.split()


def test_smart_chunk_text_splits_at_newline_boundaries():
    lines = [
        f"السطر العلمي رقم {i} يشرح كلام المصنف رحمه الله بدون علامات ترقيم ختامية"
        for i in range(1, 7)
    ]
    text = "\n".join(lines)

    chunks = chunk_transcript.smart_chunk_text(text, target_words=26, min_words=20, max_words=32)

    assert len(chunks) >= 2
    for chunk in chunks[:-1]:
        assert 20 <= len(chunk.split()) <= 32
        assert chunk.endswith("ختامية")
    assert " ".join(chunks).split() == text.split()


def test_chunk_file_creates_canonical_arabic_chunk_directory_and_parts(tmp_path):
    sentences = [
        f"فقرة رقم {i} من الدرس الشرعي المبارك تتناول بيان الحكم الشرعي بدليله الواضح."
        for i in range(1, 160)
    ]
    transcript = tmp_path / "2026-10-17_زاد.md"
    transcript.write_text(" ".join(sentences), encoding="utf-8")

    created = chunk_transcript.chunk_file(str(transcript))

    expected_dir = tmp_path / "2026-10-17_زاد_مقاطع"
    assert expected_dir.is_dir()
    assert len(created) == 2
    part_files = sorted(expected_dir.iterdir())
    assert [p.name for p in part_files] == [
        "2026-10-17_زاد_جزء_01.txt",
        "2026-10-17_زاد_جزء_02.txt",
    ]
    reconstructed = " ".join(p.read_text(encoding="utf-8") for p in part_files)
    assert reconstructed.split() == transcript.read_text(encoding="utf-8").split()


def test_chunk_file_missing_input_exits_with_nonzero(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        chunk_transcript.chunk_file(str(tmp_path / "missing_transcript.md"))
    assert exc_info.value.code == 1


def test_cli_usage_points_to_canonical_skill_script():
    result = subprocess.run(
        [sys.executable, str(CANONICAL_SCRIPT)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 1
    assert ".agents/skills/tafreegh/scripts/chunk_transcript.py" in result.stdout


def test_smart_chunk_text_scales_bounds_for_large_and_small_custom_targets():
    large_sentences = [
        f"هذه جملة علمية رقم {i} فيها شرح واضح ومفصل للمسألة الفقهية في الدرس."
        for i in range(1, 335)
    ]
    large_text = " ".join(large_sentences)  # ~4000+ words
    large_chunks = chunk_transcript.smart_chunk_text(large_text, target_words=3200)

    assert len(large_chunks) == 2
    assert 2462 <= len(large_chunks[0].split()) <= 3938
    assert " ".join(large_chunks).split() == large_text.split()

    small_sentences = [
        f"هذه جملة علمية رقم {i} فيها شرح واضح للمسألة."
        for i in range(1, 18)
    ]
    small_text = " ".join(small_sentences)  # ~153 words
    small_chunks = chunk_transcript.smart_chunk_text(small_text, target_words=100)

    assert len(small_chunks) == 2
    assert 77 <= len(small_chunks[0].split()) <= 123
    assert " ".join(small_chunks).split() == small_text.split()


def test_chunk_file_scales_thresholds_for_custom_target_words(tmp_path):
    sentences = [
        f"فقرة رقم {i} من الدرس الشرعي المبارك تتناول بيان الحكم الشرعي بدليله الواضح."
        for i in range(1, 335)
    ]
    transcript = tmp_path / "2026-10-17_رياض.md"
    transcript.write_text(" ".join(sentences), encoding="utf-8")

    created = chunk_transcript.chunk_file(str(transcript), target_words=3200)

    assert len(created) == 2
    assert 2462 <= created[0][1] <= 3938
    reconstructed = " ".join(path.read_text(encoding="utf-8") for path, _ in created)
    assert reconstructed.split() == transcript.read_text(encoding="utf-8").split()

