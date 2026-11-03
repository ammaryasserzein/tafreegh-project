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

**Markdown Leakage**:
A failure mode where an LLM agent interprets inline formatting (like backticks or code fences) in prompt instructions as literal text requirements and outputs them into the generated document. Addressed by globally stripping non-semantic syntax in export scripts and removing them from positive prompt examples.
_Avoid_: Prompt pollution, syntax leakage, literal backticks

**Numbered Lecture Stem**:
A lecture file naming convention that uses mirrored sequential lecture numbers instead of a Gregorian date (`YYYY-MM-DD`), structured as `[N]-[subject]_[N]` (e.g., `17-فقه_البيوع_17`). Matched across `01_Matn_Sources/` and `02_Raw_Inputs/` by mirrored integer identifiers and canonical keyword tokens.
_Avoid_: Date stem, unnumbered lecture, arbitrary filename

**Lecture Identity**:
A consolidated domain entity encapsulating the core identifying primitives of a lecture (`date`, `lecture_number`, `keyword`, `subject_name`, `stem`, `audio_file`). Replaces dispersed data clumps across export and training pipelines, providing unified resolution of header lines, canonical names, and cross-directory stem matching.
_Avoid_: Identity primitives, metadata tuple, stem dict

**Known Cue**:
A Sheikh utterance pattern that reliably signals an inaudible student turn. When detected at a paragraph boundary, it triggers proactive insertion of `طالب: صوت غير مسموع.`. Maintained in the Known Cue List and refined via the Diff Loop.
_Avoid_: Trigger phrase, prompt word, signal

**Rhetorical Suffix**:
A sentence-final particle (`ها؟`, `إيه؟`) the Sheikh uses as a teaching device to prompt class engagement, not as a genuine student-turn boundary. Excluded from Known Cue nomination by suffix filtering in the Diff Loop.
_Avoid_: Excluded cue, blacklisted cue, suppressed phrase

**Anchor Expiry**:
Decay of a bolded Matn block's reference status after an extended stretch of commentary or a mid-lecture break, turning subsequent clause re-reads that resume explanation back into standalone primary anchors.
_Avoid_: Distant bolding, page-distance rule, re-bold threshold

**Attendee Anonymization**:
Substitution of `فلان` for any live lecture participant's personal name across all grammatical positions while retaining titles, kunyas, classical textbook placeholders, and historical figures.
_Avoid_: Student masking, vocative replacement, name redaction

**Echoed Student Turn**:
An inaudible attendee utterance whose words are inferred only because the Sheikh repeats them aloud with questioning or evaluative intonation.
_Avoid_: Repeated student answer, guessed student turn

**Seam Repetition**:
A consecutive word repetition straddling the boundary between the final token of a book reading and the opening token of the Sheikh's immediate lexical gloss.
_Avoid_: Boundary duplicate, split repetition

**Compound Sharh-Matn**:
A single bold block preserving an unvowelized commentator lead-in ending in بقوله، / في قوله، / قوله: flowing directly into a vowelized canonical Matn clause from <matn_source>, matched via prefix/tail seam splitting.
_Avoid_: Sharh-to-Matn Continuity, compound blocks, hybrid Sharh-Matn
