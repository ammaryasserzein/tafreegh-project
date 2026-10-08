# Tafreegh (تفريغ الدروس الشرعية)

Scholarly transcription of Arabic Islamic lectures: processing automated draft transcripts and aligning them with canonical texts to produce Word-ready copy.

## Language

**Blind Literalism**:
The core transcription principle: copy matn text exactly as it appears in the canonical source, preserving every diacritic, orthographic mark, and footnote marker without alteration — even if the speaker mispronounces a word.
_Avoid_: Faithful copying, exact transcription

**Matn Source**:
A per-lecture Markdown file containing the exact vowelized canonical text the sheikh reads from, extracted from the relevant pages of the source book.
_Avoid_: Reference text, source file, book file

**Primary Mode**:
Matn matching mode that uses a `<matn_source>` file as absolute authority. Identified passages are replaced with the source's exact text including full tashkeel.
_Avoid_: Standard Mode, Branch A, normal mode

**Fallback Mode**:
Matn matching mode used when no `<matn_source>` is available. Reading boundaries are detected via linguistic cues (fusha vs colloquial shift). Matn is transcribed without tashkeel.
_Avoid_: Single-input mode, Branch B, no-matn mode

**Dynamic Fallback Interleaving**:
Hybrid matching strategy for incomplete matn source files. The system uses Primary Mode for segments found in the source and automatically switches to Fallback Mode for segments the sheikh reads that are absent from the file.
_Avoid_: Hybrid Mode, mixed mode, partial matching

**Fallback Correction**:
A diff-loop classification for user edits to segments that were processed in Fallback Mode. Distinguished from matn copy errors to preserve training signal fidelity.
_Avoid_: Fallback diff, correction type

**Sequential Cursor**:
The position tracker in the matn source file during matching. Advances as segments are matched, with forward look-ahead and full-range look-behind to handle paragraph skips and sentence-by-sentence re-reads.
_Avoid_: Read pointer, position marker
